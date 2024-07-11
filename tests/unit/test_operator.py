# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
from unittest.mock import MagicMock, patch

import pytest
import yaml
from ops.model import ActiveStatus, WaitingStatus
from ops.testing import Harness

from charm import OIDCGatekeeperOperator


@pytest.fixture
def harness():
    return Harness(OIDCGatekeeperOperator)


@patch("charm.KubernetesServicePatch", lambda x, y: None)
def test_log_forwarding(harness):
    """Test LogForwarder initialization."""
    with patch("charm.LogForwarder") as mock_logging:
        harness.begin()
        mock_logging.assert_called_once_with(charm=harness.charm)


@patch("charm.KubernetesServicePatch", lambda x, y: None)
def test_not_leader(harness):
    harness.begin_with_initial_hooks()
    assert harness.charm.model.unit.status == WaitingStatus("Waiting for leadership")


@patch("charm.KubernetesServicePatch", lambda x, y: None)
def test_no_relation(harness):
    harness.set_leader(True)
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
    harness.set_leader(True)
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
    harness.set_leader(True)
    harness.update_config({"skip-auth-urls": "/test/,/path1/"})
    harness.begin_with_initial_hooks()

    plan = harness.get_container_pebble_plan("oidc-authservice")
    assert "SKIP_AUTH_URLS" in plan.services["oidc-authservice"].environment
    assert (
        plan.services["oidc-authservice"].environment["SKIP_AUTH_URLS"] == "/dex/,/test/,/path1/"
    )


@patch("charm.KubernetesServicePatch", lambda x, y: None)
def test_skip_auth_url_config_is_empty(harness):
    harness.set_leader(True)
    harness.begin_with_initial_hooks()

    plan = harness.get_container_pebble_plan("oidc-authservice")
    assert "SKIP_AUTH_URLS" in plan.services["oidc-authservice"].environment
    assert plan.services["oidc-authservice"].environment["SKIP_AUTH_URLS"] == "/dex/"


@patch("charm.KubernetesServicePatch", lambda x, y: None)
def test_ca_bundle_config(harness):
    harness.set_leader(True)
    harness.update_config({"ca-bundle": "aaa"})
    harness.begin_with_initial_hooks()

    plan = harness.get_container_pebble_plan("oidc-authservice")
    assert "CA_BUNDLE" in plan.services["oidc-authservice"].environment
    assert (
        plan.services["oidc-authservice"].environment["CA_BUNDLE"] == "/etc/certs/oidc/root-ca.pem"
    )


@patch("charm.KubernetesServicePatch", lambda x, y: None)
def test_session_store(harness):
    harness.set_leader(True)
    harness.begin_with_initial_hooks()

    plan = harness.get_container_pebble_plan("oidc-authservice")
    assert "SESSION_STORE_PATH" in plan.services["oidc-authservice"].environment
    assert plan.services["oidc-authservice"].environment["SESSION_STORE_PATH"] == "bolt.db"

    assert "OIDC_STATE_STORE_PATH" in plan.services["oidc-authservice"].environment
    assert (
        plan.services["oidc-authservice"].environment["OIDC_STATE_STORE_PATH"] == "oidc_state.db"
    )


@patch("charm.KubernetesServicePatch", lambda x, y: None)
@patch("charm.update_layer", MagicMock())
def test_pebble_ready_hook_handled(harness: Harness):
    """
    Test if we handle oidc_authservice_pebble_ready hook. This test fails if we don't.
    """
    harness.set_leader(True)
    harness.begin()
    harness.charm._get_interfaces = MagicMock()
    harness.charm._check_secret = MagicMock()
    harness.charm._send_info = MagicMock()
    harness.charm._configure_mesh = MagicMock()

    harness.charm.on.oidc_authservice_pebble_ready.emit(harness.charm)

    assert isinstance(harness.charm.model.unit.status, ActiveStatus)
