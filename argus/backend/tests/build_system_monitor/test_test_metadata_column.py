from uuid import uuid4

import pytest
from coodie.aio import execute_raw

from argus.backend.models.web import ArgusTest


@pytest.mark.docker_required
async def test_saved_metadata_map_reads_back_unchanged(argus_db, fake_test):
    fake_test.test_metadata = {
        "description": "Basic longevity test running cassandra-stress",
        "tier": "tier1",
        "supported_backends": '["aws", "gce"]',
    }
    await fake_test.save()

    reloaded = await ArgusTest.get(id=fake_test.id)

    assert reloaded.test_metadata == fake_test.test_metadata


@pytest.mark.docker_required
async def test_empty_metadata_map_reads_back_as_empty_dict(argus_db, fake_test):
    fake_test.test_metadata = {}
    await fake_test.save()

    reloaded = await ArgusTest.get(id=fake_test.id)

    assert reloaded.test_metadata == {}


@pytest.mark.docker_required
async def test_row_written_without_the_column_reads_as_empty_dict(argus_db, group, release):
    test_id = uuid4()
    await execute_raw(
        f"INSERT INTO {ArgusTest._get_keyspace()}.{ArgusTest.table_name()} (id, group_id, release_id, name) VALUES (?, ?, ?, ?)",
        [test_id, group.id, release.id, f"legacy_row_{test_id.hex}"],
    )

    try:
        assert (await ArgusTest.get(id=test_id)).test_metadata == {}
    finally:
        await execute_raw(f"DELETE FROM {ArgusTest._get_keyspace()}.{ArgusTest.table_name()} WHERE id = ?", [test_id])


@pytest.mark.docker_required
async def test_test_info_payload_carries_the_metadata_map(argus_db, api_client, fake_test):
    metadata = {"tier": "tier1", "supported_backends": '["aws", "gce"]'}
    fake_test.test_metadata = metadata
    await fake_test.save()

    body = api_client.get(f"/api/v1/test-info?testId={fake_test.id}").json()

    assert body["status"] == "ok"
    assert body["response"]["test"]["test_metadata"] == metadata
