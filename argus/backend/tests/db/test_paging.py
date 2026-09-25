from dataclasses import asdict
from datetime import UTC, datetime

import pytest
from starlette.testclient import TestClient

from argus.backend.models.web import ArgusTest
from argus.backend.plugins.sct.testrun import SCTEventSeverity, SCTTestRun
from argus.backend.service.client_service import ClientService
from argus.backend.service.testrun import TestRunService
from argus.backend.tests.conftest import get_fake_test_run

EVENT_COUNT = 5001


@pytest.mark.docker_required
async def test_reads_every_page_of_a_large_partition(api_client: TestClient, client_service: ClientService,
                                                     testrun_service: TestRunService, fake_test: ArgusTest):
    run_type, run_req = get_fake_test_run(fake_test)
    await client_service.submit_run(run_type, asdict(run_req))

    base_ts = datetime.now(tz=UTC).timestamp()
    events = [
        {
            "run_id": run_req.run_id,
            "severity": SCTEventSeverity.NORMAL.value,
            "ts": base_ts + index,
            "message": f"paging event {index}",
            "event_type": "InfoEvent",
        }
        for index in range(EVENT_COUNT)
    ]
    response = api_client.post(f"/api/v1/client/sct/{run_req.run_id}/event/submit", json={"data": events})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ok"

    run: SCTTestRun = await testrun_service.get_run(run_type, run_req.run_id)
    stored = await run.get_events_by_severity(SCTEventSeverity.NORMAL)

    assert len(stored) == EVENT_COUNT
