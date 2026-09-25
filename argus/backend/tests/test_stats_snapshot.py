"""
Tests for the release stats snapshot cache and targeted invalidation.

Covers:
- snapshot_filter_key format and determinism
- PluginModelBase.invalidate_release_snapshot() targeted deletion logic
- PluginModelBase.index_version() write path via ClientService
- SCTTestRun.index_image() write path via ClientService
- ReleaseStatsCollector.collect() cache miss → write → hit cycle
- force=True bypass and overwrite behaviour
- Per-version cache isolation (different filter keys cached separately)
- Targeted invalidation: only the run's version + all-versions aggregate are dropped
- Unaffected versions remain warm after a run finishes on another version
- New run appears after invalidation (stale data regression)
- delete_release() cleanup of indexes and snapshots
"""
import json
import time
import types
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from argus.backend.models.web import (
    ReleaseDistinctVersions,
    ReleaseDistinctImages,
    ReleaseStatsSnapshot,
)
from argus.backend.service.stats import snapshot_filter_key, ReleaseStatsCollector
from argus.backend.tests.conftest import g, get_fake_test_run
from argus.common.enums import TestStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def get_snapshots(release_id) -> list[ReleaseStatsSnapshot]:
    return list(await ReleaseStatsSnapshot.find(release_id=release_id).all())


async def write_snapshot(release_id, filter_key: str, payload: str = '{"dummy": true}'):
    await ReleaseStatsSnapshot.create(
        release_id=release_id,
        filter_key=filter_key,
        payload=payload,
        generated_at=datetime.now(timezone.utc),
    )


def make_mock_snapshot(filter_key: str) -> MagicMock:
    s = MagicMock()
    s.delete = AsyncMock()
    s.filter_key = filter_key
    return s


def plugin_run_stub(release_id, version: str | None) -> SimpleNamespace:
    """Duck-typed stand-in for a PluginModelBase instance.

    Coodie documents cannot be instantiated without a live cluster and full
    mapper initialisation, so we bind the real unbound methods to a plain
    SimpleNamespace that carries only the attributes the methods read.
    """
    from argus.backend.plugins.core import PluginModelBase
    obj = SimpleNamespace(release_id=release_id, scylla_version=version)
    obj.invalidate_release_snapshot = types.MethodType(
        PluginModelBase.invalidate_release_snapshot, obj
    )
    obj.index_version = types.MethodType(PluginModelBase.index_version, obj)
    return obj


# ---------------------------------------------------------------------------
# Unit: snapshot_filter_key format and properties
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("version,image_id,nov,lim,expected", [
    (None,    None,      True,  False, "v=::img=::nov=1::lim=0"),
    ("5.2",   None,      True,  False, "v=5.2::img=::nov=1::lim=0"),
    (None,    "ami-abc", False, True,  "v=::img=ami-abc::nov=0::lim=1"),
    ("5.6.1", "ami-xyz", True,  True,  "v=5.6.1::img=ami-xyz::nov=1::lim=1"),
    ("5.2",   None,      False, False, "v=5.2::img=::nov=0::lim=0"),
])
def test_snapshot_filter_key_format(version, image_id, nov, lim, expected):
    assert snapshot_filter_key(version, image_id, nov, lim) == expected


def test_snapshot_filter_key_is_deterministic():
    assert snapshot_filter_key("5.2", "ami-abc", True, False) == snapshot_filter_key("5.2", "ami-abc", True, False)


def test_snapshot_filter_key_no_collisions():
    keys = {
        snapshot_filter_key("5.2", None,    True,  False),
        snapshot_filter_key("5.3", None,    True,  False),
        snapshot_filter_key(None,  None,    True,  False),
        snapshot_filter_key("5.2", None,    False, False),
        snapshot_filter_key("5.2", None,    True,  True),
        snapshot_filter_key("5.2", "ami-1", True,  False),
    }
    assert len(keys) == 6


# ---------------------------------------------------------------------------
# Unit: invalidate_release_snapshot targeted deletion
# ---------------------------------------------------------------------------

async def test_invalidate_release_snapshot_deletes_matching_version_and_aggregate(argus_db):
    snapshots = [
        make_mock_snapshot("v=5.6.1::img=::nov=1::lim=0"),
        make_mock_snapshot("v=5.6.1::img=::nov=0::lim=0"),
        make_mock_snapshot("v=::img=::nov=1::lim=0"),       # all-versions aggregate
        make_mock_snapshot("v=5.7.0::img=::nov=1::lim=0"),  # unrelated version
    ]
    with patch("argus.backend.models.web.ReleaseStatsSnapshot.find") as mock_filter:
        mock_filter.return_value.all = AsyncMock(return_value=snapshots)
        await plugin_run_stub(uuid.uuid4(), "5.6.1").invalidate_release_snapshot()

    deleted = [s for s in snapshots if s.delete.called]
    kept    = [s for s in snapshots if not s.delete.called]
    assert len(deleted) == 3
    assert len(kept) == 1
    assert kept[0].filter_key == "v=5.7.0::img=::nov=1::lim=0"


async def test_invalidate_release_snapshot_versionless_run_only_wipes_aggregate(argus_db):
    snapshots = [
        make_mock_snapshot("v=5.6.1::img=::nov=1::lim=0"),
        make_mock_snapshot("v=::img=::nov=1::lim=0"),
        make_mock_snapshot("v=5.7.0::img=::nov=1::lim=0"),
    ]
    with patch("argus.backend.models.web.ReleaseStatsSnapshot.find") as mock_filter:
        mock_filter.return_value.all = AsyncMock(return_value=snapshots)
        await plugin_run_stub(uuid.uuid4(), None).invalidate_release_snapshot()

    deleted = [s for s in snapshots if s.delete.called]
    assert len(deleted) == 1
    assert deleted[0].filter_key == "v=::img=::nov=1::lim=0"


@pytest.mark.parametrize("release_id,version", [
    (None,        "5.6.1"),  # no release_id — nothing to invalidate
])
async def test_invalidate_release_snapshot_skips_without_release_id(argus_db, release_id, version):
    with patch("argus.backend.models.web.ReleaseStatsSnapshot.find") as mock_filter:
        await plugin_run_stub(release_id, version).invalidate_release_snapshot()
        mock_filter.assert_not_called()


async def test_invalidate_release_snapshot_swallows_db_exception(argus_db):
    with patch("argus.backend.models.web.ReleaseStatsSnapshot.find", side_effect=Exception("db error")):
        await plugin_run_stub(uuid.uuid4(), "5.6.1").invalidate_release_snapshot()  # must not raise


# ---------------------------------------------------------------------------
# Integration: index_version written through the real client pipeline
# ---------------------------------------------------------------------------

@pytest.mark.docker_required
async def test_index_version_written_on_submit_product_version(argus_db, fake_test, client_service, release):
    run_type, run_req = get_fake_test_run(fake_test)
    await client_service.submit_run(run_type, asdict(run_req))
    await client_service.submit_product_version(run_type, run_req.run_id, "9.9.9-test")

    versions = [r.version for r in await ReleaseDistinctVersions.find(release_id=release.id).all()]
    assert "9.9.9-test" in versions


@pytest.mark.docker_required
async def test_index_version_written_on_finish_run(argus_db, fake_test, client_service, release):
    run_type, run_req = get_fake_test_run(fake_test)
    await client_service.submit_run(run_type, asdict(run_req))
    await client_service.submit_product_version(run_type, run_req.run_id, "8.8.8-test")
    await client_service.finish_run(run_type, run_req.run_id)

    versions = [r.version for r in await ReleaseDistinctVersions.find(release_id=release.id).all()]
    assert "8.8.8-test" in versions


# ---------------------------------------------------------------------------
# Unit: index_version guard conditions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("release_id,version", [
    (None,         "5.6.1"),  # no release_id
    (uuid.uuid4(), None),     # no version
])
async def test_index_version_skipped_when_required_fields_absent(argus_db, release_id, version):
    with patch("argus.backend.models.web.ReleaseDistinctVersions.create") as mock_create:
        await plugin_run_stub(release_id, version).index_version()
        mock_create.assert_not_called()


async def test_index_version_swallows_db_exception(argus_db):
    with patch("argus.backend.models.web.ReleaseDistinctVersions.create", side_effect=Exception("db error")):
        await plugin_run_stub(uuid.uuid4(), "5.6.1").index_version()  # must not raise


# ---------------------------------------------------------------------------
# Integration: index_image written through the real client pipeline
# (SCTTestRun.index_image is SCT-specific; tested via direct static call with
# a realistic stub since cloud_setup requires a full UDT to be materialised)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cloud_setup,expected_call", [
    (None, False),                               # no cloud_setup — nothing indexed
    (SimpleNamespace(db_node=SimpleNamespace(image_id=None)), False),  # image_id absent
])
async def test_index_image_skipped_when_image_unavailable(argus_db, cloud_setup, expected_call):
    from argus.backend.plugins.sct.testrun import SCTTestRun
    run = SimpleNamespace(release_id=uuid.uuid4(), cloud_setup=cloud_setup)
    with patch("argus.backend.models.web.ReleaseDistinctImages.create") as mock_create:
        await SCTTestRun.index_image(run)
        assert mock_create.called == expected_call


async def test_index_image_writes_row_when_image_present(argus_db):
    from argus.backend.plugins.sct.testrun import SCTTestRun
    run = SimpleNamespace(
        release_id=uuid.uuid4(),
        cloud_setup=SimpleNamespace(db_node=SimpleNamespace(image_id="ami-abc123")),
    )
    with patch("argus.backend.models.web.ReleaseDistinctImages.create") as mock_create:
        await SCTTestRun.index_image(run)
        mock_create.assert_called_once_with(release_id=run.release_id, image_id="ami-abc123")


# ---------------------------------------------------------------------------
# Integration: snapshot cache miss → write → hit
# ---------------------------------------------------------------------------

@pytest.mark.docker_required
async def test_snapshot_cache_miss_writes_snapshot_and_hit_returns_consistent_counts(argus_db, fake_test, client_service, release):
    run_type, run_req = get_fake_test_run(fake_test)
    await client_service.submit_run(run_type, asdict(run_req))

    for row in await get_snapshots(release.id):
        await row.delete()

    collector = ReleaseStatsCollector(release.name)
    result_miss = await collector.collect(force=False, include_no_version=True)

    filter_key = snapshot_filter_key(None, None, True, False)
    assert any(s.filter_key == filter_key for s in await get_snapshots(release.id)), \
        "Snapshot not written after cache miss"

    result_hit = await collector.collect(force=False, include_no_version=True)
    assert set(result_miss.keys()) == set(result_hit.keys())
    assert result_miss.get("total") == result_hit.get("total")
    assert result_miss.get("created") == result_hit.get("created")


@pytest.mark.docker_required
async def test_snapshot_force_bypasses_stale_cache_and_overwrites(argus_db, fake_test, client_service, release):
    run_type, run_req = get_fake_test_run(fake_test)
    await client_service.submit_run(run_type, asdict(run_req))

    filter_key = snapshot_filter_key(None, None, True, False)
    await write_snapshot(release.id, filter_key, payload='{"bogus": true, "groups": []}')

    result = await ReleaseStatsCollector(release.name).collect(force=True, include_no_version=True)

    assert result != {"bogus": True, "groups": []}
    snap = await ReleaseStatsSnapshot.get(release_id=release.id, filter_key=filter_key)
    assert json.loads(snap.payload) != {"bogus": True, "groups": []}


@pytest.mark.docker_required
async def test_snapshot_force_still_populates_cache_for_subsequent_hits(argus_db, fake_test, client_service, release):
    run_type, run_req = get_fake_test_run(fake_test)
    await client_service.submit_run(run_type, asdict(run_req))

    for s in await get_snapshots(release.id):
        await s.delete()

    collector = ReleaseStatsCollector(release.name)
    await collector.collect(force=True, include_no_version=True)

    filter_key = snapshot_filter_key(None, None, True, False)
    snap = await ReleaseStatsSnapshot.get(release_id=release.id, filter_key=filter_key)
    assert snap is not None and snap.payload

    result = await collector.collect(force=False, include_no_version=True)
    assert result is not None


@pytest.mark.docker_required
@pytest.mark.parametrize("versions", [("5.2.0", "5.3.0"), ("6.0.0", "6.1.0")])
async def test_different_versions_cached_under_separate_filter_keys(argus_db, fake_test, client_service, release, versions):
    ver_a, ver_b = versions
    run_type, req_a = get_fake_test_run(fake_test)
    run_type, req_b = get_fake_test_run(fake_test)
    await client_service.submit_run(run_type, asdict(req_a))
    await client_service.submit_run(run_type, asdict(req_b))
    await client_service.submit_product_version(run_type, req_a.run_id, ver_a)
    await client_service.submit_product_version(run_type, req_b.run_id, ver_b)

    for s in await get_snapshots(release.id):
        await s.delete()

    await ReleaseStatsCollector(release.name, release_version=ver_a).collect(force=False, include_no_version=False)
    await ReleaseStatsCollector(release.name, release_version=ver_b).collect(force=False, include_no_version=False)

    keys = {s.filter_key for s in await get_snapshots(release.id)}
    assert snapshot_filter_key(ver_a, None, False, False) in keys
    assert snapshot_filter_key(ver_b, None, False, False) in keys


# ---------------------------------------------------------------------------
# Integration: targeted invalidation
# ---------------------------------------------------------------------------

@pytest.mark.docker_required
async def test_finish_run_invalidates_only_matching_version_and_aggregate(argus_db, fake_test, client_service, release):
    run_type, run_req = get_fake_test_run(fake_test)
    await client_service.submit_run(run_type, asdict(run_req))

    key_561 = snapshot_filter_key("5.6.1", None, True, False)
    key_570 = snapshot_filter_key("5.7.0", None, True, False)
    key_all = snapshot_filter_key(None,    None, True, False)
    for k in (key_561, key_570, key_all):
        await write_snapshot(release.id, k)

    await client_service.submit_product_version(run_type, run_req.run_id, "5.6.1")
    await client_service.finish_run(run_type, run_req.run_id)

    remaining = {s.filter_key for s in await get_snapshots(release.id)}
    assert key_561 not in remaining, "5.6.1 snapshot must be invalidated"
    assert key_all not in remaining, "all-versions snapshot must be invalidated"
    assert key_570 in remaining,     "5.7.0 snapshot must NOT be invalidated"


@pytest.mark.docker_required
async def test_submit_run_invalidates_aggregate_but_not_version_snapshots(argus_db, fake_test, client_service, release):
    key_561 = snapshot_filter_key("5.6.1", None, True, False)
    key_570 = snapshot_filter_key("5.7.0", None, True, False)
    key_all = snapshot_filter_key(None,    None, True, False)
    for k in (key_561, key_570, key_all):
        await write_snapshot(release.id, k)

    # New run has no version at submit time — only aggregate should be wiped
    run_type, run_req = get_fake_test_run(fake_test)
    await client_service.submit_run(run_type, asdict(run_req))

    remaining = {s.filter_key for s in await get_snapshots(release.id)}
    assert key_all not in remaining, "all-versions snapshot must be invalidated on submit_run"
    assert key_561 in remaining,     "5.6.1 snapshot must survive unrelated submit_run"
    assert key_570 in remaining,     "5.7.0 snapshot must survive unrelated submit_run"


@pytest.mark.docker_required
async def test_run_finishing_on_one_release_does_not_invalidate_another(argus_db, fake_test, client_service, release, release_manager_service):
    release_b = await release_manager_service.create_release(f"release_b_{time.time_ns()}", "Release B", False)
    group_b = await release_manager_service.create_group(
        f"group_b_{time.time_ns()}", "Group B",
        build_system_id=release_b.name, release_id=str(release_b.id),
    )
    test_b = await release_manager_service.create_test(
        f"test_b_{time.time_ns()}", "test_b", "test_b", "test_b",
        group_id=str(group_b.id), release_id=str(release_b.id), plugin_name="scylla-cluster-tests",
    )

    key = snapshot_filter_key(None, None, True, False)
    await write_snapshot(release.id,   key, '{"release": "a"}')
    await write_snapshot(release_b.id, key, '{"release": "b"}')

    run_type, run_req = get_fake_test_run(test_b)
    await client_service.submit_run(run_type, asdict(run_req))
    await client_service.finish_run(run_type, run_req.run_id)

    snap_a = await ReleaseStatsSnapshot.get(release_id=release.id, filter_key=key)
    assert json.loads(snap_a.payload) == {"release": "a"}


# ---------------------------------------------------------------------------
# Integration: stale data regression — new run visible after invalidation
# ---------------------------------------------------------------------------

@pytest.mark.docker_required
async def test_new_run_visible_in_stats_after_cache_invalidation(argus_db, fake_test, client_service, release):
    for s in await get_snapshots(release.id):
        await s.delete()

    def run_count(result: dict) -> int:
        return sum(
            len(g.get("tests", [])) for g in result.get("groups", {}).values()
            if isinstance(g, dict)
        )

    collector = ReleaseStatsCollector(release.name)
    count_before = run_count(await collector.collect(force=False, include_no_version=True))

    run_type, run_req = get_fake_test_run(fake_test)
    await client_service.submit_run(run_type, asdict(run_req))
    await client_service.finish_run(run_type, run_req.run_id)

    key_all = snapshot_filter_key(None, None, True, False)
    assert key_all not in {s.filter_key for s in await get_snapshots(release.id)}, \
        "Snapshot must be invalidated after finish_run"

    count_after = run_count(await collector.collect(force=False, include_no_version=True))
    assert count_after >= count_before

    count_cached = run_count(await collector.collect(force=False, include_no_version=True))
    assert count_cached == count_after


@pytest.mark.docker_required
async def test_unaffected_version_snapshot_stays_warm_when_other_version_run_finishes(argus_db, fake_test, client_service, release):
    run_type, req_561 = get_fake_test_run(fake_test)
    run_type, req_570 = get_fake_test_run(fake_test)
    await client_service.submit_run(run_type, asdict(req_561))
    await client_service.submit_run(run_type, asdict(req_570))
    await client_service.submit_product_version(run_type, req_561.run_id, "5.6.1")
    await client_service.submit_product_version(run_type, req_570.run_id, "5.7.0")

    await ReleaseStatsCollector(release.name, release_version="5.6.1").collect(force=False, include_no_version=False)
    await ReleaseStatsCollector(release.name, release_version="5.7.0").collect(force=False, include_no_version=False)

    key_570 = snapshot_filter_key("5.7.0", None, False, False)
    assert any(s.filter_key == key_570 for s in await get_snapshots(release.id)), \
        "Pre-condition: 5.7.0 snapshot must be warm before test"

    await client_service.finish_run(run_type, req_561.run_id)

    remaining = {s.filter_key for s in await get_snapshots(release.id)}
    assert key_570 in remaining, "5.7.0 snapshot must survive 5.6.1 run finishing"


# ---------------------------------------------------------------------------
# Regression: release cleanup
# ---------------------------------------------------------------------------

@pytest.mark.docker_required
async def test_delete_release_removes_indexes_and_snapshots(argus_db, release_manager_service):
    r = await release_manager_service.create_release(f"cleanup_{time.time_ns()}", "Cleanup Test", False)
    rid = r.id

    await ReleaseDistinctVersions.create(release_id=rid, version="1.0.0")
    await ReleaseDistinctImages.create(release_id=rid, image_id="ami-cleanup")
    await write_snapshot(rid, snapshot_filter_key(None, None, True, False))

    await release_manager_service.delete_release(str(rid))

    assert list(await ReleaseDistinctVersions.find(release_id=rid).all()) == []
    assert list(await ReleaseDistinctImages.find(release_id=rid).all()) == []
    assert await get_snapshots(rid) == []


# ---------------------------------------------------------------------------
# Plans and the version filter
# ---------------------------------------------------------------------------

@pytest.mark.docker_required
async def test_planned_test_without_runs_reads_not_run_when_no_version_filter(api_client, fake_test, release):
    created = api_client.post("/api/v1/planning/plan/create", json={
        "name": f"plan_{uuid.uuid4().hex[:8]}",
        "description": "stats plan",
        "owner": str(g.user.id),
        "participants": [],
        "target_version": "9.9",
        "release_id": str(release.id),
        "tests": [str(fake_test.id)],
        "groups": [],
        "assignments": {},
    }).json()
    assert created["status"] == "ok", created
    try:
        result = await ReleaseStatsCollector(release.name).collect(force=True, include_no_version=True)
    finally:
        api_client.delete(f"/api/v1/planning/plan/{created['response']['id']}/delete?deleteView=true")

    test_stats = result["groups"][str(fake_test.group_id)]["tests"][str(fake_test.id)]
    assert test_stats["status"] == TestStatus.NOT_RUN
