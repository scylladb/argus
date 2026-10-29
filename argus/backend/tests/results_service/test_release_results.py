from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from argus.backend.error_handlers import DataValidationError
from argus.backend.plugins.sct.testrun import SCTTestRun

from argus.backend.tests.conftest import get_fake_test_run
from argus.common.enums import TestInvestigationStatus
from argus.client.generic_result import ColumnMetadata, ResultType, Status, StaticGenericResultTable

API_PREFIX = "/api/v1"


class ThroughputTable(StaticGenericResultTable):
    class Meta:
        name = "Release Throughput"
        description = "Throughput across a release"
        Columns = [ColumnMetadata(name="ops", unit="op/s", type=ResultType.FLOAT)]


class LatencyTable(StaticGenericResultTable):
    class Meta:
        name = "Release Latency"
        description = "Latency across a release"
        Columns = [ColumnMetadata(name="p99", unit="ms", type=ResultType.FLOAT)]


@pytest.fixture
async def release_run(client_service, fake_test, release, group):
    run_type, run = get_fake_test_run(test=fake_test)
    await client_service.submit_run(run_type, asdict(run))
    for table_cls, column, value, status in ((ThroughputTable, "ops", 100, Status.PASS),
                                             (LatencyTable, "p99", 5, Status.ERROR)):
        table = table_cls()
        table.sut_timestamp = 123
        table.add_result(column=column, row="write", value=value, status=status)
        try:
            await client_service.submit_results(run_type, UUID(run.run_id), table.as_dict())
        except DataValidationError:
            # an ERROR cell is stored, then reported to the submitter
            pass
    return UUID(run.run_id)


async def test_release_results_grouped_by_table_test_run(results_service, release, fake_test, release_run):
    results = await results_service.get_release_results(release=release.name, table_filter="throughput")

    [group] = [group for group in results if group["table"] == ThroughputTable.Meta.name]
    assert all("throughput" in group["table"].lower() for group in results)
    [test] = [test for test in group["tests"] if test["test_id"] == fake_test.id]
    assert test["build_id"] == fake_test.build_system_id
    [run] = test["runs"]
    assert run["run_id"] == release_run
    assert run["build_number"] == 42
    assert run["cells"] == [{"row": "write", "column": "ops", "value": 100, "status": "PASS"}]


async def test_release_results_filter_by_status_and_write_time(results_service, release, release_run):
    by_status = await results_service.get_release_results(
        release=str(release.id), table_filter="release", statuses=["ERROR"])
    tables = [group["table"] for group in by_status]
    assert LatencyTable.Meta.name in tables
    assert ThroughputTable.Meta.name not in tables

    future = datetime.now(timezone.utc) + timedelta(days=1)
    assert await results_service.get_release_results(release=release.name, table_filter="release", since=future) == []


async def test_release_results_select_runs_by_start_time(results_service, release, release_run):
    window = await results_service.get_release_results(
        release=release.name, table_filter="release", since=datetime.now(timezone.utc) - timedelta(hours=1))
    assert any(run["run_id"] == release_run
               for group in window for test in group["tests"] for run in test["runs"])

    before_start = datetime.now(timezone.utc) - timedelta(days=10)
    assert await results_service.get_release_results(
        release=release.name, table_filter="release", since=before_start - timedelta(days=1),
        until=before_start) == []


async def test_release_results_leave_out_ignored_runs(results_service, release, release_run):
    run_model = await SCTTestRun.get(id=release_run)
    run_model.investigation_status = TestInvestigationStatus.IGNORED.value
    await run_model.save()

    results = await results_service.get_release_results(release=release.name, table_filter="release")

    assert all(run["run_id"] != release_run
               for group in results for test in group["tests"] for run in test["runs"])


async def test_release_result_tables_lists_names(results_service, release, release_run):
    tables = await results_service.get_release_result_tables(release=release.name)

    by_name = {table["name"]: table for table in tables}
    assert by_name[LatencyTable.Meta.name]["columns"] == ["p99"]
    assert by_name[ThroughputTable.Meta.name]["columns"] == ["ops"]
    assert by_name[ThroughputTable.Meta.name]["tests"] >= 1


def test_release_results_endpoint(api_client, release, release_run):
    resp = api_client.get(f"{API_PREFIX}/results/release/{release.name}", params={"table": "latency"})

    assert resp.status_code == 200, resp.text
    tables = [group["table"] for group in resp.json()["response"]]
    assert LatencyTable.Meta.name in tables
    assert ThroughputTable.Meta.name not in tables


def test_release_results_endpoint_unknown_release(api_client):
    resp = api_client.get(f"{API_PREFIX}/results/release/no-such-release", params={"table": "x"})

    assert resp.json()["status"] == "error"
