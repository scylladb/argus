from dataclasses import dataclass
import subprocess
import json
import logging
import datetime
from types import NoneType
from uuid import UUID
from coodie.exceptions import DocumentNotFound

from argus.backend.db import ScyllaCluster
from argus.backend.util.config import Config
from argus.backend.models.plan import ArgusReleasePlan
from argus.backend.plugins.core import PluginModelBase
from argus.backend.plugins.loader import AVAILABLE_PLUGINS, all_plugin_models
from argus.backend.plugins.sct.testrun import SCTTestRun
from argus.backend.service.notification_manager import NotificationManagerService
from argus.backend.models.web import (
    ArgusRelease,
    ArgusGroup,
    ArgusTest,
    ArgusTestRunComment,
    ArgusEvent,
    ReleasePlannerComment,
    User,
)
from argus.backend.events.event_processors import EVENT_PROCESSORS
from argus.backend.service.planner_service import PlanningService
from argus.backend.util.common import chunk

LOGGER = logging.getLogger(__name__)


@dataclass(init=True, frozen=True)
class ScheduleUpdateRequest:
    release_id: UUID
    schedule_id: UUID
    assignee: UUID
    new_tests: list[UUID]
    old_tests: list[UUID]
    comments: dict[UUID, str]


class ArgusService:
    def __init__(self, database_session=None):
        self.session = database_session if database_session else ScyllaCluster.get_session()
        self.database = ScyllaCluster.get()
        self.notification_manager = NotificationManagerService()
        self.build_id_and_url_statement = self.database.prepare(
            f"SELECT build_id, build_job_url, test_id FROM {SCTTestRun.table_name()} WHERE id = ?"
        )  # TODO: transfer to PluginModelBase
        self.scylla_versions_by_release = self.database.prepare(
            f"SELECT scylla_version FROM {SCTTestRun.table_name()} WHERE release_id = ?"
        )  # TODO: Moved to PluginModelBase

    def get_version(self) -> str:
        try:
            proc = subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True)
        except subprocess.CalledProcessError:
            proc = None
        if proc:
            return proc.stdout.decode(encoding="utf-8").strip()
        else:
            try:
                with open("./.argus_version", 'rt', encoding="utf-8") as version_file:
                    version = version_file.read().strip()
                return version
            except FileNotFoundError:
                return "version_unknown"

    def create_release(self, payload: dict) -> dict:
        response = {}
        for release_name in payload:
            try:
                ArgusRelease.get(name=release_name)
                response[release_name] = {
                    "status": "error",
                    "message": f"Release {release_name} already exists"
                }
                continue
            except DocumentNotFound:
                pass

            new_release = ArgusRelease.model_construct()
            new_release.name = release_name
            new_release.save()
            response[release_name] = {}
            response[release_name]["groups"] = self.create_groups(
                groups=payload[release_name]["groups"],
                parent_release_id=new_release.id
            )

        return response

    def create_groups(self, groups: dict, parent_release_id) -> dict:
        response = {}
        for group_name, group_definition in groups.items():
            new_group = ArgusGroup.model_construct()
            new_group.release_id = parent_release_id
            new_group.name = group_name
            new_group.pretty_name = group_definition.get("pretty_name")
            new_group.save()
            response[group_name] = {}
            response[group_name]["status"] = "created"
            response[group_name]["tests"] = self.create_tests(
                tests=group_definition.get("tests", []),
                parent_group_id=new_group.id,
                parent_release_id=parent_release_id
            )
        return response

    def create_tests(self, tests: dict, parent_group_id: UUID, parent_release_id: UUID) -> dict:
        response = {}

        for test_name in tests:
            new_test = ArgusTest.model_construct()
            new_test.release_id = parent_release_id
            new_test.group_id = parent_group_id
            new_test.name = test_name
            new_test.save()
            response[test_name] = "created"

        return response

    def get_comment(self, comment_id: UUID) -> ArgusTestRunComment | None:
        try:
            return ArgusTestRunComment.get(id=comment_id)
        except DocumentNotFound:
            return None

    def get_releases(self):
        releases = list(ArgusRelease.find().all())
        releases = sorted(releases, key=lambda r: r.name)
        releases = sorted(releases, key=lambda r: r.dormant)
        return releases

    def get_groups(self, release_id: UUID) -> list[ArgusGroup]:
        groups = list(ArgusGroup.find(release_id=release_id).all())
        return sorted(groups, key=lambda g: g.pretty_name if g.pretty_name else g.name)

    def get_tests(self, group_id: UUID) -> list[ArgusTest]:
        return list(ArgusTest.find(group_id=group_id).all())

    def get_test_info(self, test_id: UUID) -> dict:
        test = ArgusTest.get(id=test_id)
        group = ArgusGroup.get(id=test.group_id)
        release = ArgusRelease.get(id=test.release_id)
        return {
            "test": test.model_dump(),
            "group": group.model_dump(),
            "release": release.model_dump(),
        }

    def get_data_for_release_dashboard(self, release_name: str):
        release = ArgusRelease.get(name=release_name)
        release_groups = ArgusGroup.find(release_id=release.id).all()
        release_tests = ArgusTest.find(release_id=release.id).all()

        return release, release_groups, release_tests

    def get_distinct_release_versions(self, release_id: UUID | str) -> list[str]:
        release_id = UUID(release_id) if isinstance(release_id, str) else release_id
        release = ArgusRelease.get(id=release_id)
        unique_versions = {ver for plugin in all_plugin_models()
                           for ver in plugin.get_distinct_product_versions(release=release)}

        return sorted(list(unique_versions), reverse=True)

    def get_distinct_release_images(self, release_id: UUID | str) -> list[str]:
        release_id = UUID(release_id) if isinstance(release_id, str) else release_id
        release = ArgusRelease.get(id=release_id)
        images = AVAILABLE_PLUGINS["scylla-cluster-tests"].model.get_distinct_cloud_images_for_release(release)

        return images

    def fetch_release_activity(self, release_name: str) -> dict:
        response = {}
        release = ArgusRelease.get(name=release_name)
        all_events = ArgusEvent.find(release_id=release.id).all()
        all_events = sorted(all_events, key=lambda ev: ev.created_at)
        response["release_id"] = release.id
        response["raw_events"] = [event.model_dump() for event in all_events]
        response["events"] = {str(event.id): EVENT_PROCESSORS.get(
            event.kind)(json.loads(event.body)) for event in all_events}
        return response

    # TODO: Remove - legacy scheduling, superseded by release planner
    def assign_runs_for_scheduled_test(self, schedule, test_id: UUID, new_assignee: UUID):
        """Legacy scheduling removed - kept as a stub for API compatibility."""
        return None

    # TODO: Remove - legacy scheduling, superseded by release planner
    def assign_runs_for_scheduled_group(self, schedule, group_id: UUID, new_assignee: UUID):
        """Legacy scheduling removed - kept as a stub for API compatibility."""
        return None

    # TODO: Remove - legacy scheduling, superseded by release planner
    def submit_new_schedule(self, release: str | UUID, start_time: str, end_time: str, tests: list[str | UUID],
                            groups: list[str | UUID], assignees: list[str | UUID], tag: str, comments: dict[str, str] | None, group_ids: dict[str, str] | None) -> dict:
        """Legacy scheduling removed - kept as a stub for API compatibility."""
        return {}

    # TODO: Remove - legacy scheduling, superseded by release planner
    def get_schedules_for_release(self, release_id: str | UUID) -> dict:
        """Legacy scheduling removed - kept as a stub for API compatibility."""
        return {"schedules": []}

    # TODO: Remove - legacy scheduling, superseded by release planner
    def update_schedule_assignees(self, payload: dict) -> dict:
        """Legacy scheduling removed - kept as a stub for API compatibility."""
        return {}

    # TODO: Remove - legacy scheduling, superseded by release planner
    def update_schedule_comment(self, payload: dict) -> dict:
        new_comment = payload.get("newComment")
        release_id = payload.get("releaseId")
        group_id = payload.get("groupId")
        test_id = payload.get("testId")

        if not release_id:
            raise Exception("No release provided")
        if not group_id:
            raise Exception("No group provided")
        if not test_id:
            raise Exception("No test provided")

        if isinstance(new_comment, NoneType):
            raise Exception("No comment provided in the body of request")

        release_id = UUID(release_id) if isinstance(release_id, str) else release_id
        group_id = UUID(group_id) if isinstance(group_id, str) else group_id
        test_id = UUID(test_id) if isinstance(test_id, str) else test_id
        try:
            comment = ReleasePlannerComment.get(release=release_id, group=group_id, test=test_id)
        except DocumentNotFound:
            comment = ReleasePlannerComment(release=release_id, group=group_id, test=test_id)

        comment.comment = new_comment
        comment.save()

        return {
            "releaseId": release_id,
            "groupId": group_id,
            "testId": test_id,
            "newComment": new_comment,
        }

    # TODO: Remove - legacy scheduling, superseded by release planner
    def update_schedule(self, release_id: UUID | str, schedule_id: UUID | str, old_tests: list[UUID | str], new_tests: list[UUID | str], comments: dict[str, str], assignee: UUID | str):
        """Legacy scheduling removed - kept as a stub for API compatibility."""
        return True

    # TODO: Remove - legacy scheduling, superseded by release planner
    def delete_schedule(self, payload: dict) -> dict:
        """Legacy scheduling removed - kept as a stub for API compatibility."""
        return {}

    def get_planner_data(self, release_id: UUID | str) -> dict:

        release_id = UUID(release_id) if isinstance(release_id, str) else release_id
        release = ArgusRelease.get(id=release_id)
        release_comments = list(ReleasePlannerComment.find(release=release.id).all())
        groups = ArgusGroup.find(release_id=release.id).all()
        groups_by_group_id = {str(group.id): group.model_dump() for group in groups if group.enabled}
        tests = ArgusTest.find(release_id=release.id).all()
        tests = [t.model_dump() for t in tests if t.enabled]
        tests_by_group = {}
        for test in tests:
            group = groups_by_group_id.get(str(test["group_id"]))
            if not group:
                continue
            test["group_name"] = group["name"]
            test["pretty_group_name"] = groups_by_group_id[str(test["group_id"])]["pretty_name"]
            try:
                comment = next(filter(lambda c: c.test == test["id"], release_comments))
            except StopIteration:
                comment = None
            test["comment"] = comment.comment if comment else ""
            group_tests = tests_by_group.get(test["group_name"], [])
            group_tests.append(test)
            tests_by_group[test["group_name"]] = group_tests

        response = {
            "release": release.model_dump(),
            "groups": groups_by_group_id,
            "tests": tests,
            "tests_by_group": tests_by_group,
        }

        return response

    # TODO: Remove - legacy scheduling, superseded by release planner
    def _batch_get_schedules_from_ids(self, release_id: UUID, schedule_ids: list[UUID]) -> list:
        """Legacy scheduling removed - kept as a stub for API compatibility."""
        return []

    def get_groups_assignees(self, release_id: UUID | str, version: str = None, plan_id: UUID = None):
        release_id = UUID(release_id) if isinstance(release_id, str) else release_id
        release = ArgusRelease.get(id=release_id)
        if assignments := PlanningService().get_assignments_for_groups(release_id, version, plan_id):
            return assignments

        # Legacy scheduling removed - no fallback source of assignments.
        return {}

    def get_tests_assignees(self, group_id: UUID | str, version: str = None, plan_id: UUID = None):
        group_id = UUID(group_id) if isinstance(group_id, str) else group_id
        group = ArgusGroup.get(id=group_id)

        release = ArgusRelease.get(id=group.release_id)
        if assignments := PlanningService().get_assignments_for_tests(group_id, version, plan_id):
            return assignments

        # Legacy scheduling removed - no fallback source of assignments.
        return {}

    def get_jobs_for_user(self, user: User):
        today = datetime.datetime.now()
        validity_period = today - datetime.timedelta(days=Config.load_yaml_config().get("JOB_VALIDITY_PERIOD_DAYS", 30))
        for plugin in all_plugin_models():
            for run in plugin.get_jobs_assigned_to_user(user_id=user.id):
                if run["start_time"] >= validity_period:
                    yield run

    def get_planned_jobs_for_user(self, user: User):
        owned_plans = list(ArgusReleasePlan.find(owner=user.id).allow_filtering().all())
        participating_plans = list(ArgusReleasePlan.find(participants__contains=user.id).allow_filtering().all())
        unique_plans: list[ArgusReleasePlan] = list({plan for plan in [*owned_plans, *participating_plans]})

        user_jobs = []
        for plan in unique_plans:
            if plan.owner == user.id:
                jobs = filter(lambda test: not plan.assignee_mapping.get(test) or plan.assignee_mapping.get(test) == user.id, plan.tests)
                user_jobs.extend(jobs)
            if user.id in plan.participants:
                jobs = filter(lambda test: plan.assignee_mapping.get(test) == user.id, plan.tests)
                user_jobs.extend(jobs)
        resolved: list[ArgusTest] = []
        for batch in chunk(set(user_jobs)):
            resolved.extend(ArgusTest.find(id__in=batch).all())

        last_runs: dict[UUID, PluginModelBase] = {}
        for test in resolved:
            try:
                if not test.plugin_name:
                    last_runs[test.id] = None
                    continue
                last_runs[test.id] = AVAILABLE_PLUGINS[test.plugin_name].model.find(build_id=test.build_system_id).limit(1).first()
            except DocumentNotFound:
                last_runs[test.id] = None

        return [{**test.model_dump(), "last_run": last_runs.get(test.id)} for test in resolved if test.enabled]

    # TODO: Remove - legacy scheduling, superseded by release planner
    def get_schedules_for_user(self, user: User) -> list[dict]:
        """Legacy scheduling removed - kept as a stub for API compatibility."""
        return []

    def get_planner_comment_by_test(self, test_id):
        try:
            test = ArgusTest.get(id=test_id)
            return ReleasePlannerComment.get(test=test.id, release=test.release_id, group=test.group_id).comment
        except DocumentNotFound:
            return ""
