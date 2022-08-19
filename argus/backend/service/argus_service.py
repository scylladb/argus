import subprocess
import time
import json
import re
import logging
import datetime
from types import NoneType
from collections import namedtuple
from uuid import UUID, uuid4

import requests
from cassandra.util import uuid_from_time  # pylint: disable=no-name-in-module
from cassandra.cqlengine import ValidationError
from flask import g, current_app
from argus.backend.db import ScyllaCluster
from argus.backend.plugins.sct.testrun import SCTTestRun
from argus.backend.service.notification_manager import NotificationManagerService
from argus.backend.util.enums import TestStatus, TestInvestigationStatus
from argus.backend.models.web import (
    ArgusGithubIssue,
    ArgusRelease,
    ArgusGroup,
    ArgusTest,
    ArgusSchedule,
    ArgusScheduleAssignee,
    ArgusScheduleGroup,
    ArgusScheduleTest,
    ArgusTestRunComment,
    ArgusNotificationSourceTypes,
    ArgusNotificationTypes,
    ArgusEvent,
    ArgusEventTypes,
    ReleasePlannerComment,
    User,
)
from argus.backend.events.event_processors import EVENT_PROCESSORS
from argus.backend.util.common import strip_html_tags

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
        )
        self.event_insert_statement = self.database.prepare(
            'INSERT INTO argus.argus_event '
            '("id", "release_id", "group_id", "test_id", "run_id", "user_id", "kind", "body", "created_at") '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)'
        )
        self.scylla_versions_by_release = self.database.prepare(
            f"SELECT scylla_version FROM {SCTTestRun.table_name()} WHERE release_id = ?"
        )

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

    def load_test_run(self, test_run_id: UUID):
        try:
            return SCTTestRun.get(id=test_run_id)
        except SCTTestRun.DoesNotExist:
            return None

    def get_comment(self, comment_id: UUID) -> ArgusTestRunComment | None:
        try:
            return ArgusTestRunComment.get(id=comment_id)
        except ArgusTestRunComment.DoesNotExist:
            return None

    def get_comments(self, test_id: UUID) -> list[ArgusTestRunComment]:
        return sorted(ArgusTestRunComment.filter(test_run_id=test_id).all(), key=lambda c: c.posted_at)

    def post_comment(self, payload: dict) -> list[ArgusTestRunComment]:
        test_run_id: str = payload.get("test_run_id")
        if not test_run_id:
            raise Exception("TestId wasn't specified in the payload")

        message: str = payload.get("message")
        if not message:
            raise Exception("Comment message wasn't specified in the payload")

        release_name: str = payload.get("release")
        if not release_name:
            raise Exception("Release name not specified in the payload")

        reactions = payload.get("reactions", {})
        mentions = payload.get("mentions", [])
        message_stripped = strip_html_tags(message)

        mentions = set(mentions)
        for potential_mention in re.findall(r"@[A-Za-z\d](?:[A-Za-z\d]|-(?=[A-Za-z\d])){0,38}", message_stripped):
            if user := User.exists_by_name(potential_mention.lstrip("@")):
                mentions.add(user)

        release = ArgusRelease.get(name=release_name)
        comment = ArgusTestRunComment()
        comment.message = message_stripped
        comment.reactions = reactions
        comment.mentions = [m.id for m in mentions]
        comment.test_run_id = test_run_id
        comment.release_id = release.id
        comment.user_id = g.user.id
        comment.posted_at = time.time()
        comment.save()

        run_info = self.session.execute(self.build_id_and_url_statement, parameters=(comment.test_run_id,)).one()
        build_number = run_info["build_job_url"].strip("/").split("/")[-1]
        for mention in mentions:
            params = {
                "username": g.user.username,
                "run_id": comment.test_run_id,
                "test_id": run_info["test_id"],
                "build_id": run_info["build_id"],
                "build_number": build_number,
            }
            self.notification_manager.send_notification(
                receiver=mention.id,
                sender=comment.user_id,
                notification_type=ArgusNotificationTypes.Mention,
                source_type=ArgusNotificationSourceTypes.Comment,
                source_id=comment.id,
                content_params=params,
                source_message=comment.message,
            )

        self.send_event(kind=ArgusEventTypes.TestRunCommentPosted, body={
            "message": "A comment was posted by {username}",
            "username": g.user.username
        }, user_id=g.user.id, run_id=UUID(test_run_id), release_id=release.id)

        return self.get_comments(test_id=UUID(test_run_id))

    def delete_comment(self, payload: dict) -> dict:
        comment_id = payload.get("id")
        if not comment_id:
            raise Exception("Comment id not provided in request")

        run_id = payload.get("test_run_id")
        if not run_id:
            raise Exception("Test run id not provided in request")

        release_id = payload.get("release_id")
        if not release_id:
            raise Exception("Release id not provided in request")

        comment = ArgusTestRunComment.get(id=comment_id)
        if comment.user_id != g.user.id:
            raise Exception("Unable to delete other user comments")

        comment.delete()

        self.send_event(kind=ArgusEventTypes.TestRunCommentDeleted, body={
            "message": "A comment was deleted by {username}",
            "username": g.user.username
        }, user_id=g.user.id, run_id=UUID(run_id), release_id=UUID(release_id))

        return self.get_comments(test_id=UUID(run_id))

    def update_comment(self, payload: dict) -> dict:
        comment_id = payload.get("id")
        if not comment_id:
            raise Exception("Comment id not provided in request")

        run_id = payload.get("test_run_id")
        if not run_id:
            raise Exception("Test run id not provided in request")

        release_id = payload.get("release_id")
        if not release_id:
            raise Exception("Release id not provided in request")

        message = payload.get("message")
        if not message:
            raise Exception("Empty message provided")

        mentions = payload.get("mentions", [])
        reactions = payload.get("reactions", {})

        comment = ArgusTestRunComment.get(id=comment_id)
        if comment.user_id != g.user.id:
            raise Exception("Unable to edit other user comments")
        comment.message = strip_html_tags(message)
        comment.reactions = reactions
        comment.mentions = mentions
        comment.save()

        self.send_event(kind=ArgusEventTypes.TestRunCommentUpdated, body={
            "message": "A comment was edited by {username}",
            "username": g.user.username
        }, user_id=g.user.id, run_id=UUID(run_id), release_id=UUID(release_id))

        return self.get_comments(test_id=UUID(run_id))

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
        rows = self.session.execute(self.scylla_versions_by_release, parameters=(release_id,))
        unique_versions = {r["scylla_version"] for r in rows if r["scylla_version"]}

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

        return rows

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

    def send_event(self, kind: str, body: dict, user_id=None, run_id=None, release_id=None, group_id=None, test_id=None):
        params = (
            uuid4(),
            release_id,
            group_id,
            test_id,
            run_id,
            user_id,
            ArgusEventTypes(kind),
            json.dumps(body, ensure_ascii=True, separators=(',', ':')),
            datetime.datetime.utcnow()
        )
        self.session.execute(query=self.event_insert_statement, parameters=params)

    def toggle_test_status(self, payload: dict):
        new_status = payload.get("status")
        test_run_id = payload.get("test_run_id")
        if not test_run_id:
            raise Exception("Test run id wasn't specified in the request")
        if not new_status:
            raise Exception("New Status wasn't specified in the request")

        new_status = TestStatus(new_status)
        test_run: SCTTestRun = SCTTestRun.get(id=UUID(test_run_id))
        test = ArgusTest.get(build_system_id=test_run.build_id)
        old_status = TestStatus(test_run.status)
        test_run.status = new_status.value
        test_run.save()

        self.send_event(
            kind=ArgusEventTypes.TestRunStatusChanged,
            body={
                "message": "Status was changed from {old_status} to {new_status} by {username}",
                "old_status": old_status.value,
                "new_status": new_status.value,
                "username": g.user.username
            },
            user_id=g.user.id,
            run_id=test_run.id,
            release_id=test.release_id,
            group_id=test.group_id,
            test_id=test.id
        )
        return {
            "test_run_id": test_run_id,
            "status": new_status
        }

    def toggle_test_investigation_status(self, payload: dict):
        new_status = payload.get("investigation_status")
        test_run_id = payload.get("test_run_id")
        if not test_run_id:
            raise Exception("Test run id wasn't specified in the request")
        if not new_status:
            raise Exception("New investigation status wasn't specified in the request")

        new_status = TestInvestigationStatus(new_status)
        test_run: SCTTestRun = SCTTestRun.get(id=UUID(test_run_id))
        test = ArgusTest.get(build_system_id=test_run.build_id)
        old_status = test_run.investigation_status
        test_run.investigation_status = new_status.value
        test_run.save()

        self.send_event(
            kind=ArgusEventTypes.TestRunStatusChanged,
            body={
                "message": "Investigation status was changed from {old_status} to {new_status} by {username}",
                "old_status": old_status,
                "new_status": new_status.value,
                "username": g.user.username
            },
            user_id=g.user.id,
            run_id=test_run.id,
            release_id=test.release_id,
            group_id=test.group_id,
            test_id=test.id
        )
        return {
            "test_run_id": test_run_id,
            "investigation_status": new_status
        }

    def change_assignee(self, payload: dict):
        DummyUser = namedtuple("DummyUser", ["id", "username"])
        new_assignee = payload.get("assignee")
        test_run_id = payload.get("test_run_id")
        if not test_run_id:
            raise Exception("Test run id wasn't specified in the request")
        if not new_assignee:
            raise Exception("New assignee wasn't specified in the request")

        try:
            new_assignee = User.get(id=new_assignee)
        except ValidationError:
            if new_assignee != "none-none-none":
                raise
            new_assignee = DummyUser(id=None, username="None")
        test_run: SCTTestRun = SCTTestRun.get(id=UUID(test_run_id))
        test = ArgusTest.get(build_system_id=test_run.build_id)
        old_assignee = test_run.assignee
        old_assignee = User.get(id=old_assignee) if old_assignee else None
        test_run.assignee = new_assignee.id
        test_run.save()

        self.send_event(
            kind=ArgusEventTypes.AssigneeChanged,
            body={
                "message": "Assignee was changed from \"{old_user}\" to \"{new_user}\" by {username}",
                "old_user": old_assignee.username if old_assignee else "None",
                "new_user": new_assignee.username,
                "username": g.user.username
            },
            user_id=g.user.id,
            run_id=test_run.id,
            release_id=test.release_id,
            group_id=test.group_id,
            test_id=test.id
        )
        return {
            "test_run_id": test_run_id,
            "assignee": str(new_assignee.id)
        }

    def fetch_run_activity(self, run_id: UUID) -> dict:
        response = {}
        all_events = ArgusEvent.filter(run_id=run_id).all()
        all_events = sorted(all_events, key=lambda ev: ev.created_at)
        response["run_id"] = run_id
        response["raw_events"] = [dict(event.items()) for event in all_events]
        response["events"] = {str(event.id): EVENT_PROCESSORS.get(
            event.kind)(json.loads(event.body)) for event in all_events}
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

    def submit_github_issue(self, payload: dict) -> dict:
        """
        Example payload:
        {
            "issue_url": "https://github.com/example/repo/issues/6"
            "run_id": "abcdef-5354235-1232145-dd"
        }
        """
        issue_url = payload.get("issue_url")
        run_id = payload.get("run_id")
        if not run_id:
            raise Exception("Run Id missing from request")
        if not issue_url:
            raise Exception("Missing or empty issue url")

        match = re.match(
            r"http(s)?://(www\.)?github\.com/(?P<owner>[\w\d]+)/"
            r"(?P<repo>[\w\d\-_]+)/(?P<type>issues|pull)/(?P<issue_number>\d+)(/)?",
            issue_url)
        if not match:
            raise Exception("URL doesn't match Github schema")

        run = SCTTestRun.get(id=UUID(run_id))
        release = ArgusRelease.get(id=run["release_id"])
        test = ArgusTest.get(build_system_id=run["build_id"])
        group = ArgusGroup.get(id=test.group_id)

        new_issue = ArgusGithubIssue()
        new_issue.user_id = g.user.id
        new_issue.run_id = run_id
        new_issue.group_id = group.id
        new_issue.release_id = release.id
        new_issue.test_id = test.id
        new_issue.type = match.group("type")
        new_issue.owner = match.group("owner")
        new_issue.repo = match.group("repo")
        new_issue.issue_number = int(match.group("issue_number"))

        issue_state = requests.get(
            f"https://api.github.com/repos/{new_issue.owner}/{new_issue.repo}/issues/{new_issue.issue_number}",
            headers=self.github_headers
        ).json()

        new_issue.title = issue_state.get("title")
        new_issue.url = issue_state.get("html_url")
        new_issue.last_status = issue_state.get("state")
        new_issue.save()

        self.send_event(
            kind=ArgusEventTypes.TestRunIssueAdded,
            body={
                "message": "An issue titled \"{title}\" was added by {username}",
                "username": g.user.username,
                "url": issue_url,
                "title": issue_state.get("title"),
                "state": issue_state.get("state"),
            },
            user_id=g.user.id,
            run_id=new_issue.run_id,
            release_id=new_issue.release_id,
            group_id=new_issue.group_id,
            test_id=new_issue.test_id
        )

        response = {
            **dict(list(new_issue.items())),
            "title": issue_state.get("title"),
            "state": issue_state.get("state"),
        }

        return response

    def get_github_issues(self, filter_key: str, filter_id: UUID, aggregate_by_issue: bool = False) -> dict:

        if filter_key not in ["release_id", "group_id", "test_id", "run_id", "user_id"]:
            raise Exception(
                "filter_key can only be one of: \"release_id\", \"group_id\", \"test_id\", \"run_id\", \"user_id\""
            )
        all_issues = ArgusGithubIssue.filter(**{filter_key: filter_id}).all()
        if aggregate_by_issue:
            runs_by_issue = {}
            response = []
            for issue in all_issues:
                runs = runs_by_issue.get(issue, [])
                runs.append(issue.run_id)
                runs_by_issue[issue] = runs

            for issue, runs in runs_by_issue.items():
                issue_dict = dict(issue.items())
                issue_dict["runs"] = runs
                response.append(issue_dict)

        else:
            response = [dict(issue.items()) for issue in all_issues]
        return response

    def delete_github_issue(self, payload: dict) -> dict:
        issue_id = payload.get("id")
        if not issue_id:
            raise Exception("Issue id not supplied in the request")

        issue: ArgusGithubIssue = ArgusGithubIssue.get(id=issue_id)

        self.send_event(
            kind=ArgusEventTypes.TestRunIssueRemoved,
            body={
                "message": "An issue titled \"{title}\" was removed by {username}",
                "username": g.user.username,
                "url": issue.url,
                "title": issue.title,
                "state": issue.last_status,
            },
            user_id=g.user.id,
            run_id=issue.run_id,
            release_id=issue.release_id,
            group_id=issue.group_id,
            test_id=issue.test_id
        )
        issue.delete()

        return {
            "deleted": issue_id
        }

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
            build_id__in=build_ids,
            start_time__gte=schedule.period_start,
            start_time__lte=schedule.period_end
        ).all()
        )
        for row in affected_rows:
            if row.assignee != new_assignee:
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

        scheduled_groups = ArgusScheduleGroup.filter(release_id=release.id, group_id__in=group_ids).all()
        schedule_ids = {schedule.schedule_id for schedule in scheduled_groups}

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
        runs: list[SCTTestRun] = list(SCTTestRun.filter(assignee=user.id).all())
        schedules = self.get_schedules_for_user(user)
        valid_runs = []
        today = datetime.datetime.now()
        month_ago = today - datetime.timedelta(days=30)
        for run in runs:
            run_date = run.start_time
            if user.id == run.assignee and run_date >= month_ago:
                valid_runs.append(run)
                continue
            for schedule in schedules:
                if not run.release_id == schedule["release_id"]:
                    continue
                if not schedule["period_start"] < run_date < schedule["period_end"]:
                    continue
                if run.assignee in schedule["assignees"]:
                    valid_runs.append(run)
                    break
                if run.group_id in schedule["groups"]:
                    valid_runs.append(run)
                    break
                filtered_tests = [test for test in schedule["tests"] if test == run.test_id]
                if len(filtered_tests) > 0:
                    valid_runs.append(run)
                    break
        return valid_runs

    def get_schedules_for_user(self, user: User):
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
