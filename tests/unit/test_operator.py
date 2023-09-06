# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import pytest
import yaml
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from ops.testing import Harness

from charm import Operator


@pytest.fixture
def harness():
    return Harness(Operator)


def test_not_leader(harness):
    harness.begin_with_initial_hooks()
    assert harness.charm.model.unit.status == WaitingStatus("Waiting for leadership")


def test_missing_image(harness):
    harness.set_leader(True)
    harness.begin_with_initial_hooks()
    assert harness.charm.model.unit.status == BlockedStatus("Missing resource: oci-image")

def test_missing_public_url(harness):
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
    assert harness.charm.model.unit.status == BlockedStatus("public-url config required")


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

    harness.update_config({"public-url": "10.64.140.43.nip.io"})
    assert harness.charm.model.unit.status == ActiveStatus()


def test_with_relation(harness):
    harness.set_leader(True)
    harness.add_oci_resource(
        "oci-image",
        {
            "registrypath": "ci-test",
            "username": "",
            "password": "",
        },
    )
    harness.update_config({"public-url": "10.64.140.43.nip.io"})
    rel_id = harness.add_relation("ingress", "app")

    harness.add_relation_unit(rel_id, "app/0")
    data = {"service-name": "service-name", "service-port": "6666"}
    harness.update_relation_data(
        rel_id,
        "app",
        {"_supported_versions": "- v1", "data": yaml.dump(data)},
    )
    harness.begin_with_initial_hooks()

    _ = harness.get_pod_spec()
    assert isinstance(harness.charm.model.unit.status, ActiveStatus)


def test_public_url_prepend_http(harness):
    harness.set_leader(True)
    harness.add_oci_resource(
        "oci-image",
        {
            "registrypath": "ci-test",
            "username": "",
            "password": "",
        },
    )
    harness.update_config({"public-url": "10.64.140.43.nip.io"})
    harness.begin_with_initial_hooks()

    pod_spec, _ = harness.get_pod_spec()

    assert (
        pod_spec["containers"][0]["envConfig"]["OIDC_PROVIDER"] == "http://10.64.140.43.nip.io/dex"
    )


def test_public_url_keep_existing_protocol(harness):
    harness.set_leader(True)
    harness.add_oci_resource(
        "oci-image",
        {
            "registrypath": "ci-test",
            "username": "",
            "password": "",
        },
    )
    harness.update_config({"public-url": "https://10.64.140.43.nip.io"})
    harness.begin_with_initial_hooks()

    pod_spec, _ = harness.get_pod_spec()

    assert (
        pod_spec["containers"][0]["envConfig"]["OIDC_PROVIDER"]
        == "https://10.64.140.43.nip.io/dex"
    )


def test_skip_auth_url_config_has_value(harness):
    harness.set_leader(True)
    harness.add_oci_resource(
        "oci-image",
        {
            "registrypath": "ci-test",
            "username": "",
            "password": "",
        },
    )
    harness.update_config({"public-url": "https://10.64.140.43.nip.io", "skip-auth-urls": "/test/,/path1/"})
    harness.begin_with_initial_hooks()

    pod_spec, _ = harness.get_pod_spec()

    assert pod_spec["containers"][0]["envConfig"]["SKIP_AUTH_URLS"] == "/dex/,/test/,/path1/"


def test_skip_auth_url_config_is_empty(harness):
    harness.set_leader(True)
    harness.add_oci_resource(
        "oci-image",
        {
            "registrypath": "ci-test",
            "username": "",
            "password": "",
        },
    )
    harness.update_config({"public-url": "https://10.64.140.43.nip.io"})
    harness.begin_with_initial_hooks()

    pod_spec, _ = harness.get_pod_spec()

    assert pod_spec["containers"][0]["envConfig"]["SKIP_AUTH_URLS"] == "/dex/"


def test_ca_bundle_config(harness):
    harness.set_leader(True)
    harness.add_oci_resource(
        "oci-image",
        {
            "registrypath": "ci-test",
            "username": "",
            "password": "",
        },
    )
    harness.update_config({"public-url": "https://10.64.140.43.nip.io", "ca-bundle": "aaa"})
    harness.begin_with_initial_hooks()

    pod_spec, _ = harness.get_pod_spec()

    assert pod_spec["containers"][0]["envConfig"]["CA_BUNDLE"] == "/etc/certs/oidc/root-ca.pem"


def test_session_store_path(harness):
    harness.set_leader(True)
    harness.add_oci_resource(
        "oci-image",
        {
            "registrypath": "ci-test",
            "username": "",
            "password": "",
        },
    )
    harness.update_config({"public-url": "https://10.64.140.43.nip.io"})
    harness.begin_with_initial_hooks()
    pod_spec, _ = harness.get_pod_spec()
    assert pod_spec["containers"][0]["envConfig"]["SESSION_STORE_PATH"] == "bolt.db"


def test_oidc_state_store_path(harness):
    harness.set_leader(True)
    harness.add_oci_resource(
        "oci-image",
        {
            "registrypath": "ci-test",
            "username": "",
            "password": "",
        },
    )
    harness.update_config({"public-url": "https://10.64.140.43.nip.io"})
    harness.begin_with_initial_hooks()
    pod_spec, _ = harness.get_pod_spec()
    assert pod_spec["containers"][0]["envConfig"]["OIDC_STATE_STORE_PATH"] == "oidc_state.db"
