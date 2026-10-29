from dataclasses import asdict
from datetime import UTC, datetime
from uuid import UUID

from argus.backend.models.run_cost_rollup import RunCostRollup
from argus.backend.models.web import ArgusTest
from argus.backend.service.client_service import ClientService
from argus.backend.tests.conftest import get_fake_test_run


async def submitted_run(client_service: ClientService, fake_test: ArgusTest,
                        sct_config: dict | None = None) -> tuple[str, UUID]:
    run_type, run_req = get_fake_test_run(fake_test, sct_config=sct_config)
    await client_service.submit_run(run_type, asdict(run_req))
    return run_type, UUID(run_req.run_id)


async def rollup_rows(run_id: UUID, release_id: UUID, month: str | None = None) -> list[RunCostRollup]:
    month = month or datetime.now(UTC).strftime("%Y-%m")
    rows = await RunCostRollup.find(month=month, release_id=release_id).all()
    return [row for row in rows if row.run_id == run_id]
