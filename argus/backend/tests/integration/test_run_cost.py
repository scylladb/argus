"""E2E coverage for the cost methods on the base ArgusClient.

The methods live on the base class, so every plugin client inherits them.
The run cost store is keyed by the run id alone and reads no run, so a cost
report needs no submitted run.
"""

import uuid

import pytest

from argus.client.base import ArgusClientError
from argus.client.types import CostItem

pytestmark = pytest.mark.docker_required


def _read_cost(api_client, run_id) -> dict:
    response = api_client.get(f"/api/v1/cost/run/{run_id}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok", body
    return body["response"]


def test_reports_an_estimate_and_items_for_a_run(sct_client, api_client):
    run_id = uuid.uuid4()

    sct_client.set_estimated_cost(run_id, 118.40)
    sct_client.submit_cost_items(run_id, [
        CostItem(name="longevity-loader-1", category="loader", cost=3.70),
        CostItem(name="longevity-db-node-1", category="db_node", cost=12.30, pricing_tier="spot"),
    ])

    cost = _read_cost(api_client, run_id)
    assert cost["estimated_cost"] == pytest.approx(118.40)
    assert cost["actual_cost"] == pytest.approx(16.00)
    assert [item["name"] for item in cost["items"]] == ["longevity-db-node-1", "longevity-loader-1"]
    assert cost["items"][0]["pricing_tier"] == "spot"
    assert cost["by_category"]["db_node"] == pytest.approx(12.30)
    assert cost["by_category"]["loader"] == pytest.approx(3.70)


def test_adds_a_leaked_item_found_after_the_run(generic_client, api_client):
    run_id = uuid.uuid4()
    generic_client.submit_cost_items(run_id, [
        CostItem(name="db-node-1", category="db_node", cost=10.0),
    ])

    generic_client.submit_cost_items(run_id, [
        CostItem(name="orphan-node", category="db_node", cost=4.0, leaked=True),
    ])

    cost = _read_cost(api_client, run_id)
    assert cost["actual_cost"] == pytest.approx(14.0)
    assert [item["leaked"] for item in cost["items"]] == [False, True]


def test_rejects_a_negative_amount_at_the_boundary(sct_client):
    with pytest.raises(ArgusClientError):
        sct_client.set_estimated_cost(uuid.uuid4(), -1.0)
