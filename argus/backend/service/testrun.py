from collections import defaultdict
from datetime import datetime, timedelta, UTC
from functools import reduce
import json
import logging
import re
from sys import prefix
import time
from typing import Any
from uuid import UUID

import boto3
import magic
import requests
from flask import current_app, g
from botocore.exceptions import ClientError
from cassandra.util import uuid_from_time
from cassandra.query import BatchStatement, ConsistencyLevel
from cassandra.cqlengine.query import BatchQuery
from argus.backend.db import ScyllaCluster

from argus.backend.models.pytest import PytestResultTable, PytestUserField
from argus.backend.models.web import (
    ArgusEvent,
    ArgusEventTypes,
    ArgusNotificationSourceTypes,
    ArgusNotificationTypes,
    ArgusRelease,
    ArgusTest,
    ArgusTestRunComment,
    User,
)

from argus.backend.plugins.core import PluginInfoBase, PluginModelBase

from argus.backend.plugins.loader import AVAILABLE_PLUGINS
from argus.backend.events.event_processors import EVENT_PROCESSORS
from argus.backend.plugins.sct.testrun import SCTTestRun
from argus.backend.plugins.sirenada.model import SirenadaRun
from argus.backend.service.event_service import EventService
from argus.backend.service.notification_manager import NotificationManagerService
from argus.backend.service.stats import ComparableTestStatus
from argus.backend.util.common import chunk, get_build_number, strip_html_tags
from argus.common.enums import PytestStatus, TestInvestigationStatus, TestStatus

LOGGER = logging.getLogger(__name__)


class TestRunServiceException(Exception):
    pass


class TestRunService:
    __test__ = False  # prevent pytest from collecting this production class as a test
    ASSIGNEE_PLACEHOLDER = "none-none-none"

    RE_MENTION = r"@[A-Za-z\d](?:[A-Za-z\d]|-(?=[A-Za-z\d])){0,38}"

    plugins = AVAILABLE_PLUGINS

    def __init__(self) -> None:
        self.notification_manager = NotificationManagerService()
        self.s3 = boto3.client(service_name="s3", aws_access_key_id=current_app.config.get(
            "AWS_CLIENT_ID"), aws_secret_access_key=current_app.config.get("AWS_CLIENT_SECRET"))

    def get_plugin(self, plugin_name: str) -> PluginInfoBase | None:
        return self.plugins.get(plugin_name)

    def get_run(self, run_type: str, run_id: UUID) -> PluginModelBase:
        plugin = self.plugins.get(run_type)
        if plugin:
            try:
                return plugin.model.get(id=run_id)
            except plugin.model.DoesNotExist:
                return None

    def get_run_response(self, run_type: str, run_id: UUID) -> dict | None:
        plugin = self.plugins.get(run_type)
        if plugin:
            return plugin.model.get_run_response(run_id)

    def get_runs_by_test_id(self, test_id: UUID, additional_runs: list[UUID], limit: int = 10):
        test: ArgusTest = ArgusTest.get(id=test_id)
        plugin = self.get_plugin(plugin_name=test.plugin_name)
        if not plugin:
            return []

        last_runs: list[dict] = plugin.model.get_run_meta_by_build_id(build_id=test.build_system_id, limit=limit)
        last_runs_ids = [run["id"] for run in last_runs]
        for added_run in additional_runs:
            if added_run not in last_runs_ids:
                last_runs.extend(plugin.model.get_run_meta_by_run_id(run_id=added_run))

        for row in last_runs:
            row["build_number"] = get_build_number(build_job_url=row["build_job_url"])

        last_runs = sorted(last_runs, reverse=True, key=lambda run: (
            run["build_number"], ComparableTestStatus(TestStatus(run["status"]))))

        return last_runs

    def get_runs_by_id(self, test_id: UUID, runs: list[UUID]):  # FIXME: Not needed, use get_run and individual polling
        # This is a batch request.
        test = ArgusTest.get(id=test_id)
        plugin = self.get_plugin(plugin_name=test.plugin_name)
        polled_runs: list[PluginModelBase] = []
        for run_id in runs:
            try:
                run: PluginModelBase = plugin.model.get(id=run_id)
                polled_runs.append(run)
            except plugin.model.DoesNotExist:
                pass

        response = {str(run.id): run for run in polled_runs}
        return response

    def change_run_status(self, test_id: UUID, run_id: UUID, new_status: TestStatus):
        try:
            test = ArgusTest.get(id=test_id)
        except ArgusTest.DoesNotExist as exc:
            raise TestRunServiceException("Test entity does not exist for provided test_id", test_id) from exc
        plugin = self.get_plugin(plugin_name=test.plugin_name)
        run: PluginModelBase = plugin.model.get(id=run_id)
        old_status = run.status
        run.status = new_status.value
        run.save()

        EventService.create_run_event(
            kind=ArgusEventTypes.TestRunStatusChanged,
            body={
                "message": "Status was changed from {old_status} to {new_status} by {username}",
                "old_status": old_status,
                "new_status": new_status.value,
                "username": g.user.username
            },
            user_id=g.user.id,
            run_id=run.id,
            release_id=test.release_id,
            group_id=test.group_id,
            test_id=test.id
        )

        return {
            "test_run_id": run.id,
            "status": new_status
        }

    @staticmethod
    def _match_s3_link(link: str) -> re.Match:
        return re.match(r"(https:\/\/)?(?P<bucket>[\w\-]*)\.s3(?P<region>\.[\w\-\d]*)?\.amazonaws.com\/(?P<key>.+)", link)

    def get_log(self, plugin_name: str, run_id: UUID, log_name: str):
        plugin = self.get_plugin(plugin_name=plugin_name)
        run: PluginModelBase = plugin.model.get(id=run_id)

        link = {log[0]: log[1] for log in run.logs}.get(log_name)
        if not link:
            raise TestRunServiceException(f"Log name {log_name} not found.")
        match = self._match_s3_link(link)
        if not match:
            return link
        presigned_url = self.s3.generate_presigned_url(ClientMethod="get_object", Params={
                                                       "Bucket": match.group("bucket"), "Key": match.group("key")}, ExpiresIn=3600)

        return presigned_url

    def resolve_artifact_size(self, link: str):

        match = self._match_s3_link(link)

        if not match:
            res = requests.head(link)
            if res.status_code != 200:
                raise Exception("Error requesting resource")

            length = res.headers.get("Content-Length")
            if length:
                length = int(length)

            return length

        try:
            obj = self.s3.get_object(Bucket=match.group("bucket"), Key=match.group("key"))
            return obj["ContentLength"]
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code == 'NoSuchKey':
                raise TestRunServiceException(f"S3 object not found: {link}")
            elif error_code == 'AccessDenied':
                raise TestRunServiceException(f"Access denied to S3 object: {link}")
            else:
                raise TestRunServiceException(f"Error accessing S3 object: {e}")

    def proxy_stored_s3_image(self, plugin_name: str, run_id: UUID | str, image_name: str):
        plugin = self.get_plugin(plugin_name=plugin_name)
        run: SCTTestRun | SirenadaRun = plugin.model.get(id=run_id)
        match run:
            case SCTTestRun():
                screenshot = {scr.split("/")[-1]: scr for scr in run.screenshots}.get(image_name)
            case SirenadaRun():
                screenshot = {
                    scr.split("/")[-1]: scr for scr in [result.screenshot_file for result in run.results]}.get(image_name)

        match = self._match_s3_link(screenshot)
        if not match:
            return screenshot

        return self.s3.generate_presigned_url(ClientMethod="get_object", Params={"Bucket": match.group("bucket"), "Key": match.group("key")}, ExpiresIn=3600)

    def proxy_s3_file(self, bucket_name: str, bucket_path: str):
        if bucket_name not in current_app.config.get("S3_ALLOWED_BUCKETS", []):
            raise TestRunServiceException(f"{bucket_name} is not an allowed S3 bucket to pull from")

        obj = self.s3.get_object(Bucket=bucket_name, Key=bucket_path)
        header = obj["Body"].read(1024)
        mime = magic.from_buffer(header, mime=True)
        if mime.lower() not in current_app.config.get("S3_ALLOWED_MIME", []):
            raise TestRunServiceException(f"Cannot proxy mime type that is not allowed: {mime}", mime)

        return self.s3.generate_presigned_url(ClientMethod="get_object", Params={"Bucket": bucket_name, "Key": bucket_path}, ExpiresIn=600)

    def change_run_investigation_status(self, test_id: UUID, run_id: UUID, new_status: TestInvestigationStatus):
        test = ArgusTest.get(id=test_id)
        plugin = self.get_plugin(plugin_name=test.plugin_name)
        run: PluginModelBase = plugin.model.get(id=run_id)
        old_status = run.investigation_status
        run.investigation_status = new_status.value
        run.save()

        EventService.create_run_event(
            kind=ArgusEventTypes.TestRunStatusChanged,
            body={
                "message": "Investigation status was changed from {old_status} to {new_status} by {username}",
                "old_status": old_status,
                "new_status": new_status.value,
                "username": g.user.username
            },
            user_id=g.user.id,
            run_id=run.id,
            release_id=test.release_id,
            group_id=test.group_id,
            test_id=test.id
        )

        return {
            "test_run_id": run.id,
            "investigation_status": new_status
        }

    def change_run_assignee(self, test_id: UUID, run_id: UUID, new_assignee: UUID | None):
        test = ArgusTest.get(id=test_id)
        plugin = self.get_plugin(plugin_name=test.plugin_name)
        if not plugin:
            return {
                "test_run_id": run.id,
                "assignee": None
            }

        run: PluginModelBase = plugin.model.get(id=run_id)
        old_assignee = run.assignee
        run.assignee = new_assignee
        run.save()

        if new_assignee:
            new_assignee_user = User.get(id=new_assignee)
        else:
            new_assignee_user = None
        if old_assignee:
            try:
                old_assignee_user = User.get(id=old_assignee)
            except User.DoesNotExist:
                LOGGER.warning("Non existent assignee was present on the run %s for test %s: %s",
                               run_id, test_id, old_assignee)
                old_assignee = None
        EventService.create_run_event(
            kind=ArgusEventTypes.AssigneeChanged,
            body={
                "message": "Assignee was changed from \"{old_user}\" to \"{new_user}\" by {username}",
                "old_user": old_assignee_user.username if old_assignee else "None",
                "new_user": new_assignee_user.username if new_assignee else "None",
                "username": g.user.username
            },
            user_id=g.user.id,
            run_id=run.id,
            release_id=test.release_id,
            group_id=test.group_id,
            test_id=test.id
        )
        if new_assignee_user and new_assignee_user.id != g.user.id:
            self.notification_manager.send_notification(
                receiver=new_assignee_user.id,
                sender=g.user.id,
                notification_type=ArgusNotificationTypes.AssigneeChange,
                source_type=ArgusNotificationSourceTypes.TestRun,
                source_id=run.id,
                source_message=str(run.test_id),
                content_params={
                    "username": g.user.username,
                    "run_id": run.id,
                    "test_id": test.id,
                    "build_id": run.build_id,
                    "build_number": get_build_number(run.build_job_url),
                }
            )
        return {
            "test_run_id": run.id,
            "assignee": str(new_assignee_user.id) if new_assignee_user else None
        }

    def get_run_comment(self, comment_id: UUID):
        try:
            return ArgusTestRunComment.get(id=comment_id)
        except ArgusTestRunComment.DoesNotExist:
            return None

    def get_run_comments(self, run_id: UUID):
        return sorted(ArgusTestRunComment.filter(test_run_id=run_id).all(), key=lambda c: c.posted_at)

    def post_run_comment(self, test_id: UUID, run_id: UUID, message: str, reactions: dict, mentions: list[str]):
        message_stripped = strip_html_tags(message)

        mentions = set(mentions)
        for potential_mention in re.findall(self.RE_MENTION, message_stripped):
            if user := User.exists_by_name(potential_mention.lstrip("@")):
                mentions.add(user) if user.id != g.user.id else None

        test: ArgusTest = ArgusTest.get(id=test_id)
        plugin = self.get_plugin(test.plugin_name)
        release: ArgusRelease = ArgusRelease.get(id=test.release_id)
        comment = ArgusTestRunComment()
        comment.test_id = test.id
        comment.message = message_stripped
        comment.reactions = reactions
        comment.mentions = [m.id for m in mentions]
        comment.test_run_id = run_id
        comment.release_id = release.id
        comment.user_id = g.user.id
        comment.posted_at = time.time()
        comment.save()

        run: PluginModelBase = plugin.model.get(id=run_id)
        build_number = get_build_number(build_job_url=run.build_job_url)
        for mention in mentions:
            params = {
                "username": g.user.username,
                "run_id": comment.test_run_id,
                "test_id": test.id,
                "build_id": run.build_id,
                "build_number": build_number,
            }
            self.notification_manager.send_notification(
                receiver=mention.id,
                sender=comment.user_id,
                notification_type=ArgusNotificationTypes.Mention,
                source_type=ArgusNotificationSourceTypes.Comment,
                source_id=comment.id,
                source_message=comment.message,
                content_params=params
            )

        EventService.create_run_event(kind=ArgusEventTypes.TestRunCommentPosted, body={
            "message": "A comment was posted by {username}",
            "username": g.user.username
        }, user_id=g.user.id, run_id=run_id, release_id=release.id, test_id=test.id)

        return self.get_run_comments(run_id=run_id)

    def delete_run_comment(self, comment_id: UUID, test_id: UUID, run_id: UUID):
        comment: ArgusTestRunComment = ArgusTestRunComment.get(id=comment_id)
        if comment.user_id != g.user.id:
            raise Exception("Unable to delete other user comments")
        comment.delete()

        EventService.create_run_event(kind=ArgusEventTypes.TestRunCommentDeleted, body={
            "message": "A comment was deleted by {username}",
            "username": g.user.username
        }, user_id=g.user.id, run_id=run_id, release_id=comment.release_id, test_id=test_id)

        return self.get_run_comments(run_id=run_id)

    def update_run_comment(self, comment_id: UUID, test_id: UUID, run_id: UUID, message: str, mentions: list[str], reactions: dict):
        comment: ArgusTestRunComment = ArgusTestRunComment.get(id=comment_id)
        if comment.user_id != g.user.id:
            raise Exception("Unable to edit other user comments")
        comment.message = strip_html_tags(message)
        comment.reactions = reactions
        comment.mentions = mentions
        comment.save()

        EventService.create_run_event(kind=ArgusEventTypes.TestRunCommentUpdated, body={
            "message": "A comment was edited by {username}",
            "username": g.user.username
        }, user_id=g.user.id, run_id=run_id, release_id=comment.release_id, test_id=test_id)

        return self.get_run_comments(run_id=run_id)

    def get_run_events(self, run_id: UUID):
        response = {}
        all_events = ArgusEvent.filter(run_id=run_id).all()
        all_events = sorted(all_events, key=lambda ev: ev.created_at)
        response["run_id"] = run_id
        response["raw_events"] = [dict(event.items()) for event in all_events]
        response["events"] = {
            str(event.id): EVENT_PROCESSORS.get(event.kind)(json.loads(event.body))
            for event in all_events
        }
        return response

    def resolve_run_build_id_and_number_multiple(self, runs: list[tuple[UUID, UUID]]) -> dict[UUID, dict[str, Any]]:
        test_ids = [r[0] for r in runs]
        all_tests: list = []
        for id_slice in chunk(test_ids):
            all_tests.extend(ArgusTest.filter(id__in=id_slice).all())

        tests: dict[str, ArgusTest] = {str(t.id): t for t in all_tests}
        runs_by_plugin = reduce(lambda acc, val: acc[tests[val[0]].plugin_name].append(
            val[1]) or acc, runs, defaultdict(list))
        all_runs = {}
        for plugin, run_ids in runs_by_plugin.items():
            model = AVAILABLE_PLUGINS.get(plugin).model
            model_runs = []
            for run_id in run_ids:
                model_runs.append(model.filter(id=run_id).only(
                    ["build_id", "start_time", "build_job_url", "id", "test_id"]).get())
            all_runs.update(
                {str(run["id"]): {**run, "build_number": get_build_number(run["build_job_url"])} for run in model_runs})

        return all_runs

    def terminate_stuck_runs(self):
        sct = AVAILABLE_PLUGINS.get("scylla-cluster-tests").model
        now = datetime.now(UTC)
        stuck_period = now - timedelta(minutes=45)
        stuck_runs_running = sct.filter(heartbeat__lt=int(
            stuck_period.timestamp()), status=TestStatus.RUNNING.value).allow_filtering().all()
        stuck_runs_created = sct.filter(heartbeat__lt=int(
            stuck_period.timestamp()), status=TestStatus.CREATED.value).allow_filtering().all()

        all_stuck_runs = [*stuck_runs_running, *stuck_runs_created]
        LOGGER.info("Found %s stuck runs", len(all_stuck_runs))

        for run in all_stuck_runs:
            LOGGER.info("Will set %s as ABORTED", run.id)
            old_status = run.status
            run.status = TestStatus.ABORTED.value
            run.save()

            EventService.create_run_event(
                kind=ArgusEventTypes.TestRunStatusChanged,
                body={
                    "message": "Run was automatically terminated due to not responding for more than 45 minutes "
                               "(Status changed from {old_status} to {new_status}) by {username}",
                    "old_status": old_status,
                    "new_status": run.status,
                    "username": g.user.username
                },
                user_id=g.user.id,
                run_id=run.id,
                release_id=run.release_id,
                group_id=run.group_id,
                test_id=run.test_id
            )

        return len(all_stuck_runs)

    def ignore_jobs(self, test_id: UUID, reason: str):
        test: ArgusTest = ArgusTest.get(id=test_id)
        plugin = self.get_plugin(plugin_name=test.plugin_name)

        if not reason:
            raise TestRunServiceException("Reason for ignore cannot be empty")

        cluster = ScyllaCluster.get()
        batch = BatchStatement(consistency_level=ConsistencyLevel.QUORUM)
        event_batch = BatchQuery()
        jobs_affected = 0
        for job in plugin.model.get_jobs_meta_by_test_id(test.id):
            if job["status"] != TestStatus.PASSED and job["investigation_status"] == TestInvestigationStatus.NOT_INVESTIGATED:
                batch.add(
                    plugin.model.prepare_investigation_status_update_query(
                        build_id=job["build_id"],
                        start_time=job["start_time"],
                        new_status=TestInvestigationStatus.IGNORED
                    )
                )

                ArgusEvent.batch(event_batch).create(
                    release_id=job["release_id"],
                    group_id=job["group_id"],
                    test_id=test_id,
                    user_id=g.user.id,
                    run_id=job["id"],
                    body=json.dumps({
                        "message": "Run was marked as ignored by {username} due to the following reason: {reason}",
                        "username": g.user.username,
                        "reason": reason,
                    }, ensure_ascii=True, separators=(',', ':')),
                    kind=ArgusEventTypes.TestRunBatchInvestigationStatusChange.value,
                    created_at=datetime.now(UTC),
                )

                jobs_affected += 1

        cluster.session.execute(batch)
        event_batch.execute()

        return jobs_affected

    def get_pytest_test_results(self, test_name: str, before: float = None, after: float = None) -> list[PytestResultTable]:
        query = PytestResultTable.filter(name=test_name)
        if before:
            query = query.filter(id__lt=uuid_from_time(before))

        if after:
            query = query.filter(id__gt=uuid_from_time(after))

        results = query.all()

        return list(results)

    def get_pytest_test_field_stats(self, test_name: str, field_name: str, aggr_function: str, query: dict) -> dict[str]:
        VALID_FUNCTIONS = {
            "avg": "AVG",
            "min": "MIN",
            "max": "MAX",
            "count": "COUNT",
        }

        fun = VALID_FUNCTIONS[aggr_function]

        db = ScyllaCluster.get()
        query_values = [test_name]
        if field_name not in PytestResultTable._columns.keys():
            raise TestRunServiceException(f"Invalid fixed column: {field_name}", field_name)
        raw_query = f"SELECT {fun}({field_name}) FROM pytest_v2 WHERE name = ?"

        status = query.pop("status", None)
        period = query.pop("since", None)
        if status:
            raw_query += " AND status = ?"
            query_values.append(status)

        if not status and period:
            raw_query += " AND status IN ?"
            query_values.append([s.value for s in PytestStatus])

        if period:
            try:
                since = datetime.fromtimestamp(int(period))
            except ValueError:
                raise TestRunServiceException("Malformed timestamp value")
            raw_query += " AND id >= ?"
            query_values.append(since)

        q = db.prepare(raw_query)
        stmt = q.bind(values=query_values)
        res = next(iter(db.session.execute(stmt).one().values()))

        return {
            test_name: {
                field_name: {
                    aggr_function: res
                }
            }
        }

    def get_pytest_release_results(self, release_id: str | UUID) -> list[PytestResultTable]:
        """
            Unbound filter function, will return all tests for a specific release
        """
        results = PytestResultTable.filter(release_id=release_id).all()

        return list(results)

    def get_pytest_run_results(self, run_id: str | UUID) -> list[PytestResultTable]:
        """
            Unbound filter function, will return all tests for a specific release
        """
        results = PytestResultTable.filter(run_id=run_id).all()

        return list(results)
