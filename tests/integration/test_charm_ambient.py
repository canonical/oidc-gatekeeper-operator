# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
from pathlib import Path

import pytest
import yaml
from charmed_kubeflow_chisme.testing import (
    GRAFANA_AGENT_APP,
    assert_logging,
    assert_path_reachable_through_ingress,
    deploy_and_assert_grafana_agent,
    deploy_and_integrate_service_mesh_charms,
)
from charms_dependencies import DEX_AUTH, JUPYTER_UI
from pytest_operator.plugin import OpsTest

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
PREVIOUS_RELEASE = "ckf-1.9/stable"
PREVIOUS_RELEASE_TRUST = True
OIDC_CONFIG = {
    "client-name": "Ambassador Auth OIDC",
    "client-secret": "oidc-client-secret",
}
ISTIO_K8S = "istio-k8s"
ISTIO_INGRESS_K8S = "istio-ingress-k8s"
FORWARD_AUTH_ENDPOINT = "forward-auth"
ISTIO_INGRESS_ROUTE_ENDPOINT = "istio-ingress-route"
ISTIO_INGRESS_ROUTE_UNAUTHENTICATED_ENDPOINT = "istio-ingress-route-unauthenticated"


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
            pytest.charm_under_test,
            resources=RESOURCES,
            trust=True,
            config=OIDC_CONFIG,
        )

        await deploy_and_integrate_service_mesh_charms(
            APP_NAME,
            ops_test.model,
            model_on_mesh=False,
            relate_to_beacon=True,
            relate_to_ingress_route_endpoint=False,
        )

        # relate istio-ingress-k8s and istio-k8s, for handling the forward-auth relation
        await ops_test.model.integrate(
            f"{ISTIO_K8S}",
            f"{ISTIO_INGRESS_K8S}",
        )

        # manually relate to the unauthenticated endpoint and to act as an external authorizer
        await ops_test.model.integrate(
            f"{APP_NAME}:{ISTIO_INGRESS_ROUTE_UNAUTHENTICATED_ENDPOINT}",
            f"{ISTIO_INGRESS_K8S}:{ISTIO_INGRESS_ROUTE_UNAUTHENTICATED_ENDPOINT}",
        )

        await ops_test.model.integrate(
            f"{APP_NAME}:{FORWARD_AUTH_ENDPOINT}",
            f"{ISTIO_INGRESS_K8S}:{FORWARD_AUTH_ENDPOINT}",
        )

        # Deploying dex-auth is a hard requirement for this charm as
        # a dex-oidc-config requirer; otherwise it will block
        await ops_test.model.deploy(DEX_AUTH.charm, channel=DEX_AUTH.channel, trust=DEX_AUTH.trust)
        await ops_test.model.wait_for_idle(
            apps=[DEX_AUTH.charm],
            status="active",
            raise_on_blocked=False,
            timeout=60 * 10,
        )
        await ops_test.model.integrate(
            f"{APP_NAME}:dex-oidc-config", f"{DEX_AUTH.charm}:dex-oidc-config"
        )

        await ops_test.model.wait_for_idle(
            apps=[APP_NAME], status="active", raise_on_blocked=False, timeout=60 * 10
        )
        assert ops_test.model.applications[APP_NAME].units[0].workload_status == "active"

        # Deploy a test web app, that needs to be protected by the oidc charm
        await ops_test.model.deploy(
            JUPYTER_UI.charm, channel=JUPYTER_UI.channel, trust=JUPYTER_UI.trust
        )
        await ops_test.model.integrate(
            f"{JUPYTER_UI.charm}:{ISTIO_INGRESS_ROUTE_ENDPOINT}",
            f"{ISTIO_INGRESS_K8S}:{ISTIO_INGRESS_ROUTE_ENDPOINT}",
        )
        await ops_test.model.wait_for_idle(
            apps=[JUPYTER_UI.charm],
            status="active",
            raise_on_blocked=False,
            timeout=60 * 10,
        )

        # Deploying grafana-agent-k8s and add all relations
        await deploy_and_assert_grafana_agent(
            ops_test.model, APP_NAME, metrics=False, dashboard=False, logging=True
        )

    async def test_logging(self, ops_test: OpsTest):
        """Test logging is defined in relation data bag."""
        app = ops_test.model.applications[GRAFANA_AGENT_APP]
        await assert_logging(app)

    @pytest.mark.abort_on_fail
    async def test_login_redirection(self, ops_test: OpsTest):
        await assert_path_reachable_through_ingress(
            http_path="/jupyter/",
            namespace=ops_test.model.name,
            expected_status=302,
            expected_response_text="dex/auth?client_id",
        )
