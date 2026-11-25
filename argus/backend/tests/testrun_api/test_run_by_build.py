import json
from uuid import uuid4

import pytest
from starlette.testclient import TestClient

from argus.backend.models.web import ArgusTest
from argus.backend.tests.util import script_value

API_PREFIX = "/api/v1"


def _submit_run(api_client, fake_test: ArgusTest, *, run_id: str | None = None, build_number: int = 1) -> str:
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
    resp = api_client.post(
        f"{API_PREFIX}/client/testrun/scylla-cluster-tests/submit",
        json=payload,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"
    return run_id


@pytest.mark.docker_required
def test_get_run_by_build_resolves_run(api_client, fake_test: ArgusTest) -> None:
    """The build_id + build_number pair resolves to the submitted run."""
    run_id = _submit_run(api_client, fake_test, build_number=77)

    resp = api_client.get(f"{API_PREFIX}/test/{fake_test.build_system_id}/77")

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"
    body = resp.json()["response"]
    assert body["runs"] == [{"run_id": run_id, "plugin_name": "scylla-cluster-tests"}]
    assert body["url"].endswith(f"/test/{fake_test.build_system_id}/77")


@pytest.mark.docker_required
def test_get_run_by_build_returns_parallel_runs(api_client, fake_test: ArgusTest) -> None:
    first = _submit_run(api_client, fake_test, build_number=78)
    second = _submit_run(api_client, fake_test, build_number=78)

    resp = api_client.get(f"{API_PREFIX}/test/{fake_test.build_system_id}/78")
    page = api_client.get(f"/test/{fake_test.build_system_id}/78", follow_redirects=False)

    assert {run["run_id"] for run in resp.json()["response"]["runs"]} == {first, second}
    assert page.status_code == 200, page.text
    assert set(script_value(page.text, "gRun")) == {first, second}


@pytest.mark.docker_required
def test_get_run_by_build_unknown_build_number_errors(api_client, fake_test: ArgusTest) -> None:
    """A build number with no matching run yields an error response."""
    _submit_run(api_client, fake_test, build_number=1)

    resp = api_client.get(f"{API_PREFIX}/test/{fake_test.build_system_id}/999999")

    assert resp.json()["status"] != "ok"


@pytest.mark.docker_required
def test_get_run_by_build_unknown_build_id_errors(api_client) -> None:
    """An unknown build_id yields an error response rather than resolving."""
    resp = api_client.get(f"{API_PREFIX}/test/does-not-exist-{uuid4()}/1")

    assert resp.json()["status"] != "ok"
