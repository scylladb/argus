"""
Invalidation tests: verify that specific actions wipe exactly the right
StatsSnapshot cache entries and leave all others intact.

Every test:
  1. Seeds specific StatsSnapshot rows directly into the real DB.
  2. Executes the real action (submit_run, finish_run, update_view, …).
  3. Queries the DB and asserts which filter keys survived and which are gone.

No mocking of StatsSnapshot — the table is used for real.
"""
import json
import time
import uuid
from dataclasses import asdict
from datetime import UTC, datetime

import pytest

from argus.backend.models.web import ArgusUserView, StatsSnapshot
from argus.backend.service.stats import snapshot_filter_key
from argus.backend.service.stats_snapshot import SnapshotScope
from argus.backend.service.views import UserViewService
from argus.backend.tests.conftest import get_fake_test_run


# ---------------------------------------------------------------------------
# Seed / query helpers
# ---------------------------------------------------------------------------

def seed(scope: SnapshotScope, scope_id, *filter_keys: str, variant_key: str = "") -> None:
    """Write snapshot rows for the given scope/id and filter keys."""
    for fk in filter_keys:
        StatsSnapshot.create(
            scope_type=scope.value,
            scope_id=scope_id,
            filter_key=fk,
            variant_key=variant_key,
            payload=json.dumps({"seeded": True}),
            generated_at=datetime.now(UTC),
        )


def live_keys(scope: SnapshotScope, scope_id) -> set[str]:
    """Return the set of filter_keys currently in the DB for a scope."""
    return {
        r.filter_key
        for r in StatsSnapshot.filter(scope_type=scope.value, scope_id=scope_id).all()
    }


def clear(scope: SnapshotScope, scope_id) -> None:
    """Delete all snapshot rows for a scope — called in teardown."""
    for row in StatsSnapshot.filter(scope_type=scope.value, scope_id=scope_id).all():
        row.delete()


# Canonical filter keys used across tests
KEY_611 = snapshot_filter_key("6.1.0", None, True, False)   # v=6.1.0::img=::nov=1::lim=0
KEY_620 = snapshot_filter_key("6.2.0", None, True, False)   # v=6.2.0::img=::nov=1::lim=0
KEY_ALL = snapshot_filter_key(None,    None, True, False)   # v=::img=::nov=1::lim=0  (aggregate)
KEY_IMG = snapshot_filter_key("6.1.0", "ami-abc", True, False)  # version+image combo


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def view_with_test(argus_db, fake_test):
    """A view that contains fake_test. Deleted after the test."""
    view = ArgusUserView.create(
        id=uuid.uuid4(),
        name=f"inv_view_{time.time_ns()}",
        display_name="Invalidation Test View",
        description="",
        widget_settings="[]",
        tests=[fake_test.id],
        release_ids=[],
        group_ids=[],
        user_id=uuid.uuid4(),
    )
    yield view
    try:
        view.delete()
    except Exception:
        pass
    clear(SnapshotScope.VIEW, view.id)


@pytest.fixture
def view_with_release(argus_db, release):
    """A view that lists release in release_ids but has no explicit tests."""
    view = ArgusUserView.create(
        id=uuid.uuid4(),
        name=f"inv_view_rel_{time.time_ns()}",
        display_name="Invalidation Release View",
        description="",
        widget_settings="[]",
        tests=[],
        release_ids=[release.id],
        group_ids=[],
        user_id=uuid.uuid4(),
    )
    yield view
    try:
        view.delete()
    except Exception:
        pass
    clear(SnapshotScope.VIEW, view.id)


@pytest.fixture
def unrelated_view(argus_db):
    """A view with a random test id — not touched by actions on fake_test/release."""
    view = ArgusUserView.create(
        id=uuid.uuid4(),
        name=f"inv_view_unrelated_{time.time_ns()}",
        display_name="Unrelated View",
        description="",
        widget_settings="[]",
        tests=[uuid.uuid4()],  # a test that doesn't exist in the DB
        release_ids=[],
        group_ids=[],
        user_id=uuid.uuid4(),
    )
    yield view
    try:
        view.delete()
    except Exception:
        pass
    clear(SnapshotScope.VIEW, view.id)


@pytest.fixture
def second_release(release_manager_service):
    """An independent release; used to verify cross-release isolation."""
    r = release_manager_service.create_release(f"inv_r2_{time.time_ns()}", "Inv Release 2", False)
    yield r
    release_manager_service.delete_release(str(r.id))


@pytest.fixture
def user_view_service():
    return UserViewService()


# ---------------------------------------------------------------------------
# Section 1 — submit_run
#
# At submit time scylla_version is not yet set on the run, so
# invalidate_release_snapshot fires with version=None.
# _version_prefix(None) == "v=::" == aggregate_prefix, so only the
# aggregate key v=::* is wiped.
# ---------------------------------------------------------------------------

@pytest.mark.docker_required
def test_submit_run_wipes_aggregate_only_for_release(
    argus_db, fake_test, client_service, release
):
    seed(SnapshotScope.RELEASE, release.id, KEY_611, KEY_620, KEY_ALL)

    run_type, run_req = get_fake_test_run(fake_test)
    client_service.submit_run(run_type, asdict(run_req))

    remaining = live_keys(SnapshotScope.RELEASE, release.id)
    assert KEY_ALL not in remaining,  "aggregate must be wiped on submit_run"
    assert KEY_611 in remaining,      "v=6.1.0 must survive (no version on run yet)"
    assert KEY_620 in remaining,      "v=6.2.0 must survive (no version on run yet)"

    clear(SnapshotScope.RELEASE, release.id)


@pytest.mark.docker_required
def test_submit_run_wipes_aggregate_only_for_containing_view(
    argus_db, fake_test, client_service, view_with_test
):
    seed(SnapshotScope.VIEW, view_with_test.id, KEY_611, KEY_620, KEY_ALL)

    run_type, run_req = get_fake_test_run(fake_test)
    client_service.submit_run(run_type, asdict(run_req))

    remaining = live_keys(SnapshotScope.VIEW, view_with_test.id)
    assert KEY_ALL not in remaining,  "view aggregate must be wiped on submit_run"
    assert KEY_611 in remaining,      "view v=6.1.0 must survive (no version yet)"
    assert KEY_620 in remaining,      "view v=6.2.0 must survive (no version yet)"


@pytest.mark.docker_required
def test_submit_run_does_not_touch_unrelated_view(
    argus_db, fake_test, client_service, release, unrelated_view
):
    seed(SnapshotScope.VIEW, unrelated_view.id, KEY_611, KEY_ALL)

    run_type, run_req = get_fake_test_run(fake_test)
    client_service.submit_run(run_type, asdict(run_req))

    remaining = live_keys(SnapshotScope.VIEW, unrelated_view.id)
    assert KEY_611 in remaining, "unrelated view v=6.1.0 must not be touched"
    assert KEY_ALL in remaining, "unrelated view aggregate must not be touched"

    clear(SnapshotScope.RELEASE, release.id)


# ---------------------------------------------------------------------------
# Section 2 — finish_run (after submit_product_version sets scylla_version)
#
# finish_run calls invalidate_release_snapshot with the real version, so
# v=<version>::* AND v=::* (aggregate) are both wiped; other versions survive.
# ---------------------------------------------------------------------------

@pytest.mark.docker_required
def test_finish_run_wipes_version_and_aggregate_for_release(
    argus_db, fake_test, client_service, release
):
    seed(SnapshotScope.RELEASE, release.id, KEY_611, KEY_620, KEY_ALL, KEY_IMG)

    run_type, run_req = get_fake_test_run(fake_test)
    client_service.submit_run(run_type, asdict(run_req))
    client_service.submit_product_version(run_type, run_req.run_id, "6.1.0")
    client_service.finish_run(run_type, run_req.run_id)

    remaining = live_keys(SnapshotScope.RELEASE, release.id)
    assert KEY_611 not in remaining, "v=6.1.0 must be wiped after finish_run"
    assert KEY_ALL not in remaining, "aggregate must be wiped after finish_run"
    assert KEY_IMG not in remaining, "v=6.1.0+image combo must be wiped (same version prefix)"
    assert KEY_620 in remaining,     "v=6.2.0 must survive — unrelated version"

    clear(SnapshotScope.RELEASE, release.id)


@pytest.mark.docker_required
def test_finish_run_wipes_version_and_aggregate_for_containing_view(
    argus_db, fake_test, client_service, view_with_test
):
    seed(SnapshotScope.VIEW, view_with_test.id, KEY_611, KEY_620, KEY_ALL)

    run_type, run_req = get_fake_test_run(fake_test)
    client_service.submit_run(run_type, asdict(run_req))
    client_service.submit_product_version(run_type, run_req.run_id, "6.1.0")
    client_service.finish_run(run_type, run_req.run_id)

    remaining = live_keys(SnapshotScope.VIEW, view_with_test.id)
    assert KEY_611 not in remaining, "view v=6.1.0 must be wiped"
    assert KEY_ALL not in remaining, "view aggregate must be wiped"
    assert KEY_620 in remaining,     "view v=6.2.0 must survive"


@pytest.mark.docker_required
def test_finish_run_does_not_touch_unrelated_view(
    argus_db, fake_test, client_service, release, unrelated_view
):
    seed(SnapshotScope.VIEW, unrelated_view.id, KEY_611, KEY_620, KEY_ALL)

    run_type, run_req = get_fake_test_run(fake_test)
    client_service.submit_run(run_type, asdict(run_req))
    client_service.submit_product_version(run_type, run_req.run_id, "6.1.0")
    client_service.finish_run(run_type, run_req.run_id)

    remaining = live_keys(SnapshotScope.VIEW, unrelated_view.id)
    assert KEY_611 in remaining, "unrelated view v=6.1.0 must not be touched"
    assert KEY_ALL in remaining, "unrelated view aggregate must not be touched"
    assert KEY_620 in remaining, "unrelated view v=6.2.0 must not be touched"

    clear(SnapshotScope.RELEASE, release.id)


# ---------------------------------------------------------------------------
# Section 3 — invalidate_release_snapshots (structural events)
#
# Full wipe for the release scope AND full wipe for every view that covers it
# (via test membership or release_ids).
# ---------------------------------------------------------------------------

@pytest.mark.docker_required
def test_invalidate_release_snapshots_wipes_all_release_keys(
    argus_db, release
):
    from argus.backend.service.stats_snapshot import invalidate_release_snapshots
    seed(SnapshotScope.RELEASE, release.id, KEY_611, KEY_620, KEY_ALL, KEY_IMG)

    invalidate_release_snapshots(release.id)

    assert live_keys(SnapshotScope.RELEASE, release.id) == set(), \
        "all release snapshot keys must be gone after structural invalidation"


@pytest.mark.docker_required
def test_invalidate_release_snapshots_wipes_view_containing_test_from_release(
    argus_db, release, view_with_test
):
    from argus.backend.service.stats_snapshot import invalidate_release_snapshots
    seed(SnapshotScope.VIEW, view_with_test.id, KEY_611, KEY_620, KEY_ALL)

    invalidate_release_snapshots(release.id)

    assert live_keys(SnapshotScope.VIEW, view_with_test.id) == set(), \
        "view covering a test from the release must be fully wiped"


@pytest.mark.docker_required
def test_invalidate_release_snapshots_wipes_view_by_release_ids_membership(
    argus_db, release, view_with_release
):
    from argus.backend.service.stats_snapshot import invalidate_release_snapshots
    seed(SnapshotScope.VIEW, view_with_release.id, KEY_611, KEY_ALL)

    invalidate_release_snapshots(release.id)

    assert live_keys(SnapshotScope.VIEW, view_with_release.id) == set(), \
        "view with release in release_ids must be wiped even with no explicit tests"


@pytest.mark.docker_required
def test_invalidate_release_snapshots_does_not_touch_unrelated_release(
    argus_db, release, second_release
):
    from argus.backend.service.stats_snapshot import invalidate_release_snapshots
    seed(SnapshotScope.RELEASE, second_release.id, KEY_611, KEY_ALL)

    invalidate_release_snapshots(release.id)

    remaining = live_keys(SnapshotScope.RELEASE, second_release.id)
    assert KEY_611 in remaining, "other release v=6.1.0 must not be touched"
    assert KEY_ALL in remaining, "other release aggregate must not be touched"

    clear(SnapshotScope.RELEASE, second_release.id)


@pytest.mark.docker_required
def test_invalidate_release_snapshots_does_not_touch_unrelated_view(
    argus_db, release, unrelated_view
):
    from argus.backend.service.stats_snapshot import invalidate_release_snapshots
    seed(SnapshotScope.VIEW, unrelated_view.id, KEY_611, KEY_ALL)

    invalidate_release_snapshots(release.id)

    remaining = live_keys(SnapshotScope.VIEW, unrelated_view.id)
    assert KEY_611 in remaining, "unrelated view v=6.1.0 must not be touched"
    assert KEY_ALL in remaining, "unrelated view aggregate must not be touched"


# ---------------------------------------------------------------------------
# Section 4 — update_view
#
# Full wipe of the updated view's snapshot partition; other views untouched.
# ---------------------------------------------------------------------------

@pytest.mark.docker_required
def test_update_view_wipes_all_view_snapshots(
    argus_db, fake_test, view_with_test, user_view_service
):
    # Also seed a widget variant to prove full wipe (not version-scoped)
    seed(SnapshotScope.VIEW, view_with_test.id, KEY_611, KEY_620, KEY_ALL)
    seed(SnapshotScope.VIEW, view_with_test.id, KEY_611, variant_key="widget:0")

    user_view_service.update_view(view_with_test.id, {
        "name": view_with_test.name,
        "display_name": view_with_test.display_name,
        "description": view_with_test.description,
        "widget_settings": "[]",
        "plan_id": None,
        "items": [f"test:{fake_test.id}"],
    })

    assert live_keys(SnapshotScope.VIEW, view_with_test.id) == set(), \
        "all view snapshot keys must be gone after update_view"


@pytest.mark.docker_required
def test_update_view_does_not_touch_other_views(
    argus_db, fake_test, view_with_test, unrelated_view, user_view_service
):
    seed(SnapshotScope.VIEW, unrelated_view.id, KEY_611, KEY_ALL)

    user_view_service.update_view(view_with_test.id, {
        "name": view_with_test.name,
        "display_name": view_with_test.display_name,
        "description": view_with_test.description,
        "widget_settings": "[]",
        "plan_id": None,
        "items": [f"test:{fake_test.id}"],
    })

    remaining = live_keys(SnapshotScope.VIEW, unrelated_view.id)
    assert KEY_611 in remaining, "unrelated view v=6.1.0 must not be touched by update_view"
    assert KEY_ALL in remaining, "unrelated view aggregate must not be touched by update_view"


# ---------------------------------------------------------------------------
# Section 5 — refresh_stale_view
#
# Same contract as update_view: full wipe of the refreshed view, others intact.
# ---------------------------------------------------------------------------

@pytest.mark.docker_required
def test_refresh_stale_view_wipes_all_view_snapshots(
    argus_db, view_with_test, user_view_service
):
    seed(SnapshotScope.VIEW, view_with_test.id, KEY_611, KEY_620, KEY_ALL)
    seed(SnapshotScope.VIEW, view_with_test.id, KEY_611, variant_key="widget:0")

    user_view_service.refresh_stale_view(view_with_test)

    assert live_keys(SnapshotScope.VIEW, view_with_test.id) == set(), \
        "all view snapshot keys must be gone after refresh_stale_view"


@pytest.mark.docker_required
def test_refresh_stale_view_does_not_touch_other_views(
    argus_db, view_with_test, unrelated_view, user_view_service
):
    seed(SnapshotScope.VIEW, unrelated_view.id, KEY_611, KEY_ALL)

    user_view_service.refresh_stale_view(view_with_test)

    remaining = live_keys(SnapshotScope.VIEW, unrelated_view.id)
    assert KEY_611 in remaining, "unrelated view v=6.1.0 must not be touched by refresh_stale_view"
    assert KEY_ALL in remaining, "unrelated view aggregate must not be touched by refresh_stale_view"
