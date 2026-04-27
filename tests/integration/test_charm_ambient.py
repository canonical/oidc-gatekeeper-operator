# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
from pathlib import Path

import lightkube
import pytest
import yaml
from charmed_kubeflow_chisme.testing import (
    GRAFANA_AGENT_APP,
    assert_logging,
    assert_path_reachable_through_ingress,
    assert_security_context,
    deploy_and_assert_grafana_agent,
    deploy_and_integrate_service_mesh_charms,
    generate_container_securitycontext_map,
    get_pod_names,
    integrate_with_service_mesh,
)
from charms_dependencies import DEX_AUTH, JUPYTER_UI
from pytest_operator.plugin import OpsTest

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
CHARM_ROOT = "."
CONTAINERS_SECURITY_CONTEXT_MAP = generate_container_securitycontext_map(METADATA)
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


@pytest.fixture(scope="session")
def lightkube_client() -> lightkube.Client:
    client = lightkube.Client(field_manager=APP_NAME)
    return client


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest):
    """Test that we can build the local charm and deploy it."""
    charm = await ops_test.build_charm(CHARM_ROOT)
    image_path = METADATA["resources"]["oci-image"]["upstream-source"]
    resources = {"oci-image": image_path}

    # deploy oidc-authservice
    await ops_test.model.deploy(
        charm,
        resources=resources,
        trust=True,
        config=OIDC_CONFIG,
    )

    # relate oidc-authservice to ambient
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
    await integrate_with_service_mesh(JUPYTER_UI.charm, ops_test.model)
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


async def test_logging(ops_test: OpsTest):
    """Test logging is defined in relation data bag."""
    app = ops_test.model.applications[GRAFANA_AGENT_APP]
    await assert_logging(app)


@pytest.mark.parametrize("container_name", list(CONTAINERS_SECURITY_CONTEXT_MAP.keys()))
async def test_container_security_context(
    ops_test: OpsTest,
    lightkube_client: lightkube.Client,
    container_name: str,
):
    """Test container security context is correctly set.

    Verify that container spec defines the security context with correct
    user ID and group ID.
    """
    pod_name = get_pod_names(ops_test.model.name, APP_NAME)[0]
    assert_security_context(
        lightkube_client,
        pod_name,
        container_name,
        CONTAINERS_SECURITY_CONTEXT_MAP,
        ops_test.model.name,
    )


@pytest.mark.abort_on_fail
async def test_login_redirection(ops_test: OpsTest):
    """Test that authservice is registered as external authorizer and redirects to Dex."""
    await assert_path_reachable_through_ingress(
        http_path="/jupyter/",
        namespace=ops_test.model.name,
        expected_status=302,
        expected_response_text="dex/auth?client_id",
    )


@pytest.mark.abort_on_fail
async def test_authservice_url_is_unauthenticated(ops_test: OpsTest):
    """Test that the authservice url is accessible without auth redirects."""
    await assert_path_reachable_through_ingress(
        http_path="/authservice/",
        namespace=ops_test.model.name,
        expected_status=200,
        expected_response_text="OK",
    )


@pytest.mark.abort_on_fail
async def test_remove_application(ops_test: OpsTest):
    """Test that the application can be removed successfully."""
    await ops_test.model.remove_application(APP_NAME, block_until_done=True)
