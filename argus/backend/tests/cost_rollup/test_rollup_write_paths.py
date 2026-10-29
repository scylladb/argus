import uuid
from dataclasses import asdict, replace
from unittest.mock import patch
from uuid import UUID

import pytest
from cassandra.cluster import NoHostAvailable

from argus.backend.models.run_cost_rollup import UNASSIGNED_RELEASE
from argus.backend.service.cost_rollup_service import CostRollupService
from argus.backend.service.run_cost_service import CostItemRequest, RunCostService
from argus.backend.tests.conftest import get_fake_test_run
from argus.backend.tests.cost_rollup.helpers import rollup_rows, submitted_run
from argus.common.enums import TestStatus


@pytest.fixture(scope="session")
def run_cost_service(argus_db) -> RunCostService:
    return RunCostService()


async def test_item_submit_refreshes_the_rollup(client_service, run_cost_service, fake_test):
    _, run_id = await submitted_run(client_service, fake_test)

    await run_cost_service.submit_cost_items(run_id, [CostItemRequest(name="db-node-1", category="db_node", cost=7.0)])

    (row,) = await rollup_rows(run_id, fake_test.release_id)
    assert row.actual_cost == pytest.approx(7.0)
    assert row.item_count == 1


async def test_estimate_submit_refreshes_the_rollup(client_service, run_cost_service, fake_test):
    _, run_id = await submitted_run(client_service, fake_test)

    await run_cost_service.set_estimated_cost(run_id, 55.0)

    (row,) = await rollup_rows(run_id, fake_test.release_id)
    assert row.estimated_cost == pytest.approx(55.0)
    assert row.actual_cost is None
    assert row.coverage == "none"


async def test_finalize_writes_a_row_for_a_run_without_cost(client_service, fake_test):
    run_type, run_id = await submitted_run(client_service, fake_test)

    await client_service.finish_run(run_type=run_type, run_id=run_id)

    (row,) = await rollup_rows(run_id, fake_test.release_id)
    assert row.end_time is not None
    assert row.actual_cost is None
    assert row.coverage == "none"


async def test_leaked_item_after_finalize_updates_the_row(client_service, run_cost_service, fake_test):
    run_type, run_id = await submitted_run(client_service, fake_test)
    await run_cost_service.submit_cost_items(run_id, [CostItemRequest(name="db-node-1", category="db_node", cost=4.0)])
    await client_service.finish_run(run_type=run_type, run_id=run_id)
    (finalized,) = await rollup_rows(run_id, fake_test.release_id)

    await run_cost_service.submit_cost_items(run_id, [
        CostItemRequest(name="db-node-2", category="db_node", cost=1.5, leaked=True),
    ])

    (row,) = await rollup_rows(run_id, fake_test.release_id)
    assert row.actual_cost == pytest.approx(5.5)
    assert row.leaked_cost == pytest.approx(1.5)
    assert row.leaked_count == 1
    assert row.status == finalized.status
    assert row.end_time == finalized.end_time


async def test_finalize_survives_a_rollup_failure(client_service, fake_test):
    run_type, run_id = await submitted_run(client_service, fake_test)

    with patch.object(CostRollupService, "refresh", side_effect=NoHostAvailable("down", {})):
        assert await client_service.finish_run(run_type=run_type, run_id=run_id) == "Finalized"


async def test_item_submit_survives_a_rollup_failure(client_service, run_cost_service, fake_test):
    _, run_id = await submitted_run(client_service, fake_test)

    with patch.object(CostRollupService, "refresh", side_effect=NoHostAvailable("down", {})):
        result = await run_cost_service.submit_cost_items(run_id, [
            CostItemRequest(name="db-node-1", category="db_node", cost=2.0),
        ])

    assert result["submitted"] == 1
    assert result["actual_cost"] == pytest.approx(2.0)


async def test_client_status_update_refreshes_the_row(client_service, fake_test):
    run_type, run_id = await submitted_run(client_service, fake_test)

    await client_service.update_run_status(run_type=run_type, run_id=run_id, new_status=TestStatus.FAILED.value)

    (row,) = await rollup_rows(run_id, fake_test.release_id)
    assert row.status == TestStatus.FAILED.value


async def test_ui_status_change_refreshes_the_row(client_service, testrun_service, fake_test, logged_in_user):
    run_type, run_id = await submitted_run(client_service, fake_test)
    await client_service.finish_run(run_type=run_type, run_id=run_id)

    await testrun_service.change_run_status(fake_test.id, run_id, TestStatus.ABORTED, logged_in_user)

    (row,) = await rollup_rows(run_id, fake_test.release_id)
    assert row.status == TestStatus.ABORTED.value
    assert row.end_time is not None


async def test_registering_the_test_moves_the_row_out_of_unassigned(client_service, run_cost_service,
                                                                     release_manager_service, fake_test, group,
                                                                     release):
    run_type, request = get_fake_test_run(fake_test)
    request = replace(request, job_name=f"unregistered/{uuid.uuid4()}")
    await client_service.submit_run(run_type, asdict(request))
    run_id = UUID(request.run_id)
    await run_cost_service.set_estimated_cost(run_id, 20.0)
    (unassigned,) = await rollup_rows(run_id, UNASSIGNED_RELEASE)
    assert unassigned.test_id is None

    test = await release_manager_service.create_test(request.job_name, request.job_name, request.job_name,
                                                     "http://example.com/job", group_id=group.id,
                                                     release_id=release.id, plugin_name="scylla-cluster-tests")

    assert await rollup_rows(run_id, UNASSIGNED_RELEASE) == []
    (row,) = await rollup_rows(run_id, release.id)
    assert row.test_id == test.id
    assert row.group_id == group.id
    assert row.estimated_cost == pytest.approx(20.0)
