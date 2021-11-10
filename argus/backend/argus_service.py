import time
from uuid import UUID
import datetime
import humanize
from flask import g

from cassandra.cluster import ExecutionProfile
from cassandra import ConsistencyLevel
from cassandra.cqlengine.models import _DoesNotExist
from argus.backend.db import ScyllaCluster
from argus.db.testrun import TestRun, TestStatus
from argus.backend.models import (
    ArgusRelease,
    ArgusReleaseGroup,
    ArgusReleaseGroupTest,
    User,
    WebRunComment,
    WebRunComments
)


class ArgusService:
    def __init__(self, session=None):
        self.session = session if session else ScyllaCluster.get_session()
        self.db = ScyllaCluster.get()

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
            "SELECT id, name, group, release_name, build_job_url, build_job_name, status, start_time, end_time, heartbeat FROM test_runs")
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

    def get_comments(self, test_id: UUID) -> WebRunComments:
        try:
            comments = WebRunComments.get(test_id=test_id)
        except _DoesNotExist:
            comments = WebRunComments()
            comments.test_id = test_id
            comments.save()
        return comments

    def get_user_info(self, payload: dict) -> dict:
        users = User.all()
        return {str(user.id): user.to_json() for user in users}

    def post_comment(self, payload: dict) -> WebRunComment:
        test_id: str = payload["test_id"]
        comments = self.get_comments(test_id=UUID(test_id))
        message: str = payload["message"]
        message_stripped = message.replace("<", "&lt;").replace(">", "&gt;")
        comment = WebRunComment()
        comment.mentions = []
        comment.message = message_stripped
        comment.user_id = g.user.id
        comment.timestamp = time.time()
        comments.comments.append(comment)
        comments.save()

        return comments

    def get_releases(self):
        web_releases = list(ArgusRelease.all())
        return sorted(web_releases, key=lambda val: val.name)

    def get_groups_for_release(self, release_id: UUID):
        release_groups = ArgusReleaseGroup.filter(release_id=release_id)
        return sorted(release_groups, key=lambda val: val.name)

    def get_tests_for_release_group(self, group_id: UUID):
        tests = ArgusReleaseGroupTest.filter(group_id=group_id)
        return sorted(tests, key=lambda val: val.name)

    def get_test_last_run_status(self, payload: dict) -> dict:
        response = {}
        statement = self.db.prepare("SELECT id, release_name, name, status, start_time FROM test_runs WHERE release_name = ?")
        runs = self.session.execute(statement, parameters=(payload["release_name"],)).all()
        runs = sorted(runs, key=lambda val: val["start_time"], reverse=True)
        for test in payload.get("tests", []):
            runs_for_test = [run for run in runs if run["name"].startswith(test["name"])]
            response[test["name"]] = runs_for_test[0]["status"] if len(runs_for_test) > 0 else "none"

        return response

    def get_runs_for_release_group(self, release_name: str, group_name: str, limit=10):
        query = self.session.execute("SELECT id, name, group, release_name, build_job_name, build_job_url, "
                                     "status, start_time, end_time, heartbeat"
                                     " FROM test_runs")
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
        query = self.session.execute("SELECT id, name, group, release_name, build_job_name, build_job_url, "
                                     "status, start_time, end_time, heartbeat"
                                     " FROM test_runs")
        rows = query.all()
        rows = [row for row in rows if row["release_name"]
                == release_name and row["name"].startswith(test_name)]
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
        response = {
            "releases": {

            },
            "groups": {

            },
            "tests": {

            }
        }

        test_runs = self.session.execute(
            "SELECT id, name, group, release_name, status, start_time, end_time, heartbeat FROM test_runs")
        test_runs = sorted(
            test_runs, key=lambda val: val["start_time"], reverse=True)

        releases = payload.get("releases")
        if releases:
            for release in releases["items"]:
                release_runs = [
                    run for run in test_runs if run["release_name"] == release][:releases["limit"]]
                stats = {e.value: len(
                    [run for run in release_runs if run["status"] == e.value]) for e in TestStatus}
                stats["total"] = len(release_runs)
                stats["lastStatus"] = release_runs[0]["status"] if len(release_runs) > 0 else "none"
                response["releases"][release] = stats

        groups = payload.get("groups")
        if groups:
            for release, group in groups["items"]:
                release_group_runs = [
                    run
                    for run in test_runs
                    if run["release_name"] == release and run["group"].startswith(group)
                ][:groups["limit"]]

                stats = {e.value: len(
                    [run for run in release_group_runs if run["status"] == e.value]) for e in TestStatus}
                stats["total"] = len(release_group_runs)
                stats["lastStatus"] = release_group_runs[0]["status"] if len(release_group_runs) > 0 else "none"
                release_res = response["groups"].get(release, {})
                release_res[group] = stats
                response["groups"][release] = release_res

        tests = payload.get("tests")
        if tests:
            for release, group, test in tests["items"]:
                tests_runs = [
                    run
                    for run in test_runs
                    if run["release_name"] == release and run["group"].startswith(group) and run["name"].startswith(test)
                ][:tests["limit"]]

                stats = {e.value: len(
                    [run for run in tests_runs if run["status"] == e.value]) for e in TestStatus}
                stats["total"] = len(tests_runs)
                stats["lastStatus"] = tests_runs[0]["status"] if len(tests_runs) > 0 else "none"
                release_group_res = response["tests"].get(release, {})
                tests_res = release_group_res.get(group, {})
                tests_res[test] = stats
                release_group_res[group] = tests_res
                response["tests"][release] = release_group_res

        return response

    def poll_test_runs(self, payload: dict):
        ts_begin = time.time()
        limit = payload["limit"]
        runs: dict = payload["runs"]
    
        statement = self.db.prepare("SELECT id, name, group, release_name, build_job_name, build_job_url, "
                                     "status, start_time, end_time, heartbeat"
                                     " FROM test_runs")
        rows = self.session.execute(statement, execution_profile="read_fast").all()
        ts_after_execute = time.time()
        rows = sorted(rows, key=lambda val: val["start_time"], reverse=True)
        for row in rows:
            row["natural_heartbeat"] = humanize.naturaltime(
                datetime.datetime.fromtimestamp(row["heartbeat"]))
            row["natural_start_time"] = humanize.naturaltime(
                datetime.datetime.fromtimestamp(row["start_time"]))
            row["natural_end_time"] = humanize.naturaltime(
                datetime.datetime.fromtimestamp(row["end_time"]))
            row["build_number"] = int(
                row["build_job_url"].rstrip("/").split("/")[-1])
        ts_after_additional_data = time.time()
        response = {}
        for uid, [release_name, test_name] in runs.items():
            result = [
                row for row in rows
                if row["release_name"] == release_name and row["name"].startswith(test_name)
            ][:limit]
            response[uid] = result
        ts_after_filter = time.time()

        print("Total: {}s\nAfter Execute: {}s\nAfter extra data: {}s\nAfter filter: {}s\n".format(ts_after_filter - ts_begin, ts_after_execute - ts_begin, ts_after_additional_data - ts_after_execute, ts_after_filter - ts_after_additional_data))

        return response
