from dataclasses import asdict
from datetime import UTC, datetime
from uuid import UUID

from argus.backend.models.argus_ai import SCTCriticalEventEmbedding, SCTErrorEventEmbedding
from argus.backend.models.web import ArgusTest
from argus.backend.plugins.sct.service import SCTService
from argus.backend.plugins.sct.testrun import SCTEventSeverity, SCTUnprocessedEvent
from argus.backend.service.client_service import ClientService
from argus.backend.tests.util import get_fake_test_run
from argus.common.sct_types import RawEventPayload
from argus.common.utils import clamp_ts_to_milliseconds


async def submitted_run(client_service: ClientService, fake_test: ArgusTest) -> UUID:
    run_type, run_req = get_fake_test_run(fake_test)
    await client_service.submit_run(run_type, asdict(run_req))
    return UUID(run_req.run_id)


def event_payload(run_id: UUID, severity: str, message: str, ts: float | None = None) -> RawEventPayload:
    return {
        "duration": None,
        "event_type": "DatabaseLogEvent",
        "known_issue": None,
        "message": message,
        "nemesis_name": None,
        "nemesis_status": None,
        "node": "node-1",
        "received_timestamp": None,
        "run_id": str(run_id),
        "severity": severity,
        "target_node": None,
        "ts": clamp_ts_to_milliseconds(ts if ts is not None else datetime.now(tz=UTC).timestamp()),
    }


async def stored_events(run_id: UUID, severity: SCTEventSeverity = SCTEventSeverity.ERROR) -> list[dict]:
    return await SCTService.get_events(run_id=run_id, limit=100, severities=[severity], before=None)


async def stored_embedding(run_id: UUID, severity: str, ts: datetime) -> list[float] | None:
    model = SCTErrorEventEmbedding if severity == SCTEventSeverity.ERROR.value else SCTCriticalEventEmbedding
    row = await model.find(run_id=run_id, ts=ts).first()
    return row.embedding if row else None


async def queued(run_id: UUID) -> list[tuple[str, datetime]]:
    return [(row.severity, row.ts) for row in await SCTUnprocessedEvent.find(run_id=run_id).all()]
