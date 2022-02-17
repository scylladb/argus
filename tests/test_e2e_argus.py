from random import choice
import datetime
import logging
from uuid import uuid4, UUID
import pytest
from argus.db.testrun import TestRun, TestRunInfo
from argus.db.db_types import TestInvestigationStatus
from argus.db.interface import ArgusDatabase
from argus.db.models import ArgusReleaseSchedule, ArgusReleaseScheduleAssignee, \
    ArgusReleaseScheduleGroup

LOGGER = logging.getLogger(__name__)


class TestEndToEnd:
    @staticmethod
    @pytest.mark.docker_required
    def test_serialize_deserialize(completed_testrun: TestRunInfo, argus_database: ArgusDatabase):
        TestRun.set_argus(argus_database)
        test_id = uuid4()
        test_run = TestRun(test_id=test_id, group="longevity-test", release_name="4_5rc5", assignee="",
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
        test_run = TestRun(test_id=test_id, group="longevity-test", release_name="4_5rc5", assignee="",
                           run_info=completed_testrun, investigation_status=TestInvestigationStatus.INVESTIGATED)

        test_run.save()

        rebuilt_test_run = TestRun.from_id(test_id)

        assert rebuilt_test_run.serialize() == test_run.serialize()

    @staticmethod
    @pytest.mark.docker_required
    def test_update(completed_testrun: TestRunInfo, argus_database: ArgusDatabase):
        TestRun.set_argus(argus_database)
        test_id = uuid4()
        test_run = TestRun(test_id=test_id, group="longevity-test", release_name="4_5rc5", assignee="",
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
    def test_auto_assign_run(completed_testrun: TestRunInfo, argus_database: ArgusDatabase):
        group_assignee_user = uuid4()

        today = datetime.datetime.utcnow()
        this_monday = today - datetime.timedelta(today.weekday() + 1)
        next_week = this_monday + datetime.timedelta(8)

        schedule = ArgusReleaseSchedule()
        schedule.release = "4_5rc5"
        schedule.period_start = this_monday
        schedule.period_end = next_week
        schedule.using(connection=argus_database.CQL_ENGINE_CONNECTION_NAME).save()

        scheduled_group = ArgusReleaseScheduleGroup()
        scheduled_group.schedule_id = schedule.schedule_id
        scheduled_group.release = "4_5rc5"
        scheduled_group.name = "longevity-test"
        scheduled_group.using(connection=argus_database.CQL_ENGINE_CONNECTION_NAME).save()

        scheduled_assignee = ArgusReleaseScheduleAssignee()
        scheduled_assignee.schedule_id = schedule.schedule_id
        scheduled_assignee.release = "4_5rc5"
        scheduled_assignee.assignee = group_assignee_user
        scheduled_assignee.using(connection=argus_database.CQL_ENGINE_CONNECTION_NAME).save()

        TestRun.set_argus(argus_database)
        test_id = uuid4()
        test_run = TestRun(test_id=test_id, group="longevity-test", release_name="4_5rc5", assignee="",
                           run_info=completed_testrun, investigation_status=TestInvestigationStatus.INVESTIGATED)
        test_run.save()
        assert group_assignee_user == UUID(test_run.assignee)

        row = argus_database.fetch(table_name=TestRun.table_name(), run_id=test_id)
        rebuilt_testrun = TestRun.from_db_row(row)
        assert group_assignee_user == UUID(rebuilt_testrun.assignee)
