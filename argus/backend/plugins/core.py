import logging
from datetime import datetime
from math import ceil
from uuid import UUID
from time import time

from cassandra.cqlengine import columns
from cassandra.cqlengine.models import Model
from cassandra.cqlengine.usertype import UserType
from flask import Blueprint
from argus.backend.db import ScyllaCluster
from argus.backend.models.web import (
    ArgusTest,
    ArgusGroup,
    ArgusRelease,
    ArgusScheduleGroup,
    ArgusSchedule,
    ArgusScheduleTest,
    ArgusScheduleAssignee,
    ArgusUserView,
    User
)
from argus.backend.util.common import chunk
from argus.backend.util.enums import TestInvestigationStatus, TestStatus

LOGGER = logging.getLogger(__name__)


class PluginModelBase(Model):
    _plugin_name = "unknown"
    # Metadata
    build_id = columns.Text(required=True, partition_key=True)
    start_time = columns.DateTime(required=True, primary_key=True, clustering_order="DESC", default=datetime.utcnow, custom_index=True)
    id = columns.UUID(index=True, required=True)
    release_id = columns.UUID(index=True)
    group_id = columns.UUID(index=True)
    test_id = columns.UUID(index=True)
    assignee = columns.UUID(index=True)
    status = columns.Text(default=lambda: TestStatus.CREATED.value)
    investigation_status = columns.Text(default=lambda: TestInvestigationStatus.NOT_INVESTIGATED.value)
    heartbeat = columns.Integer(default=lambda: int(time()))
    end_time = columns.DateTime(default=lambda: datetime.utcfromtimestamp(0))
    build_job_url = columns.Text()
    product_version = columns.Text(index=True)

    # Test Logs Collection
    logs = columns.List(value_type=columns.Tuple(columns.Text(), columns.Text()))

    @classmethod
    def table_name(cls) -> str:
        return cls.__table_name__

    @classmethod
    def _stats_query(cls) -> str:
        raise NotImplementedError()

    def assign_categories(self):
        key = self.build_id
        try:
            test: ArgusTest = ArgusTest.get(build_system_id=key)
            self.release_id = test.release_id
            self.group_id = test.group_id
            self.test_id = test.id
            if not test.plugin_name or test.plugin_name != self._plugin_name:
                test.plugin_name = self._plugin_name
                test.save()
        except ArgusTest.DoesNotExist:
            LOGGER.warning("Test entity missing for key \"%s\", run won't be visible until this is corrected", key)

    def get_scheduled_assignee(self) -> UUID:
        """
            Iterate over all schedules (groups and tests) and return first available assignee
        """
        associated_test = ArgusTest.get(build_system_id=self.build_id)
        associated_group = ArgusGroup.get(id=associated_test.group_id)
        associated_release = ArgusRelease.get(id=associated_test.release_id)

        scheduled_groups = ArgusScheduleGroup.filter(
            release_id=associated_release.id,
            group_id=associated_group.id,
        ).all()

        scheduled_tests = ArgusScheduleTest.filter(
            release_id=associated_release.id,
            test_id=associated_test.id
        ).all()

        unique_schedule_ids = {scheduled_obj.schedule_id for scheduled_obj in [
            *scheduled_tests, *scheduled_groups]}

        schedules = ArgusSchedule.filter(
            release_id=associated_release.id,
            id__in=tuple(unique_schedule_ids),
        ).all()

        today = datetime.utcnow()

        valid_schedules = []
        for schedule in schedules:
            if schedule.period_start <= today <= schedule.period_end:
                valid_schedules.append(schedule)

        assignees_uuids = []
        for schedule in valid_schedules:
            assignees = ArgusScheduleAssignee.filter(
                schedule_id=schedule.id
            ).all()
            assignees_uuids.extend([assignee.assignee for assignee in assignees])

        return assignees_uuids[0] if len(assignees_uuids) > 0 else None

    @classmethod
    def get_jobs_assigned_to_user(cls, user_id: str | UUID):
        cluster = ScyllaCluster.get()
        query = cluster.prepare("SELECT build_id, start_time, release_id, group_id, assignee, "
                                f"test_id, id, status, investigation_status, build_job_url, scylla_version FROM {cls.table_name()} WHERE assignee = ?")
        rows = cluster.session.execute(query=query, parameters=(user_id,))

        return list(rows)

    @classmethod
    def get_jobs_meta_by_test_id(cls, test_id: UUID):
        cluster = ScyllaCluster.get()
        query = cluster.prepare(f"SELECT build_id, start_time, id, test_id, release_id, group_id, status, investigation_status FROM {cls.table_name()} WHERE test_id = ?")
        rows = cluster.session.execute(query=query, parameters=(test_id,))

        return list(rows)

    @classmethod
    def prepare_investigation_status_update_query(cls, build_id: str, start_time: datetime, new_status: TestInvestigationStatus):
        cluster = ScyllaCluster.get()
        query = cluster.prepare(f"UPDATE {cls.table_name()} SET investigation_status = ? WHERE build_id = ? AND start_time = ?")
        bound_query = query.bind(values=(new_status.value, build_id, start_time))

        return bound_query

    @classmethod
    def get_stats_for_release(cls, release: ArgusRelease, build_ids=list[str]):
        cluster = ScyllaCluster.get()
        query = cluster.prepare(cls._stats_query())
        futures = []
        step_size = 90

        for step in range(0, ceil(len(build_ids) / step_size)):
            start_pos = step*step_size
            next_slice = build_ids[start_pos:start_pos+step_size]
            futures.append(cluster.session.execute_async(query=query, parameters=(next_slice,)))

        return futures
    @classmethod
    def get_run_meta_by_build_id(cls, build_id: str, limit: int = 10):
        cluster = ScyllaCluster.get()
        query = cluster.prepare("SELECT id, test_id, group_id, release_id, status, start_time, build_job_url, build_id, "
                                f"assignee, end_time, investigation_status, heartbeat FROM {cls.table_name()} WHERE build_id = ? LIMIT ?")
        rows = cluster.session.execute(query=query, parameters=(build_id, limit))

        return list(rows)

    @classmethod
    def get_run_meta_by_run_id(cls, run_id: UUID | str):
        cluster = ScyllaCluster.get()
        query = cluster.prepare("SELECT id, test_id, group_id, release_id, status, start_time, build_job_url, build_id, "
                                f"assignee, end_time, investigation_status, heartbeat FROM {cls.table_name()} WHERE id = ?")
        rows = cluster.session.execute(query=query, parameters=(run_id,))

        return list(rows)

    @classmethod
    def load_test_run(cls, run_id: UUID) -> 'PluginModelBase':
        raise NotImplementedError()

    @classmethod
    def submit_run(cls, request_data: dict) -> 'PluginModelBase':
        raise NotImplementedError()

    @classmethod
    def get_distinct_product_versions(cls, release: ArgusRelease) -> list[str]:
        raise NotImplementedError()

    @classmethod
    def get_distinct_versions_for_view(cls, tests: list[ArgusTest]) -> list[str]:
        cluster = ScyllaCluster.get()
        statement = cluster.prepare(f"SELECT scylla_version FROM {cls.table_name()} WHERE build_id IN ?")
        futures = []
        for batch in chunk(tests):
            futures.append(cluster.session.execute_async(query=statement, parameters=([t.build_system_id for t in batch],)))
        
        rows = []
        for future in futures:
            rows.extend(future.result())
        unique_versions = {r["scylla_version"] for r in rows if r["scylla_version"]}

        return sorted(list(unique_versions), reverse=True)

    def update_heartbeat(self):
        self.heartbeat = int(time())

    def change_status(self, new_status: TestStatus):
        self.status = new_status.value

    def change_investigation_status(self, new_investigation_status: TestInvestigationStatus):
        self.investigation_status = new_investigation_status.value

    def submit_product_version(self, version: str):
        raise NotImplementedError()

    def set_full_version(self, version: str):
        self.product_version = version

    def submit_logs(self, logs: list[dict]):
        raise NotImplementedError()

    def finish_run(self, payload: dict = None):
        raise NotImplementedError()

    def sut_timestamp(self) -> float:
        raise NotImplementedError()

class PluginInfoBase:
    # pylint: disable=too-few-public-methods
    name: str
    controller: Blueprint
    model: PluginModelBase
    all_models: list[Model]
    all_types: list[UserType]
