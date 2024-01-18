#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from random import choices
from string import ascii_uppercase, digits

from charmed_kubeflow_chisme.exceptions import ErrorWithStatus
from charmed_kubeflow_chisme.pebble import update_layer
from charms.observability_libs.v1.kubernetes_service_patch import KubernetesServicePatch
from lightkube.models.core_v1 import ServicePort
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from ops.pebble import Layer
from serialized_data_interface import NoCompatibleVersions, NoVersionsListed, get_interfaces


class OIDCGatekeeperOperator(CharmBase):
    """Charm OIDC Gatekeeper Operator."""

    _http_port = 8080

    def __init__(self, *args):
        super().__init__(*args)

        self.logger = logging.getLogger(__name__)
        self._container_name = "oidc-authservice"
        self._container = self.unit.get_container(self._container_name)
        self.pebble_service_name = "oidc-authservice"

        http_service_port = ServicePort(self._http_port, name="http-port")
        self.service_patcher = KubernetesServicePatch(
            self,
            [http_service_port],
        )

        self.public_url = self.model.config["public-url"]
        if not self.public_url.startswith(("http://", "https://")):
            self.public_url = f"http://{self.public_url}"

        for event in [
            self.on.start,
            self.on.leader_elected,
            self.on.upgrade_charm,
            self.on.config_changed,
            self.on.oidc_authservice_pebble_ready,
            self.on["ingress"].relation_changed,
            self.on["ingress-auth"].relation_changed,
            self.on["oidc-client"].relation_changed,
            self.on["client-secret"].relation_changed,
        ]:
            self.framework.observe(event, self.main)

    def main(self, event):
        try:
            self._check_public_url()
            self._check_leader()
            interfaces = self._get_interfaces()
            secret_key = self._check_secret()
            self._send_info(interfaces, secret_key)
            self._configure_mesh(interfaces)
            update_layer(self._container_name, self._container, self._oidc_layer, self.logger)
        except ErrorWithStatus as err:
            self.model.unit.status = err.status
            self.logger.error(f"Failed to handle {event} with error: {err}")
            return

        self.model.unit.status = ActiveStatus()

    @property
    def service_environment(self):
        """Return environment variables based on model configuration."""
        secret_key = self._check_secret()
        skip_urls = self.model.config["skip-auth-urls"] or ""
        dex_skip_urls = "/dex/" if not skip_urls else "/dex/," + skip_urls

        ret_env_vars = {
            "CLIENT_ID": self.model.config["client-id"],
            "CLIENT_SECRET": secret_key,
            "DISABLE_USERINFO": True,
            "OIDC_PROVIDER": f"{self.public_url}/dex",
            "OIDC_SCOPES": self.model.config["oidc-scopes"],
            "SERVER_PORT": self._http_port,
            "USERID_CLAIM": self.model.config["userid-claim"],
            "USERID_HEADER": "kubeflow-userid",
            "USERID_PREFIX": "",
            "SESSION_STORE_PATH": "bolt.db",
            # Added to fix https://github.com/canonical/oidc-gatekeeper-operator/issues/64
            "OIDC_STATE_STORE_PATH": "oidc_state.db",
            "SKIP_AUTH_URLS": dex_skip_urls,
            "AUTHSERVICE_URL_PREFIX": "/authservice/",
            "AFTER_LOGOUT_URL": self.model.config["public-url"],
        }

        if self.model.config["ca-bundle"]:
            if self._container.can_connect():
                self._container.push(
                    "/etc/certs/oidc/root-ca.pem", self.model.config["ca-bundle"], make_dirs=True
                )
                ret_env_vars["CA_BUNDLE"] = "/etc/certs/oidc/root-ca.pem"

        return ret_env_vars

    @property
    def _oidc_layer(self):
        """Return Pebble layer for OIDC."""

        pebble_layer = {
            "summary": "OIDC Authservice",
            "description": "pebble config layer for FastAPI demo server",
            "services": {
                self.pebble_service_name: {
                    "override": "replace",
                    "summary": "oidc-gatekeeper service",
                    "command": "/home/authservice/oidc-authservice",
                    "environment": self.service_environment,
                    "startup": "enabled",
                    # working-dir is required to interchangeably support docker images and rocks.
                    # Rocks always set their entrypoint working-dir to "/" because pebble is the
                    # entrypoint, so we need to be explicit.  This was not needed for running
                    # the upstream docker image because that image has a entrypoint working-dir
                    # of "/home/authservice", which is used if working-dir is not set here.
                    "working-dir": "/home/authservice",
                }
            },
        }
        return Layer(pebble_layer)

    def _check_leader(self):
        """Check if the unit is a leader."""
        if not self.unit.is_leader():
            self.logger.info("Not a leader, skipping")
            raise ErrorWithStatus("Waiting for leadership", WaitingStatus)

    def _get_interfaces(self):
        """Get all SDI interfaces."""
        try:
            interfaces = get_interfaces(self)
        except NoVersionsListed as err:
            raise ErrorWithStatus(str(err), WaitingStatus)
        except NoCompatibleVersions as err:
            raise ErrorWithStatus(str(err), BlockedStatus)
        return interfaces

    def _check_public_url(self):
        """Check if `public-url` config is set."""
        if not self.model.config.get("public-url"):
            raise ErrorWithStatus("public-url config required", BlockedStatus)

    def _configure_mesh(self, interfaces):
        """Update ingress and ingress-auth relations with mesh info."""
        if interfaces["ingress"]:
            interfaces["ingress"].send_data(
                {
                    "prefix": "/authservice",
                    "rewrite": "/",
                    "service": self.model.app.name,
                    "port": self._http_port,
                }
            )
        if interfaces["ingress-auth"]:
            interfaces["ingress-auth"].send_data(
                {
                    "service": self.model.app.name,
                    "port": self._http_port,
                    "allowed-request-headers": [
                        "cookie",
                        "X-Auth-Token",
                    ],
                    "allowed-response-headers": ["kubeflow-userid"],
                }
            )

    def _send_info(self, interfaces, secret_key):
        """Send info to oidc-client relation."""
        config = self.model.config

        if not config.get("public-url"):
            return False

        if interfaces["oidc-client"]:
            interfaces["oidc-client"].send_data(
                {
                    "id": config["client-id"],
                    "name": config["client-name"],
                    "redirectURIs": ["/authservice/oidc/callback"],
                    "secret": secret_key,
                }
            )

    def _check_secret(self, event=None):
        """Check if secret is present in relation data, if not generate one."""
        for rel in self.model.relations["client-secret"]:
            if "client-secret" not in rel.data[self.model.app]:
                rel.data[self.model.app]["client-secret"] = _gen_pass()
            return rel.data[self.model.app]["client-secret"]
        else:
            raise ErrorWithStatus("Waiting for Client Secret", WaitingStatus)


def _gen_pass() -> str:
    """Generate a random password."""
    return "".join(choices(ascii_uppercase + digits, k=30))


if __name__ == "__main__":
    main(OIDCGatekeeperOperator)
