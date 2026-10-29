import uuid
from datetime import UTC, datetime, timedelta

import pytest
from starlette.testclient import TestClient

from argus.backend.tests.cost_explorer.helpers import END, START, create_view, seed

EXPLORER = "/api/v1/cost/explorer"
PANELS = {"window", "span", "tiles", "series", "releases", "top_runs", "coverage", "tiers", "spot_terminations"}


def _explore(client: TestClient, **params) -> dict:
    return client.get(EXPLORER, params=params).json()


def test_returns_every_panel_with_the_defaults(api_client: TestClient, argus_db):
    body = _explore(api_client, plugin=f"plugin-{uuid.uuid4()}")

    assert body["status"] == "ok"
    assert set(body["response"]) == PANELS
    window = body["response"]["window"]
    assert window == {**window, "granularity": "week", "breakdown": "group", "tiers": []}
    end = datetime.fromisoformat(window["to"])
    start = datetime.fromisoformat(window["from"])
    assert datetime.now(UTC) - end < timedelta(minutes=1)
    assert start == (end - timedelta(days=90)).replace(hour=0, minute=0, second=0, microsecond=0)
    assert body["response"]["tiles"]["runs"] == 0
    assert body["response"]["releases"] == []


async def test_filters_by_release_name_within_an_offset_iso_window(api_client: TestClient, argus_db, release):
    plugin = f"plugin-{uuid.uuid4()}"
    await seed(plugin, START + timedelta(hours=1), release.id, actual_cost=5.0)
    await seed(plugin, START - timedelta(hours=1), release.id, actual_cost=50.0)
    await seed(plugin, START + timedelta(hours=1), uuid.uuid4(), actual_cost=500.0)

    body = _explore(api_client, plugin=plugin, releaseName=release.name, granularity="day", breakdown="test",
                    **{"from": "2026-10-21T02:00:00+02:00", "to": END.isoformat()})

    tiles = body["response"]["tiles"]
    assert tiles["spend"] == pytest.approx(5.0)
    assert tiles["previous_spend"] == pytest.approx(50.0)
    assert datetime.fromisoformat(body["response"]["window"]["from"]) == START
    assert body["response"]["window"]["granularity"] == "day"
    assert body["response"]["window"]["breakdown"] == "test"
    assert [entry["id"] for entry in body["response"]["releases"]] == [str(release.id)]


async def test_view_id_expands_to_the_view_ids(api_client: TestClient, argus_db):
    plugin, release_id, test_id = f"plugin-{uuid.uuid4()}", uuid.uuid4(), uuid.uuid4()
    view_id = create_view(api_client, [f"release:{release_id}", f"test:{test_id}"])
    await seed(plugin, START + timedelta(days=1), release_id, actual_cost=1.0)
    await seed(plugin, START + timedelta(days=1), uuid.uuid4(), actual_cost=2.0, test_id=test_id)
    await seed(plugin, START + timedelta(days=1), uuid.uuid4(), actual_cost=4.0)

    body = _explore(api_client, plugin=plugin, viewId=view_id, **{"from": START.isoformat(), "to": END.isoformat()})

    assert body["response"]["tiles"]["spend"] == pytest.approx(3.0)


async def test_filters_accept_several_values(api_client: TestClient, argus_db, release):
    plugin = f"plugin-{uuid.uuid4()}"
    await seed(plugin, START + timedelta(days=1), release.id, actual_cost=1.0, backend="aws", spot_cost=1.0, spot_count=1)
    await seed(plugin, START + timedelta(days=1), release.id, actual_cost=2.0, backend="gce", on_demand_cost=2.0,
               on_demand_count=1)
    await seed(plugin, START + timedelta(days=1), release.id, actual_cost=4.0, backend="azure", on_demand_cost=4.0,
               on_demand_count=1)

    body = _explore(api_client, plugin=plugin, releaseName=[release.name, release.name], backend=["aws", "gce"],
                    tier=["spot", "on-demand"], **{"from": START.isoformat(), "to": END.isoformat()})

    assert body["response"]["tiles"]["spend"] == pytest.approx(3.0)
    assert body["response"]["window"]["tiers"] == ["on-demand", "spot"]


def test_rejects_an_unknown_granularity_or_window(api_client: TestClient, argus_db):
    assert _explore(api_client, granularity="hour")["status"] == "error"
    assert _explore(api_client, tier="free")["status"] == "error"
    assert _explore(api_client, **{"from": END.isoformat(), "to": START.isoformat()})["status"] == "error"
    assert _explore(api_client, viewId=str(uuid.uuid4()))["status"] == "error"
    assert _explore(api_client, releaseName=f"no-such-release-{uuid.uuid4()}")["status"] == "error"


def test_requires_a_logged_in_user(anon_client: TestClient, argus_db):
    assert anon_client.get(EXPLORER).status_code == 403
