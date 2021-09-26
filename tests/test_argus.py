from random import choice

from argus.test_run import TestResourcesSetup, TestRun, TestRunInfo
from argus.db import ArgusDatabase
from argus.config import Config

from argus.helpers import ColumnInfo
from uuid import uuid4

import pytest
import logging

LOGGER = logging.getLogger(__name__)


def test_serialization(preset_details: TestResourcesSetup):
    serialized_setup = preset_details.serialize()
    assert serialized_setup["cloud_setup"]["db_node"]["image_id"] == "ami-abcdef99"


def test_schema_dump(preset_details: TestResourcesSetup):
    schema_dump = preset_details.schema()
    assert schema_dump["cloud_setup"].value.db_node.image_id == "ami-abcdef99"


@pytest.mark.skip("Not needed if test_full_run isn't skipped")
@pytest.mark.docker_required
def test_db_setupinfo(preset_details: TestResourcesSetup, argus_database: ArgusDatabase):
    column_info = ColumnInfo(name="id", type=str, value=str(uuid4()), constraints=[])
    schema = preset_details.schema()
    schema["id"] = column_info
    argus_database.init_keyspace(prefix="test", suffix="4_5rc5")
    argus_database.init_table(column_info=schema, table_name="setup_schema_test")
    argus_database.insert(table_name="setup_schema_test",
                          run_data={"id": str(uuid4()), **preset_details.serialize()})


@pytest.mark.docker_required
def test_serialize_deserialize(completed_testrun: TestRunInfo, argus_database: ArgusDatabase):
    test_id = uuid4()
    test_run = TestRun(test_id=test_id, group="longevity-test", release_name="4_5rc5", assignee="k0machi",
                       run_info=completed_testrun)

    test_run.save()

    res = argus_database.fetch(table_name=f"test_run_{test_run.release_name}", run_id=test_id)
    LOGGER.debug("Fetched: %s", res)
    LOGGER.info("Rebuilding object...")

    rebuilt_test_run = TestRun.from_db_row(res)

    assert rebuilt_test_run.serialize() == test_run.serialize()


@pytest.mark.docker_required
def test_update(completed_testrun: TestRunInfo, argus_database: ArgusDatabase):
    test_id = uuid4()
    test_run = TestRun(test_id=test_id, group="longevity-test", release_name="4_5rc5", assignee="k0machi",
                       run_info=completed_testrun)
    test_run.save()

    resource = choice(test_run.resources.leftover_resources)
    test_run.resources.detach_resource(resource)
    test_run.save()

    row = argus_database.fetch(table_name=f"test_run_{test_run.release_name}", run_id=test_id)

    rebuilt_testrun = TestRun.from_db_row(row)

    assert test_run.serialize() == rebuilt_testrun.serialize()
