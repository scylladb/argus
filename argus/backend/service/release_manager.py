import logging
from typing import TypedDict
from uuid import UUID
from coodie.exceptions import DocumentNotFound

from argus.backend.plugins.sct.testrun import SCTTestRun
from argus.backend.models.web import ArgusRelease, ArgusGroup, ArgusTest, ReleaseDistinctVersions, ReleaseDistinctImages, ReleaseStatsSnapshot, invalidate_release_snapshots

LOGGER = logging.getLogger(__name__)


class ReleaseManagerException(Exception):
    pass


class ReleaseEditPayload(TypedDict):
    id: str
    pretty_name: str
    description: str
    valid_version_regex: str | None
    enabled: bool
    perpetual: bool
    dormant: bool


class ReleaseManagerService:
    def __init__(self) -> None:
        pass

    async def get_releases(self) -> list[ArgusRelease]:
        return await ArgusRelease.find().all()

    async def get_groups(self, release_id: UUID) -> list[ArgusGroup]:
        return await ArgusGroup.find(release_id=release_id).all()

    async def get_tests(self, group_id: UUID) -> list[ArgusTest]:
        return await ArgusTest.find(group_id=group_id).all()

    async def toggle_test_enabled(self, test_id: UUID, new_state: bool) -> bool:
        test_id = UUID(test_id) if isinstance(test_id, str) else test_id
        test: ArgusTest = await ArgusTest.get(id=test_id)
        test.enabled = new_state
        await test.save()
        await invalidate_release_snapshots(test.release_id)
        return test

    async def toggle_group_enabled(self, group_id: UUID, new_state: bool) -> bool:
        group_id = UUID(group_id) if isinstance(group_id, str) else group_id
        test: ArgusGroup = await ArgusGroup.get(id=group_id)
        test.enabled = new_state
        await test.save()
        await invalidate_release_snapshots(test.release_id)
        return test

    async def create_release(self, release_name: str, pretty_name: str, perpetual: bool) -> ArgusRelease:
        try:
            release = await ArgusRelease.get(name=release_name)
        except DocumentNotFound:
            release = ArgusRelease.model_construct()
            release.name = release_name
            release.pretty_name = pretty_name
            release.perpetual = perpetual

            await release.save()
        else:
            raise ReleaseManagerException(
                f"Release {release_name} already exists!", release_name)

        return release

    async def create_group(self, group_name: str, pretty_name: str, build_system_id: str,
                     release_id: str) -> ArgusGroup:
        release = await ArgusRelease.get(id=UUID(release_id))

        new_group = ArgusGroup.model_construct()
        new_group.name = group_name
        new_group.pretty_name = pretty_name
        new_group.release_id = release.id
        new_group.build_system_id = build_system_id
        await new_group.save()
        await invalidate_release_snapshots(release.id)
        return new_group

    async def create_test(self, test_name, pretty_name, build_id, build_url, group_id, release_id,
                          plugin_name) -> ArgusTest:
        release = await ArgusRelease.get(id=UUID(release_id))
        group = await ArgusGroup.get(id=UUID(group_id))

        new_test = ArgusTest.model_construct()
        new_test.name = test_name
        new_test.pretty_name = pretty_name
        new_test.build_system_id = build_id
        new_test.release_id = release.id
        new_test.group_id = group.id
        new_test.plugin_name = plugin_name
        new_test.build_system_url = build_url
        await new_test.validate_build_system_id()
        await new_test.save()
        await self.move_test_runs(new_test)
        await invalidate_release_snapshots(release.id)
        return new_test

    async def delete_group(self, group_id: str, delete_tests: bool = True, new_group_id: str = "") -> bool:
        group_to_delete = await ArgusGroup.get(id=UUID(group_id))

        tests_to_change = ArgusTest.find(
            group_id=group_to_delete.id)
        if delete_tests:
            for test in await tests_to_change.all():
                await test.delete()
        else:
            new_group = await ArgusGroup.get(id=UUID(new_group_id))
            for test in await tests_to_change.all():
                test.group_id = new_group.id
                await test.save()

        await group_to_delete.delete()
        await invalidate_release_snapshots(group_to_delete.release_id)
        return True

    async def delete_test(self, test_id: str) -> bool:
        test_to_delete = await ArgusTest.get(id=UUID(test_id) if isinstance(test_id, str) else test_id)
        await test_to_delete.delete()
        await invalidate_release_snapshots(test_to_delete.release_id)
        return True

    async def update_group(self, group_id: str, name: str, pretty_name: str, enabled: bool,
                           build_system_id: str) -> bool:
        group = await ArgusGroup.get(id=UUID(group_id))

        group.name = name
        group.build_system_id = build_system_id
        group.pretty_name = pretty_name
        group.enabled = enabled

        await group.save()
        await invalidate_release_snapshots(group.release_id)
        return True

    async def update_test(self, test_id: str, name: str, pretty_name: str, plugin_name: str,
                    enabled: bool, build_system_id: str, build_system_url: str, group_id) -> bool:
        test: ArgusTest = await ArgusTest.get(id=UUID(test_id))
        group = await ArgusGroup.get(id=UUID(group_id))

        test.name = name
        test.pretty_name = pretty_name
        test.plugin_name = plugin_name
        test.enabled = enabled
        test.build_system_id = build_system_id
        test.build_system_url = build_system_url
        if test.group_id != group.id:
            test.group_id = group.id
            LOGGER.info("Relocating old test runs into a new group")

        await test.validate_build_system_id()
        await test.save()
        await self.move_test_runs(test)
        await invalidate_release_snapshots(test.release_id)
        return True

    async def set_release_state(self, release_id: str, state: bool) -> bool:
        release = await ArgusRelease.get(id=UUID(release_id))
        release.enabled = state
        await release.save()
        await invalidate_release_snapshots(release.id)
        return True

    async def set_release_dormancy(self, release_id: str, dormant: bool) -> bool:
        release = await ArgusRelease.get(id=UUID(release_id))
        release.dormant = dormant
        await release.save()
        await invalidate_release_snapshots(release.id)
        return True

    async def set_release_perpetuality(self, release_id: str, perpetual: bool) -> bool:
        release = await ArgusRelease.get(id=UUID(release_id))
        release.perpetual = perpetual
        await release.save()
        await invalidate_release_snapshots(release.id)
        return True

    async def edit_release(self, payload: ReleaseEditPayload) -> bool:

        release_id = UUID(payload["id"]) if isinstance(payload["id"], str) else payload["id"]
        release: ArgusRelease = await ArgusRelease.get(id=release_id)
        release.pretty_name = payload["pretty_name"]
        release.perpetual = payload["perpetual"]
        release.enabled = payload["enabled"]
        release.dormant = payload["dormant"]
        release.description = payload["description"]
        release.valid_version_regex = payload["valid_version_regex"]

        await release.save()
        await invalidate_release_snapshots(release.id)
        return True

    async def delete_release(self, release_id: str) -> bool:

        release_id = UUID(release_id) if isinstance(release_id, str) else release_id
        release: ArgusRelease = await ArgusRelease.get(id=release_id)

        release_groups = ArgusGroup.find(release_id=release.id)
        release_tests = ArgusTest.find(release_id=release.id)

        for entity in [*await release_groups.all(), *await release_tests.all()]:
            await entity.delete()

        # Clean up denormalized index tables so no orphaned rows remain
        for row in await ReleaseDistinctVersions.find(release_id=release.id).all():
            await row.delete()
        for row in await ReleaseDistinctImages.find(release_id=release.id).all():
            await row.delete()
        for row in await ReleaseStatsSnapshot.find(release_id=release.id).all():
            await row.delete()

        await release.delete()
        return True

    async def batch_move_tests(self, new_group_id: str, tests: list[str]) -> bool:
        group = await ArgusGroup.get(id=UUID(new_group_id))

        tests: list[ArgusTest] = [await ArgusTest.get(id=UUID(test_id)) for test_id in tests]

        for test in tests:
            test.group_id = group.id
            await test.save()
            await self.move_test_runs(test)

        await invalidate_release_snapshots(group.release_id)
        return True

    async def move_test_runs(self, test: ArgusTest) -> None:
        runs = await SCTTestRun.find(build_id=test.build_system_id).only("build_id", "start_time") \
            .values_list("build_id", "start_time").consistency("ONE").all()
        for build_id, start_time in runs:
            await SCTTestRun.find(build_id=build_id, start_time=start_time).update(
                test_id=test.id, group_id=test.group_id, release_id=test.release_id)
