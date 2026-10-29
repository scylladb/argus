import uuid
from datetime import UTC, datetime
from uuid import UUID

from starlette.testclient import TestClient

from argus.backend.models.run_cost_rollup import RunCostReleaseSpan, RunCostRollup
from argus.backend.service.cost_rollup_service import CostRollupService

START = datetime(2026, 10, 21, tzinfo=UTC)
END = datetime(2026, 11, 20, tzinfo=UTC)


async def seed(plugin: str, start_time: datetime, release_id: UUID | None = None, actual_cost: float | None = 10.0,
               **overrides) -> RunCostRollup:
    fields = {
        "month": CostRollupService.month_of(start_time),
        "release_id": release_id or uuid.uuid4(),
        "start_time": start_time,
        "run_id": uuid.uuid4(),
        "plugin_name": plugin,
        "build_id": "job/run",
        "build_number": 1,
        "status": "passed",
        "actual_cost": actual_cost,
        "backend": "aws",
        "item_count": 1 if actual_cost is not None else 0,
        "coverage": "complete" if actual_cost is not None else "none",
    }
    fields.update(overrides)
    row = RunCostRollup(**fields)
    await row.save()
    return row


def create_view(client: TestClient, items: list[str]) -> str:
    body = client.post("/api/v1/views/create", json={"name": f"costs_{uuid.uuid4().hex[:8]}", "items": items,
                                                     "settings": "{}"}).json()
    assert body["status"] == "ok", body
    return body["response"]["id"]


async def seed_span(release_id: UUID, first_start: datetime, last_start: datetime) -> None:
    await RunCostReleaseSpan(release_id=release_id, first_start=first_start, last_start=last_start).save()
