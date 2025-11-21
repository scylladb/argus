from dataclasses import asdict
from datetime import datetime, UTC
import json
import logging
from time import sleep

from flask.testing import FlaskClient

from argus.backend.models.web import ArgusRelease, ArgusGroup, ArgusTest
from argus.backend.plugins.sct.testrun import SCTEventSeverity, SCTTestRun
from argus.backend.service.client_service import ClientService
from argus.backend.plugins.sct.service import SCTService
from argus.backend.service.testrun import TestRunService
from argus.backend.tests.conftest import get_fake_test_run
from argus.backend.util.encoders import ArgusJSONEncoder
from argus.common.sct_types import RawEventPayload

LOGGER = logging.getLogger(__name__)

def test_submit_event(client_service: ClientService, sct_service: SCTService, testrun_service: TestRunService, fake_test: ArgusTest):
    run_type, run_req = get_fake_test_run(fake_test)
    client_service.submit_run(run_type, asdict(run_req))
    run: SCTTestRun = testrun_service.get_run(run_type, run_req.run_id)

    event_data: RawEventPayload = {
        "duration": 30.0,
        "event_type": "end",
        "known_issue": None,
        "message": "Sample event - body contains\nmultiple lines.",
        "nemesis_name": None,
        "nemesis_status": None,
        "node": None,
        "received_timestamp": None,
        "run_id": run.id,
        "severity": SCTEventSeverity.CRITICAL.value,
        "target_node": None,
        "ts": datetime.now(tz=UTC).timestamp()
    }

    _ = sct_service.submit_event(str(run.id), event_data)

    all_events = run.get_all_events()
    assert len(all_events) == 1, "Event not found"


def test_get_events_by_severity(client_service: ClientService, sct_service: SCTService, testrun_service: TestRunService, fake_test: ArgusTest):
    run_type, run_req = get_fake_test_run(fake_test)
    client_service.submit_run(run_type, asdict(run_req))
    run: SCTTestRun = testrun_service.get_run(run_type, run_req.run_id)

    event_template: RawEventPayload = {
        "duration": 30.0,
        "event_type": "end",
        "known_issue": None,
        "message": "Sample event - body contains\nmultiple lines.",
        "nemesis_name": None,
        "nemesis_status": None,
        "node": None,
        "received_timestamp": None,
        "run_id": run.id,
        "severity": None,
        "target_node": None,
        "ts": None
    }

    events = []
    for i in range(3):
        raw_event = dict(event_template)
        raw_event["ts"] = datetime.now(tz=UTC).timestamp() - i
        raw_event["severity"] = SCTEventSeverity.CRITICAL.value
        events.append(raw_event)

    for i in range(10):
        raw_event = dict(event_template)
        raw_event["ts"] = datetime.now(tz=UTC).timestamp() - i
        raw_event["severity"] = SCTEventSeverity.NORMAL.value
        events.append(raw_event)

    for event in events:
        _ = sct_service.submit_event(str(run.id), event)

    all_events = run.get_all_events()
    assert len(all_events) == 13, "Event not found"

    events_by_severity = run.get_events_by_severity(SCTEventSeverity.CRITICAL)
    assert len(events_by_severity) == 3, "Not all events were added or count mismatch"


def test_submit_event_sparse_fields(client_service: ClientService, sct_service: SCTService, testrun_service: TestRunService, fake_test: ArgusTest):
    run_type, run_req = get_fake_test_run(fake_test)
    client_service.submit_run(run_type, asdict(run_req))
    run: SCTTestRun = testrun_service.get_run(run_type, run_req.run_id)

    event_data: RawEventPayload = {
        "message": "Sample event - body contains\nmultiple lines.",
        "run_id": run.id,
        "severity": SCTEventSeverity.CRITICAL.value,
        "ts": datetime.now(tz=UTC).timestamp(),
        "event_type": "DatabaseEvent"
    }

    _ = sct_service.submit_event(str(run.id), event_data)

    all_events = run.get_all_events()
    assert len(all_events) == 1, "Event not found"


def test_submit_event_ordering(client_service: ClientService, sct_service: SCTService, testrun_service: TestRunService, fake_test: ArgusTest):
    run_type, run_req = get_fake_test_run(fake_test)
    client_service.submit_run(run_type, asdict(run_req))
    run: SCTTestRun = testrun_service.get_run(run_type, run_req.run_id)

    event_template: RawEventPayload = {
        "message": None,
        "run_id": run.id,
        "severity": SCTEventSeverity.CRITICAL.value,
        "ts": None,
        "event_type": "DatabaseEvent"
    }

    base_ts = datetime.now(tz=UTC).timestamp()
    for i in range(100):
        event_data = dict(event_template)
        event_data["ts"] = base_ts + i * 0.001  # Each event 1ms apart
        event_data["message"] = f"This is event {i}"
        _ = sct_service.submit_event(str(run.id), event_data)


    all_events = run.get_all_events()
    assert len(all_events) > 0 and all_events[0]["message"] == "This is event 0", "Incorrect event in set! Expected oldest event first with ASC ordering."

    # Insert more events with later timestamps
    later_ts = base_ts + 1.0  # 1 second later
    for i in range(100):
        event_data = dict(event_template)
        event_data["ts"] = later_ts + i * 0.001
        event_data["message"] = f"This is event r{i}"
        _ = sct_service.submit_event(str(run.id), event_data)

    all_events = run.get_all_events()
    assert len(all_events) > 0 and all_events[0]["message"] == "This is event 0", "Incorrect event in set! Expected oldest event first with ASC ordering."


def test_fetch_partition_limit(client_service: ClientService, sct_service: SCTService, testrun_service: TestRunService, fake_test: ArgusTest):
    run_type, run_req = get_fake_test_run(fake_test)
    client_service.submit_run(run_type, asdict(run_req))
    run: SCTTestRun = testrun_service.get_run(run_type, run_req.run_id)

    event_template: RawEventPayload = {
        "message": None,
        "run_id": run.id,
        "severity": SCTEventSeverity.CRITICAL.value,
        "ts": None,
        "event_type": "DatabaseEvent"
    }

    for i in range(11):
        event_data = dict(event_template)
        event_data["ts"] = datetime.now(tz=UTC).timestamp() + i * 0.001
        event_data["message"] = f"This is event {i}"
        _ = sct_service.submit_event(str(run.id), event_data)

    for i in range(11):
        event_data = dict(event_template)
        event_data["severity"] = SCTEventSeverity.NORMAL.value
        event_data["ts"] = datetime.now(tz=UTC).timestamp() + i * 0.001
        event_data["message"] = f"This is event {i}"
        _ = sct_service.submit_event(str(run.id), event_data)

    all_events = run.get_events_limited(run.id, per_partition_limit=10)
    assert len(all_events) == 20, "Incorrect event in set!"


def test_fetch_custom_limit(client_service: ClientService, sct_service: SCTService, testrun_service: TestRunService, fake_test: ArgusTest):
    run_type, run_req = get_fake_test_run(fake_test)
    client_service.submit_run(run_type, asdict(run_req))
    run: SCTTestRun = testrun_service.get_run(run_type, run_req.run_id)

    event_template: RawEventPayload = {
        "message": None,
        "run_id": run.id,
        "severity": SCTEventSeverity.CRITICAL.value,
        "ts": None,
        "event_type": "DatabaseEvent"
    }

    for i in range(50):
        event_data = dict(event_template)
        event_data["ts"] = datetime.now(tz=UTC).timestamp() - 1
        event_data["message"] = f"This is event {i}"
        _ = sct_service.submit_event(str(run.id), event_data)

    for i in range(50):
        event_data = dict(event_template)
        event_data["severity"] = SCTEventSeverity.NORMAL.value
        event_data["ts"] = datetime.now(tz=UTC).timestamp() - 1
        event_data["message"] = f"This is event {i}"
        _ = sct_service.submit_event(str(run.id), event_data)

    all_events = run.get_events_limited(run.id, per_partition_limit=10, severities=[SCTEventSeverity.CRITICAL])
    assert len(all_events) == 10, "Incorrect events in set!"


def test_submit_event_with_nemesis_data(client_service: ClientService, sct_service: SCTService, testrun_service: TestRunService, fake_test: ArgusTest):
    run_type, run_req = get_fake_test_run(fake_test)
    client_service.submit_run(run_type, asdict(run_req))
    run: SCTTestRun = testrun_service.get_run(run_type, run_req.run_id)

    event_data: RawEventPayload = {
        "duration": 30.0,
        "event_type": "NemesisEvent",
        "known_issue": "http://example.com/yes/1",
        "message": "Sample event - body contains\nmultiple lines.",
        "nemesis_name": "NemesisName",
        "nemesis_status": "passed",
        "run_id": run.id,
        "severity": SCTEventSeverity.CRITICAL.value,
        "target_node": "127.0.0.1",
        "ts": datetime.now(tz=UTC).timestamp()
    }

    _ = sct_service.submit_event(str(run.id), event_data)

    all_events = run.get_all_events()
    assert len(all_events) == 1, "Event not found"


def test_submit_event_db_event(client_service: ClientService, sct_service: SCTService, testrun_service: TestRunService, fake_test: ArgusTest):
    run_type, run_req = get_fake_test_run(fake_test)
    client_service.submit_run(run_type, asdict(run_req))
    run: SCTTestRun = testrun_service.get_run(run_type, run_req.run_id)

    event_data: RawEventPayload = {
        "duration": 30.0,
        "event_type": "DatabaseEvent",
        "message": "Sample event - body contains\nmultiple lines.",
        "node": "127.0.0.1",
        "received_timestamp": "2025-05-01T19:30:21.666Z",
        "run_id": run.id,
        "severity": SCTEventSeverity.CRITICAL.value,
        "ts": datetime.now(tz=UTC).timestamp()
    }

    _ = sct_service.submit_event(str(run.id), event_data)

    all_events = run.get_all_events()
    assert len(all_events) == 1, "Event not found"


def test_controller_submit_event(flask_client: FlaskClient, fake_test: ArgusTest, client_service: ClientService, testrun_service: TestRunService):
    run_type, run_req = get_fake_test_run(fake_test)
    client_service.submit_run(run_type, asdict(run_req))
    run: SCTTestRun = testrun_service.get_run(run_type, run_req.run_id)

    body: RawEventPayload = {
        "duration": 30.0,
        "event_type": "DatabaseEvent",
        "message": "Sample event - body contains\nmultiple lines.",
        "node": "127.0.0.1",
        "received_timestamp": "2025-05-01T19:30:21.666Z",
        "run_id": run.id,
        "severity": SCTEventSeverity.CRITICAL.value,
        "ts": datetime.now(tz=UTC).timestamp()
    }

    response = flask_client.post(
        f"/api/v1/client/sct/{run.id}/event/submit",
        data=json.dumps({
            "data": body,
            "schema_version": "v8",
        }, cls=ArgusJSONEncoder),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.content_type == "application/json"
    assert response.json["status"] == "ok"
    assert response.json["response"]



def test_controller_submit_multiple_events(flask_client: FlaskClient, fake_test: ArgusTest, client_service: ClientService, testrun_service: TestRunService):
    run_type, run_req = get_fake_test_run(fake_test)
    client_service.submit_run(run_type, asdict(run_req))
    run: SCTTestRun = testrun_service.get_run(run_type, run_req.run_id)

    body: RawEventPayload = {
        "duration": 30.0,
        "event_type": "DatabaseEvent",
        "message": "Sample event - body contains\nmultiple lines.",
        "node": "127.0.0.1",
        "received_timestamp": "2025-05-01T19:30:21.666Z",
        "run_id": run.id,
        "severity": SCTEventSeverity.CRITICAL.value,
        "ts": datetime.now(tz=UTC).timestamp()
    }

    events = []
    for i in range(10):
        event = dict(body)
        event["ts"] += i
        events.append(event)

    response = flask_client.post(
        f"/api/v1/client/sct/{run.id}/event/submit",
        data=json.dumps({
            "data": events,
            "schema_version": "v8",
        }, cls=ArgusJSONEncoder),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.content_type == "application/json"
    assert response.json["status"] == "ok"
    assert response.json["response"]



def test_controller_submit_events_and_get_by_severity(flask_client: FlaskClient, fake_test: ArgusTest, client_service: ClientService, testrun_service: TestRunService):
    run_type, run_req = get_fake_test_run(fake_test)
    client_service.submit_run(run_type, asdict(run_req))
    run: SCTTestRun = testrun_service.get_run(run_type, run_req.run_id)

    body: RawEventPayload = {
        "duration": 30.0,
        "event_type": "DatabaseEvent",
        "message": "Sample event - body contains\nmultiple lines.",
        "node": "127.0.0.1",
        "received_timestamp": "2025-05-01T19:30:21.666Z",
        "run_id": run.id,
        "severity": SCTEventSeverity.CRITICAL.value,
        "ts": datetime.now(tz=UTC).timestamp()
    }

    events = []
    for i in range(100):
        event = dict(body)
        event["ts"] += i
        events.append(event)


    events = []
    for i in range(1000):
        event = dict(body)
        event["ts"] += i
        event["severity"] = SCTEventSeverity.NORMAL.value
        events.append(event)


    response = flask_client.post(
        f"/api/v1/client/sct/{run.id}/event/submit",
        data=json.dumps({
            "data": events,
            "schema_version": "v8",
        }, cls=ArgusJSONEncoder),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.content_type == "application/json"
    assert response.json["status"] == "ok"
    assert response.json["response"]


    response = flask_client.get(
        f"/api/v1/client/sct/{run.id}/events/{SCTEventSeverity.NORMAL.value}/get?limit=50",
    )

    assert response.status_code == 200
    assert response.content_type == "application/json"
    assert response.json["status"] == "ok"
    assert len(response.json["response"]) == 50


    only_normal = [e for e in events if e["severity"] == "NORMAL"]
    ev = only_normal[25]
    response = flask_client.get(
        f"/api/v1/client/sct/{run.id}/events/{SCTEventSeverity.NORMAL.value}/get?limit=50&before={int(ev["ts"])}",
    )

    assert response.status_code == 200
    assert response.content_type == "application/json"
    assert response.json["status"] == "ok"
    assert len(response.json["response"]) == 25
