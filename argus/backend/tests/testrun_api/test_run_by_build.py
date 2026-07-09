import json
from uuid import uuid4

import pytest
from flask.testing import FlaskClient

from argus.backend.models.web import ArgusTest

API_PREFIX = "/api/v1"


def _submit_run(flask_client: FlaskClient, fake_test: ArgusTest, *, run_id: str | None = None, build_number: int = 1) -> str:
    """Submit a single SCT run against `fake_test` and return its run_id."""
    run_id = run_id or str(uuid4())
    payload = {
        "run_id": run_id,
        "job_name": fake_test.build_system_id,
        "job_url": f"http://ci.example.com/job/{build_number}",
        "started_by": "test_user",
        "commit_id": "deadbeef",
        "origin_url": "http://example.com/repo.git",
        "branch_name": "main",
        "sct_config": {"cluster_backend": "aws"},
        "schema_version": "v8",
    }
    resp = flask_client.post(
        f"{API_PREFIX}/client/testrun/scylla-cluster-tests/submit",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.text
    assert resp.json["status"] == "ok"
    return run_id


@pytest.mark.docker_required
def test_get_run_by_build_resolves_run(flask_client: FlaskClient, fake_test: ArgusTest) -> None:
    """The build_id + build_number pair resolves to the submitted run."""
    run_id = _submit_run(flask_client, fake_test, build_number=77)

    resp = flask_client.get(f"{API_PREFIX}/test/{fake_test.build_system_id}/77")

    assert resp.status_code == 200, resp.text
    assert resp.json["status"] == "ok"
    body = resp.json["response"]
    assert body["run_id"] == run_id
    assert body["plugin_name"] == "scylla-cluster-tests"
    # The Argus URL points at the canonical run view for this plugin/run.
    assert body["url"].endswith(f"/tests/scylla-cluster-tests/{run_id}")


@pytest.mark.docker_required
def test_get_run_by_build_unknown_build_number_errors(flask_client: FlaskClient, fake_test: ArgusTest) -> None:
    """A build number with no matching run yields an error response."""
    _submit_run(flask_client, fake_test, build_number=1)

    resp = flask_client.get(f"{API_PREFIX}/test/{fake_test.build_system_id}/999999")

    assert resp.json["status"] != "ok"


@pytest.mark.docker_required
def test_get_run_by_build_unknown_build_id_errors(flask_client: FlaskClient) -> None:
    """An unknown build_id yields an error response rather than resolving."""
    resp = flask_client.get(f"{API_PREFIX}/test/does-not-exist-{uuid4()}/1")

    assert resp.json["status"] != "ok"
