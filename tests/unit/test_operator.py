# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
from unittest.mock import MagicMock, patch

import pytest
import yaml
from charmed_kubeflow_chisme.exceptions import ErrorWithStatus
from charms.dex_auth.v0.dex_oidc_config import (
    DexOidcConfigRelationDataMissingError,
    DexOidcConfigRelationMissingError,
    DexOidcConfigRequirer,
)
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from ops.testing import Harness

from charm import OIDCGatekeeperOperator


@pytest.fixture
def harness():
    harness = Harness(OIDCGatekeeperOperator)
    harness.set_model_name("kubeflow")
    harness.set_leader(True)
    yield harness
    harness.cleanup()


@patch("charm.KubernetesServicePatch", lambda x, y: None)
def test_log_forwarding(harness):
    """Test LogForwarder initialization."""
    with patch("charm.LogForwarder") as mock_logging:
        harness.begin()
        mock_logging.assert_called_once_with(charm=harness.charm)


@patch("charm.KubernetesServicePatch", lambda x, y: None)
def test_not_leader(harness: Harness):
    harness.set_leader(False)
    harness.begin_with_initial_hooks()
    assert harness.charm.model.unit.status == WaitingStatus("Waiting for leadership")


@patch("charm.KubernetesServicePatch", lambda x, y: None)
def test_no_relation(harness):
    # Add dex-oidc-config relation by default; otherwise charm will block
    harness.add_relation("dex-oidc-config", "app", app_data={"issuer-url": "http://dex.io/dex"})

    harness.add_oci_resource(
        "oci-image",
        {
            "registrypath": "ci-test",
            "username": "",
            "password": "",
        },
    )
    harness.begin_with_initial_hooks()

    assert harness.charm.model.unit.status == ActiveStatus()


@patch("charm.KubernetesServicePatch", lambda x, y: None)
def test_with_relation(harness):
    # Add dex-oidc-config relation by default; otherwise charm will block
    harness.add_relation("dex-oidc-config", "app", app_data={"issuer-url": "http://dex.io/dex"})

    rel_id = harness.add_relation("ingress", "app")
    harness.add_relation_unit(rel_id, "app/0")

    data = {"service-name": "service-name", "service-port": "6666"}
    harness.update_relation_data(
        rel_id,
        "app",
        {"_supported_versions": "- v1", "data": yaml.dump(data)},
    )
    harness.begin_with_initial_hooks()

    assert isinstance(harness.charm.model.unit.status, ActiveStatus)


@patch("charm.KubernetesServicePatch", lambda x, y: None)
def test_skip_auth_url_config_has_value(harness):
    harness.update_config({"skip-auth-urls": "/test/,/path1/"})

    # Add dex-oidc-config relation by default; otherwise charm will block
    harness.add_relation("dex-oidc-config", "app", app_data={"issuer-url": "http://dex.io/dex"})

    harness.begin_with_initial_hooks()

    plan = harness.get_container_pebble_plan("oidc-authservice")
    assert "SKIP_AUTH_URLS" in plan.services["oidc-authservice"].environment
    assert (
        plan.services["oidc-authservice"].environment["SKIP_AUTH_URLS"] == "/dex/,/test/,/path1/"
    )


@patch("charm.KubernetesServicePatch", lambda x, y: None)
def test_skip_auth_url_config_is_empty(harness):
    # Add dex-oidc-config relation by default; otherwise charm will block
    harness.add_relation("dex-oidc-config", "app", app_data={"issuer-url": "http://dex.io/dex"})

    harness.begin_with_initial_hooks()

    plan = harness.get_container_pebble_plan("oidc-authservice")
    assert "SKIP_AUTH_URLS" in plan.services["oidc-authservice"].environment
    assert plan.services["oidc-authservice"].environment["SKIP_AUTH_URLS"] == "/dex/"


@patch("charm.KubernetesServicePatch", lambda x, y: None)
def test_ca_bundle_config(harness):
    harness.update_config({"ca-bundle": "aaa"})
    # Add dex-oidc-config relation by default; otherwise charm will block
    harness.add_relation("dex-oidc-config", "app", app_data={"issuer-url": "http://dex.io/dex"})

    harness.begin_with_initial_hooks()

    plan = harness.get_container_pebble_plan("oidc-authservice")
    assert "CA_BUNDLE" in plan.services["oidc-authservice"].environment
    assert (
        plan.services["oidc-authservice"].environment["CA_BUNDLE"] == "/etc/certs/oidc/root-ca.pem"
    )


@patch("charm.KubernetesServicePatch", lambda x, y: None)
def test_session_store(harness):
    # Add dex-oidc-config relation by default; otherwise charm will block
    harness.add_relation("dex-oidc-config", "app", app_data={"issuer-url": "http://dex.io/dex"})

    harness.begin_with_initial_hooks()

    plan = harness.get_container_pebble_plan("oidc-authservice")
    assert "SESSION_STORE_PATH" in plan.services["oidc-authservice"].environment
    assert plan.services["oidc-authservice"].environment["SESSION_STORE_PATH"] == "bolt.db"

    assert "OIDC_STATE_STORE_PATH" in plan.services["oidc-authservice"].environment
    assert (
        plan.services["oidc-authservice"].environment["OIDC_STATE_STORE_PATH"] == "oidc_state.db"
    )


@patch("charm.update_layer", MagicMock())
@patch("charm.KubernetesServicePatch", lambda x, y: None)
def test_pebble_ready_hook_handled(harness: Harness):
    """
    Test if we handle oidc_authservice_pebble_ready hook. This test fails if we don't.
    """
    # Add dex-oidc-config relation by default; otherwise charm will block
    harness.add_relation("dex-oidc-config", "app", app_data={"issuer-url": "http://dex.io/dex"})

    harness.begin()
    harness.charm._get_interfaces = MagicMock()
    harness.charm._check_secret = MagicMock()
    harness.charm._send_info = MagicMock()
    harness.charm._configure_mesh = MagicMock()

    harness.charm.on.oidc_authservice_pebble_ready.emit(harness.charm)

    assert isinstance(harness.charm.model.unit.status, ActiveStatus)


@patch("charm.KubernetesServicePatch", lambda x, y: None)
def test_charm_blocks_on_missing_dex_oidc_config_relation(harness):
    """Test the charm goes into BlockedStatus when the relation is missing."""
    harness.add_oci_resource(
        "oci-image",
        {
            "registrypath": "ci-test",
            "username": "",
            "password": "",
        },
    )
    harness.begin_with_initial_hooks()

    assert isinstance(harness.charm.model.unit.status, BlockedStatus)
    assert (
        "Missing relation with a Dex OIDC config provider"
        in harness.charm.model.unit.status.message
    )


@patch("charm.KubernetesServicePatch", lambda x, y: None)
def test_service_environment_uses_data_from_relation(harness):
    """Test the service_environment property has the correct values set by the relation data."""
    # Add the client-secret peer relation as it is required to render the service environment
    harness.add_relation("client-secret", harness.model.app.name)

    expected_oidc_provider = "http://dex.io/dex"
    harness.add_relation("dex-oidc-config", "app", app_data={"issuer-url": expected_oidc_provider})

    harness.begin()

    service_environment = harness.charm.service_environment
    assert service_environment["OIDC_PROVIDER"] == expected_oidc_provider


@patch("charm.KubernetesServicePatch", lambda x, y: None)
@pytest.mark.parametrize(
    "expected_raise, expected_status",
    (
        (DexOidcConfigRelationMissingError, BlockedStatus),
        (DexOidcConfigRelationDataMissingError("Empty or missing data"), WaitingStatus),
    ),
)
@patch.object(DexOidcConfigRequirer, "get_data")
def test_check_dex_oidc_config_relation(mocked_get_data, expected_raise, expected_status, harness):
    """Verify the method raises ErrorWithStatus with correct status."""
    harness.begin()
    mocked_get_data.side_effect = expected_raise
    with pytest.raises(ErrorWithStatus) as raised_exception:
        harness.charm._check_dex_oidc_config_relation()

    # We can only check what status is sent to the main handler, which is the one setting it
    assert raised_exception.value.status_type == expected_status
