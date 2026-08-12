import logging
from collections.abc import Iterable
from datetime import datetime, UTC
from math import ceil
from typing import Annotated, ClassVar, Optional
from uuid import UUID
from time import time
from cassandra.concurrent import execute_concurrent_with_args
from flask import Blueprint
from pydantic import Field
from coodie import ClusteringKey, Indexed, PrimaryKey
from coodie.sync import Document
from coodie.usertype import UserType
from coodie.exceptions import DocumentNotFound

from argus.backend.db import ScyllaCluster
from argus.backend.models.plan import ArgusReleasePlan
from argus.backend.models.web import (
    ArgusTest,
    ArgusGroup,
    ArgusRelease,
    ReleaseStatsSnapshot,
    ReleaseDistinctVersions,
)
from argus.backend.util.common import chunk
from argus.common.enums import TestInvestigationStatus, TestStatus

LOGGER = logging.getLogger(__name__)


class PluginModelBase(Document):
    class Settings:
        __abstract__ = True

    _plugin_name: ClassVar[str] = "unknown"
    # Metadata
    build_id: Annotated[Optional[str], PrimaryKey()] = None
    start_time: Annotated[Optional[datetime], ClusteringKey(order="DESC")] = Field(
        default_factory=lambda: datetime.now(UTC))
    id: Annotated[Optional[UUID], Indexed()] = None
    release_id: Annotated[Optional[UUID], Indexed()] = None
    group_id: Annotated[Optional[UUID], Indexed()] = None
    test_id: Annotated[Optional[UUID], Indexed()] = None
    assignee: Annotated[Optional[UUID], Indexed()] = None
    status: Optional[str] = Field(default=TestStatus.CREATED.value)
    investigation_status: Optional[str] = Field(default=TestInvestigationStatus.NOT_INVESTIGATED.value)
    heartbeat: Optional[int] = Field(default_factory=lambda: int(time()))
    end_time: Optional[datetime] = Field(default_factory=lambda: datetime.fromtimestamp(0, UTC))
    build_job_url: Optional[str] = None
    build_number: Optional[int] = None
    product_version: Annotated[Optional[str], Indexed()] = None
    scylla_version: Optional[str] = None

    # Test Logs Collection
    logs: list[tuple[str, str]] = Field(default_factory=list)

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
        except DocumentNotFound:
            LOGGER.warning("Test entity missing for key \"%s\", run won't be visible until this is corrected", key)

    def get_assignment(self, version: str | None = None) -> UUID | None:
        associated_test: ArgusTest = ArgusTest.get(build_system_id=self.build_id)
        associated_release: ArgusRelease = ArgusRelease.get(id=associated_test.release_id)

        plans: list[ArgusReleasePlan] = list(ArgusReleasePlan.find(release_id=associated_release.id))

        if version:
            plans = [plan for plan in plans if plan.target_version == version]

        for plan in plans:
            if associated_test.group_id in plan.groups:
                return plan.assignee_mapping.get(associated_test.group_id, plan.owner)
            if associated_test.id in plan.tests:
                return plan.assignee_mapping.get(associated_test.id, plan.owner)

        # FIXME: Legacy fallback until we fully migrate to new plans
        return self._legacy_get_scheduled_assignee(associated_test=associated_test, associated_release=associated_release)

    def get_scheduled_assignee(self) -> UUID:
        return self.get_assignment()

    def _legacy_get_scheduled_assignee(self, associated_test: ArgusTest, associated_release: ArgusRelease) -> UUID:
        """Legacy scheduling removed - schedules no longer exist."""
        return None

    @classmethod
    def get_jobs_assigned_to_user(cls, user_id: str | UUID):
        cluster = ScyllaCluster.get()
        query = cluster.prepare("SELECT build_id, start_time, release_id, group_id, assignee, "
                                f"test_id, id, status, investigation_status, build_job_url, build_number, scylla_version FROM {cls.table_name()} WHERE assignee = ?")
        rows = cluster.session.execute(query=query, parameters=(user_id,))

        return list(rows)

    @classmethod
    def get_jobs_meta_by_test_id(cls, test_id: UUID):
        cluster = ScyllaCluster.get()
        query = cluster.prepare(
            f"SELECT build_id, start_time, id, test_id, release_id, group_id, status, investigation_status, build_number FROM {cls.table_name()} WHERE test_id = ?")
        rows = cluster.session.execute(query=query, parameters=(test_id,))

        return list(rows)

    @classmethod
    def prepare_investigation_status_update_query(cls, build_id: str, start_time: datetime, new_status: TestInvestigationStatus):
        cluster = ScyllaCluster.get()
        query = cluster.prepare(
            f"UPDATE {cls.table_name()} SET investigation_status = ? WHERE build_id = ? AND start_time = ?")
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
            futures.append(cluster.session.execute_async(query=query, parameters=(next_slice,),
                                                         execution_profile="read_fast"))

        return futures

    @classmethod
    def get_run_meta_by_build_id(cls, build_id: str, limit: int = 10):
        cluster = ScyllaCluster.get()
        query = cluster.prepare("SELECT id, test_id, group_id, release_id, status, start_time, build_job_url, build_id, "
                                f"assignee, end_time, investigation_status, heartbeat, build_number FROM {cls.table_name()} WHERE build_id = ? LIMIT ?")
        rows = cluster.session.execute(query=query, parameters=(build_id, limit))

        return list(rows)

    @classmethod
    def get_run_meta_by_run_id(cls, run_id: UUID | str):
        cluster = ScyllaCluster.get()
        query = cluster.prepare("SELECT id, test_id, group_id, release_id, status, start_time, build_job_url, build_id, "
                                f"assignee, end_time, investigation_status, heartbeat, build_number FROM {cls.table_name()} WHERE id = ?")
        rows = cluster.session.execute(query=query, parameters=(run_id,))

        return list(rows)

    @classmethod
    def get_versions_by_run_ids(cls, run_ids: Iterable[UUID]) -> dict[UUID, str | None]:
        """Parallel per-run_id lookups of scylla_version from the plugin table."""
        cluster = ScyllaCluster.get()
        query = cluster.prepare(f"SELECT scylla_version FROM {cls.table_name()} WHERE id = ?")
        params = [(rid,) for rid in run_ids]
        results = execute_concurrent_with_args(cluster.session, query, params, concurrency=50)
        return {
            p[0]: rows.one().get("scylla_version")
            for p, (success, rows) in zip(params, results)
            if success and rows
        }

    @classmethod
    def get_run_response(cls, run_id: UUID) -> dict | None:
        try:
            run = cls.get(id=run_id)
        except DocumentNotFound:
            return None
        return run.model_dump()

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
    def get_distinct_cloud_images_for_release(cls, release: ArgusRelease):
        raise NotImplementedError()

    @classmethod
    def get_distinct_cloud_images_for_view(cls, tests: list[ArgusTest]):
        raise NotImplementedError()

    @classmethod
    def get_distinct_versions_for_view(cls, tests: list[ArgusTest]) -> list[str]:
        cluster = ScyllaCluster.get()
        statement = cluster.prepare(f"SELECT scylla_version FROM {cls.table_name()} WHERE build_id IN ?")
        futures = []
        for batch in chunk(tests):
            futures.append(cluster.session.execute_async(query=statement,
                           parameters=([t.build_system_id for t in batch],)))

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

    def sut_timestamp(self, sut_package_name) -> float:
        raise NotImplementedError()

    def invalidate_release_snapshot(self) -> None:
        if not self.release_id:
            return
        try:
            version = self.scylla_version or ""
            version_prefix = f"v={version}::"
            all_versions_prefix = "v=::"
            for snapshot in ReleaseStatsSnapshot.find(release_id=self.release_id).all():
                if snapshot.filter_key.startswith(version_prefix) or snapshot.filter_key.startswith(all_versions_prefix):
                    snapshot.delete()
        except Exception:
            LOGGER.warning("Failed to invalidate stats snapshot for release %s", self.release_id, exc_info=True)

    def index_version(self) -> None:
        if not self.release_id or not self.scylla_version:
            return
        try:
            ReleaseDistinctVersions.create(release_id=self.release_id, version=self.scylla_version)
        except Exception:
            LOGGER.warning("Failed to index version %s for release %s", self.scylla_version, self.release_id, exc_info=True)


class PluginInfoBase:
    name: str
    controller: Blueprint
    model: PluginModelBase
    all_models: list[type[Document]]
    all_types: list[type[UserType]]
