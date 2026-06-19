"""Generic stats snapshot store for release and view scopes.

Provides get/put/invalidate helpers keyed by (scope_type, scope_id, filter_key, variant_key).
Both ReleaseStatsCollector and ViewStatsCollector use this module.

The legacy ReleaseStatsSnapshot table is kept intact for Phase A; release stats still
read/write it directly.  This module serves the *view* scope in Phase A and will absorb
the release scope in Phase B (B4).

A6 instrumentation
-------------------
Metrics are emitted via the standard Python logging module at DEBUG level with a
structured prefix so they can be parsed by log aggregation tooling:

  [stats_snapshot.metric] views_scanned=<int> views_affected=<int>
  [stats_snapshot.metric] cache_hit scope_type=view scope_id=<uuid> key_class=<aggregate|version|widget>
  [stats_snapshot.metric] cache_miss scope_type=view scope_id=<uuid> key_class=<aggregate|version|widget>

Decision gate (scan → reverse-index table):
  If log aggregation shows that views_scanned grows materially under production ingest,
  build the test_id → view_ids reverse-index table (constant-time lookup, cost
  amortised to rare view edits). Otherwise keep the scan.
  Track per-key-class hit rate to identify the broad-view aggregate ceiling.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from uuid import UUID

from flask import current_app

from argus.backend.models.web import ArgusTest, ArgusUserView, ReleaseStatsSnapshot, StatsSnapshot

LOGGER = logging.getLogger(__name__)
_METRIC_LOGGER = logging.getLogger("stats_snapshot.metric")

SCOPE_RELEASE = "release"
SCOPE_VIEW = "view"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _key_class(filter_key: str, variant_key: str) -> str:
    """Classify a (filter_key, variant_key) pair for hit-rate tracking."""
    if variant_key:
        return "widget"
    if filter_key.startswith("v=::"):
        return "aggregate"
    return "version"


def _version_prefix(version: str | None) -> str:
    return f"v={version or ''}::"


# ---------------------------------------------------------------------------
# Read / write
# ---------------------------------------------------------------------------

def get_snapshot(scope_type: str, scope_id: UUID, filter_key: str, variant_key: str = "") -> dict | None:
    """Return parsed payload dict on hit, None on miss."""
    klass = _key_class(filter_key, variant_key)
    try:
        row = StatsSnapshot.get(scope_type=scope_type, scope_id=scope_id,
                                filter_key=filter_key, variant_key=variant_key)
        _METRIC_LOGGER.debug(
            "[stats_snapshot.metric] cache_hit scope_type=%s scope_id=%s key_class=%s",
            scope_type, scope_id, klass,
        )
        return json.loads(row.payload)
    except StatsSnapshot.DoesNotExist:
        _METRIC_LOGGER.debug(
            "[stats_snapshot.metric] cache_miss scope_type=%s scope_id=%s key_class=%s",
            scope_type, scope_id, klass,
        )
        return None
    except Exception:
        LOGGER.warning("Failed to read stats snapshot (%s, %s)", scope_type, scope_id, exc_info=True)
        return None


def put_snapshot(scope_type: str, scope_id: UUID, filter_key: str, result: dict, variant_key: str = "") -> None:
    """Serialize *result* and write it to the snapshot store.  Swallows write failures."""
    try:
        payload = current_app.json.dumps(result)
        StatsSnapshot.create(
            scope_type=scope_type,
            scope_id=scope_id,
            filter_key=filter_key,
            variant_key=variant_key,
            payload=payload,
            generated_at=datetime.now(UTC),
        )
    except Exception:
        LOGGER.warning("Failed to write stats snapshot (%s, %s)", scope_type, scope_id, exc_info=True)


# ---------------------------------------------------------------------------
# Invalidation
# ---------------------------------------------------------------------------

def invalidate_scope(scope_type: str, scope_id: UUID) -> None:
    """Full-partition wipe: drop all snapshots for a scope.

    Use for structural changes (view updated, tests added/removed, group toggled).
    """
    try:
        for row in StatsSnapshot.filter(scope_type=scope_type, scope_id=scope_id).all():
            row.delete()
    except Exception:
        LOGGER.warning("Failed to wipe snapshot partition (%s, %s)", scope_type, scope_id, exc_info=True)


def invalidate_version_scoped(scope_type: str, scope_id: UUID, version: str | None) -> None:
    """Version-scoped delete: remove rows whose filter_key starts with v=<version>::
    and the all-versions aggregate (v=::).

    Use on run lifecycle events (submit_run / finish_run).
    """
    try:
        version_prefix = _version_prefix(version)
        aggregate_prefix = "v=::"
        for row in StatsSnapshot.filter(scope_type=scope_type, scope_id=scope_id).all():
            if row.filter_key.startswith(version_prefix) or row.filter_key.startswith(aggregate_prefix):
                row.delete()
    except Exception:
        LOGGER.warning("Failed to invalidate version-scoped snapshot (%s, %s, v=%s)",
                       scope_type, scope_id, version, exc_info=True)


def affected_view_ids(test_ids: set[UUID]) -> set[UUID]:
    """Return the set of ArgusUserView ids whose test set intersects *test_ids*.

    v1: linear scan over all views.  Acceptable at current view counts.

    A6 instrumentation: logs views_scanned and views_affected so log aggregation
    can determine whether the reverse-index upgrade threshold is met.

    Decision gate: if the scan becomes a material write-path cost under production
    ingest (determined by log analysis, not inline timing), build the
    test_id → view_ids reverse-index table for constant-time lookup.
    """
    if not test_ids:
        return set()
    try:
        result: set[UUID] = set()
        scanned = 0
        for view in ArgusUserView.filter().all():
            scanned += 1
            if set(view.tests) & test_ids:
                result.add(view.id)
        _METRIC_LOGGER.debug(
            "[stats_snapshot.metric] views_scanned=%d views_affected=%d",
            scanned, len(result),
        )
        return result
    except Exception:
        LOGGER.warning("Failed to compute affected_view_ids for test_ids=%s", test_ids, exc_info=True)
        return set()


def invalidate_release_snapshots(release_id: UUID) -> None:
    """Full-partition delete of all ReleaseStatsSnapshot rows for a release.

    Also performs a full-partition wipe of StatsSnapshot rows for every view
    that covers this release (structural/metadata changes).

    Use for structural changes that affect all filter combinations (admin edits,
    group/test toggles, issue/comment/plan mutations).  Version-scoped invalidation
    in PluginModelBase.invalidate_release_snapshot() is used only for run lifecycle
    events (submit/finish).
    """
    try:
        for snapshot in ReleaseStatsSnapshot.filter(release_id=release_id).all():
            snapshot.delete()
    except Exception:
        LOGGER.warning("Failed to invalidate release snapshots for %s", release_id, exc_info=True)

    # Structural event: expand release_id → test ids for precise matching,
    # and also cover views that list this release directly in release_ids.
    try:
        release_tests = {t.id for t in ArgusTest.filter(release_id=release_id).all()}
        view_ids = affected_view_ids(release_tests)
        for view in ArgusUserView.filter().all():
            if release_id in (view.release_ids or []):
                view_ids.add(view.id)
        for vid in view_ids:
            invalidate_scope(SCOPE_VIEW, vid)
    except Exception:
        LOGGER.warning(
            "Failed to invalidate view snapshots for release %s", release_id, exc_info=True
        )
