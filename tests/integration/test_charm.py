# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
from pathlib import Path

import lightkube
import pytest
import yaml
from charmed_kubeflow_chisme.testing import fire_update_status_to_unit
from lightkube.resources.core_v1 import Service
from pytest_operator.plugin import OpsTest
from tenacity import sleep

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
OIDC_CONFIG = {
    "client-name": "Ambassador Auth OIDC",
    "client-secret": "oidc-client-secret",
}
ISTIO_PILOT = "istio-pilot"
ISTIO_GATEWAY = "istio-gateway"
DEX_AUTH = "dex-auth"
FALSE_PUBLIC_URL = "test-url"
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

        await ops_test.model.applications[APP_NAME].set_config({"public-url": FALSE_PUBLIC_URL})

        await ops_test.model.wait_for_idle(
            apps=[APP_NAME], status="active", raise_on_blocked=False, timeout=60 * 10
        )
        assert ops_test.model.applications[APP_NAME].units[0].workload_status == "active"

        # Fire update-status every 10 seconds and expect oidc to go to Maintenance
        # Didn't use `wait_for_idle()` here because although the unit and apps were
        # in maintenance, it kept waiting.
        async with ops_test.fast_forward(fast_interval="10s"):
            await ops_test.model.block_until(
                lambda: ops_test.model.applications[APP_NAME].status == "maintenance",
                timeout=1000,
            )
        assert ops_test.model.applications[APP_NAME].units[0].workload_status == "maintenance"

    @pytest.mark.abort_on_fail
    async def test_relations(self, ops_test: OpsTest):
        await ops_test.model.deploy(ISTIO_PILOT, channel="latest/edge", trust=True)
        await ops_test.model.deploy(
            ISTIO_GATEWAY, channel="latest/edge", trust=True, config={"kind": "ingress"}
        )
        await ops_test.model.deploy(DEX_AUTH, channel="latest/edge", trust=True)
        await ops_test.model.add_relation(
            f"{ISTIO_PILOT}:istio-pilot", f"{ISTIO_GATEWAY}:istio-pilot"
        )
        await ops_test.model.add_relation(f"{ISTIO_PILOT}:ingress", f"{APP_NAME}:ingress")
        await ops_test.model.add_relation(
            f"{ISTIO_PILOT}:ingress-auth", f"{APP_NAME}:ingress-auth"
        )
        await ops_test.model.add_relation(f"{APP_NAME}:oidc-client", f"{DEX_AUTH}:oidc-client")
        await ops_test.model.add_relation(f"{ISTIO_PILOT}:ingress", f"{DEX_AUTH}:ingress")

        await ops_test.model.wait_for_idle(
            [ISTIO_PILOT, ISTIO_GATEWAY],
            status="active",
            timeout=600,
        )

        public_url = get_public_url(ops_test.model_name)
        await ops_test.model.applications[DEX_AUTH].set_config({"public-url": public_url})
        await ops_test.model.applications[APP_NAME].set_config({"public-url": public_url})

        # Sleep 45 to allow OIDC workload container to have hit the health check failure
        # threshold after being reconfigured. Then fire an update-status to set the charm
        # status and ensure its workload is working.
        sleep(45)
        unit_name = f"{APP_NAME}/0"
        fire_update_status_to_unit(unit_name, ops_test.model_name)

        await ops_test.model.wait_for_idle(
            status="active",
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

        For this test we use 1.7/stable channel as the source for podspec charm.

        Note: juju has a bug due to which you have to first scale podspec charm to 0,
        then refresh, then scale up newly deployed app.
        See https://github.com/juju/juju/pull/15701 for more info.
        """
        print(f"Deploy {APP_NAME} from 1.7/stable channel")
        await ops_test.model.deploy(
            APP_NAME, channel="ckf-1.7/stable", trust=True, config=OIDC_CONFIG
        )
        await ops_test.model.add_relation(f"{ISTIO_PILOT}:ingress", f"{APP_NAME}:ingress")
        await ops_test.model.add_relation(
            f"{ISTIO_PILOT}:ingress-auth", f"{APP_NAME}:ingress-auth"
        )
        await ops_test.model.add_relation(f"{APP_NAME}:oidc-client", f"{DEX_AUTH}:oidc-client")
        public_url = get_public_url(ops_test.model_name)
        await ops_test.model.applications[APP_NAME].set_config({"public-url": public_url})

        print("Stable charm is deployed, add relations")
        await ops_test.model.wait_for_idle(
            status="active",
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

        sleep(45)
        unit_name = f"{APP_NAME}/2"
        fire_update_status_to_unit(unit_name, ops_test.model_name)
        await ops_test.model.wait_for_idle(
            status="active",
            raise_on_blocked=True,
            raise_on_error=True,
            timeout=1200,
        )


def get_public_url(namespace: str):
    """Extracts public url from service istio-ingressgateway-workload."""
    lightkube_client = lightkube.Client()
    ingressgateway_svc = lightkube_client.get(
        Service, "istio-ingressgateway-workload", namespace=namespace
    )
    public_url = f"http://{ingressgateway_svc.status.loadBalancer.ingress[0].ip}"
    return public_url
