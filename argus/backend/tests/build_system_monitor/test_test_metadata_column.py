from uuid import uuid4

import pytest

from argus.backend.db import ScyllaCluster
from argus.backend.models.web import ArgusTest


@pytest.mark.docker_required
def test_saved_metadata_map_reads_back_unchanged(argus_db, fake_test):
    fake_test.test_metadata = {
        "description": "Basic longevity test running cassandra-stress",
        "tier": "tier1",
        "supported_backends": '["aws", "gce"]',
    }
    fake_test.save()

    reloaded = ArgusTest.get(id=fake_test.id)

    assert reloaded.test_metadata == fake_test.test_metadata


@pytest.mark.docker_required
def test_empty_metadata_map_reads_back_as_empty_dict(argus_db, fake_test):
    fake_test.test_metadata = {}
    fake_test.save()

    reloaded = ArgusTest.get(id=fake_test.id)

    assert reloaded.test_metadata == {}


@pytest.mark.docker_required
def test_row_written_without_the_column_reads_as_empty_dict(argus_db, group, release):
    test_id = uuid4()
    session = ScyllaCluster.get_session()
    session.execute(
        "INSERT INTO argus_test_v2 (id, group_id, release_id, name) VALUES (%s, %s, %s, %s)",
        (test_id, group.id, release.id, f"legacy_row_{test_id.hex}"),
    )

    try:
        assert ArgusTest.get(id=test_id).test_metadata == {}
    finally:
        session.execute("DELETE FROM argus_test_v2 WHERE id = %s", (test_id,))


@pytest.mark.docker_required
def test_test_info_payload_carries_the_metadata_map(argus_db, api_client, fake_test):
    metadata = {"tier": "tier1", "supported_backends": '["aws", "gce"]'}
    fake_test.test_metadata = metadata
    fake_test.save()

    body = api_client.get(f"/api/v1/test-info?testId={fake_test.id}").json()

    assert body["status"] == "ok"
    assert body["response"]["test"]["test_metadata"] == metadata
