from random import choice
import datetime
import logging
from time import sleep
from uuid import uuid4, UUID
import pytest
from argus.db.testrun import TestRun, TestRunInfo, TestRunWithHeartbeat
from argus.db.db_types import TestInvestigationStatus
from argus.db.interface import ArgusDatabase
from argus.backend.models.web import ArgusRelease, ArgusReleaseGroup, ArgusReleaseGroupTest, ArgusReleaseSchedule, ArgusReleaseScheduleAssignee, \
    ArgusReleaseScheduleGroup, ArgusReleaseScheduleTest

LOGGER = logging.getLogger(__name__)


class TestEndToEnd:
    @staticmethod
    @pytest.mark.docker_required
    def test_serialize_deserialize(completed_testrun: TestRunInfo, argus_database: ArgusDatabase):
        TestRun.set_argus(argus_database)
        test_id = uuid4()
        test_run = TestRun(test_id=test_id, build_id='argus-test/argus/argus-testing', assignee=None,
                           run_info=completed_testrun, investigation_status=TestInvestigationStatus.INVESTIGATED)

        test_run.save()

        res = argus_database.fetch(table_name=TestRun.table_name(), run_id=test_id)
        LOGGER.debug("Fetched: %s", res)
        LOGGER.info("Rebuilding object...")

        rebuilt_test_run = TestRun.from_db_row(res)

        assert rebuilt_test_run.serialize() == test_run.serialize()

    @staticmethod
    @pytest.mark.docker_required
    def test_recreate_from_id(completed_testrun: TestRunInfo, argus_database: ArgusDatabase):
        TestRun.set_argus(argus_database)
        test_id = uuid4()
        test_run = TestRun(test_id=test_id, build_id='argus-test/argus/argus-testing', assignee=None,
                           run_info=completed_testrun, investigation_status=TestInvestigationStatus.INVESTIGATED)

        test_run.save()

        rebuilt_test_run = TestRun.from_id(test_id)

        assert rebuilt_test_run.serialize() == test_run.serialize()

    @staticmethod
    @pytest.mark.docker_required
    def test_heartbeat_thread(completed_testrun: TestRunInfo, argus_database: ArgusDatabase):
        TestRunWithHeartbeat.set_argus(argus_database)
        test_id = uuid4()
        test_run = TestRunWithHeartbeat(test_id=test_id, build_id='argus-test/argus/argus-testing', assignee=None,
                                        run_info=completed_testrun, investigation_status=TestInvestigationStatus.INVESTIGATED,
                                        heartbeat_interval=8)

        test_run.save()
        sleep(test_run.heartbeat_interval + test_run.heartbeat_interval // 2)
        new_heartbeat = argus_database.session.execute(f"SELECT heartbeat FROM {TestRun.table_name()} WHERE id = %s",
                                                       parameters=(test_run.id,)).one()["heartbeat"]
        # pylint: disable=protected-access
        test_run._shutdown_event.set()
        LOGGER.info("Awaiting heartbeat thread exit")
        test_run.thread.join(timeout=10)
        assert new_heartbeat == test_run.heartbeat

    @staticmethod
    @pytest.mark.docker_required
    def test_update(completed_testrun: TestRunInfo, argus_database: ArgusDatabase):
        TestRun.set_argus(argus_database)
        test_id = uuid4()
        test_run = TestRun(test_id=test_id, build_id='argus-test/argus/argus-testing', assignee=None,
                           run_info=completed_testrun, investigation_status=TestInvestigationStatus.INVESTIGATED)
        test_run.save()

        resource = choice(test_run.run_info.resources.allocated_resources)
        test_run.run_info.resources.detach_resource(resource)
        test_run.save()

        row = argus_database.fetch(table_name=TestRun.table_name(), run_id=test_id)

        rebuilt_testrun = TestRun.from_db_row(row)

        assert test_run.serialize() == rebuilt_testrun.serialize()

    @staticmethod
    @pytest.mark.docker_required
    def test_auto_assign_run_by_group(completed_testrun: TestRunInfo,
                                      argus_with_release: tuple[ArgusDatabase, tuple[ArgusRelease, ArgusReleaseGroup, ArgusReleaseGroupTest]]):
        group_assignee_user = uuid4()
        argus_database, [release, group, test] = argus_with_release

        today = datetime.datetime.utcnow()
        this_monday = today - datetime.timedelta(today.weekday() + 1)
        next_week = this_monday + datetime.timedelta(8)

        schedule = ArgusReleaseSchedule()
        schedule.release_id = release.id
        schedule.period_start = this_monday
        schedule.period_end = next_week
        schedule.using(connection=argus_database.CQL_ENGINE_CONNECTION_NAME).save()

        scheduled_group = ArgusReleaseScheduleGroup()
        scheduled_group.schedule_id = schedule.id
        scheduled_group.release_id = release.id
        scheduled_group.group_id = group.id
        scheduled_group.using(connection=argus_database.CQL_ENGINE_CONNECTION_NAME).save()

        scheduled_assignee = ArgusReleaseScheduleAssignee()
        scheduled_assignee.schedule_id = schedule.id
        scheduled_assignee.release_id = release.id
        scheduled_assignee.assignee = group_assignee_user
        scheduled_assignee.using(connection=argus_database.CQL_ENGINE_CONNECTION_NAME).save()

        TestRun.set_argus(argus_database)
        test_id = uuid4()
        test_run = TestRun(test_id=test_id, build_id=test.build_system_id, assignee=None,
                           run_info=completed_testrun, investigation_status=TestInvestigationStatus.INVESTIGATED)
        test_run.save()
        assert group_assignee_user == test_run.assignee

        row = argus_database.fetch(table_name=TestRun.table_name(), run_id=test_id)
        rebuilt_testrun = TestRun.from_db_row(row)
        assert group_assignee_user == rebuilt_testrun.assignee

        scheduled_assignee.using(connection=argus_database.CQL_ENGINE_CONNECTION_NAME).delete()
        scheduled_group.using(connection=argus_database.CQL_ENGINE_CONNECTION_NAME).delete()
        schedule.using(connection=argus_database.CQL_ENGINE_CONNECTION_NAME).delete()

    @staticmethod
    @pytest.mark.docker_required
    def test_auto_assign_run_by_test_name(completed_testrun: TestRunInfo,
                                          argus_with_release: tuple[ArgusDatabase, tuple[ArgusRelease, ArgusReleaseGroup, ArgusReleaseGroupTest]]):
        test_assignee_user = uuid4()
        argus_database, [release, _, test] = argus_with_release

        today = datetime.datetime.utcnow()
        this_monday = today - datetime.timedelta(today.weekday() + 1)
        next_week = this_monday + datetime.timedelta(8)

        schedule = ArgusReleaseSchedule()
        schedule.release_id = release.id
        schedule.period_start = this_monday
        schedule.period_end = next_week
        schedule.using(connection=argus_database.CQL_ENGINE_CONNECTION_NAME).save()

        scheduled_test = ArgusReleaseScheduleTest()
        scheduled_test.schedule_id = schedule.id
        scheduled_test.release_id = release.id
        scheduled_test.test_id = test.id
        scheduled_test.using(connection=argus_database.CQL_ENGINE_CONNECTION_NAME).save()

        scheduled_assignee = ArgusReleaseScheduleAssignee()
        scheduled_assignee.schedule_id = schedule.id
        scheduled_assignee.release_id = release.id
        scheduled_assignee.assignee = test_assignee_user
        scheduled_assignee.using(connection=argus_database.CQL_ENGINE_CONNECTION_NAME).save()

        TestRun.set_argus(argus_database)
        test_id = uuid4()
        test_run = TestRun(test_id=test_id, build_id=test.build_system_id, assignee=None,
                           run_info=completed_testrun, investigation_status=TestInvestigationStatus.INVESTIGATED)
        test_run.save()
        assert test_assignee_user == test_run.assignee

        row = argus_database.fetch(table_name=TestRun.table_name(), run_id=test_id)
        rebuilt_testrun = TestRun.from_db_row(row)
        assert test_assignee_user == rebuilt_testrun.assignee
        scheduled_assignee.using(connection=argus_database.CQL_ENGINE_CONNECTION_NAME).delete()
        scheduled_test.using(connection=argus_database.CQL_ENGINE_CONNECTION_NAME).delete()
        schedule.using(connection=argus_database.CQL_ENGINE_CONNECTION_NAME).delete()
