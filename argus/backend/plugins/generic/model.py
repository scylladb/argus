from datetime import UTC, datetime
import re
from uuid import UUID
from typing import ClassVar, Optional

from pydantic import Field
from coodie.exceptions import DocumentNotFound

from argus.backend.models.web import ArgusRelease
from argus.backend.plugins.core import PluginModelBase
from argus.backend.plugins.generic.types import GenericRunFinishRequest, GenericRunSubmitRequest
from argus.backend.util.common import get_build_number
from argus.common.enums import TestStatus

class GenericPluginException(Exception):
    pass


class GenericRun(PluginModelBase):
    _plugin_name: ClassVar[str] = "generic"

    class Settings:
        name = "generic_run"

    logs: dict[str, str] = Field(default_factory=dict)
    started_by: str
    sub_type: Optional[str] = None  # Used to tell which framework the GenericRun belongs to

    @classmethod
    def _stats_columns(cls) -> tuple[str, ...]:
        return ("id", "test_id", "group_id", "release_id", "status", "start_time", "build_job_url", "build_id",
                "assignee", "end_time", "investigation_status", "heartbeat", "build_number", "scylla_version")

    @classmethod
    async def get_distinct_product_versions(cls, release: ArgusRelease) -> list[str]:
        versions = await cls.find(release_id=release.id).only("scylla_version").values_list("scylla_version").all()
        return sorted({version for (version,) in versions if version}, reverse=True)

    async def submit_product_version(self, version: str):
        pattern = re.compile(r"((?P<short>[\w.\-~]+)-(?P<build>(0\.)?(?P<date>[0-9]{8,8})\.(?P<commit>\w+).*))")
        if match := pattern.search(version):
            self.scylla_version = match.group("short")
            try:
                new_assignee = await self.get_assignment(match.group("short"))
            except DocumentNotFound:
                new_assignee = None
            if new_assignee:
                self.assignee = new_assignee
            self.set_full_version(version)
            await self.index_version()

    @classmethod
    async def load_test_run(cls, run_id: UUID) -> 'GenericRun':
        return await cls.get(id=run_id)

    @classmethod
    async def submit_run(cls, request_data: GenericRunSubmitRequest) -> 'GenericRun':
        run_id = UUID(request_data["run_id"]) if isinstance(request_data["run_id"], str) else request_data["run_id"]
        try:
            return await cls.get(id=run_id)
        except DocumentNotFound:
            pass
        run = cls.model_construct()
        run.start_time = datetime.now(UTC)
        run.build_id = request_data["build_id"]
        run.started_by = request_data["started_by"]
        run.id = run_id
        run.build_job_url = request_data["build_url"]
        run.build_number = get_build_number(request_data["build_url"])
        run.sub_type = request_data.get("sub_type")
        await run.assign_categories()
        try:
            run.assignee = await run.get_scheduled_assignee()
        except DocumentNotFound:
            run.assignee = None
        if version := request_data.get("scylla_version"):
            await run.submit_product_version(version)
        run.status = TestStatus.RUNNING.value
        await run.save()
        await run.invalidate_release_snapshot()
        return run

    async def finish_run(self, payload: GenericRunFinishRequest = None):
        payload = payload or {}
        end_time = payload.get("end_time")
        if end_time is not None:
            self.end_time = datetime.fromtimestamp(end_time, UTC)
        else:
            self.end_time = datetime.now(UTC)
        if status := payload.get("status"):
            self.status = TestStatus(status).value
        if version := payload.get("scylla_version"):
            await self.submit_product_version(version)
        await self.invalidate_release_snapshot()
        await self.index_version()
