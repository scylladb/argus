import base64
import subprocess
import time
import json
import re
import os
import hashlib
import datetime
from types import NoneType
from typing import Callable
from collections import namedtuple
from uuid import UUID, uuid4

import humanize
import requests
from cassandra.cqlengine import ValidationError
from flask import g, current_app, session
from werkzeug.security import check_password_hash, generate_password_hash
from argus.backend.db import ScyllaCluster
from argus.db.db_types import TestInvestigationStatus
from argus.db.testrun import TestRun, TestStatus
from argus.db.models import (
    ArgusGithubIssue,
    ArgusRelease,
    ArgusReleaseGroup,
    ArgusReleaseGroupTest,
    ArgusReleaseSchedule,
    ArgusReleaseScheduleAssignee,
    ArgusReleaseScheduleGroup,
    ArgusReleaseScheduleTest,
    ArgusTestRunComment,
    ArgusEvent,
    ArgusEventTypes,
    ReleasePlannerComment,
    User,
    UserOauthToken,
    WebFileStorage,
)
from argus.backend.event_processors import EVENT_PROCESSORS


def first(iterable, value, key: Callable = None, predicate: Callable = None):
    for elem in iterable:
        if predicate and predicate(elem, value):
            return elem
        elif key and key(elem) == value:
            return elem
        elif elem == value:
            return elem
    return None


def check_scheduled_test(test, group, testname):
    return testname == f"{group}/{test}" or testname == test


class GithubOrganizationMissingError(Exception):
    pass


class ArgusService:
    # pylint: disable=no-self-use,too-many-arguments,too-many-instance-attributes,too-many-locals, too-many-public-methods
    def __init__(self, database_session=None):
        self.session = database_session if database_session else ScyllaCluster.get_session()
        self.database = ScyllaCluster.get()
        self.github_headers = {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"token {current_app.config['GITHUB_ACCESS_TOKEN']}"
        }
        self.runs_by_id_stmt = self.database.prepare(
            f"SELECT * FROM {TestRun.table_name()} WHERE id in ?"
        )
        self.run_by_release_name_stmt = self.database.prepare(
            "SELECT id, name, group, release_name, build_job_name, build_job_url, "
            "status, start_time, end_time, heartbeat "
            f"FROM {TestRun.table_name()} WHERE release_name = ?"
        )
        self.jobs_by_assignee = self.database.prepare(
            "SELECT id, status, start_time, assignee, release_name, "
            "investigation_status, "
            "group, name, build_job_name, build_job_url FROM "
            f"{TestRun.table_name()} WHERE assignee = ?"
        )
        self.test_table_statement = self.database.prepare(
            "SELECT id, name, group, release_name, "
            "build_job_url, build_job_name, status, "
            f"start_time, end_time, heartbeat FROM {TestRun.table_name()}"
        )
        self.run_by_release_stats_statement = self.database.prepare(
            "SELECT id, name, group, release_name, status, start_time, build_job_url, "
            f"end_time, investigation_status, heartbeat FROM {TestRun.table_name()} WHERE release_name = ?"
        )
        self.event_insert_statement = self.database.prepare(
            'INSERT INTO argus.argus_event '
            '("id", "release_id", "group_id", "test_id", "run_id", "user_id", "kind", "body", "created_at") '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)'
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
            new_group = ArgusReleaseGroup()
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
            new_test = ArgusReleaseGroupTest()
            new_test.release_id = parent_release_id
            new_test.group_id = parent_group_id
            new_test.name = test_name
            new_test.save()
            response[test_name] = "created"

        return response

    def get_test_table(self):
        rows = self.session.execute(self.test_table_statement).all()
        for row in rows:
            row["natural_heartbeat"] = humanize.naturaltime(
                datetime.datetime.fromtimestamp(row["heartbeat"]))
            row["natural_start_time"] = humanize.naturaltime(
                datetime.datetime.fromtimestamp(row["start_time"]))
            row["natural_end_time"] = humanize.naturaltime(
                datetime.datetime.fromtimestamp(row["end_time"]))

        return sorted(rows, key=lambda x: x["start_time"], reverse=True)

    def load_test_run(self, test_run_id: UUID):
        run = TestRun.from_id(test_id=test_run_id)
        return run

    def get_comments(self, test_id: UUID) -> list[ArgusTestRunComment]:
        return sorted(ArgusTestRunComment.filter(test_run_id=test_id).all(), key=lambda c: c.posted_at)

    def get_user_info(self) -> dict:
        users = User.all()
        return {str(user.id): user.to_json() for user in users}

    def post_comment(self, payload: dict) -> list[ArgusTestRunComment]:
        test_id: str = payload["test_id"]
        message: str = payload["message"]
        message_stripped = message.replace("<", "&lt;").replace(">", "&gt;")
        release_name_stmt = self.database.prepare(
            f"SELECT release_name FROM {TestRun.table_name()} WHERE id = ?")
        release_name = self.session.execute(
            release_name_stmt, parameters=(UUID(test_id),)).one()["release_name"]
        release = ArgusRelease.get(name=release_name)
        comment = ArgusTestRunComment()
        comment.test_run_id = test_id
        comment.release_id = release.id
        comment.user_id = g.user.id
        comment.mentions = []
        comment.message = message_stripped
        comment.posted_at = time.time()
        comment.save()
        self.send_event(kind=ArgusEventTypes.TestRunCommentPosted, body={
            "message": "A comment was posted by {username}",
            "username": g.user.username
        }, user_id=g.user.id, run_id=UUID(test_id), release_id=release.id)
        return self.get_comments(test_id=UUID(test_id))

    def get_releases(self):
        web_releases = list(ArgusRelease.all())
        return sorted(web_releases, key=lambda val: val.name)

    def get_groups_for_release(self, release_id: UUID):
        release_groups = ArgusReleaseGroup.filter(release_id=release_id)
        return sorted(release_groups, key=lambda val: val.name)

    def get_tests_for_release_group(self, group_id: UUID):
        tests = ArgusReleaseGroupTest.filter(group_id=group_id)
        return sorted(tests, key=lambda val: val.name)

    def get_data_for_release_dashboard(self, release_name: str):
        release = ArgusRelease.get(name=release_name)
        release_groups = ArgusReleaseGroup.filter(release_id=release.id).all()
        release_tests = ArgusReleaseGroupTest.filter(release_id=release.id).all()

        return release, release_groups, release_tests

    def get_test_last_run_status(self, payload: dict) -> dict:
        response = {}
        runs = self.session.execute(
            self.run_by_release_name_stmt,
            parameters=(payload["release_name"],)
        ).all()
        runs = sorted(runs, key=lambda val: val["start_time"], reverse=True)
        for test in payload.get("tests", []):
            runs_for_test = [
                run for run in runs if run["name"].startswith(test["name"])]
            response[test["name"]] = runs_for_test[0]["status"] if len(
                runs_for_test) > 0 else "none"

        return response

    def get_runs_by_name_for_release_group(self, test_name: str, release_name: str, limit=10):
        rows = self.session.execute(self.run_by_release_name_stmt, parameters=(release_name,)).all()
        rows = [row for row in rows if row["release_name"]
                == release_name and re.match(f"^{test_name}(-test)?$", row["name"])]
        for row in rows:
            row["natural_heartbeat"] = humanize.naturaltime(
                datetime.datetime.fromtimestamp(row["heartbeat"]))
            row["natural_start_time"] = humanize.naturaltime(
                datetime.datetime.fromtimestamp(row["start_time"]))
            row["natural_end_time"] = humanize.naturaltime(
                datetime.datetime.fromtimestamp(row["end_time"]))
            row["build_number"] = int(
                row["build_job_url"].rstrip("/").split("/")[-1])

        return sorted(rows, key=lambda x: x["start_time"], reverse=True)[:limit]

    def collect_stats(self, payload: dict) -> dict:
        """
        Example body:
        {
            "master": {
                "force": true, // Forcefully retrieve stats even if release is disabled
                "limited": false, // Do not retrieve extra information (last runs, bug reports)
                "groups": ["longevity", "artifacts"],
                "tests": ["longevity-100gb", "artifacts-ami"]
            }
        }
        Both groups and tests are considered prefixes to test_run names
        """
        response = {
            "releases": {

            }
        }
        all_releases = {release.name: release for release in ArgusRelease.all()}

        group_stats_body = {
            "total": 0,
            **{e.value: 0 for e in TestStatus},
            "not_run": 0,
            "lastStatus": "unknown",
            "lastInvestigationStatus": "unknown",
            "hasBugReport": False,
            "tests": None,
        }

        for release_name, release_body in payload.items():
            release = all_releases[release_name]
            release_tests = ArgusReleaseGroupTest.filter(release_id=release.id).all()
            release_groups = ArgusReleaseGroup.filter(release_id=release.id).all()
            release_groups_by_id = {group.id: group for group in release_groups}
            override = release_body.get("force", False)
            limited = release_body.get("limited", False)
            release_stats = {
                "total": 0,
                **{e.value: 0 for e in TestStatus},
                "not_run": 0,
                "lastStatus": "unknown",
                "lastInvestigationStatus": "unknown",
                "hasBugReport": False,
                "groups": {
                    group.name: dict(**group_stats_body) for group in release_groups
                },
                "tests": {},
                "disabled": False,
            }
            if not all_releases[release_name].enabled and not override:
                release_stats["disabled"] = True
                response["releases"][release_name] = release_stats
                continue

            rows = self.session.execute(self.run_by_release_stats_statement, parameters=(release_name,))
            rows = sorted(rows, key=lambda r: r["start_time"], reverse=True)
            release_issues = ArgusGithubIssue.filter(release_id=release.id).all()
            release_comments = ArgusTestRunComment.filter(release_id=release.id)
            for test in release_tests:
                test_group = release_groups_by_id[test.group_id]
                if not release_stats["groups"][test_group.name]["tests"]:
                    release_stats["groups"][test_group.name]["tests"] = dict()
                release_stats["total"] += 1
                rows_by_group = [row for row in rows if row["group"] == test_group.name]
                run = first(rows_by_group, test.name, predicate=lambda elem,
                            val: re.match(f"^{val}(-test)?$", elem["name"]))
                if not limited and run:
                    last_runs = list(filter(lambda run: re.match(
                        f"^{test.name}(-test)?$", run["name"]), rows_by_group))[:4]
                    last_runs = [
                        {
                            "status": run["status"],
                            "build_number": run["build_job_url"].rstrip("/").split("/")[-1],
                            "build_job_url": run["build_job_url"],
                            "start_time": run["start_time"],
                            "issues": [dict(i.items()) for i in release_issues if i.run_id == run["id"]],
                            "comments": [dict(i.items()) for i in release_comments if i.test_run_id == run["id"]],
                        }
                        for run in last_runs
                    ]
                    issues = last_runs[0]["issues"] if len(last_runs) > 0 else []
                    comments = last_runs[0]["comments"] if len(last_runs) > 0 else []

                if not run:
                    release_stats["groups"][test_group.name]["tests"][test.name] = {
                        "name": test.name,
                        "status": "unknown",
                        "group": test_group.name,
                        "start_time": 0
                    }
                    release_stats["not_run"] += 1
                    release_stats["groups"][test_group.name]["not_run"] += 1
                    release_stats["groups"][test_group.name]["total"] += 1
                    continue

                release_stats["groups"][test_group.name]["tests"][test.name] = {
                    "name": test.name,
                    "group": test_group.name,
                    "status": run["status"],
                    "start_time": run["start_time"],
                    "investigation_status": run["investigation_status"],
                }

                if not limited:
                    release_stats["hasBugReport"] = len(issues) > 0
                    release_stats["groups"][test_group.name]["tests"][test.name]["last_runs"] = last_runs
                    release_stats["groups"][test_group.name]["tests"][test.name]["hasBugReport"] = len(issues) > 0
                    release_stats["groups"][test_group.name]["hasBugReport"] = len(issues) > 0
                    release_stats["groups"][test_group.name]["tests"][test.name]["hasComments"] = len(comments) > 0
                    release_stats["groups"][test_group.name]["hasComments"] = len(comments) > 0

                release_stats["groups"][test_group.name][run["status"]] += 1
                release_stats["groups"][test_group.name]["total"] += 1
                release_stats["groups"][test_group.name]["lastStatus"] = run["status"]
                release_stats["groups"][test_group.name]["lastInvestigationStatus"] = run["investigation_status"]
                release_stats[run["status"]] += 1
                release_stats["lastStatus"] = run["status"]
                release_stats["lastInvestigationStatus"] = run["investigation_status"]

            response["releases"][release_name] = release_stats

        return response

    def poll_test_runs(self, payload: dict):
        limit = payload["limit"]
        runs: dict = payload["runs"]
        response = {}

        for uid, [release_name, test_name, group_name] in runs.items():
            rows = self.session.execute(
                self.run_by_release_name_stmt,
                parameters=(release_name,),
                execution_profile="read_fast"
            ).all()
            rows = sorted(rows, key=lambda val: val["start_time"], reverse=True)
            for row in rows:
                try:
                    row["build_number"] = int(
                        row["build_job_url"].rstrip("/").split("/")[-1])
                except ValueError:
                    row["build_number"] = -1

            result = [
                row for row in rows
                if re.match(f"^{test_name}(-test)?$", row["name"]) and row["group"] == group_name
            ][:limit]
            response[uid] = result
        return response

    def poll_test_runs_single(self, payload: dict):
        runs = [UUID(id) for id in payload["runs"]]

        statement = self.runs_by_id_stmt
        rows = self.session.execute(statement, parameters=(
            runs,), execution_profile="read_fast_named_tuple").all()

        response = {str(row.id): TestRun.from_db_row(row).serialize()
                    for row in rows}

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
        test_run = TestRun.from_id(test_id=UUID(test_run_id))
        release_name = test_run.release_name
        release = ArgusRelease.get(name=release_name)
        test_name = test_run.run_info.details.name
        test = [test for test in ArgusReleaseGroupTest.all() if test.release_id ==
                release.id and test.name.startswith(test_name)]
        test = test[0]
        old_status = test_run.run_info.results.status
        test_run.run_info.results.status = new_status
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
        test_run = TestRun.from_id(test_id=UUID(test_run_id))
        release_name = test_run.release_name
        release = ArgusRelease.get(name=release_name)
        test_name = test_run.run_info.details.name
        test = [test for test in ArgusReleaseGroupTest.all() if test.release_id ==
                release.id and test.name.startswith(test_name)]
        test = test[0]
        old_status = test_run.investigation_status
        test_run.investigation_status = new_status
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
            new_assignee = DummyUser(id="", username="None")
        test_run = TestRun.from_id(test_id=UUID(test_run_id))
        release_name = test_run.release_name
        release = ArgusRelease.get(name=release_name)
        test_name = test_run.run_info.details.name
        test = [test for test in ArgusReleaseGroupTest.filter(
            name=test_name).all() if test.release_id == release.id][0]
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

    def fetch_run_activity(self, payload: dict) -> dict:
        response = {}
        run_id = payload.get("test_run_id")
        if not run_id:
            raise Exception("TestRun id wasn't specified in the request")

        all_events = ArgusEvent.filter(run_id=run_id).all()
        all_events = sorted(all_events, key=lambda ev: ev.created_at)
        response["run_id"] = run_id
        response["raw_events"] = [dict(event.items()) for event in all_events]
        response["events"] = {str(event.id): EVENT_PROCESSORS.get(
            event.kind)(json.loads(event.body)) for event in all_events}
        return response

    def fetch_release_activity(self, payload: dict) -> dict:
        response = {}
        release_name = payload.get("release_name")
        if not release_name:
            raise Exception("Release Name wasn't specified in the request")
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

        run = self.session.execute(self.runs_by_id_stmt, parameters=([UUID(run_id)],)).one()
        test_name = run["name"]
        release = ArgusRelease.get(name=run["release_name"])
        test = ArgusReleaseGroupTest.filter(name=test_name).all()
        test = first(test, release.id, key=lambda val: val.release_id)
        group = ArgusReleaseGroup.get(id=test.group_id)

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

    def get_github_issues(self, payload: dict) -> dict:
        """
        Example payload:
        {
            "filter_key": "release_id",
            "id": "abcdef-bcdedf-00000",
        }
        """

        filter_key = payload.get("filter_key")
        if not filter_key:
            raise Exception("A filter_key field is required")

        if filter_key not in ["release_id", "group_id", "test_id", "run_id", "user_id"]:
            raise Exception(
                "filter_key can only be one of: \"release_id\", \"group_id\", \"test_id\", \"run_id\", \"user_id\""
            )

        filter_id = payload.get("id")
        if not filter_id:
            raise Exception("A filter_id field is required")

        filter_id = UUID(filter_id)
        all_issues = ArgusGithubIssue.filter(**{filter_key: filter_id}).all()

        response = [dict(list(issue.items())) for issue in all_issues]
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

    def get_github_issue_state(self, payload: dict) -> dict:
        """
        Example payload:
        {
            "issues": [
                [1, 'example-repo', 'example-owner']
            ]
        }

        Response:
        {
            "https://github.com/example-owner/example-repo/issues/1": "open"
        }
        """
        issues = payload.get("issues")
        if not issues:
            raise Exception("Empty request")
        response = {}
        for num, repo, owner in issues:
            issue_state = requests.get(f"https://api.github.com/repos/{owner}/{repo}/issues/{num}",
                                       headers=self.github_headers).json()
            response[issue_state.get("html_url")] = issue_state.get("state")

        return response

    def fetch_release_issues(self, payload: dict) -> dict:
        """
        Example payload
        {
            "release_id": "abcadedf-efadd-24124",
            "tests": [ArgusReleaseGroupTest <, ...>]
        }
        Response
        [[ArgusReleaseGroupTest, GithubIssue[]], ...]
        """

        release_id = payload.get("release_id")
        if not release_id:
            raise Exception("ReleaseId wasn't specified in the request")

        release_issues = self.get_github_issues({
            "filter_key": "release_id",
            "id": release_id
        })

        tests = payload.get("tests", [])

        response = []
        for test in tests:
            issues_for_test = [issue for issue in release_issues if issue["test_id"] == UUID(test["id"])]
            if len(issues_for_test) > 0:
                response.append([test, issues_for_test])

        return response

    def submit_new_schedule(self, payload: dict) -> dict:
        """
        Payload:
        {
            "release": "master",
            "groups": ["longevity", ...],
            "tests": ["longevity-10gb-3h", ...],
            "start": 160000000,
            "end": 1600000001,
            "assignees": [uuid<, ...>]
        }
        """
        release = payload.get("release")
        if not release:
            raise Exception("Release wasn't specified in the request")

        start_time = payload.get("start", int(datetime.datetime.utcnow().timestamp()))
        end_time = payload.get("end")
        if not end_time:
            raise Exception("End time wasn't specified by the schedule")

        if not start_time:
            raise Exception("Start time wasn't specified by the schedule")

        assignees = payload.get("assignees", [])
        tests = payload.get("tests", [])
        groups = payload.get("groups", [])

        if len(assignees) == 0:
            raise Exception("Assignees must be specified for the schedule to be valid!")

        if len(tests) == 0 and len(groups) == 0:
            raise Exception("At least one group or test must be assigned for the schedule to be valid")

        tag = payload.get("tag", "")

        schedule = ArgusReleaseSchedule()
        schedule.release = release
        schedule.period_start = datetime.datetime.fromisoformat(start_time)
        schedule.period_end = datetime.datetime.fromisoformat(end_time)
        schedule.tag = tag
        schedule.save()

        response = dict(schedule.items())
        response["assignees"] = []
        response["tests"] = []
        response["groups"] = []

        for test in tests:
            test_entity = ArgusReleaseScheduleTest()
            test_entity.schedule_id = schedule.schedule_id
            test_entity.name = test
            test_entity.release = release
            test_entity.save()
            response["tests"].append(test)

        for group in groups:
            group_entity = ArgusReleaseScheduleGroup()
            group_entity.schedule_id = schedule.schedule_id
            group_entity.name = group
            group_entity.release = release
            group_entity.save()
            response["groups"].append(group)

        for assignee in assignees:
            assignee_entity = ArgusReleaseScheduleAssignee()
            assignee_entity.schedule_id = schedule.schedule_id
            assignee_entity.assignee = assignee
            assignee_entity.release = release
            assignee_entity.save()
            response["assignees"].append(assignee)

        return response

    def get_schedules_for_release(self, payload: dict) -> dict:
        """
        {
            "release": "master"
        }
        """
        release = payload.get("release")
        if not release:
            raise Exception("Release name not specified in the request")

        release = ArgusRelease.get(name=release)
        schedules = ArgusReleaseSchedule.filter(release=release.name).all()
        response = {
            "schedules": []
        }
        for schedule in schedules:
            serialized_schedule = dict(schedule.items())
            tests = ArgusReleaseScheduleTest.filter(schedule_id=schedule.schedule_id).all()
            serialized_schedule["tests"] = [test.name for test in tests]
            groups = ArgusReleaseScheduleGroup.filter(schedule_id=schedule.schedule_id).all()
            serialized_schedule["groups"] = [group.name for group in groups]
            assignees = ArgusReleaseScheduleAssignee.filter(schedule_id=schedule.schedule_id).all()
            serialized_schedule["assignees"] = [assignee.assignee for assignee in assignees]
            response["schedules"].append(serialized_schedule)

        return response

    def update_schedule_comment(self, payload: dict) -> dict:
        new_comment = payload.get("newComment")
        release = payload.get("release")
        group = payload.get("group")
        test = payload.get("test")

        if not release:
            raise Exception("No release provided")
        if not group:
            raise Exception("No group provided")
        if not test:
            raise Exception("No test provided")

        if isinstance(new_comment, NoneType):
            raise Exception("No comment provided in the body of request")

        try:
            comment = ReleasePlannerComment.get(release=release, group=group, test=test)
        except ReleasePlannerComment.DoesNotExist:
            comment = ReleasePlannerComment()
            comment.release = release
            comment.group = group
            comment.test = test

        comment.comment = new_comment
        comment.save()

        return {
            "release": release,
            "group": group,
            "test": test,
            "newComment": new_comment,
        }

    def delete_schedule(self, payload: dict) -> dict:
        """
        {
            "release": "master",
            "schedule_id": uuid1
        }
        """
        release = payload.get("release")
        if not release:
            raise Exception("Release name not specified in the request")

        schedule_id = payload.get("schedule_id")
        if not schedule_id:
            raise Exception("Schedule id not specified in the request")

        release = ArgusRelease.get(name=release)
        schedule = ArgusReleaseSchedule.get(release=release.name, schedule_id=schedule_id)
        tests = ArgusReleaseScheduleTest.filter(schedule_id=schedule.schedule_id).all()
        groups = ArgusReleaseScheduleGroup.filter(schedule_id=schedule.schedule_id).all()
        assignees = ArgusReleaseScheduleAssignee.filter(schedule_id=schedule.schedule_id).all()

        for entities in [tests, groups, assignees]:
            for entity in entities:
                entity.delete()

        schedule.delete()
        return {
            "release": release.name,
            "schedule": schedule_id,
            "result": "deleted"
        }

    def get_planner_data(self, payload: dict) -> dict:
        release_name = payload.get("release", None)
        if not release_name:
            raise Exception("Release wasn't specified in the payload")

        release = ArgusRelease.get(name=release_name)
        release_comments = list(ReleasePlannerComment.filter(release=release.name).all())
        groups = ArgusReleaseGroup.filter(release_id=release.id).all()
        groups_by_group_id = {str(group.id): dict(group.items()) for group in groups}
        tests = ArgusReleaseGroupTest.filter(release_id=release.id).all()
        tests = [dict(t.items()) for t in tests]
        tests_by_group = {}
        for test in tests:
            test["group_name"] = groups_by_group_id[str(test["group_id"])]["name"]
            try:
                comment = next(filter(lambda c: c.test == test["name"]
                               and c.group == test["group_name"], release_comments))
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

    def get_assignees(self, payload: dict) -> dict:
        """
        {
            "master": {
                "groups": ["longevity", ...],
                "tests": ["longevity-3gb-4h", ...]
            },
            <...>
        }
        """
        response = {}
        for release, body in payload.items():
            response[release] = {
                "groups": {},
                "tests": {}
            }
            scheduled_groups = ArgusReleaseScheduleGroup.filter(release=release, name__in=body.get("groups", [])).all()
            scheduled_tests = ArgusReleaseScheduleTest.filter(release=release, name__in=body.get("tests", [])).all()

            schedule_ids = {schedule.schedule_id for schedule in [*scheduled_groups, *scheduled_tests]}

            schedules = ArgusReleaseSchedule.filter(release=release, schedule_id__in=tuple(schedule_ids)).all()
            today = datetime.datetime.utcnow()
            valid_schedules = []
            for schedule in schedules:
                if schedule.period_start <= today <= schedule.period_end:
                    valid_schedules.append(schedule)
            for schedule in valid_schedules:
                assignees = ArgusReleaseScheduleAssignee.filter(schedule_id=schedule.schedule_id).all()
                assignees_uuids = [assignee.assignee for assignee in assignees]
                schedule_groups = filter(lambda g: g.schedule_id == schedule.schedule_id, scheduled_groups)
                schedule_tests = filter(lambda t: t.schedule_id == schedule.schedule_id, scheduled_tests)
                groups = {group.name: assignees_uuids for group in schedule_groups}
                tests = {test.name: assignees_uuids for test in schedule_tests}
                response[release]["groups"] = {**groups, **response[release]["groups"]}
                response[release]["tests"] = {**tests, **response[release]["tests"]}

        return response

    def update_email(self, user: User, new_email: str):
        user.email = new_email
        user.save()

    def update_password(self, user: User, old_password: str, new_password: str):
        if check_password_hash(user.password, old_password):
            raise Exception("Incorrect old password")

        user.password = generate_password_hash(new_password)
        user.save()

    def update_name(self, user: User, new_name: str):
        user.full_name = new_name
        user.save()

    def update_profile_picture(self, filename, filepath):
        web_file = WebFileStorage()
        web_file.filename = filename
        web_file.filepath = filepath
        web_file.save()

        try:
            if old_picture_id := g.user.picture_id:
                old_file = WebFileStorage.get(id=old_picture_id)
                os.unlink(old_file.filepath)
                old_file.delete()
        except Exception as exc:  # pylint: disable=broad-except
            print(exc)

        g.user.picture_id = web_file.id
        g.user.save()

    def save_profile_picture_to_disk(self, original_filename, filedata, suffix):
        filename_fragment = hashlib.sha256(os.urandom(64)).hexdigest()[:10]
        filename = f"profile_{suffix}_{filename_fragment}"
        filepath = f"storage/profile_pictures/{filename}"
        with open(filepath, "wb") as file:
            file.write(filedata)

        return original_filename, filepath

    def github_callback(self, req_code):
        oauth_response = requests.post("https://github.com/login/oauth/access_token",
                                       headers={
                                           "Accept": "application/json",
                                       },
                                       params={
                                           "code": req_code,
                                           "client_id": current_app.config.get("GITHUB_CLIENT_ID"),
                                           "client_secret": current_app.config.get("GITHUB_CLIENT_SECRET"),
                                       })

        oauth_data = oauth_response.json()

        user_info = requests.get("https://api.github.com/user",
                                 headers={
                                     "Accept": "application/json",
                                     "Authorization": f"token {oauth_data.get('access_token')}"
                                 }).json()
        email_info = requests.get("https://api.github.com/user/emails",
                                  headers={
                                      "Accept": "application/json",
                                      "Authorization": f"token {oauth_data.get('access_token')}"
                                  }).json()

        organizations = requests.get("https://api.github.com/user/orgs", headers={
            "Accept": "application/json",
            "Authorization": f"token {oauth_data.get('access_token')}"
        }).json()
        temp_password = None
        required_organizations = current_app.config.get("GITHUB_REQUIRED_ORGANIZATIONS")
        if required_organizations:
            logins = set([org["login"] for org in organizations])  # pylint: disable=consider-using-set-comprehension
            required_organizations = set(required_organizations)
            if len(logins.intersection(required_organizations)) == 0:
                raise GithubOrganizationMissingError(
                    "Not a member of a required organization or missing organization scope")

        try:
            user = User.get(username=user_info.get("login"))
        except User.DoesNotExist:
            user = User()
            user.username = user_info.get("login")
            user.email = email_info[-1].get("email")
            user.full_name = user_info.get("name")
            user.registration_date = datetime.datetime.utcnow()
            user.roles = ["ROLE_USER"]
            temp_password = base64.encodebytes(
                os.urandom(48)).decode("ascii").strip()
            user.password = generate_password_hash(temp_password)

            avatar_url: str = user_info.get("avatar_url")
            avatar = requests.get(avatar_url).content
            avatar_name = avatar_url.split("/")[-1]
            filename, filepath = self.save_profile_picture_to_disk(avatar_name, avatar, user.username)

            web_file = WebFileStorage()
            web_file.filename = filename
            web_file.filepath = filepath
            web_file.save()
            user.picture_id = web_file.id
            user.save()

        try:
            tokens = list(UserOauthToken.filter(user_id=user.id).all())
            github_token = [
                token for token in tokens if token["kind"] == "github"][0]
            github_token.token = oauth_data.get('access_token')
            github_token.save()
        except (UserOauthToken.DoesNotExist, IndexError):
            github_token = UserOauthToken()
            github_token.kind = "github"
            github_token.user_id = user.id
            github_token.token = oauth_data.get('access_token')
            github_token.save()

        session.clear()
        session["user_id"] = str(user.id)
        if temp_password:
            return {
                "password": temp_password,
                "first_login": True
            }
        return None

    def get_jobs_for_user(self, user: User):
        runs = self.session.execute(self.jobs_by_assignee, parameters=(str(user.id),))
        schedules = self.get_schedules_for_user(user)
        valid_runs = []
        today = datetime.datetime.now()
        month_ago = today - datetime.timedelta(days=30)
        for run in runs:
            run_date = datetime.datetime.fromtimestamp(run["start_time"])
            if user.id == UUID(run["assignee"]) and run_date >= month_ago:
                valid_runs.append(run)
                continue
            for schedule in schedules:
                if not run["release_name"] == schedule["release"]:
                    continue
                if not schedule["period_start"] < run_date < schedule["period_end"]:
                    continue
                if run["assignee"] in schedule["assignees"]:
                    valid_runs.append(run)
                    continue
                if run["group"] in schedule["groups"]:
                    valid_runs.append(run)
                    break
                filtered_tests = [test for test in schedule["tests"]
                                  if check_scheduled_test(run["name"], run["group"], test)]
                if len(filtered_tests) > 0:
                    valid_runs.append(run)
                    break
        return valid_runs

    def get_schedules_for_user(self, user: User):
        all_assigned_schedules = ArgusReleaseScheduleAssignee.filter(assignee=user.id).all()
        schedule_keys = [(schedule_assignee.release, schedule_assignee.schedule_id)
                         for schedule_assignee in all_assigned_schedules]
        schedules = []
        today = datetime.datetime.utcnow()
        last_week = today - datetime.timedelta(days=today.weekday() + 1)
        for release, schedule_id in schedule_keys:
            schedule = dict(ArgusReleaseSchedule.get(release=release, schedule_id=schedule_id).items())
            if last_week > schedule["period_end"]:
                continue
            tests = ArgusReleaseScheduleTest.filter(schedule_id=schedule_id).all()
            schedule["tests"] = [test.name for test in tests]
            groups = ArgusReleaseScheduleGroup.filter(schedule_id=schedule_id).all()
            schedule["groups"] = [group.name for group in groups]
            assignees = ArgusReleaseScheduleAssignee.filter(schedule_id=schedule_id).all()
            schedule["assignees"] = [assignee.assignee for assignee in assignees]
            schedules.append(schedule)

        return schedules
