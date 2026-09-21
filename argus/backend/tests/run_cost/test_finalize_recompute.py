from dataclasses import asdict
from unittest.mock import patch
from uuid import UUID

import pytest
from cassandra.cluster import NoHostAvailable

from argus.backend.models.run_cost import RunCost
from argus.backend.models.web import ArgusTest
from argus.backend.service.client_service import ClientService
from argus.backend.service.run_cost_service import CostItemRequest, RunCostService
from argus.backend.tests.conftest import get_fake_test_run


@pytest.fixture(scope="session")
def run_cost_service(argus_db) -> RunCostService:
    return RunCostService()


def _submitted_run(client_service: ClientService, fake_test: ArgusTest) -> tuple[str, str]:
    run_type, run_req = get_fake_test_run(fake_test)
    client_service.submit_run(run_type, asdict(run_req))
    return run_type, run_req.run_id


def test_finalize_repairs_a_sum_left_stale(client_service: ClientService, run_cost_service: RunCostService,
                                           fake_test: ArgusTest):
    run_type, run_id = _submitted_run(client_service, fake_test)
    run_cost_service.submit_cost_items(run_id, [
        CostItemRequest(name="db-node-1", category="db_node", cost=10.0),
    ])
    RunCost.find(run_id=UUID(run_id)).update(actual_cost=999.0)

    client_service.finish_run(run_type=run_type, run_id=str(run_id))

    assert run_cost_service.get_run_cost(run_id)["actual_cost"] == pytest.approx(10.0)


def test_finalize_takes_the_estimate_when_no_item_was_reported(client_service: ClientService,
                                                               run_cost_service: RunCostService,
                                                               fake_test: ArgusTest):
    run_type, run_id = _submitted_run(client_service, fake_test)
    run_cost_service.set_estimated_cost(run_id, 118.40)

    client_service.finish_run(run_type=run_type, run_id=str(run_id))

    cost = run_cost_service.get_run_cost(run_id)
    assert cost["actual_cost"] == pytest.approx(118.40)
    assert cost["estimated_cost"] == pytest.approx(118.40)


def test_finalize_survives_a_database_failure_in_the_recompute(client_service: ClientService,
                                                               run_cost_service: RunCostService,
                                                               fake_test: ArgusTest):
    run_type, run_id = _submitted_run(client_service, fake_test)
    run_cost_service.submit_cost_items(run_id, [
        CostItemRequest(name="db-node-1", category="db_node", cost=10.0),
    ])

    with patch.object(RunCostService, "recompute_actual_cost", side_effect=NoHostAvailable("down", {})):
        assert client_service.finish_run(run_type=run_type, run_id=str(run_id)) == "Finalized"


def test_finalize_leaves_a_run_that_reported_no_cost_alone(client_service: ClientService,
                                                           run_cost_service: RunCostService,
                                                           fake_test: ArgusTest):
    run_type, run_id = _submitted_run(client_service, fake_test)

    assert client_service.finish_run(run_type=run_type, run_id=str(run_id)) == "Finalized"

    cost = run_cost_service.get_run_cost(run_id)
    assert cost["actual_cost"] is None
    assert cost["estimated_cost"] is None
