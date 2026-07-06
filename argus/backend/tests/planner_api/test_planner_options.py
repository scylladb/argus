"""
Standalone tests for per-entity ``options`` on ``ArgusReleasePlan``.

Covers the JSON-text ``options`` column threaded through the planner service:
- ``create_plan`` persists options and they round-trip from the DB.
- ``update_plan`` applies ``options_set`` / ``options_remove`` diffs.
- options are pruned when their test/group leaves the plan.
- options are keyed by both test and group UUIDs.
- ``copy_plan`` remaps options onto the copied entities.
"""
import json
import time
import uuid

import pytest
from flask import g

from argus.backend.models.plan import ArgusReleasePlan
from argus.backend.service.planner_service import (
    CopyPlanPayload,
    PlanningService,
    TempPlanPayload,
)


@pytest.fixture
def planning_service():
    return PlanningService()


def _create_payload(release, tests=None, groups=None, options=None):
    suffix = uuid.uuid4().hex[:8]
    return {
        "name": f"options_plan_{suffix}",
        "description": "options test plan",
        "owner": str(g.user.id),
        "participants": [],
        "target_version": f"1.0.0-{suffix}",
        "release_id": str(release.id),
        "tests": [str(t) for t in (tests or [])],
        "groups": [str(gid) for gid in (groups or [])],
        "assignments": {},
        "options": options or {},
    }


@pytest.mark.docker_required
def test_create_plan_persists_options(planning_service, release, fake_test):
    labels = {str(fake_test.id): {"labels": ["alpha", "beta"]}}
    plan = planning_service.create_plan(
        _create_payload(release, tests=[fake_test.id], options=labels))

    stored = ArgusReleasePlan.get(id=plan.id)
    assert json.loads(stored.options) == labels


@pytest.mark.docker_required
def test_create_plan_defaults_to_empty_options(planning_service, release, fake_test):
    plan = planning_service.create_plan(_create_payload(release, tests=[fake_test.id]))

    stored = ArgusReleasePlan.get(id=plan.id)
    assert json.loads(stored.options) == {}


@pytest.mark.docker_required
def test_update_plan_sets_and_removes_options(planning_service, release, fake_test, group):
    plan = planning_service.create_plan(
        _create_payload(release, tests=[fake_test.id], groups=[group.id]))

    # Set options for both a test and a group (collision-free shared keyspace).
    planning_service.update_plan({
        "id": str(plan.id),
        "options_set": {
            str(fake_test.id): {"labels": ["needs-triage"]},
            str(group.id): {"labels": ["group-wide"]},
        },
    })
    stored = ArgusReleasePlan.get(id=plan.id)
    assert json.loads(stored.options) == {
        str(fake_test.id): {"labels": ["needs-triage"]},
        str(group.id): {"labels": ["group-wide"]},
    }

    # Remove the test's options; the group's options remain untouched.
    planning_service.update_plan({
        "id": str(plan.id),
        "options_remove": [str(fake_test.id)],
    })
    stored = ArgusReleasePlan.get(id=plan.id)
    assert json.loads(stored.options) == {str(group.id): {"labels": ["group-wide"]}}


@pytest.mark.docker_required
def test_update_plan_prunes_options_for_removed_entities(planning_service, release, fake_test, group):
    plan = planning_service.create_plan(
        _create_payload(
            release,
            tests=[fake_test.id],
            groups=[group.id],
            options={
                str(fake_test.id): {"labels": ["t"]},
                str(group.id): {"labels": ["g"]},
            },
        ))

    # Dropping the test from the plan prunes its options entry.
    planning_service.update_plan({
        "id": str(plan.id),
        "tests_remove": [str(fake_test.id)],
    })
    stored = ArgusReleasePlan.get(id=plan.id)
    assert json.loads(stored.options) == {str(group.id): {"labels": ["g"]}}

    # Dropping the group prunes the remaining entry.
    planning_service.update_plan({
        "id": str(plan.id),
        "groups_remove": [str(group.id)],
    })
    stored = ArgusReleasePlan.get(id=plan.id)
    assert json.loads(stored.options) == {}


@pytest.mark.docker_required
def test_copy_plan_remaps_options(planning_service, release_manager_service):
    ns = time.time_ns()
    # Source release/group/test with build ids that embed the release name, so
    # copy_plan can remap them onto the target release by substring replacement.
    src_release = release_manager_service.create_release(f"opt_src_{ns}", f"opt_src_{ns}", False)
    src_group = release_manager_service.create_group(
        f"g_{ns}", f"g_{ns}", build_system_id=f"{src_release.name}/g", release_id=str(src_release.id))
    src_test = release_manager_service.create_test(
        f"t_{ns}", f"t_{ns}", f"{src_release.name}/g/t", f"{src_release.name}/g/t",
        group_id=str(src_group.id), release_id=str(src_release.id),
        plugin_name="scylla-cluster-tests")

    source_options = {str(src_test.id): {"labels": ["carry-me"]}}
    plan = planning_service.create_plan(
        _create_payload(src_release, tests=[src_test.id], options=source_options))

    target_release = release_manager_service.create_release(f"opt_dst_{ns}", f"opt_dst_{ns}", False)
    target_group = release_manager_service.create_group(
        src_group.name, src_group.pretty_name,
        build_system_id=src_group.build_system_id.replace(src_release.name, target_release.name, 1),
        release_id=str(target_release.id))
    target_test = release_manager_service.create_test(
        src_test.name, src_test.pretty_name,
        src_test.build_system_id.replace(src_release.name, target_release.name, 1),
        src_test.build_system_url,
        group_id=str(target_group.id), release_id=str(target_release.id),
        plugin_name=src_test.plugin_name)

    temp_plan = TempPlanPayload(
        id=str(plan.id),
        name=f"copied_{ns}",
        completed=False,
        description="copied plan",
        owner=str(g.user.id),
        key=plan.key,
        participants=[],
        target_version=f"2.0.0-{ns}",
        assignee_mapping={},
        release_id=str(target_release.id),
        tests=[str(src_test.id)],
        groups=[],
        creation_time="",
        last_updated="",
        ends_at="",
        created_from=None,
    )
    payload = CopyPlanPayload(
        plan=temp_plan,
        keepParticipants=False,
        replacements={},
        targetReleaseId=str(target_release.id),
        targetReleaseName=target_release.name,
    )
    new_plan = planning_service.copy_plan(payload)

    stored = ArgusReleasePlan.get(id=new_plan.id)
    assert json.loads(stored.options) == {str(target_test.id): {"labels": ["carry-me"]}}
