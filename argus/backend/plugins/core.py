import asyncio
import logging
from collections.abc import Iterable
from datetime import datetime, UTC
from typing import Annotated, ClassVar, Optional
from uuid import UUID
from time import time
from fastapi import APIRouter
from pydantic import Field
from coodie import ClusteringKey, Indexed, PrimaryKey
from coodie.aio import Document
from coodie.usertype import UserType
from coodie.cql_builder import build_update, parse_filter_kwargs, parse_update_kwargs
from coodie.exceptions import DocumentNotFound

from argus.backend.models.plan import ArgusReleasePlan
from argus.backend.models.web import (
    ArgusTest,
    ArgusGroup,
    ArgusRelease,
    ReleaseStatsSnapshot,
    ReleaseDistinctVersions,
)
from argus.backend.util.common import chunk, gather_limited, select_rows
from argus.common.enums import TestInvestigationStatus, TestStatus

LOGGER = logging.getLogger(__name__)


class PluginModelBase(Document):
    class Settings:
        __abstract__ = True

    _plugin_name: ClassVar[str] = "unknown"
    # Metadata
    build_id: Annotated[str, PrimaryKey()]
    start_time: Annotated[datetime, ClusteringKey(order="DESC")] = Field(
        default_factory=lambda: datetime.now(UTC))
    id: Annotated[UUID, Indexed()]
    release_id: Annotated[Optional[UUID], Indexed()] = None
    group_id: Annotated[Optional[UUID], Indexed()] = None
    test_id: Annotated[Optional[UUID], Indexed()] = None
    assignee: Annotated[Optional[UUID], Indexed()] = None
    status: str = Field(default=TestStatus.CREATED.value)
    investigation_status: str = Field(default=TestInvestigationStatus.NOT_INVESTIGATED.value)
    heartbeat: int = Field(default_factory=lambda: int(time()))
    end_time: datetime = Field(default_factory=lambda: datetime.fromtimestamp(0, UTC))
    build_job_url: str
    build_number: Optional[int] = None
    product_version: Annotated[Optional[str], Indexed()] = None
    scylla_version: Optional[str] = None

    # Test Logs Collection
    logs: list[tuple[str, str]] = Field(default_factory=list)

    @classmethod
    def _stats_columns(cls) -> tuple[str, ...]:
        raise NotImplementedError()

    async def assign_categories(self):
        key = self.build_id
        try:
            test: ArgusTest = await ArgusTest.get(build_system_id=key)
            self.release_id = test.release_id
            self.group_id = test.group_id
            self.test_id = test.id
            if not test.plugin_name or test.plugin_name != self._plugin_name:
                test.plugin_name = self._plugin_name
                await test.save()
        except DocumentNotFound:
            LOGGER.warning("Test entity missing for key \"%s\", run won't be visible until this is corrected", key)

    async def get_assignment(self, version: str | None = None) -> UUID | None:
        associated_test: ArgusTest = await ArgusTest.get(build_system_id=self.build_id)
        associated_release: ArgusRelease = await ArgusRelease.get(id=associated_test.release_id)

        plans: list[ArgusReleasePlan] = await ArgusReleasePlan.find(release_id=associated_release.id).all()

        if version:
            plans = [plan for plan in plans if plan.target_version == version]

        for plan in plans:
            if associated_test.group_id in plan.groups:
                return plan.assignee_mapping.get(associated_test.group_id, plan.owner)
            if associated_test.id in plan.tests:
                return plan.assignee_mapping.get(associated_test.id, plan.owner)

        # FIXME: Legacy fallback until we fully migrate to new plans
        return self._legacy_get_scheduled_assignee(associated_test=associated_test, associated_release=associated_release)

    async def get_scheduled_assignee(self) -> UUID:
        return await self.get_assignment()

    def _legacy_get_scheduled_assignee(self, associated_test: ArgusTest, associated_release: ArgusRelease) -> UUID:
        """Legacy scheduling removed - schedules no longer exist."""
        return None

    @classmethod
    async def get_jobs_assigned_to_user(cls, user_id: str | UUID) -> list[dict]:
        return await select_rows(cls.find(assignee=user_id), "build_id", "start_time", "release_id", "group_id",
                                 "assignee", "test_id", "id", "status", "investigation_status", "build_job_url",
                                 "build_number", "scylla_version")

    @classmethod
    async def get_jobs_meta_by_test_id(cls, test_id: UUID) -> list[dict]:
        return await select_rows(cls.find(test_id=test_id), "build_id", "start_time", "id", "test_id", "release_id",
                                 "group_id", "status", "investigation_status", "build_number")

    @classmethod
    def prepare_investigation_status_update_query(cls, build_id: str, start_time: datetime,
                                                  new_status: TestInvestigationStatus) -> tuple[str, list]:
        set_data, _ = parse_update_kwargs({"investigation_status": new_status.value})
        return build_update(
            cls._get_table(),
            cls._get_keyspace(),
            set_data,
            parse_filter_kwargs({"build_id": build_id, "start_time": start_time}),
        )

    @classmethod
    async def get_stats_for_release(cls, release: ArgusRelease, build_ids: list[str]) -> list[dict]:
        cols = cls._stats_columns()
        queries = [
            cls.find(build_id__in=batch).per_partition_limit(15).only(*cols).values_list(*cols).consistency("ONE").all()
            for batch in chunk(build_ids)
        ]
        rows = [row for batch_rows in await asyncio.gather(*queries) for row in batch_rows]
        return [dict(zip(cols, row)) for row in rows]

    @classmethod
    async def get_versions_by_run_ids(cls, run_ids: Iterable[UUID]) -> dict[UUID, str | None]:
        """Parallel per-run_id lookups of scylla_version from the plugin table."""
        run_ids = list(run_ids)
        rows = await gather_limited(
            cls.find(id=rid).only("scylla_version").values_list("scylla_version").first() for rid in run_ids
        )
        return {rid: row[0] for rid, row in zip(run_ids, rows) if row is not None}

    @classmethod
    async def get_run_response(cls, run_id: UUID) -> dict | None:
        try:
            run = await cls.get(id=run_id)
        except DocumentNotFound:
            return None
        return run.model_dump()

    @classmethod
    async def load_test_run(cls, run_id: UUID) -> 'PluginModelBase':
        raise NotImplementedError()

    @classmethod
    async def submit_run(cls, request_data: dict) -> 'PluginModelBase':
        raise NotImplementedError()

    @classmethod
    async def get_distinct_product_versions(cls, release: ArgusRelease) -> list[str]:
        raise NotImplementedError()

    @classmethod
    async def get_distinct_cloud_images_for_release(cls, release: ArgusRelease) -> list[str]:
        raise NotImplementedError()

    @classmethod
    async def get_distinct_cloud_images_for_view(cls, tests: list[ArgusTest]) -> list[str]:
        raise NotImplementedError()

    @classmethod
    async def get_distinct_versions_for_view(cls, tests: list[ArgusTest]) -> list[str]:
        queries = [
            cls.find(build_id__in=[t.build_system_id for t in batch])
            .only("scylla_version").values_list("scylla_version").all()
            for batch in chunk(tests)
        ]
        rows = [row for batch_rows in await asyncio.gather(*queries) for row in batch_rows]
        unique_versions = {version for (version,) in rows if version}

        return sorted(list(unique_versions), reverse=True)

    def update_heartbeat(self):
        self.heartbeat = int(time())

    def change_status(self, new_status: TestStatus):
        self.status = new_status.value

    def change_investigation_status(self, new_investigation_status: TestInvestigationStatus):
        self.investigation_status = new_investigation_status.value

    async def submit_product_version(self, version: str):
        raise NotImplementedError()

    def set_full_version(self, version: str):
        self.product_version = version

    async def submit_logs(self, logs: list[dict]):
        raise NotImplementedError()

    async def finish_run(self, payload: dict = None):
        raise NotImplementedError()

    async def sut_timestamp(self, sut_package_name) -> float:
        raise NotImplementedError()

    async def invalidate_release_snapshot(self) -> None:
        if not self.release_id:
            return
        try:
            version = self.scylla_version or ""
            version_prefix = f"v={version}::"
            all_versions_prefix = "v=::"
            for snapshot in await ReleaseStatsSnapshot.find(release_id=self.release_id).all():
                if snapshot.filter_key.startswith(version_prefix) or snapshot.filter_key.startswith(all_versions_prefix):
                    await snapshot.delete()
        except Exception:
            LOGGER.warning("Failed to invalidate stats snapshot for release %s", self.release_id, exc_info=True)

    async def index_version(self) -> None:
        if not self.release_id or not self.scylla_version:
            return
        try:
            await ReleaseDistinctVersions.create(release_id=self.release_id, version=self.scylla_version)
        except Exception:
            LOGGER.warning("Failed to index version %s for release %s", self.scylla_version, self.release_id, exc_info=True)


class PluginInfoBase:
    name: str
    controller: APIRouter | None
    model: PluginModelBase
    all_models: list[type[Document]]
    all_types: list[type[UserType]]
