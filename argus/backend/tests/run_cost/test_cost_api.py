import uuid

import pytest
from starlette.testclient import TestClient

CLIENT_PREFIX = "/api/v1/client"
READ_PREFIX = "/api/v1/cost"


def _estimated(client: TestClient, run_id, value):
    return client.post(f"{CLIENT_PREFIX}/testrun/{run_id}/cost/estimated",
                       json={"value": value, "schema_version": "v8"})


def _items(client: TestClient, run_id, items):
    return client.post(f"{CLIENT_PREFIX}/testrun/{run_id}/cost/items",
                       json={"items": items, "schema_version": "v8"})


def _read(client: TestClient, run_id):
    return client.get(f"{READ_PREFIX}/run/{run_id}")


def test_stores_and_reads_back_a_full_cost_report(api_client: TestClient, argus_db):
    run_id = uuid.uuid4()
    assert _estimated(api_client, run_id, 118.40).json()["status"] == "ok"

    response = _items(api_client, run_id, [
        {"name": "longevity-db-node-1", "category": "db_node", "cost": 12.30, "pricing_tier": "spot"},
        {"name": "longevity-loader-1", "category": "loader", "cost": 3.70},
    ])

    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    cost = _read(api_client, run_id).json()["response"]
    assert cost["estimated_cost"] == pytest.approx(118.40)
    assert cost["actual_cost"] == pytest.approx(16.00)
    assert [item["name"] for item in cost["items"]] == ["longevity-db-node-1", "longevity-loader-1"]
    assert cost["items"][0]["pricing_tier"] == "spot"
    assert cost["items"][1]["leaked"] is False
    assert cost["by_category"]["db_node"] == pytest.approx(12.30)


def test_reads_null_totals_for_a_run_without_cost(api_client: TestClient, argus_db):
    cost = _read(api_client, uuid.uuid4()).json()["response"]

    assert cost == {"estimated_cost": None, "actual_cost": None, "items": [], "by_category": {}}


@pytest.mark.parametrize("value", [-1.0, float("nan"), float("inf")])
def test_rejects_an_estimate_that_is_negative_or_not_finite(api_client: TestClient, argus_db, value):
    run_id = uuid.uuid4()

    response = api_client.post(f"{CLIENT_PREFIX}/testrun/{run_id}/cost/estimated",
                               content=f'{{"value": {value}, "schema_version": "v8"}}',
                               headers={"Content-Type": "application/json"})

    assert response.status_code == 200
    assert response.json()["status"] == "error"
    assert _read(api_client, run_id).json()["response"]["estimated_cost"] is None


@pytest.mark.parametrize("item", [
    {"name": "", "category": "db_node", "cost": 1.0},
    {"name": "db-node-1", "category": "", "cost": 1.0},
    {"name": "db-node-1", "category": "db_node", "cost": -1.0},
])
def test_rejects_an_item_that_fails_validation(api_client: TestClient, argus_db, item):
    run_id = uuid.uuid4()

    response = _items(api_client, run_id, [item])

    assert response.status_code == 200
    assert response.json()["status"] == "error"
    assert _read(api_client, run_id).json()["response"]["items"] == []


def test_rejects_a_payload_that_repeats_an_item_name(api_client: TestClient, argus_db):
    run_id = uuid.uuid4()

    response = _items(api_client, run_id, [
        {"name": "db-node-1", "category": "db_node", "cost": 1.0},
        {"name": "db-node-1", "category": "db_node", "cost": 2.0},
    ])

    assert response.status_code == 200
    assert response.json()["status"] == "error"
    assert _read(api_client, run_id).json()["response"]["items"] == []


def test_requires_authentication_on_every_cost_route(anon_client: TestClient, argus_db):
    run_id = uuid.uuid4()

    assert _estimated(anon_client, run_id, 1.0).status_code == 403
    assert _items(anon_client, run_id, [{"name": "n", "category": "c", "cost": 1.0}]).status_code == 403
    assert _read(anon_client, run_id).status_code == 403
