"""E2E coverage for the remaining ArgusSCTClient methods.

Complements test_sct_lifecycle.py (which drives the core run cycle) with the
SCT plugin endpoints: runner/resources, nemeses, events, stress commands,
screenshots, junit reports, run configs, and email reports.

Verification goes through the client's own getters where one exists
(get_resources, get_resource, get_nemeses) and through the backend API
otherwise. submit_performance_results is deliberately not covered: the
performance tracking on SCTTestRun is deprecated and excluded from the
backend suite as well (see argus/backend/tests/sct_api/test_sct_api.py).

Tunnel behavior is out of scope (unit-tested in argus/client/tests).
"""

import time
from datetime import UTC, datetime

import pytest

from argus.backend.service.email_service import EmailService
from argus.backend.tests.email_service.utils import EmailListener
from argus.client.sct.types import EventsInfo
from argus.common.utils import clamp_ts_to_milliseconds

pytestmark = pytest.mark.docker_required


@pytest.fixture
def submitted_sct_client(sct_client, fake_test):
    """An ArgusSCTClient whose run already exists on the backend."""
    sct_client.submit_sct_run(
        job_name=fake_test.build_system_id,
        job_url="http://example.com/job/11/",
        started_by="e2e_sct_user",
        commit_id="cafef00d",
        origin_url="http://example.com/repo.git",
        branch_name="master",
        sct_config={"cluster_backend": "aws"},
    )
    return sct_client


def _run_dump(api_client, run_id) -> dict:
    resp = api_client.get(f"/api/v1/run/scylla-cluster-tests/{run_id}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok", resp.json()
    return resp.json()["response"]


def test_runner_and_resource_cycle(submitted_sct_client):
    client = submitted_sct_client

    client.set_sct_runner(public_ip="1.2.3.4", private_ip="10.0.0.1",
                          region="us-east-1", backend="aws", name="runner-1")

    client.create_resource(
        name="node-1",
        resource_type="db_node",
        public_ip="1.2.3.5",
        private_ip="10.0.0.2",
        instance_type="i3.4xlarge",
        region="us-east-1",
        provider="aws",
        dc_name="us-east",
        rack_name="rack-1",
        shards_amount=8,
    )

    resources = client.get_resources()
    names = {r["name"] for r in resources}
    # set_sct_runner also registers the runner host as an sct-runner resource.
    assert {"node-1", "runner-1"} <= names

    node = client.get_resource("node-1")
    assert node["state"] == "running"
    assert node["instance_info"]["shards_amount"] == 8

    client.update_shards_for_resource(name="node-1", new_shards=16)
    assert client.get_resource("node-1")["instance_info"]["shards_amount"] == 16

    client.update_resource(name="node-1", update_data={"instance_info": {"rack_name": "rack-2"}})
    assert client.get_resource("node-1")["instance_info"]["rack_name"] == "rack-2"

    client.terminate_resource(name="node-1", reason="test-complete")
    node = client.get_resource("node-1")
    assert node["state"] == "terminated"
    assert node["instance_info"]["termination_reason"] == "test-complete"
    # An old client sends no cost - the resource terminates without one, never as a zero.
    assert node["instance_info"]["cost"] is None


def test_resource_cost_cycle(submitted_sct_client, api_client):
    """SCT reports the hourly rate at creation and the final cost at termination."""
    client = submitted_sct_client

    client.create_resource(
        name="node-priced",
        resource_type="db_node",
        public_ip="1.2.3.6",
        private_ip="10.0.0.3",
        instance_type="i3.4xlarge",
        region="us-east-1",
        provider="aws",
        dc_name="us-east",
        rack_name="rack-1",
        shards_amount=8,
        price_per_hour=1.25,
        is_spot=True,
    )

    node = client.get_resource("node-priced")
    assert node["instance_info"]["price_per_hour"] == pytest.approx(1.25)
    assert node["instance_info"]["is_spot"] is True
    assert node["instance_info"]["cost"] is None

    client.terminate_resource(name="node-priced", reason="test-complete", cost=2.5)
    node = client.get_resource("node-priced")
    assert node["instance_info"]["cost"] == pytest.approx(2.5)

    client.submit_cost_estimate(estimated_cost=42.0)
    run = _run_dump(api_client, client.run_id)
    assert run["estimated_cost"] == pytest.approx(42.0)
    priced = next(r for r in run["allocated_resources"] if r["name"] == "node-priced")
    assert priced["instance_info"]["cost"] == pytest.approx(2.5)


def test_nemesis_cycle(submitted_sct_client):
    client = submitted_sct_client
    start_time = int(time.time())

    client.submit_nemesis(name="ChaosMonkey", class_name="NemesisChaosMonkey",
                          start_time=start_time, target_name="node-1",
                          target_ip="10.0.0.1", target_shards=8,
                          description="Killing nodes randomly")

    nemeses = client.get_nemeses()
    nem = next(n for n in nemeses if n["name"] == "ChaosMonkey")
    assert nem["status"] == "running"

    client.finalize_nemesis(name="ChaosMonkey", start_time=start_time,
                            status="succeeded", message="done")

    nemeses = client.get_nemeses()
    nem = next(n for n in nemeses if n["name"] == "ChaosMonkey")
    assert nem["status"] == "succeeded"
    assert nem["stack_trace"] == "done"
    assert nem["end_time"] > 0


def test_event_submission(submitted_sct_client, api_client):
    client = submitted_sct_client
    run_id = str(client.run_id)
    base_ts = clamp_ts_to_milliseconds(datetime.now(tz=UTC).timestamp())

    client.submit_event({
        "run_id": run_id,
        "severity": "ERROR",
        "ts": base_ts,
        "message": "Something went wrong on node-1",
        "event_type": "DatabaseLogEvent",
        "node": "node-1",
    })
    client.submit_event([
        {
            "run_id": run_id,
            "severity": "WARNING",
            "ts": base_ts + 1,
            "message": "Disk usage above 80%",
            "event_type": "DiskUsageEvent",
            "node": "node-2",
        },
        {
            "run_id": run_id,
            "severity": "CRITICAL",
            "ts": base_ts + 2,
            "message": "Process crashed unexpectedly",
            "event_type": "DatabaseLogEvent",
            "node": "node-3",
        },
    ])

    resp = api_client.get(f"/api/v1/client/sct/{run_id}/events/get")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"
    events = resp.json()["response"]
    assert sorted(e["severity"] for e in events) == ["CRITICAL", "ERROR", "WARNING"]

    # Legacy end-of-run aggregate: the backend endpoint is dummied out
    # (kept only for old-client compatibility), so only the call contract
    # is verified.
    client.submit_events([
        EventsInfo(severity="ERROR", total_events=2, messages=["err-A", "err-B"]),
    ])


def test_stress_command(submitted_sct_client, api_client):
    client = submitted_sct_client
    ts = clamp_ts_to_milliseconds(datetime.now(tz=UTC).timestamp())

    client.add_stress_command(command="cassandra-stress write duration=10m",
                              ts=ts, log_name="loader-1.log", loader_name="loader-1")

    resp = api_client.get(f"/api/v1/client/sct/{client.run_id}/stress_cmd/get")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"
    commands = resp.json()["response"]
    assert len(commands) == 1
    assert commands[0]["cmd"] == "cassandra-stress write duration=10m"
    assert commands[0]["node_name"] == "loader-1"


def test_screenshots(submitted_sct_client, api_client):
    client = submitted_sct_client
    links = [
        "https://example.com/screenshots/overview.png",
        "https://example.com/screenshots/per-server-metrics.png",
    ]
    client.submit_screenshots(links)

    run = _run_dump(api_client, client.run_id)
    assert run["screenshots"] == links


def test_junit_report_and_config(submitted_sct_client, api_client):
    client = submitted_sct_client

    client.sct_submit_junit_report(file_name="report.xml", raw_content="<junit></junit>")
    run = _run_dump(api_client, client.run_id)
    assert any(r["file_name"] == "report.xml" for r in run["junit_reports"])

    client.sct_submit_config(name="sct-config", content="cluster_backend: aws\nn_db_nodes: 3\n")
    resp = api_client.get(f"/api/v1/client/{client.run_id}/config/all")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"
    configs = resp.json()["response"]
    config = next(c for c in configs if c["name"] == "sct-config")
    assert config["content"] == "cluster_backend: aws\nn_db_nodes: 3\n"


def test_gemini_results(submitted_sct_client, api_client):
    client = submitted_sct_client
    client.submit_gemini_results({
        "oracle_nodes_count": 1,
        "oracle_node_ami_id": "ami-123",
        "oracle_node_instance_type": "i3.large",
        "oracle_node_scylla_version": "6.0.0",
        "gemini_command": "gemini run",
        "gemini_version": "1.0.0",
        "gemini_status": "PASSED",
        "gemini_seed": "42",
        "gemini_write_ops": 100,
        "gemini_write_errors": 0,
        "gemini_read_ops": 50,
        "gemini_read_errors": 0,
    })

    run = _run_dump(api_client, client.run_id)
    assert run["subtest_name"] == "gemini"
    assert run["gemini_command"] == "gemini run"
    assert run["gemini_status"] == "PASSED"


def test_send_email(submitted_sct_client):
    client = submitted_sct_client
    listener = EmailListener()
    EmailService.set_sender(listener)
    try:
        client.send_email(recipients=["nobody@example.com"])
    finally:
        EmailService.set_sender(None)

    assert listener.recipients == ["nobody@example.com"]
    assert listener.content and "<" in listener.content
