"""Full SCT run lifecycle through the real ArgusSCTClient.

Mirrors the endpoint-level cycle in
``argus/backend/tests/client_api/test_client_api.py`` but drives it through
the shipped client over a real socket. Persisted state is cross-checked
through ``api_client`` (the in-process TestClient) -- both stacks hit the
same database.
"""

import pytest

from argus.client.generic_result import ColumnMetadata, GenericResultTable, ResultType, Status
from argus.client.sct.types import LogLink, Package
from argus.common.enums import TestStatus

pytestmark = pytest.mark.docker_required


def _run_info(api_client, run_id) -> dict:
    resp = api_client.get(f"/api/v1/client/testrun/{run_id}/info")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok", resp.json()
    return resp.json()["response"]


def test_sct_full_lifecycle(sct_client, fake_test, api_client):
    run_id = sct_client.run_id

    sct_client.submit_sct_run(
        job_name=fake_test.build_system_id,
        job_url="http://example.com/job/7/",
        started_by="e2e_sct_user",
        commit_id="cafef00d",
        origin_url="http://example.com/repo.git",
        branch_name="master",
        sct_config={"cluster_backend": "aws"},
    )

    run = sct_client.get_run()
    assert str(run["id"]) == str(run_id)

    sct_client.sct_heartbeat()

    sct_client.set_sct_run_status(TestStatus.RUNNING)
    assert sct_client.get_status() is TestStatus.RUNNING

    sct_client.update_scylla_version("6.1.0")

    sct_client.submit_sct_logs([
        LogLink(log_name="monitor.log", log_link="http://example.com/m.log"),
        LogLink(log_name="loader.log", log_link="http://example.com/l.log"),
    ])

    sct_client.submit_packages([
        # date must be %Y%m%d -- the backend derives sut_timestamp from it.
        Package(name="scylla-server", version="6.1.0", date="20260829",
                revision_id="deadbeef", build_id="e2e-build"),
    ])

    results = GenericResultTable(
        name="E2E Lifecycle Results",
        description="Results submitted by the client E2E suite",
        columns=[
            ColumnMetadata(name="latency", unit="ms", type=ResultType.FLOAT, higher_is_better=False),
        ],
    )
    results.add_result(column="latency", row="mean", value=1.5, status=Status.PASS)
    sct_client.submit_results(results)

    sct_client.finalize_sct_run()

    info = _run_info(api_client, run_id)
    test_run = info["test_run"]
    assert info["plugin_name"] == "scylla-cluster-tests"
    assert test_run["scylla_version"] == "6.1.0"
    assert test_run["status"] == TestStatus.RUNNING.value
    assert test_run["heartbeat"] is not None
    assert test_run["end_time"] is not None
    assert {entry[0] for entry in test_run["logs"]} == {"monitor.log", "loader.log"}
    assert [p["name"] for p in test_run["packages"]] == ["scylla-server"]
