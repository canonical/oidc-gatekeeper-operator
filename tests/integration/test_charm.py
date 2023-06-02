# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
OIDC_CONFIG = {
    "client-name": "Ambassador Auth OIDC",
    "client-secret": "oidc-client-secret",
}
ISTIO_PILOT = "istio-pilot"
DEX_AUTH = "dex-auth"
PUBLIC_URL = "test-url"
image_path = METADATA["resources"]["oci-image"]["upstream-source"]
RESOURCES = {"oci-image": image_path}


def pytest_configure():
    """Register the charm under test."""
    pytest.charm_under_test = None


class TestOIDCOperator:
    charm_under_test = None

    async def test_build(self, ops_test: OpsTest):
        pytest.charm_under_test = await ops_test.build_charm(".")

    @pytest.mark.abort_on_fail
    async def test_deploy(self, ops_test: OpsTest):
        """Build and deploy the charm.

        Assert on the unit status.
        """
        await ops_test.model.deploy(
            pytest.charm_under_test, resources=RESOURCES, trust=True, config=OIDC_CONFIG
        )

        await ops_test.model.applications[APP_NAME].set_config({"public-url": PUBLIC_URL})

        await ops_test.model.wait_for_idle(
            apps=[APP_NAME], status="active", raise_on_blocked=False, timeout=60 * 10
        )
        assert ops_test.model.applications[APP_NAME].units[0].workload_status == "active"

    @pytest.mark.abort_on_fail
    async def test_relations(self, ops_test: OpsTest):
        await ops_test.model.deploy(ISTIO_PILOT, channel="1.5/stable", trust=True)
        await ops_test.model.deploy(DEX_AUTH, channel="2.31/stable", trust=True)
        await ops_test.model.add_relation(ISTIO_PILOT, DEX_AUTH)
        await ops_test.model.add_relation(f"{ISTIO_PILOT}:ingress", f"{APP_NAME}:ingress")
        await ops_test.model.add_relation(
            f"{ISTIO_PILOT}:ingress-auth", f"{APP_NAME}:ingress-auth"
        )
        await ops_test.model.add_relation(f"{APP_NAME}:oidc-client", f"{DEX_AUTH}:oidc-client")

        await ops_test.model.applications[DEX_AUTH].set_config({"public-url": PUBLIC_URL})

        await ops_test.model.wait_for_idle(
            [APP_NAME, ISTIO_PILOT, DEX_AUTH],
            status="active",
            raise_on_blocked=True,
            raise_on_error=True,
            timeout=600,
        )

    @pytest.mark.abort_on_fail
    @pytest.mark.timeout(1200)
    async def test_upgrade(self, ops_test: OpsTest):
        await ops_test.model.remove_application(APP_NAME, block_until_done=True)

        await ops_test.model.deploy(
            APP_NAME, channel="ckf-1.7/stable", trust=True, config=OIDC_CONFIG
        )
        await ops_test.model.add_relation(f"{ISTIO_PILOT}:ingress", f"{APP_NAME}:ingress")
        await ops_test.model.add_relation(
            f"{ISTIO_PILOT}:ingress-auth", f"{APP_NAME}:ingress-auth"
        )
        await ops_test.model.add_relation(f"{APP_NAME}:oidc-client", f"{DEX_AUTH}:oidc-client")
        await ops_test.model.applications[APP_NAME].set_config({"public-url": PUBLIC_URL})
        await ops_test.model.wait_for_idle(
            [APP_NAME, ISTIO_PILOT, DEX_AUTH],
            status="active",
            raise_on_blocked=False,
            raise_on_error=True,
            timeout=600,
        )

        cmd = (
            f"juju refresh {APP_NAME} "
            f'--path "{pytest.charm_under_test}" --resource oci-image="{image_path}"'
        )
        await ops_test.run(*shlex.split(cmd))

        await ops_test.model.wait_for_idle(
            [APP_NAME, ISTIO_PILOT, DEX_AUTH],
            status="active",
            raise_on_blocked=True,
            raise_on_error=True,
            timeout=600,
        )
