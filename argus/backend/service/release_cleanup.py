import logging
from uuid import UUID

from argus.backend.models.argus_ai import (
    CriticalEventEmbeddings,
    ErrorEventEmbeddings,
    SCTCriticalEventEmbedding,
    SCTErrorEventEmbedding,
)
from argus.backend.models.github_issue import IssueLink
from argus.backend.models.pytest import PytestResultTable, PytestResultTableOld
from argus.backend.models.result import (
    ArgusBestResultData,
    ArgusGenericResultData,
    ArgusGenericResultMetadata,
    ArgusGraphView,
)
from argus.backend.models.run_config import RunConfigParam, RunConfigParamByRun, RunConfiguration
from argus.backend.models.run_cost import RunCost
from argus.backend.models.web import (
    ArgusEvent,
    ArgusGroup,
    ArgusRelease,
    ArgusTest,
    ArgusTestRunComment,
    User,
    invalidate_release_snapshots,
)
from argus.backend.plugins.core import PluginInfoBase, PluginModelBase
from argus.backend.plugins.loader import AVAILABLE_PLUGINS
from argus.backend.service.release_manager import ReleaseManagerService

LOGGER = logging.getLogger(__name__)

RUN_PARTITION_TABLES = (
    RunConfiguration,
    RunConfigParamByRun,
    RunCost,
    IssueLink,
    SCTErrorEventEmbedding,
    SCTCriticalEventEmbedding,
    ErrorEventEmbeddings,
    CriticalEventEmbeddings,
)
RUN_INDEXED_TABLES = (PytestResultTable, PytestResultTableOld)
RUN_KEY_COLUMNS = ("build_id", "start_time", "id", "test_id", "release_id")


class ReleaseCleanupError(Exception):
    pass


class ReleaseCleanupService:
    def __init__(self) -> None:
        self.release_manager = ReleaseManagerService()

    async def delete_group(self, group_id: UUID, user: User) -> None:
        group = await ArgusGroup.get(id=group_id)
        await self._require_editable(group.release_id)
        for test in await ArgusTest.find(group_id=group.id).all():
            await self._delete_test_cascade(test)
        await self.release_manager.delete_group(group.id, delete_tests=True)
        LOGGER.info("Group %s (%s) deleted by %s", group.name, group.id, user.username)

    async def delete_test(self, test_id: UUID, user: User) -> None:
        test = await ArgusTest.get(id=test_id)
        await self._require_editable(test.release_id)
        await self._delete_test_cascade(test)
        LOGGER.info("Test %s (%s) deleted by %s", test.name, test.id, user.username)

    async def delete_run(self, test_id: UUID, run_id: UUID, user: User) -> None:
        test = await ArgusTest.get(id=test_id)
        await self._require_editable(test.release_id)
        plugin, run = await self._find_run(run_id)
        if run.test_id != test.id and run.build_id != test.build_system_id:
            raise ReleaseCleanupError(f"Run {run_id} is not a run of test {test.name}")
        await self._delete_run_rows(plugin.model, run)
        await invalidate_release_snapshots(test.release_id)
        LOGGER.info("Run %s of test %s deleted by %s", run.id, test.name, user.username)

    async def _require_editable(self, release_id: UUID) -> ArgusRelease:
        release = await ArgusRelease.get(id=release_id)
        if not release.user_editable:
            raise ReleaseCleanupError(f"Release {release.name} is not user editable")
        return release

    async def _find_run(self, run_id: UUID) -> tuple[PluginInfoBase, PluginModelBase]:
        for plugin in AVAILABLE_PLUGINS.values():
            run = await plugin.model.find(id=run_id).only(*RUN_KEY_COLUMNS).first()
            if run:
                return plugin, run
        raise ReleaseCleanupError(f"Run {run_id} does not exist")

    async def _runs_of(self, test: ArgusTest) -> list[tuple[PluginInfoBase, PluginModelBase]]:
        runs: dict[UUID, tuple[PluginInfoBase, PluginModelBase]] = {}
        for plugin in AVAILABLE_PLUGINS.values():
            queries = [plugin.model.find(test_id=test.id)]
            if test.build_system_id:
                queries.append(plugin.model.find(build_id=test.build_system_id))
            for query in queries:
                for run in await query.only(*RUN_KEY_COLUMNS).all():
                    runs.setdefault(run.id, (plugin, run))
        return list(runs.values())

    async def _delete_test_cascade(self, test: ArgusTest) -> None:
        for plugin, run in await self._runs_of(test):
            await self._delete_run_rows(plugin.model, run)
        await self._delete_test_results(test)
        await self.release_manager.delete_test(test.id)

    async def _delete_run_rows(self, model: type[PluginModelBase], run: PluginModelBase) -> None:
        for comment in await ArgusTestRunComment.find(test_run_id=run.id).all():
            await comment.delete()
        for event in await ArgusEvent.find(run_id=run.id).all():
            await event.delete()
        for table in RUN_INDEXED_TABLES:
            for row in await table.find(run_id=run.id).all():
                await row.delete()
        for param in await RunConfigParamByRun.find(run_id=run.id).all():
            if param.value is not None:
                await RunConfigParam.find(name=param.name, value=param.value, run_id=str(run.id)).delete()
        for table in RUN_PARTITION_TABLES:
            await table.find(run_id=run.id).delete()
        if run.test_id:
            for meta in await ArgusGenericResultMetadata.find(test_id=run.test_id).all():
                await ArgusGenericResultData.find(test_id=run.test_id, name=meta.name, run_id=run.id).delete()
        await model.delete_run_data(run.id)
        await run.delete()

    async def _delete_test_results(self, test: ArgusTest) -> None:
        for meta in await ArgusGenericResultMetadata.find(test_id=test.id).all():
            await ArgusGenericResultData.find(test_id=test.id, name=meta.name).delete()
            await ArgusBestResultData.find(test_id=test.id, name=meta.name).delete()
        await ArgusGenericResultMetadata.find(test_id=test.id).delete()
        await ArgusGraphView.find(test_id=test.id).delete()
