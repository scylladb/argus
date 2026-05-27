"""Unit tests for the build-id parser in
:mod:`argus.backend.service.test_hierarchy`.

Only ``parse_build_id`` is exercised here -- the row-creation helpers require
a live ScyllaDB and are covered by integration tests.
"""
from __future__ import annotations

import pytest

from argus.backend.service.test_hierarchy import UNTRACKED, parse_build_id


@pytest.mark.parametrize(
    "build_id, expected",
    [
        # Three or more segments: release / group / test.
        ("scylla-staging/dusan/longevity-10gb-3h-gce-test",
         ("scylla-staging", "dusan", "longevity-10gb-3h-gce-test")),

        # Deeper nesting: middle segments are joined with '-'.
        ("scylla-master/teamA/longevity/nightly",
         ("scylla-master", "teamA-longevity", "nightly")),

        # Exactly two segments: group falls back to "<release>-root" so it
        # mirrors the Jenkins monitor's root-folder naming.
        ("scylla-master/perf-regression",
         ("scylla-master", "scylla-master-root", "perf-regression")),

        # Single segment: both release and group become the untracked
        # sentinel so the orphan is still navigable in the UI.
        ("solo-test",
         (UNTRACKED, UNTRACKED, "solo-test")),

        # Leading/trailing slashes are stripped before parsing.
        ("/scylla-staging/dusan/longevity/",
         ("scylla-staging", "dusan", "longevity")),

        # Empty string falls back to the untracked sentinels.
        ("", (UNTRACKED, UNTRACKED, UNTRACKED)),

        # Repeated slashes collapse to single segments (no empty group).
        ("scylla-staging//longevity",
         ("scylla-staging", "scylla-staging-root", "longevity")),
    ],
)
def test_parse_build_id(build_id: str, expected: tuple[str, str, str]) -> None:
    assert parse_build_id(build_id) == expected
