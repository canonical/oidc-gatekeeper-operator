#!/usr/bin/env python3

import logging
from random import choices
from string import ascii_uppercase, digits

from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, MaintenanceStatus, WaitingStatus, BlockedStatus
from ops.framework import StoredState

from oci_image import OCIImageResource, OCIImageResourceError
from serialized_data_interface import (
    NoCompatibleVersions,
    NoVersionsListed,
    get_interfaces,
)


def gen_pass() -> str:
    return "".join(choices(ascii_uppercase + digits, k=30))


class Operator(CharmBase):
    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        if not self.unit.is_leader():
            # We can't do anything useful when not the leader, so do nothing.
            self.model.unit.status = WaitingStatus("Waiting for leadership")
            return
        self.log = logging.getLogger(__name__)
        self.image = OCIImageResource(self, "oci-image")

        self._stored.set_default(secret_key=gen_pass())

        try:
            self.interfaces = get_interfaces(self)
        except NoVersionsListed as err:
            self.model.unit.status = WaitingStatus(str(err))
            return
        except NoCompatibleVersions as err:
            self.model.unit.status = BlockedStatus(str(err))
            return
        else:
            self.model.unit.status = ActiveStatus()

        for event in [
            self.on.install,
            self.on.leader_elected,
            self.on.upgrade_charm,
            self.on.config_changed,
        ]:
            self.framework.observe(event, self.main)

        self.framework.observe(self.on["ingress"].relation_changed, self.configure_mesh)
        self.framework.observe(
            self.on["ingress-auth"].relation_changed, self.configure_mesh
        )
        self.framework.observe(self.on["oidc-client"].relation_changed, self.send_info)

    def configure_mesh(self, event):
        if self.interfaces["ingress"]:
            self.interfaces["ingress"].send_data(
                {
                    "prefix": "/authservice",
                    "rewrite": "/",
                    "service": self.model.app.name,
                    "port": self.model.config["port"],
                }
            )
        if self.interfaces["ingress-auth"]:
            self.interfaces["ingress-auth"].send_data(
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

    def send_info(self, event):
        config = self.model.config

        if not config.get("public-url"):
            return False

        secret_key = self.model.config["client-secret"] or self._stored.secret_key

        if self.interfaces["oidc-client"]:
            self.interfaces["oidc-client"].send_data(
                {
                    "id": config["client-id"],
                    "name": config["client-name"],
                    "redirectURIs": ["/authservice/oidc/callback"],
                    "secret": secret_key,
                }
            )

    def main(self, event):
        try:
            image_details = self.image.fetch()
        except OCIImageResourceError as e:
            self.model.unit.status = e.status
            self.log.info(e)
            return

        public_url = self.model.config["public-url"]
        port = self.model.config["port"]
        oidc_scopes = self.model.config["oidc-scopes"]
        secret_key = self.model.config["client-secret"] or self._stored.secret_key

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


if __name__ == "__main__":
    main(Operator)
