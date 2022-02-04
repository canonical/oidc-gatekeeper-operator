# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import pytest
from ops.model import ActiveStatus, BlockedStatus
from ops.testing import Harness
import yaml

from charm import Operator


@pytest.fixture
def harness():
    return Harness(Operator)


def test_missing_image(harness):
    harness.set_leader(True)
    harness.begin_with_initial_hooks()
    assert harness.charm.model.unit.status == BlockedStatus("Missing resource: oci-image")


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
