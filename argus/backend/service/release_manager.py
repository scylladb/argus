import logging
from typing import TypedDict
from uuid import UUID
from argus.backend.db import ScyllaCluster
from argus.backend.plugins.sct.testrun import SCTTestRun
from argus.backend.models.web import ArgusRelease, ArgusGroup, ArgusTest

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
        self.session = ScyllaCluster.get_session()
        self.database = ScyllaCluster.get()
        self.runs_by_build_id_stmt = self.database.prepare(
            "SELECT id, test_id, group_id, release_id, build_id, start_time "
            f"FROM {SCTTestRun.table_name()} WHERE build_id = ?"
        )
        self.update_run_stmt = self.database.prepare(
            f"UPDATE {SCTTestRun.table_name()} SET test_id = ?, group_id = ?, release_id = ? "
            "WHERE build_id = ? AND start_time = ?"
        )

    def get_releases(self) -> list[ArgusRelease]:
        return list(ArgusRelease.all())

    def get_groups(self, release_id: UUID) -> list[ArgusGroup]:
        return list(ArgusGroup.filter(release_id=release_id).all())

    def get_tests(self, group_id: UUID) -> list[ArgusTest]:
        return list(ArgusTest.filter(group_id=group_id).all())

    def create_release(self, release_name: str, pretty_name: str, perpetual: bool) -> ArgusRelease:
        try:
            release = ArgusRelease.get(name=release_name)
        except ArgusRelease.DoesNotExist:
            release = ArgusRelease()
            release.name = release_name
            release.pretty_name = pretty_name
            release.perpetual = perpetual

            release.save()
        else:
            raise ReleaseManagerException(
                f"Release {release_name} already exists!", release_name)

        return release

    def create_group(self, group_name: str, pretty_name: str, build_system_id: str,
                     release_id: str) -> ArgusGroup:
        release = ArgusRelease.get(id=UUID(release_id))

        new_group = ArgusGroup()
        new_group.name = group_name
        new_group.pretty_name = pretty_name
        new_group.release_id = release.id
        new_group.build_system_id = build_system_id
        new_group.save()

        return new_group

    def create_test(self, test_name, pretty_name, build_id, build_url, group_id, release_id, plugin_name) -> ArgusTest:
        release = ArgusRelease.get(id=UUID(release_id))
        group = ArgusGroup.get(id=UUID(group_id))

        new_test = ArgusTest()
        new_test.name = test_name
        new_test.pretty_name = pretty_name
        new_test.build_system_id = build_id
        new_test.release_id = release.id
        new_test.group_id = group.id
        new_test.plugin_name = plugin_name
        new_test.build_system_url = build_url
        new_test.validate_build_system_id()
        new_test.save()
        self.move_test_runs(new_test)
        return new_test

    def delete_group(self, group_id: str, delete_tests: bool = True, new_group_id: str = "") -> bool:
        group_to_delete = ArgusGroup.get(id=UUID(group_id))

        tests_to_change = ArgusTest.filter(
            group_id=group_to_delete.id)
        if delete_tests:
            for test in tests_to_change.all():
                test.delete()
        else:
            new_group = ArgusGroup.get(id=UUID(new_group_id))
            for test in tests_to_change.all():
                test.group_id = new_group.id
                test.save()

        group_to_delete.delete()

        return True

    def delete_test(self, test_id: str) -> bool:
        test_to_delete = ArgusTest.get(id=test_id)
        test_to_delete.delete()

        return True

    def update_group(self, group_id: str, name: str, pretty_name: str, enabled: bool, build_system_id: str) -> bool:
        group = ArgusGroup.get(id=UUID(group_id))

        group.name = name
        group.build_system_id = build_system_id
        group.pretty_name = pretty_name
        group.enabled = enabled

        group.save()

        return True

    def update_test(self, test_id: str, name: str, pretty_name: str, plugin_name: str,
                    enabled: bool, build_system_id: str, build_system_url: str, group_id) -> bool:
        test: ArgusTest = ArgusTest.get(id=UUID(test_id))
        group = ArgusGroup.get(id=UUID(group_id))

        test.name = name
        test.pretty_name = pretty_name
        test.plugin_name = plugin_name
        test.enabled = enabled
        test.build_system_id = build_system_id
        test.build_system_url = build_system_url
        if test.group_id != group.id:
            test.group_id = group.id
            LOGGER.info("Relocating old test runs into a new group")

        test.validate_build_system_id()
        test.save()
        self.move_test_runs(test)
        return True

    def set_release_state(self, release_id: str, state: bool) -> bool:
        release = ArgusRelease.get(id=UUID(release_id))
        release.enabled = state
        release.save()

        return True

    def set_release_dormancy(self, release_id: str, dormant: bool) -> bool:
        release = ArgusRelease.get(id=UUID(release_id))
        release.dormant = dormant
        release.save()

        return True

    def set_release_perpetuality(self, release_id: str, perpetual: bool) -> bool:
        release = ArgusRelease.get(id=UUID(release_id))
        release.perpetual = perpetual
        release.save()

        return True

    def edit_release(self, payload: ReleaseEditPayload) -> bool:

        release: ArgusRelease = ArgusRelease.get(id=payload["id"])
        release.pretty_name = payload["pretty_name"]
        release.perpetual = payload["perpetual"]
        release.enabled = payload["enabled"]
        release.dormant = payload["dormant"]
        release.description = payload["description"]
        release.valid_version_regex = payload["valid_version_regex"]


        release.save()
        return True

    def delete_release(self, release_id: str) -> bool:

        release: ArgusRelease = ArgusRelease.get(id=release_id)

        release_groups = ArgusGroup.filter(release_id=release.id)
        release_tests = ArgusTest.filter(release_id=release.id)

        for entity in [*release_groups.all(), *release_tests.all()]:
            entity.delete()

        release.delete()
        return True

    def batch_move_tests(self, new_group_id: str, tests: list[str]) -> bool:
        group = ArgusGroup.get(id=UUID(new_group_id))

        tests: list[ArgusTest] = [ArgusTest.get(id=UUID(test_id)) for test_id in tests]

        for test in tests:
            test.group_id = group.id
            test.save()
            self.move_test_runs(test)

        return True

    def move_test_runs(self, test: ArgusTest) -> None:
        run_rows = self.session.execute(self.runs_by_build_id_stmt, parameters=(
            test.build_system_id,), execution_profile="read_fast")
        for run in run_rows:
            run["test_id"] = test.id
            run["group_id"] = test.group_id
            run["release_id"] = test.release_id
            self.session.execute(self.update_run_stmt, parameters=run)
