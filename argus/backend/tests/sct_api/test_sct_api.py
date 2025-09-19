import json
from uuid import uuid4
import pytest

from argus.backend.plugins.sct.testrun import SCTTestRun

API_PREFIX = "/api/v1/client/sct"


@pytest.fixture
def sct_run_id(flask_client, fake_test):
    # Create an SCT run that other tests can use
    run_id = str(uuid4())
    payload = {
        "run_id": run_id,
        "job_name": fake_test.build_system_id,
        "job_url": "http://example.com/job/1",
        "started_by": "test_user",
        "commit_id": "deadbeef",
        "origin_url": "http://example.com/repo.git",
        "branch_name": "main",
        "sct_config": {"cluster_backend": "aws"},
        "schema_version": "v8",
    }
    resp = flask_client.post(
        "/api/v1/client/testrun/scylla-cluster-tests/submit",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.text
    assert resp.json["status"] == "ok"
    return run_id


def test_submit_packages(flask_client, sct_run_id):
    payload = {
        "packages": [
            {
                "name": "scylla-server",
                "version": "6.0.0",
                "commit_id": "deadbeef",
                "origin": "scylla",
            }
        ],
        "schema_version": "v8",
    }
    resp = flask_client.post(
        f"{API_PREFIX}/{sct_run_id}/packages/submit",
        data=json.dumps(payload),
        content_type="application/json",

    )
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"

    # Verify model updated
    run = SCTTestRun.get(id=sct_run_id)
    assert any(p.name == "scylla-server" and p.version == "6.0.0" for p in run.packages)


def test_submit_screenshots(flask_client, sct_run_id):
    payload = {
        "screenshot_links": ["https://grafana/snap/1", "https://grafana/snap/2"],
        "schema_version": "v8",
    }
    resp = flask_client.post(
        f"{API_PREFIX}/{sct_run_id}/screenshots/submit",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"

    # Verify screenshots stored
    run = SCTTestRun.get(id=sct_run_id)
    assert "https://grafana/snap/1" in run.screenshots
    assert "https://grafana/snap/2" in run.screenshots


def test_set_runner(flask_client, sct_run_id):
    payload = {
        "public_ip": "1.2.3.4",
        "private_ip": "10.0.0.1",
        "region": "us-east-1",
        "backend": "aws",
        "name": "runner-1",
        "schema_version": "v8",
    }
    resp = flask_client.post(
        f"{API_PREFIX}/{sct_run_id}/sct_runner/set",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"

    # Verify runner details persisted
    run = SCTTestRun.get(id=sct_run_id)
    assert run.sct_runner_host is not None
    assert run.sct_runner_host.provider == "aws"
    assert run.sct_runner_host.public_ip == "1.2.3.4"
    assert any(res.resource_type == "sct-runner" and res.name == "runner-1" for res in run.allocated_resources)


def _create_resource(flask_client, sct_run_id, resource_name="node-1"):
    payload = {
        "resource": {
            "name": resource_name,
            "state": "running",
            "resource_type": "db_node",
            "instance_details": {
                "instance_type": "i3.4xlarge",
                "provider": "aws",
                "region": "us-east-1",
                "dc_name": "us-east",
                "rack_name": "rack-1",
                "public_ip": "1.2.3.4",
                "private_ip": "10.0.0.1",
                "shards_amount": 8,
            },
        },
        "schema_version": "v8",
    }
    return flask_client.post(
        f"{API_PREFIX}/{sct_run_id}/resource/create",
        data=json.dumps(payload),
        content_type="application/json",
    )


def test_resource_create(flask_client, sct_run_id):
    resp = _create_resource(flask_client, sct_run_id)
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"

    # Verify resource persisted
    run = SCTTestRun.get(id=sct_run_id)
    res = next(r for r in run.allocated_resources if r.name == "node-1")
    assert res.resource_type == "db_node"
    assert res.instance_info.shards_amount == 8
    assert res.state == "running"


def test_resource_update_shards(flask_client, sct_run_id):
    # Ensure resource exists
    _create_resource(flask_client, sct_run_id, resource_name="node-2")
    payload = {
        "shards": 16,
        "schema_version": "v8"
    }
    resp = flask_client.post(
        f"{API_PREFIX}/{sct_run_id}/resource/node-2/shards",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"

    # Verify shards updated
    run = SCTTestRun.get(id=sct_run_id)
    res = next(r for r in run.allocated_resources if r.name == "node-2")
    assert res.instance_info.shards_amount == 16


def test_resource_update(flask_client, sct_run_id):
    # Ensure resource exists
    _create_resource(flask_client, sct_run_id, resource_name="node-3")
    payload = {"update_data": {"instance_info": {"shards_amount": 12}}, "schema_version": "v8"}
    resp = flask_client.post(
        f"{API_PREFIX}/{sct_run_id}/resource/node-3/update",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"

    # Verify update applied
    run = SCTTestRun.get(id=sct_run_id)
    res = next(r for r in run.allocated_resources if r.name == "node-3")
    assert res.instance_info.shards_amount == 12


def test_resource_terminate(flask_client, sct_run_id):
    # Ensure resource exists
    _create_resource(flask_client, sct_run_id, resource_name="node-4")
    payload = {"reason": "test-complete", "schema_version": "v8"}
    resp = flask_client.post(
        f"{API_PREFIX}/{sct_run_id}/resource/node-4/terminate",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"

    # Verify termination reflected in model
    run = SCTTestRun.get(id=sct_run_id)
    res = next(r for r in run.allocated_resources if r.name == "node-4")
    assert res.state == "terminated"
    assert res.instance_info.termination_reason == "test-complete"
    assert res.instance_info.termination_time and res.instance_info.termination_time > 0


def test_nemesis_submit_and_finalize(flask_client, sct_run_id):
    submit_payload = {
        "nemesis": {
            "name": "ChaosMonkey",
            "class_name": "NemesisChaosMonkey",
            "start_time": 123456,
            "node_name": "node-1",
            "node_ip": "10.0.0.1",
            "node_shards": 8,
        },
        "schema_version": "v8"
    }
    resp = flask_client.post(
        f"{API_PREFIX}/{sct_run_id}/nemesis/submit",
        data=json.dumps(submit_payload),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"

    # Verify nemesis created
    run = SCTTestRun.get(id=sct_run_id)
    nem = next(n for n in run.nemesis_data if n.name == "ChaosMonkey" and n.start_time == 123456)
    assert nem.status == "running"

    finalize_payload = {
        "nemesis": {
            "name": "ChaosMonkey",
            "start_time": 123456,
            "status": "succeeded",
            "message": "done",
        }
    }
    resp = flask_client.post(
        f"{API_PREFIX}/{sct_run_id}/nemesis/finalize",
        data=json.dumps(finalize_payload),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"

    # Verify nemesis finalized
    run = SCTTestRun.get(id=sct_run_id)
    nem = next(n for n in run.nemesis_data if n.name == "ChaosMonkey" and n.start_time == 123456)
    assert nem.status == "succeeded"
    assert nem.end_time and nem.end_time > 0
    assert nem.stack_trace == "done"


def test_submit_legacy_events(flask_client, sct_run_id):
    # Legacy endpoint: /sct/<run_id>/events/submit
    payload = {
        "events": [
            {
                "severity": "ERROR",
                "total_events": 2,
                "messages": [
                    "2025-09-19 09:30:00.000 Something bad happened",
                    "2025-09-19 09:31:00.000 Another bad thing"
                ],
            },
            {
                "severity": "CRITICAL",
                "total_events": 1,
                "messages": [
                    "2025-09-19 09:32:00.000 CoreDumpEvent node=node-1 corefile_url=https://example.com/core.zst"
                ],
            },
        ],
        "schema_version": "v8",
    }

    resp = flask_client.post(
        f"{API_PREFIX}/{sct_run_id}/events/submit",
        data=json.dumps(payload),
        content_type="application/json",
    )

    assert resp.status_code == 200
    assert resp.json["status"] == "ok"

    # Verify run was updated with events (legacy storage)
    run = SCTTestRun.get(id=sct_run_id)
    assert run.events is not None and len(run.events) >= 2
    by_sev = {e.severity: e for e in run.events}
    assert "ERROR" in by_sev and by_sev["ERROR"].event_amount == 2
    assert any("Something bad happened" in m for m in by_sev["ERROR"].last_events)
    assert "CRITICAL" in by_sev and by_sev["CRITICAL"].event_amount == 1
    assert any("CoreDumpEvent" in m for m in by_sev["CRITICAL"].last_events)



def test_submit_gemini_results(flask_client, sct_run_id):
    payload = {
        "gemini_data": {
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
        },
        "schema_version": "v8"
    }
    resp = flask_client.post(
        f"{API_PREFIX}/{sct_run_id}/gemini/submit",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"

    # Verify gemini fields persisted
    run = SCTTestRun.get(id=sct_run_id)
    assert run.subtest_name == "gemini"
    assert run.gemini_command == "gemini run"
    assert run.gemini_status == "PASSED"


def test_submit_and_get_junit_report(flask_client, sct_run_id):
    payload = {"file_name": "report.xml", "content": "PGp1bml0PjwvanVuaXQ+", "schema_version": "v8"}
    resp = flask_client.post(
        f"{API_PREFIX}/{sct_run_id}/junit/submit",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"

    resp = flask_client.get(f"{API_PREFIX}/{sct_run_id}/junit/get_all")
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"
    assert isinstance(resp.json["response"], list)
    assert any(item.get("file_name") == "report.xml" for item in resp.json["response"])
