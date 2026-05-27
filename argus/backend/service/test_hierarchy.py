"""Resolve or auto-create the ArgusRelease / ArgusGroup / ArgusTest hierarchy
needed by ``PluginModelBase.assign_categories``.

The build_id stored on every run is the Jenkins job path (e.g.
``scylla-staging/dusan/longevity-10gb-3h-gce-test``). When a run is submitted
against an Argus instance that has not been pre-populated by the Jenkins
monitor (``argus/backend/service/build_system_monitor.py``), the matching
``ArgusTest`` row is missing and ``test_id`` ends up empty on the run --
which then breaks every subsequent ``submit_results`` (whose C* partition key
is ``test_id``).

``ensure_test_hierarchy`` parses the build_id and idempotently creates the
release / group / test triple so the next ``assign_categories`` call resolves
``test_id`` correctly. It is intended to be opted into by the replay-ingest
endpoint (``?create_missing_tests=true``) and is safe to call on every
submit_run record.
"""
from __future__ import annotations

import logging

from argus.backend.models.web import (
    ArgusRelease,
    ArgusGroup,
    ArgusTest,
    ArgusTestException,
)

LOGGER = logging.getLogger(__name__)

# Sentinel name used when a build_id has only one path segment and we have
# nowhere to derive a meaningful release / group from. Keeps every "orphan"
# build in a single, easily findable bucket.
UNTRACKED = "untracked"


def parse_build_id(build_id: str) -> tuple[str, str, str]:
    """Split ``build_id`` into ``(release_name, group_name, test_name)``.

    ``build_id`` is the Jenkins job path. The mapping mirrors the
    folder layout the Jenkins monitor uses:

    * ``release/group/test``           -> as written
    * ``release/test``                 -> group becomes ``"<release>-root"``
                                          (matches the root-folder convention
                                          in :class:`JenkinsMonitor`)
    * ``test`` (no slash)              -> both release and group become
                                          ``UNTRACKED`` so the orphan run is
                                          still navigable.
    * ``release/folder/sub/.../test``  -> middle segments are joined with
                                          ``-`` to form the group name; the
                                          first segment is the release and the
                                          last is the test.

    Empty segments produced by leading/trailing slashes are stripped.
    """
    if not build_id:
        return (UNTRACKED, UNTRACKED, UNTRACKED)

    parts = [p for p in build_id.strip("/").split("/") if p]
    if not parts:
        return (UNTRACKED, UNTRACKED, UNTRACKED)
    if len(parts) == 1:
        return (UNTRACKED, UNTRACKED, parts[0])
    if len(parts) == 2:
        return (parts[0], f"{parts[0]}-root", parts[1])

    release = parts[0]
    test = parts[-1]
    group = "-".join(parts[1:-1])
    return (release, group, test)


def _get_or_create_release(name: str) -> ArgusRelease:
    try:
        return ArgusRelease.get(name=name)
    except ArgusRelease.DoesNotExist:
        release = ArgusRelease()
        release.name = name
        release.save()
        LOGGER.info("Auto-created ArgusRelease %s", name)
        return release


def _get_or_create_group(release: ArgusRelease, name: str, build_system_id: str) -> ArgusGroup:
    # ArgusGroup has no unique constraint on (release_id, name), so we look up
    # by build_system_id which is the stable identifier from Jenkins.
    for g in ArgusGroup.filter(release_id=release.id).all():
        if g.build_system_id == build_system_id:
            return g
    group = ArgusGroup()
    group.release_id = release.id
    group.name = name
    group.build_system_id = build_system_id
    group.save()
    LOGGER.info("Auto-created ArgusGroup %s (release=%s)", name, release.name)
    return group


def _get_or_create_test(
    release: ArgusRelease,
    group: ArgusGroup,
    name: str,
    build_system_id: str,
    build_system_url: str | None,
    plugin_name: str | None,
) -> ArgusTest:
    try:
        return ArgusTest.get(build_system_id=build_system_id)
    except ArgusTest.DoesNotExist:
        test = ArgusTest()
        test.name = name
        test.group_id = group.id
        test.release_id = release.id
        test.build_system_id = build_system_id
        if build_system_url:
            test.build_system_url = build_system_url
        if plugin_name:
            test.plugin_name = plugin_name
        try:
            test.validate_build_system_id()
        except ArgusTestException:
            # Race: another process created the row between our get() and
            # save(). Re-fetch and return that one.
            return ArgusTest.get(build_system_id=build_system_id)
        test.save()
        LOGGER.info("Auto-created ArgusTest %s (build_id=%s)", name, build_system_id)
        return test


def ensure_test_hierarchy(
    build_id: str,
    build_url: str | None = None,
    plugin_name: str | None = None,
) -> ArgusTest:
    """Idempotently ensure the release/group/test row triple exists.

    Returns the resolved or freshly-created :class:`ArgusTest`. Safe to call
    repeatedly for the same ``build_id``.
    """
    release_name, group_name, test_name = parse_build_id(build_id)

    # Group's build_system_id is the release/.../middle path (everything but
    # the trailing test segment) so the same group is reused across the
    # release.
    parts = [p for p in build_id.strip("/").split("/") if p]
    if len(parts) >= 2:
        group_build_id = "/".join(parts[:-1])
    else:
        group_build_id = release_name

    release = _get_or_create_release(release_name)
    group = _get_or_create_group(release, group_name, group_build_id)
    return _get_or_create_test(release, group, test_name, build_id, build_url, plugin_name)
