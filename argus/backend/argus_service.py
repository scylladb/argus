import time
import json
import re
from typing import Callable
from collections import namedtuple
from uuid import UUID, uuid4
import datetime
from cassandra.cqlengine import ValidationError
import humanize
from flask import g, current_app
import requests

from cassandra.cqlengine.models import _DoesNotExist
from argus.backend.db import ScyllaCluster
from argus.db.testrun import TestRun, TestStatus
from argus.backend.models import (
    ArgusGithubIssue,
    ArgusRelease,
    ArgusReleaseGroup,
    ArgusReleaseGroupTest,
    ArgusTestRunComment,
    ArgusEvent,
    ArgusEventTypes,
    User,
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


class ArgusService:
    def __init__(self, session=None):
        self.session = session if session else ScyllaCluster.get_session()
        self.db = ScyllaCluster.get()
        self.github_headers = {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"token {current_app.config['GITHUB_ACCESS_TOKEN']}"
        }
        self.runs_by_id_stmt = self.db.prepare(f"SELECT * FROM {TestRun.table_name()} WHERE id in ?")

    def terminate_session(self):
        pass  # TODO: Remove this

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
            except _DoesNotExist:
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
            response[group_name]["tests"] = self.create_tests(tests=group_definition.get("tests", []),
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
        ts_begin = time.time()
        statement = self.db.prepare(
            f"SELECT id, name, group, release_name, build_job_url, build_job_name, status, start_time, end_time, heartbeat FROM {TestRun.table_name()}")
        rows = self.session.execute(statement).all()
        ts_fetch = time.time()
        for row in rows:
            row["natural_heartbeat"] = humanize.naturaltime(
                datetime.datetime.fromtimestamp(row["heartbeat"]))
            row["natural_start_time"] = humanize.naturaltime(
                datetime.datetime.fromtimestamp(row["start_time"]))
            row["natural_end_time"] = humanize.naturaltime(
                datetime.datetime.fromtimestamp(row["end_time"]))
        ts_human_time_iter = time.time()

        print(
            f"Fetch took: {ts_fetch - ts_begin}s\nProcessing Took: {ts_human_time_iter - ts_fetch}s\nTotal: {ts_human_time_iter - ts_begin}s")
        return sorted(rows, key=lambda x: x["start_time"], reverse=True)

    def load_test_run(self, test_run_id: UUID):
        run = TestRun.from_id(test_id=test_run_id)
        comments = None
        return run, comments

    def get_comments(self, test_id: UUID) -> list[ArgusTestRunComment]:
        return sorted(ArgusTestRunComment.filter(test_run_id=test_id).all(), key=lambda c: c.posted_at)

    def get_user_info(self, payload: dict) -> dict:
        users = User.all()
        return {str(user.id): user.to_json() for user in users}

    def post_comment(self, payload: dict) -> list[ArgusTestRunComment]:
        test_id: str = payload["test_id"]
        message: str = payload["message"]
        message_stripped = message.replace("<", "&lt;").replace(">", "&gt;")
        release_name_stmt = self.db.prepare(
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
        statement = self.db.prepare(
            f"SELECT id, release_name, name, status, start_time FROM {TestRun.table_name()} WHERE release_name = ?")
        runs = self.session.execute(
            statement, parameters=(payload["release_name"],)).all()
        runs = sorted(runs, key=lambda val: val["start_time"], reverse=True)
        for test in payload.get("tests", []):
            runs_for_test = [
                run for run in runs if run["name"].startswith(test["name"])]
            response[test["name"]] = runs_for_test[0]["status"] if len(
                runs_for_test) > 0 else "none"

        return response

    def get_runs_for_release_group(self, release_name: str, group_name: str, limit=10):
        query = self.session.execute("SELECT id, name, group, release_name, build_job_name, build_job_url, "
                                     "status, start_time, end_time, heartbeat"
                                     f" FROM {TestRun.table_name()}")
        rows = query.all()
        rows = [row for row in rows if row["release_name"]
                == release_name and row["group"] == group_name]
        rows = rows
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

    def get_runs_by_name_for_release_group(self, test_name: str, release_name: str, limit=10):
        statement = self.db.prepare("SELECT id, name, group, release_name, build_job_name, build_job_url, "
                                    "status, start_time, end_time, heartbeat "
                                    f"FROM {TestRun.table_name()} WHERE release_name = ?")
        rows = self.session.execute(statement, parameters=(release_name,)).all()
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

    """
    Example body:
    {
        "master": {
            "force": true, // Forcefully retrieve stats even if release is disabled
            "groups": ["longevity", "artifacts"],
            "tests": ["longevity-100gb", "artifacts-ami"]
        }
    }
    Both groups and tests are considered prefixes to test_run names
    """

    def collect_stats(self, payload: dict) -> dict:

        response = {
            "releases": {

            }
        }
        all_releases = {release.name: release for release in ArgusRelease.all()}

        all_groups = ArgusReleaseGroup.all()
        all_groups_by_id = {group.id: group for group in all_groups}

        all_groups_by_release_id = {}
        for release in all_releases.values():
            all_groups_by_release_id[release.id] = [group for group in all_groups if group.release_id == release.id]

        all_tests = ArgusReleaseGroupTest.all()
        all_tests_by_release_id = {}
        for release in all_releases.values():
            all_tests_by_release_id[release.id] = [test for test in all_tests if test.release_id == release.id]
        group_stats_body = {
            "total": 0,
            **{e.value: 0 for e in TestStatus},
            "not_run": 0
        }
        run_by_release_stats_statement = self.db.prepare(
            f"SELECT id, name, group, release_name, status, start_time, end_time, heartbeat FROM {TestRun.table_name()} WHERE release_name = ?")
        for release_name, release_body in payload.items():
            release = all_releases[release_name]
            override = release_body.get("force", False)
            release_stats = {
                "total": 0,
                **{e.value: 0 for e in TestStatus},
                "not_run": 0,
                "lastStatus": "unknown",
                "groups": {
                    group.name: dict(**group_stats_body) for group in all_groups_by_release_id[release.id]
                },
                "tests": {},
                "disabled": False,
            }
            if not all_releases[release_name].enabled and not override:
                release_stats["disabled"] = True
                response["releases"][release_name] = release_stats
                continue

            rows = self.session.execute(run_by_release_stats_statement, parameters=(release_name,))
            rows = sorted(rows, key=lambda r: r["start_time"], reverse=True)
            release_tests = [test for test in all_tests_by_release_id[release.id]]
            for test in release_tests:
                test_group = all_groups_by_id[test.group_id]
                release_stats["total"] += 1
                run = first(rows, test.name, predicate=lambda elem, val: re.match(f"^{val}(-test)?$", elem["name"]))
                if not run:
                    release_stats["tests"][test.name] = "unknown"
                    release_stats["not_run"] += 1
                    release_stats["groups"][test_group.name]["not_run"] += 1
                    release_stats["groups"][test_group.name]["total"] += 1
                    continue
                release_stats["tests"][test.name] = run["status"]
                release_stats["groups"][test_group.name][run["status"]] += 1
                release_stats["groups"][test_group.name]["total"] += 1
                release_stats[run["status"]] += 1

            response["releases"][release_name] = release_stats

        return response

    def poll_test_runs(self, payload: dict):
        limit = payload["limit"]
        runs: dict = payload["runs"]

        statement = self.db.prepare("SELECT id, name, group, release_name, build_job_name, build_job_url, "
                                    "status, start_time, end_time, heartbeat "
                                    f"FROM {TestRun.table_name()} WHERE release_name = ?")
        response = {}
        for uid, [release_name, test_name] in runs.items():
            rows = self.session.execute(
                statement, parameters=(release_name,), execution_profile="read_fast").all()
            rows = sorted(rows, key=lambda val: val["start_time"], reverse=True)
            for row in rows:
                row["build_number"] = int(
                    row["build_job_url"].rstrip("/").split("/")[-1])
            result = [
                row for row in rows
                if re.match(f"^{test_name}(-test)?$", row["name"])
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
        statement = self.db.prepare(
            'INSERT INTO argus.argus_event ("id", "release_id", "group_id", "test_id", "run_id", "user_id", "kind", "body", "created_at") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)')
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
        self.session.execute(query=statement, parameters=params)
        pass

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
        test_name = test_run.run_info.details.name.rstrip("-test")
        test = [test for test in ArgusReleaseGroupTest.all() if test.release_id ==
                release.id and test.name.startswith(test_name)]
        test = test[0]
        old_status = test_run.run_info.results.status
        test_run.run_info.results.status = new_status
        test_run.save()

        self.send_event(kind=ArgusEventTypes.TestRunStatusChanged,
                        body={
                            "message": "Status was changed from {old_status} to {new_status} by {username}",
                            "old_status": old_status.value,
                            "new_status": new_status.value,
                            "username": g.user.username
                        }, user_id=g.user.id, run_id=test_run.id, release_id=test.release_id, group_id=test.group_id, test_id=test.id)
        return {
            "test_run_id": test_run_id,
            "status": new_status
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
        test_name = test_run.run_info.details.name.rstrip("-test")
        test = [test for test in ArgusReleaseGroupTest.filter(
            name=test_name).all() if test.release_id == release.id][0]
        old_assignee = test_run.assignee
        old_assignee = User.get(id=old_assignee) if old_assignee else None
        test_run.assignee = new_assignee.id
        test_run.save()

        self.send_event(kind=ArgusEventTypes.AssigneeChanged,
                        body={
                            "message": "Assignee was changed from \"{old_user}\" to \"{new_user}\" by {username}",
                            "old_user": old_assignee.username if old_assignee else "None",
                            "new_user": new_assignee.username,
                            "username": g.user.username
                        }, user_id=g.user.id, run_id=test_run.id, release_id=test.release_id, group_id=test.group_id, test_id=test.id)
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

    """
    Example payload:
    {
        "issue_url": "https://github.com/example/repo/issues/6"
        "run_id": "abcdef-5354235-1232145-dd"
    }
    """

    def submit_github_issue(self, payload: dict) -> dict:
        issue_url = payload.get("issue_url")
        run_id = payload.get("run_id")
        if not run_id:
            raise Exception("Run Id missing from request")
        if not issue_url:
            raise Exception("Missing or empty issue url")

        match = re.match(
            r"http(s)?://(www\.)?github\.com/(?P<owner>[\w\d]+)/(?P<repo>[\w\d\-_]+)/(?P<type>issues|pull)/(?P<issue_number>\d+)(/)?",
            issue_url)
        if not match:
            raise Exception("URL doesn't match Github schema")

        run = self.session.execute(self.runs_by_id_stmt, parameters=([UUID(run_id)],)).one()
        test_name = run["name"].rstrip("-test")
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

        issue_state = requests.get(f"https://api.github.com/repos/{new_issue.owner}/{new_issue.repo}/issues/{new_issue.issue_number}",
                                   headers=self.github_headers).json()

        new_issue.title = issue_state.get("title")
        new_issue.url = issue_state.get("html_url")
        new_issue.last_status = issue_state.get("state")
        new_issue.save()

        self.send_event(kind=ArgusEventTypes.TestRunIssueAdded,
                        body={
                            "message": "An issue titled \"{title}\" was added by {username}",
                            "username": g.user.username,
                            "url": issue_url,
                            "title": issue_state.get("title"),
                            "state": issue_state.get("state"),
                        }, user_id=g.user.id, run_id=new_issue.run_id, release_id=new_issue.release_id, group_id=new_issue.group_id, test_id=new_issue.test_id)

        response = {
            **dict([o for o in new_issue.items()]),
            "title": issue_state.get("title"),
            "state": issue_state.get("state"),
        }

        return response
    """
    Example payload:
    {
        "filter_key": "release_id",
        "id": "abcdef-bcdedf-00000",
    }
    """

    def get_github_issues(self, payload: dict) -> dict:
        filter_key = payload.get("filter_key")
        if not filter_key:
            raise Exception("A filter_key field is required")

        if filter_key not in ["release_id", "group_id", "test_id", "run_id", "user_id"]:
            raise Exception(
                "filter_key can only be one of: \"release_id\", \"group_id\", \"test_id\", \"run_id\", \"user_id\"")

        filter_id = payload.get("id")
        if not filter_id:
            raise Exception("A filter_id field is required")

        filter_id = UUID(filter_id)
        all_issues = ArgusGithubIssue.filter(**{filter_key: filter_id}).all()

        response = [dict([o for o in issue.items()]) for issue in all_issues]
        return response

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

    def get_github_issue_state(self, payload: dict) -> dict:
        issues = payload.get("issues")
        if not issues:
            raise Exception("Empty request")
        response = {}
        for num, repo, owner in issues:
            issue_state = requests.get(f"https://api.github.com/repos/{owner}/{repo}/issues/{num}",
                                       headers=self.github_headers).json()
            response[issue_state.get("html_url")] = issue_state.get("state")

        return response
