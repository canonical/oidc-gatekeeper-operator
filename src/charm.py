#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from random import choices
from string import ascii_uppercase, digits

from oci_image import OCIImageResource, OCIImageResourceError
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from serialized_data_interface import (
    NoCompatibleVersions,
    NoVersionsListed,
    get_interfaces,
)


class Operator(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)

        self.log = logging.getLogger(__name__)
        self.image = OCIImageResource(self, "oci-image")

        for event in [
            self.on.start,
            self.on.leader_elected,
            self.on.upgrade_charm,
            self.on.config_changed,
            self.on["ingress"].relation_changed,
            self.on["ingress-auth"].relation_changed,
            self.on["oidc-client"].relation_changed,
            self.on["client-secret"].relation_changed,
        ]:
            self.framework.observe(event, self.main)

    def main(self, event):
        if not self.unit.is_leader():
            self.model.unit.status = WaitingStatus("Waiting for Leadership")
            exit()

        try:
            interfaces = self._get_interfaces()

            secret_key = self._check_secret()

            image_details = self._check_image_details()

        except CheckFailed as error:
            self.model.unit.status = error.status
            return

        self._send_info(interfaces, secret_key)
        self._configure_mesh(interfaces)

        public_url = self.model.config["public-url"]
        if not public_url.startswith(("http://", "https://")):
            public_url = f"http://{public_url}"
        port = self.model.config["port"]
        oidc_scopes = self.model.config["oidc-scopes"]

        self.model.unit.status = MaintenanceStatus("Setting pod spec")

        self.model.pod.set_spec(
            {
                "version": 3,
                "containers": [
                    {
                        "name": "oidc-gatekeeper",
                        "imageDetails": image_details,
                        "ports": [{"name": "http", "containerPort": port}],
                        "envConfig": {
                            "CLIENT_ID": self.model.config["client-id"],
                            "CLIENT_SECRET": secret_key,
                            "DISABLE_USERINFO": True,
                            "OIDC_PROVIDER": f"{public_url}/dex",
                            "OIDC_SCOPES": oidc_scopes,
                            "SERVER_PORT": port,
                            "USERID_HEADER": "kubeflow-userid",
                            "USERID_PREFIX": "",
                            "SESSION_STORE_PATH": "bolt.db",
                            "SKIP_AUTH_URLS": "/dex/",
                            "AUTHSERVICE_URL_PREFIX": "/authservice/",
                        },
                    }
                ],
            }
        )

        self.model.unit.status = ActiveStatus()

    def _get_interfaces(self):
        try:
            interfaces = get_interfaces(self)
        except NoVersionsListed as err:
            raise CheckFailed(str(err), WaitingStatus)
        except NoCompatibleVersions as err:
            raise CheckFailed(str(err), BlockedStatus)
        return interfaces

    def _check_image_details(self):
        try:
            image_details = self.image.fetch()
        except OCIImageResourceError as e:
            raise CheckFailed(f"{e.status_message}: oci-image", e.status_type)
        return image_details

    def _check_public_url(self):
        if not self.model.config.get("public-url"):
            raise CheckFailed("public-url config required", BlockedStatus)

    def _configure_mesh(self, interfaces):
        if interfaces["ingress"]:
            interfaces["ingress"].send_data(
                {
                    "prefix": "/authservice",
                    "rewrite": "/",
                    "service": self.model.app.name,
                    "port": self.model.config["port"],
                }
            )
        if interfaces["ingress-auth"]:
            interfaces["ingress-auth"].send_data(
                {
                    "service": self.model.app.name,
                    "port": self.model.config["port"],
                    "allowed-request-headers": [
                        "cookie",
                        "X-Auth-Token",
                    ],
                    "allowed-response-headers": ["kubeflow-userid"],
                }
            )

    def _send_info(self, interfaces, secret_key):
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
        for rel in self.model.relations["client-secret"]:
            if "client-secret" not in rel.data[self.model.app]:
                rel.data[self.model.app]["client-secret"] = _gen_pass()
            return rel.data[self.model.app]["client-secret"]
        else:
            raise CheckFailed("Waiting for Client Secret", WaitingStatus)


def _gen_pass() -> str:
    return "".join(choices(ascii_uppercase + digits, k=30))


class CheckFailed(Exception):
    """Raise this exception if one of the checks in main fails."""

    def __init__(self, msg, status_type=None):
        super().__init__()

        self.msg = str(msg)
        self.status_type = status_type
        self.status = status_type(self.msg)


if __name__ == "__main__":
    main(Operator)
