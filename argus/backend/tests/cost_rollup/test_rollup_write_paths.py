from unittest.mock import patch

import pytest
from cassandra.cluster import NoHostAvailable

from argus.backend.service.cost_rollup_service import CostRollupService
from argus.backend.service.run_cost_service import CostItemRequest, RunCostService
from argus.backend.tests.cost_rollup.helpers import rollup_rows, submitted_run


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
