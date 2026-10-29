import uuid
from datetime import UTC, datetime, timedelta

import pytest
from starlette.testclient import TestClient

from argus.backend.tests.cost_explorer.helpers import create_view, seed

WIDGET = "/api/v1/views/widgets/costs"


async def test_widget_reads_the_view_ids_over_the_last_days(api_client: TestClient, argus_db):
    plugin, release_id = f"plugin-{uuid.uuid4()}", uuid.uuid4()
    view_id = create_view(api_client, [f"release:{release_id}"])
    now = datetime.now(UTC)
    await seed(plugin, now - timedelta(days=2), release_id, actual_cost=5.0)
    await seed(plugin, now - timedelta(days=20), release_id, actual_cost=50.0)
    await seed(plugin, now - timedelta(days=2), uuid.uuid4(), actual_cost=500.0)

    body = api_client.get(WIDGET, params={"view_id": view_id, "days": 7}).json()

    assert body["status"] == "ok"
    assert body["response"]["tiles"]["spend"] == pytest.approx(5.0)
    assert body["response"]["window"]["granularity"] == "day"
    assert [release["id"] for release in body["response"]["releases"]] == [str(release_id)]


def test_widget_uses_weeks_past_a_month_and_rejects_a_long_window(api_client: TestClient, argus_db):
    view_id = create_view(api_client, [])

    assert api_client.get(WIDGET, params={"view_id": view_id, "days": 90}).json()["response"]["window"]["granularity"] == "week"
    assert api_client.get(WIDGET, params={"view_id": view_id, "days": 400}).json()["status"] == "error"
    assert api_client.get(WIDGET, params={"view_id": str(uuid.uuid4())}).json()["status"] == "error"
