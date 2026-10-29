from datetime import UTC, datetime
from uuid import UUID

import pytest

from argus.backend.plugins.sct.service import SCTService
from argus.backend.plugins.sct.testrun import SCTEventSeverity
from argus.backend.service.client_service import ClientService
from argus.backend.service.run_cost_service import RunCostService
from argus.backend.tests.cost_rollup.helpers import rollup_rows, submitted_run
from argus.common.sct_types import RawEventPayload


def _event(run_id: UUID, event_type: str) -> RawEventPayload:
    return {
        "duration": None,
        "event_type": event_type,
        "known_issue": None,
        "message": f"{event_type} on node-1",
        "nemesis_name": None,
        "nemesis_status": None,
        "node": "node-1",
        "received_timestamp": None,
        "run_id": str(run_id),
        "severity": SCTEventSeverity.CRITICAL.value,
        "target_node": None,
        "ts": datetime.now(tz=UTC).timestamp(),
    }


@pytest.fixture(scope="session")
def run_cost_service(argus_db) -> RunCostService:
    return RunCostService()


async def test_spot_termination_event_marks_the_rollup(client_service: ClientService, sct_service: SCTService,
                                                       fake_test):
    _, run_id = await submitted_run(client_service, fake_test)

    await sct_service.submit_event(run_id, _event(run_id, "SpotTerminationEvent"))

    (row,) = await rollup_rows(run_id, fake_test.release_id)
    assert row.spot_terminated is True


async def test_a_stored_spot_termination_event_marks_a_later_refresh(client_service: ClientService,
                                                                     sct_service: SCTService,
                                                                     run_cost_service: RunCostService, fake_test):
    _, run_id = await submitted_run(client_service, fake_test)
    await sct_service.submit_event(run_id, _event(run_id, "SpotTerminationEvent"))
    await sct_service.submit_event(run_id, _event(run_id, "CassandraStressLogEvent"))

    row = await run_cost_service.refresh_rollup(run_id)

    assert row.spot_terminated is True


async def test_other_critical_events_do_not_mark_the_run(client_service: ClientService, sct_service: SCTService,
                                                         run_cost_service: RunCostService, fake_test):
    _, run_id = await submitted_run(client_service, fake_test)

    await sct_service.submit_event(run_id, _event(run_id, "DatabaseLogEvent"))

    assert await rollup_rows(run_id, fake_test.release_id) == []
    assert (await run_cost_service.refresh_rollup(run_id)).spot_terminated is False
