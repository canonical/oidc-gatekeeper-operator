# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

# Test dependencies
DEX_AUTH = "dex-auth"
DEX_AUTH_CHANNEL = "2.36/stable"
TRUST_DEX_AUTH = True
ISTIO_PILOT = "istio-pilot"
ISTIO_PILOT_CHANNEL = "1.17/stable"
TRUST_ISTIO_PILOT = True

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
PUBLIC_URL = "test-url"
APP_NAME = METADATA["name"]
APP_PREV_VERSION = "ckf-1.7/stable"
TRUST_PREV_APP = True
OIDC_CONFIG = {
    "client-name": "Ambassador Auth OIDC",
    "client-secret": "oidc-client-secret",
}

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
        await ops_test.model.deploy(
            ISTIO_PILOT, channel=ISTIO_PILOT_CHANNEL, trust=TRUST_ISTIO_PILOT
        )
        await ops_test.model.deploy(DEX_AUTH, channel=DEX_AUTH_CHANNEL, trust=TRUST_DEX_AUTH)
        await ops_test.model.add_relation(ISTIO_PILOT, DEX_AUTH)
        await ops_test.model.add_relation(f"{ISTIO_PILOT}:ingress", f"{APP_NAME}:ingress")
        await ops_test.model.add_relation(
            f"{ISTIO_PILOT}:ingress-auth", f"{APP_NAME}:ingress-auth"
        )
        await ops_test.model.add_relation(f"{APP_NAME}:oidc-client", f"{DEX_AUTH}:oidc-client")

        await ops_test.model.applications[DEX_AUTH].set_config({"public-url": PUBLIC_URL})

        # Not raising on blocked will allow istio-pilot to be deployed
        # without istio-gateway and provide oidc with the data it needs.
        await ops_test.model.wait_for_idle(
            [APP_NAME, ISTIO_PILOT, DEX_AUTH],
            status="active",
            raise_on_blocked=False,
            raise_on_error=True,
            timeout=600,
        )

    @pytest.mark.abort_on_fail
    async def test_remove_application(self, ops_test: OpsTest):
        """Test that the application can be removed successfully."""
        await ops_test.model.remove_application(APP_NAME, block_until_done=True)

    @pytest.mark.abort_on_fail
    @pytest.mark.timeout(1200)
    async def test_upgrade(self, ops_test: OpsTest):
        """Test that charm can be upgraded from podspec to sidecar.

        For this test we use APP_PREV_VERSION channel as the source for podspec charm.

        Note: juju has a bug due to which you have to first scale podspec charm to 0,
        then refresh, then scale up newly deployed app.
        See https://github.com/juju/juju/pull/15701 for more info.
        """
        print(f"Deploy {APP_NAME} from stable channel")
        await ops_test.model.deploy(
            APP_NAME, channel=APP_PREV_VERSION, trust=TRUST_PREV_APP, config=OIDC_CONFIG
        )
        await ops_test.model.add_relation(f"{ISTIO_PILOT}:ingress", f"{APP_NAME}:ingress")
        await ops_test.model.add_relation(
            f"{ISTIO_PILOT}:ingress-auth", f"{APP_NAME}:ingress-auth"
        )
        await ops_test.model.add_relation(f"{APP_NAME}:oidc-client", f"{DEX_AUTH}:oidc-client")
        await ops_test.model.applications[APP_NAME].set_config({"public-url": PUBLIC_URL})

        print("Stable charm is deployed, add relations")
        await ops_test.model.wait_for_idle(
            [APP_NAME, ISTIO_PILOT, DEX_AUTH],
            status="active",
            raise_on_blocked=False,
            raise_on_error=True,
            timeout=600,
        )
        print(f"Scale {APP_NAME} to 0 units")
        await ops_test.model.applications[APP_NAME].scale(scale=0)

        print("Try to refresh stable charm to locally built")
        # temporary measure while we don't have a solution for this:
        # * https://github.com/juju/python-libjuju/issues/881
        # Currently `application.local_refresh` doesn't work as expected.
        await ops_test.juju(
            [
                "refresh",
                APP_NAME,
                "--path",
                pytest.charm_under_test,
                "--resource",
                f"oci-image='{image_path}'",
            ]
        )

        print(f"Scale {APP_NAME} to 1 unit")
        await ops_test.model.applications[APP_NAME].scale(scale=1)

        await ops_test.model.wait_for_idle(
            status="active",
            raise_on_blocked=True,
            raise_on_error=True,
            timeout=1200,
        )
