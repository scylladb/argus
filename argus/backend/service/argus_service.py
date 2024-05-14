import subprocess
import json
import logging
import datetime
from types import NoneType
from uuid import UUID
from cassandra.util import uuid_from_time  # pylint: disable=no-name-in-module
from flask import current_app
from argus.backend.db import ScyllaCluster
from argus.backend.plugins.loader import AVAILABLE_PLUGINS, all_plugin_models
from argus.backend.plugins.sct.testrun import SCTTestRun
from argus.backend.service.notification_manager import NotificationManagerService
from argus.backend.models.web import (
    ArgusRelease,
    ArgusGroup,
    ArgusTest,
    ArgusSchedule,
    ArgusScheduleAssignee,
    ArgusScheduleGroup,
    ArgusScheduleTest,
    ArgusTestRunComment,
    ArgusEvent,
    ReleasePlannerComment,
    User,
)
from argus.backend.events.event_processors import EVENT_PROCESSORS
from argus.backend.service.testrun import TestRunService

LOGGER = logging.getLogger(__name__)


class ArgusService:
    # pylint: disable=no-self-use,too-many-arguments,too-many-instance-attributes,too-many-locals, too-many-public-methods
    def __init__(self, database_session=None):
        self.session = database_session if database_session else ScyllaCluster.get_session()
        self.database = ScyllaCluster.get()
        self.notification_manager = NotificationManagerService()
        self.github_headers = {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"token {current_app.config['GITHUB_ACCESS_TOKEN']}"
        }
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
            except ArgusRelease.DoesNotExist:
                pass

            new_release = ArgusRelease()
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
            new_group = ArgusGroup()
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
            new_test = ArgusTest()
            new_test.release_id = parent_release_id
            new_test.group_id = parent_group_id
            new_test.name = test_name
            new_test.save()
            response[test_name] = "created"

        return response

    def get_comment(self, comment_id: UUID) -> ArgusTestRunComment | None:
        try:
            return ArgusTestRunComment.get(id=comment_id)
        except ArgusTestRunComment.DoesNotExist:
            return None

    def get_releases(self):
        releases = list(ArgusRelease.all())
        releases = sorted(releases, key=lambda r: r.name)
        releases = sorted(releases, key=lambda r: r.dormant)
        return releases

    def get_groups(self, release_id: UUID) -> list[ArgusGroup]:
        groups = list(ArgusGroup.filter(release_id=release_id).all())
        return sorted(groups, key=lambda g: g.pretty_name if g.pretty_name else g.name)

    def get_groups_for_release(self, release: ArgusRelease):
        groups = ArgusGroup.filter(release_id=release.id).all()
        return sorted(groups, key=lambda g: g.pretty_name if g.pretty_name else g.name)

    def get_tests(self, group_id: UUID) -> list[ArgusTest]:
        return list(ArgusTest.filter(group_id=group_id).all())

    def get_test_info(self, test_id: UUID) -> dict:
        test = ArgusTest.get(id=test_id)
        group = ArgusGroup.get(id=test.group_id)
        release = ArgusRelease.get(id=test.release_id)
        return {
            "test": dict(test.items()),
            "group": dict(group.items()),
            "release": dict(release.items()),
        }

    def get_data_for_release_dashboard(self, release_name: str):
        release = ArgusRelease.get(name=release_name)
        release_groups = ArgusGroup.filter(release_id=release.id).all()
        release_tests = ArgusTest.filter(release_id=release.id).all()

        return release, release_groups, release_tests

    def get_distinct_release_versions(self, release_id: UUID | str) -> list[str]:
        release_id = UUID(release_id) if isinstance(release_id, str) else release_id
        release = ArgusRelease.get(id=release_id)
        unique_versions = {ver for plugin in all_plugin_models()
                           for ver in plugin.get_distinct_product_versions(release=release)}

        return sorted(list(unique_versions), reverse=True)

    def poll_test_runs(self, test_id: UUID, additional_runs: list[UUID], limit: int = 10):
        test: ArgusTest = ArgusTest.get(id=test_id)

        rows: list[SCTTestRun] = list(SCTTestRun.filter(build_id=test.build_system_id).all().limit(limit))

        rows_ids = [row.id for row in rows]

        for run_id in additional_runs:
            if run_id not in rows_ids:
                row: SCTTestRun = SCTTestRun.get(id=run_id)
                rows.append(row)

        for row in rows:
            try:
                setattr(row, "build_number", int(row["build_job_url"].rstrip("/").split("/")[-1]))
            except ValueError:
                setattr(row, "build_number", -1)

        return sorted(rows, reverse=True, key=lambda r: r.build_number)

    def poll_test_runs_single(self, runs: list[UUID]):
        rows: list[SCTTestRun] = []
        for run_id in runs:
            try:
                row: SCTTestRun = SCTTestRun.get(id=run_id)
                rows.append(row)
            except SCTTestRun.DoesNotExist:
                pass

        response = {str(row.id): row for row in rows}
        return response

    def fetch_release_activity(self, release_name: str) -> dict:
        response = {}
        release = ArgusRelease.get(name=release_name)
        all_events = ArgusEvent.filter(release_id=release.id).all()
        all_events = sorted(all_events, key=lambda ev: ev.created_at)
        response["release_id"] = release.id
        response["raw_events"] = [dict(event.items()) for event in all_events]
        response["events"] = {str(event.id): EVENT_PROCESSORS.get(
            event.kind)(json.loads(event.body)) for event in all_events}
        return response

    def assign_runs_for_scheduled_test(self, schedule: ArgusSchedule, test_id: UUID, new_assignee: UUID):
        test: ArgusTest = ArgusTest.get(id=test_id)
        affected_rows: list[SCTTestRun] = list(SCTTestRun.filter(
            build_id=test.build_system_id,
            start_time__gte=schedule.period_start,
            start_time__lte=schedule.period_end
        ).all()
        )
        for row in affected_rows:
            if row.assignee != new_assignee:
                row.assignee = new_assignee
                row.save()

    def assign_runs_for_scheduled_group(self, schedule: ArgusSchedule, group_id: UUID, new_assignee: UUID):
        tests = ArgusTest.filter(group_id=group_id).all()
        build_ids = [test.build_system_id for test in tests]
        affected_rows: list[SCTTestRun] = list(SCTTestRun.filter(
            start_time__gte=schedule.period_start,
            start_time__lte=schedule.period_end
        ).all()
        )
        for row in affected_rows:
            if row.build_id in build_ids and row.assignee != new_assignee:
                row.assignee = new_assignee
                row.save()

    def submit_new_schedule(self, release: str | UUID, start_time: str, end_time: str, tests: list[str | UUID],
                            groups: list[str | UUID], assignees: list[str | UUID], tag: str) -> dict:
        release = UUID(release) if isinstance(release, str) else release
        if len(assignees) == 0:
            raise Exception("Assignees not specified in the new schedule")

        if len(tests) == 0 and len(groups) == 0:
            raise Exception("Schedule does not contain scheduled objects")

        schedule = ArgusSchedule()
        schedule.release_id = release
        schedule.period_start = datetime.datetime.fromisoformat(start_time)
        schedule.period_end = datetime.datetime.fromisoformat(end_time)
        schedule.id = uuid_from_time(schedule.period_start)
        schedule.tag = tag
        schedule.save()

        response = dict(schedule.items())
        response["assignees"] = []
        response["tests"] = []
        response["groups"] = []

        for test_id in tests:
            test_entity = ArgusScheduleTest()
            test_entity.id = uuid_from_time(schedule.period_start)
            test_entity.schedule_id = schedule.id
            test_entity.test_id = UUID(test_id) if isinstance(test_id, str) else test_id
            test_entity.release_id = release
            test_entity.save()
            self.assign_runs_for_scheduled_test(schedule, test_entity.test_id, UUID(assignees[0]))
            response["tests"].append(test_id)

        for group_id in groups:
            group_entity = ArgusScheduleGroup()
            group_entity.id = uuid_from_time(schedule.period_start)
            group_entity.schedule_id = schedule.id
            group_entity.group_id = UUID(group_id) if isinstance(group_id, str) else group_id
            group_entity.release_id = release
            group_entity.save()
            self.assign_runs_for_scheduled_group(schedule, group_entity.group_id, UUID(assignees[0]))
            response["groups"].append(group_id)

        for assignee_id in assignees:
            assignee_entity = ArgusScheduleAssignee()
            assignee_entity.id = uuid_from_time(schedule.period_start)
            assignee_entity.schedule_id = schedule.id
            assignee_entity.assignee = UUID(assignee_id) if isinstance(assignee_id, str) else assignee_id
            assignee_entity.release_id = release
            assignee_entity.save()
            response["assignees"].append(assignee_id)

        return response

    def get_schedules_for_release(self, release_id: str | UUID) -> dict:
        """
        {
            "release": "hex-uuid"
        }
        """
        release_id = UUID(release_id) if isinstance(release_id, str) else release_id
        release: ArgusRelease = ArgusRelease.get(id=release_id)
        if release.perpetual:
            today = datetime.datetime.utcnow()
            six_months_ago = today - datetime.timedelta(days=180)
            uuid_six_months = uuid_from_time(six_months_ago)
            schedules = ArgusSchedule.filter(release_id=release_id, id__gte=uuid_six_months).all()
        else:
            schedules = ArgusSchedule.filter(release_id=release_id).all()
        response = {
            "schedules": []
        }
        for schedule in schedules:
            serialized_schedule = dict(schedule.items())
            tests = ArgusScheduleTest.filter(schedule_id=schedule.id).all()
            serialized_schedule["tests"] = [test.test_id for test in tests]
            groups = ArgusScheduleGroup.filter(schedule_id=schedule.id).all()
            serialized_schedule["groups"] = [group.group_id for group in groups]
            assignees = ArgusScheduleAssignee.filter(schedule_id=schedule.id).all()
            serialized_schedule["assignees"] = [assignee.assignee for assignee in assignees]
            response["schedules"].append(serialized_schedule)

        return response

    def update_schedule_assignees(self, payload: dict) -> dict:
        """
        {
            "releaseId": "hex-uuid",
            "scheduleId": "hex-uuid",
        }
        """
        release_id = payload.get("releaseId")
        if not release_id:
            raise Exception("Release name not specified in the request")

        schedule_id = payload.get("scheduleId")
        if not schedule_id:
            raise Exception("No schedule Id provided")

        assignees = payload.get("newAssignees")
        if not assignees:
            raise Exception("No assignees provided")

        release = ArgusRelease.get(id=release_id)
        schedule = ArgusSchedule.get(release_id=release.id, id=schedule_id)
        schedule_tests = ArgusScheduleTest.filter(schedule_id=schedule.id).all()
        schedule_groups = ArgusScheduleGroup.filter(schedule_id=schedule.id).all()
        for test in schedule_tests:
            self.assign_runs_for_scheduled_test(schedule, test.test_id, UUID(assignees[0]))

        for group in schedule_groups:
            self.assign_runs_for_scheduled_group(schedule, group.group_id, UUID(assignees[0]))

        old_assignees = list(ArgusScheduleAssignee.filter(schedule_id=schedule.id).all())
        for new_assignee in assignees:
            assignee = ArgusScheduleAssignee()
            assignee.release_id = release.id
            assignee.schedule_id = schedule.id
            assignee.assignee = UUID(new_assignee)
            assignee.save()

        for old_assignee in old_assignees:
            old_assignee.delete()

        response = {
            "scheduleId": schedule_id,
            "status": "changed assignees",
            "newAssignees": assignees,
        }

        return response

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

        try:
            comment = ReleasePlannerComment.get(release=release_id, group=group_id, test=test_id)
        except ReleasePlannerComment.DoesNotExist:
            comment = ReleasePlannerComment()
            comment.release = release_id
            comment.group = group_id
            comment.test = test_id

        comment.comment = new_comment
        comment.save()

        return {
            "releaseId": release_id,
            "groupId": group_id,
            "testId": test_id,
            "newComment": new_comment,
        }

    def delete_schedule(self, payload: dict) -> dict:
        """
        {
            "release": hex-uuid,
            "schedule_id": uuid1
        }
        """
        release_id = payload.get("releaseId")
        if not release_id:
            raise Exception("Release name not specified in the request")

        schedule_id = payload.get("scheduleId")
        if not schedule_id:
            raise Exception("Schedule id not specified in the request")

        release = ArgusRelease.get(id=release_id)
        schedule = ArgusSchedule.get(release_id=release.id, id=schedule_id)
        tests = ArgusScheduleTest.filter(schedule_id=schedule.id).all()
        groups = ArgusScheduleGroup.filter(schedule_id=schedule.id).all()
        assignees = ArgusScheduleAssignee.filter(schedule_id=schedule.id).all()

        full_schedule = dict(schedule)
        full_schedule["tests"] = [test.test_id for test in tests]
        full_schedule["groups"] = [group.group_id for group in groups]
        full_schedule["assignees"] = [assignee.assignee for assignee in assignees]

        if len(assignees) > 0:
            schedule_user = User.get(id=assignees[0].assignee)
            service = TestRunService()

            for model in all_plugin_models():
                for run in model.get_jobs_assigned_to_user(schedule_user):
                    if run["release_id"] != release.id:
                        continue
                    if run["test_id"] not in full_schedule["tests"]:
                        continue
                    if schedule.period_start < run["start_time"] < schedule.period_end:
                        service.change_run_assignee(test_id=run["test_id"], run_id=run["id"], new_assignee=None)

        for entities in [tests, groups, assignees]:
            for entity in entities:
                entity.delete()

        schedule.delete()
        return {
            "releaseId": release.id,
            "scheduleId": schedule_id,
            "result": "deleted"
        }

    def get_planner_data(self, release_id: UUID | str) -> dict:

        release = ArgusRelease.get(id=release_id)
        release_comments = list(ReleasePlannerComment.filter(release=release.id).all())
        groups = ArgusGroup.filter(release_id=release.id).all()
        groups_by_group_id = {str(group.id): dict(group.items()) for group in groups if group.enabled}
        tests = ArgusTest.filter(release_id=release.id).all()
        tests = [dict(t.items()) for t in tests if t.enabled]
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
            "release": dict(release.items()),
            "groups": groups_by_group_id,
            "tests": tests,
            "tests_by_group": tests_by_group,
        }

        return response

    def get_groups_assignees(self, release_id: UUID | str):
        release_id = UUID(release_id) if isinstance(release_id, str) else release_id
        release = ArgusRelease.get(id=release_id)

        groups = ArgusGroup.filter(release_id=release_id).all()
        group_ids = [group.id for group in groups if group.enabled]

        total_ids = len(group_ids)
        schedule_ids = set()
        step = 0
        step_size = 60
        while total_ids > 0:
            group_slice = group_ids[step:step+step_size]
            scheduled_groups = ArgusScheduleGroup.filter(release_id=release.id, group_id__in=group_slice).all()
            batch_ids = {schedule.schedule_id for schedule in scheduled_groups}
            schedule_ids.union(batch_ids)
            total_ids = max(0, total_ids - step_size)
            step += step_size

        schedules = ArgusSchedule.filter(release_id=release.id, id__in=tuple(schedule_ids)).all()

        valid_schedules = schedules
        if release.perpetual:
            today = datetime.datetime.utcnow()
            valid_schedules = [s for s in schedules if s.period_start <= today <= s.period_end]

        response = {}
        for schedule in valid_schedules:
            assignees = ArgusScheduleAssignee.filter(schedule_id=schedule.id).all()
            assignees_uuids = [assignee.assignee for assignee in assignees]
            schedule_groups = filter(lambda g: g.schedule_id == schedule.id, scheduled_groups)
            groups = {str(group.group_id): assignees_uuids for group in schedule_groups}
            response = {**groups, **response}

        return response

    def get_tests_assignees(self, group_id: UUID | str):
        group_id = UUID(group_id) if isinstance(group_id, str) else group_id
        group = ArgusGroup.get(id=group_id)

        release = ArgusRelease.get(id=group.release_id)
        tests = ArgusTest.filter(group_id=group_id).all()

        test_ids = [test.id for test in tests if test.enabled]

        scheduled_tests = ArgusScheduleTest.filter(release_id=release.id, test_id__in=tuple(test_ids)).all()
        schedule_ids = {test.schedule_id for test in scheduled_tests}
        schedules: list[ArgusSchedule] = list(ArgusSchedule.filter(
            release_id=release.id, id__in=tuple(schedule_ids)).all())

        if release.perpetual:
            today = datetime.datetime.utcnow()
            schedules = list(filter(lambda s: s.period_start <= today <= s.period_end, schedules))

        response = {}
        for schedule in schedules:
            assignees = ArgusScheduleAssignee.filter(schedule_id=schedule.id).all()
            assignees_uuids = [assignee.assignee for assignee in assignees]
            schedule_tests = filter(lambda t: t.schedule_id == schedule.id, scheduled_tests)
            tests = {str(test.test_id): assignees_uuids for test in schedule_tests}
            response = {**tests, **response}

        return response

    def get_jobs_for_user(self, user: User):
        today = datetime.datetime.now()
        validity_period = today - datetime.timedelta(days=current_app.config.get("JOB_VALIDITY_PERIOD_DAYS", 30))
        for plugin in all_plugin_models():
            for run in plugin.get_jobs_assigned_to_user(user=user):
                if run["start_time"] >= validity_period:
                    yield run

    def get_schedules_for_user(self, user: User) -> list[dict]:
        all_assigned_schedules = ArgusScheduleAssignee.filter(assignee=user.id).all()
        schedule_keys = [(schedule_assignee.release_id, schedule_assignee.schedule_id)
                         for schedule_assignee in all_assigned_schedules]
        schedules = []
        today = datetime.datetime.utcnow()
        for release_id, schedule_id in schedule_keys:
            try:
                schedule = dict(ArgusSchedule.get(release_id=release_id, id=schedule_id).items())
            except ArgusSchedule.DoesNotExist:
                continue
            if schedule["period_start"] <= today <= schedule["period_end"]:
                tests = ArgusScheduleTest.filter(schedule_id=schedule_id).all()
                schedule["tests"] = [test.test_id for test in tests]
                groups = ArgusScheduleGroup.filter(schedule_id=schedule_id).all()
                schedule["groups"] = [group.group_id for group in groups]
                assignees = ArgusScheduleAssignee.filter(schedule_id=schedule_id).all()
                schedule["assignees"] = [assignee.assignee for assignee in assignees]
                schedules.append(schedule)

        return schedules

    def get_planner_comment_by_test(self, test_id):
        try:
            test = ArgusTest.get(id=test_id)
            return ReleasePlannerComment.get(test=test.id, release=test.release_id, group=test.group_id).comment
        except ReleasePlannerComment.DoesNotExist:
            return ""
