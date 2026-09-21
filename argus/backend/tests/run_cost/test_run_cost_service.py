import uuid

import pytest

from argus.backend.error_handlers import DataValidationError
from argus.backend.models.run_cost import RunCost
from argus.backend.service.run_cost_service import CostItemRequest, RunCostService


@pytest.fixture(scope="session")
def run_cost_service(argus_db) -> RunCostService:
    return RunCostService()


def _item(name: str, category: str, cost: float, **kwargs) -> CostItemRequest:
    return CostItemRequest(name=name, category=category, cost=cost, **kwargs)


def test_reports_null_totals_and_no_items_for_a_run_without_cost(run_cost_service: RunCostService):
    cost = run_cost_service.get_run_cost(uuid.uuid4())

    assert cost["estimated_cost"] is None
    assert cost["actual_cost"] is None
    assert cost["items"] == []
    assert cost["by_category"] == {}


def test_stores_an_estimate_before_any_item_arrives(run_cost_service: RunCostService):
    run_id = uuid.uuid4()

    run_cost_service.set_estimated_cost(run_id, 118.40)

    cost = run_cost_service.get_run_cost(run_id)
    assert cost["estimated_cost"] == pytest.approx(118.40)
    assert cost["actual_cost"] is None
    assert cost["items"] == []


def test_sums_submitted_items_into_the_actual_cost(run_cost_service: RunCostService):
    run_id = uuid.uuid4()

    run_cost_service.submit_cost_items(run_id, [
        _item("longevity-db-node-1", "db_node", 12.30),
        _item("longevity-loader-1", "loader", 3.70),
    ])

    cost = run_cost_service.get_run_cost(run_id)
    assert cost["actual_cost"] == pytest.approx(16.00)
    assert cost["by_category"]["db_node"] == pytest.approx(12.30)
    assert cost["by_category"]["loader"] == pytest.approx(3.70)


def test_adds_a_later_item_to_the_same_run(run_cost_service: RunCostService):
    run_id = uuid.uuid4()
    run_cost_service.submit_cost_items(run_id, [_item("db-node-1", "db_node", 10.0)])

    run_cost_service.submit_cost_items(run_id, [_item("db-node-2", "db_node", 5.5)])

    cost = run_cost_service.get_run_cost(run_id)
    assert cost["actual_cost"] == pytest.approx(15.5)
    assert [item["name"] for item in cost["items"]] == ["db-node-1", "db-node-2"]


def test_overwrites_an_item_reported_twice_under_one_name(run_cost_service: RunCostService):
    run_id = uuid.uuid4()
    run_cost_service.submit_cost_items(run_id, [_item("db-node-1", "db_node", 10.0)])

    run_cost_service.submit_cost_items(run_id, [_item("db-node-1", "db_node", 7.25)])

    cost = run_cost_service.get_run_cost(run_id)
    assert len(cost["items"]) == 1
    assert cost["items"][0]["cost"] == pytest.approx(7.25)
    assert cost["actual_cost"] == pytest.approx(7.25)


def test_counts_a_leaked_item_towards_the_actual_cost(run_cost_service: RunCostService):
    run_id = uuid.uuid4()

    run_cost_service.submit_cost_items(run_id, [
        _item("db-node-1", "db_node", 10.0),
        _item("orphan-node", "db_node", 4.0, leaked=True),
    ])

    cost = run_cost_service.get_run_cost(run_id)
    assert cost["actual_cost"] == pytest.approx(14.0)
    leaked = next(item for item in cost["items"] if item["name"] == "orphan-node")
    assert leaked["leaked"] is True


def test_keeps_the_estimate_when_an_item_arrives(run_cost_service: RunCostService):
    run_id = uuid.uuid4()
    run_cost_service.set_estimated_cost(run_id, 100.0)

    run_cost_service.submit_cost_items(run_id, [_item("db-node-1", "db_node", 42.0)])

    cost = run_cost_service.get_run_cost(run_id)
    assert cost["estimated_cost"] == pytest.approx(100.0)
    assert cost["actual_cost"] == pytest.approx(42.0)


def test_keeps_the_actual_cost_when_a_later_estimate_arrives(run_cost_service: RunCostService):
    run_id = uuid.uuid4()
    run_cost_service.submit_cost_items(run_id, [_item("db-node-1", "db_node", 42.0)])

    run_cost_service.set_estimated_cost(run_id, 100.0)

    cost = run_cost_service.get_run_cost(run_id)
    assert cost["actual_cost"] == pytest.approx(42.0)
    assert cost["estimated_cost"] == pytest.approx(100.0)


def test_stores_the_optional_item_fields(run_cost_service: RunCostService):
    run_id = uuid.uuid4()

    run_cost_service.submit_cost_items(run_id, [
        _item("db-node-1", "db_node", 12.30, pricing_tier="spot"),
    ])

    item = run_cost_service.get_run_cost(run_id)["items"][0]
    assert item["pricing_tier"] == "spot"
    assert item["leaked"] is False


def test_sorts_items_by_category_then_name(run_cost_service: RunCostService):
    run_id = uuid.uuid4()

    run_cost_service.submit_cost_items(run_id, [
        _item("loader-2", "loader", 1.0),
        _item("db-node-2", "db_node", 1.0),
        _item("loader-1", "loader", 1.0),
        _item("db-node-1", "db_node", 1.0),
    ])

    names = [item["name"] for item in run_cost_service.get_run_cost(run_id)["items"]]
    assert names == ["db-node-1", "db-node-2", "loader-1", "loader-2"]


def test_accepts_a_zero_amount_as_a_real_figure(run_cost_service: RunCostService):
    run_id = uuid.uuid4()

    run_cost_service.submit_cost_items(run_id, [_item("free-tier-node", "db_node", 0.0)])

    cost = run_cost_service.get_run_cost(run_id)
    assert cost["actual_cost"] == pytest.approx(0.0)
    assert cost["items"][0]["cost"] == pytest.approx(0.0)


def test_rejects_a_repeated_name_within_one_payload(run_cost_service: RunCostService):
    run_id = uuid.uuid4()

    with pytest.raises(DataValidationError):
        run_cost_service.submit_cost_items(run_id, [
            _item("db-node-1", "db_node", 10.0),
            _item("db-node-1", "db_node", 12.0),
        ])

    assert run_cost_service.get_run_cost(run_id)["items"] == []


def test_writes_every_item_of_one_submission_or_none(run_cost_service: RunCostService):
    run_id = uuid.uuid4()

    run_cost_service.submit_cost_items(run_id, [
        _item("db-node-1", "db_node", 1.0),
        _item("db-node-2", "db_node", 2.0),
        _item("loader-1", "loader", 3.0),
    ])

    cost = run_cost_service.get_run_cost(run_id)
    assert [item["name"] for item in cost["items"]] == ["db-node-1", "db-node-2", "loader-1"]
    assert cost["actual_cost"] == pytest.approx(6.0)


def test_recompute_falls_back_to_the_estimate_only_when_asked(run_cost_service: RunCostService):
    run_id = uuid.uuid4()
    run_cost_service.set_estimated_cost(run_id, 118.40)

    run_cost_service.recompute_actual_cost(run_id, use_estimate=True)

    assert run_cost_service.get_run_cost(run_id)["actual_cost"] == pytest.approx(118.40)


def test_recompute_leaves_the_actual_cost_null_while_the_run_is_in_flight(run_cost_service: RunCostService):
    run_id = uuid.uuid4()
    run_cost_service.set_estimated_cost(run_id, 118.40)

    run_cost_service.recompute_actual_cost(run_id)

    assert run_cost_service.get_run_cost(run_id)["actual_cost"] is None


def test_an_empty_submission_does_not_take_the_estimate_as_the_actual_cost(run_cost_service: RunCostService):
    run_id = uuid.uuid4()
    run_cost_service.set_estimated_cost(run_id, 118.40)

    run_cost_service.submit_cost_items(run_id, [])

    cost = run_cost_service.get_run_cost(run_id)
    assert cost["actual_cost"] is None
    assert cost["estimated_cost"] == pytest.approx(118.40)


def test_recompute_leaves_a_run_without_any_cost_alone(run_cost_service: RunCostService):
    run_id = uuid.uuid4()

    run_cost_service.recompute_actual_cost(run_id)

    cost = run_cost_service.get_run_cost(run_id)
    assert cost["actual_cost"] is None
    assert cost["estimated_cost"] is None


def test_recompute_repairs_a_sum_left_stale(run_cost_service: RunCostService):
    run_id = uuid.uuid4()
    run_cost_service.submit_cost_items(run_id, [_item("db-node-1", "db_node", 10.0)])
    RunCost.find(run_id=run_id).update(actual_cost=999.0)

    run_cost_service.recompute_actual_cost(run_id)

    assert run_cost_service.get_run_cost(run_id)["actual_cost"] == pytest.approx(10.0)
