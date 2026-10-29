from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import time
from uuid import UUID, uuid4

import pytest
from coodie.aio import execute_raw

from argus.backend.error_handlers import DataValidationError
from argus.backend.models.result import ArgusGenericResultData, ArgusGenericResultMetadata, ColumnMetadata as ColumnMeta
from argus.backend.plugins.generic.model import GenericRun
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


async def _generic_run_with_result(release_manager_service, release, group, table_name: str,
                                   started: datetime, written: datetime | None = None, test=None,
                                   **run_fields) -> tuple:
    """A generic plugin run that started at ``started`` and wrote one cell at ``written``.

    The table has a visible ``ops`` column and a hidden ``debug`` column, and the run writes both.
    """
    written = written or started
    if test is None:
        name = f"generic_{time.time_ns()}"
        test = await release_manager_service.create_test(name, name, name, name, group_id=group.id,
                                                         release_id=release.id, plugin_name="generic")
        await ArgusGenericResultMetadata(test_id=test.id, name=table_name,
                                         columns_meta=[ColumnMeta(name="ops", unit="op/s", type="FLOAT"),
                                                       ColumnMeta(name="debug", unit="", type="FLOAT",
                                                                  visible=False)],
                                         rows_meta=["write"]).save()
    run_fields.setdefault("heartbeat", int(started.timestamp()))
    run = GenericRun(id=uuid4(), build_id=test.build_system_id, test_id=test.id, release_id=release.id,
                     group_id=group.id, build_job_url="http://example.com/job/generic/3/", build_number=3,
                     started_by="tester", start_time=started, **run_fields)
    await run.save()
    for column, value in (("ops", 7.0), ("debug", 1.0)):
        await execute_raw(
            f"INSERT INTO {ArgusGenericResultData._get_keyspace()}.{ArgusGenericResultData.table_name()} "
            "(test_id, name, run_id, column, row, sut_timestamp, value, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            f"USING TIMESTAMP {int(written.timestamp() * 1_000_000)}",
            [test.id, table_name, run.id, column, "write", started, value, "PASS"])
    return test, run


def _run_ids(results) -> list:
    return [run["run_id"] for group in results for test in group["tests"] for run in test["runs"]]


async def test_release_results_until_alone_reads_the_window_before_it(results_service, release_manager_service,
                                                                     release, group):
    started = datetime.now(timezone.utc) - timedelta(days=60)
    _, run = await _generic_run_with_result(release_manager_service, release, group, "Old Release Table", started)

    results = await results_service.get_release_results(release=release.name, table_filter="old release",
                                                        until=started + timedelta(days=1))

    assert _run_ids(results) == [run.id]


async def test_release_results_read_generic_plugin_runs(results_service, release_manager_service, release, group):
    test, run = await _generic_run_with_result(release_manager_service, release, group, "Generic Release Table",
                                               datetime.now(timezone.utc))

    results = await results_service.get_release_results(release=release.name, table_filter="generic release")

    [group_result] = results
    [test_result] = group_result["tests"]
    assert test_result["test_id"] == test.id
    assert [(r["run_id"], r["build_number"]) for r in test_result["runs"]] == [(run.id, 3)]


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


async def test_release_results_keep_a_long_run_that_writes_in_the_window(results_service, release_manager_service,
                                                                        release, group):
    now = datetime.now(timezone.utc)
    _, run = await _generic_run_with_result(release_manager_service, release, group, "Long Release Table",
                                            started=now - timedelta(days=40), written=now,
                                            end_time=now, heartbeat=int(now.timestamp()))

    results = await results_service.get_release_results(release=release.name, table_filter="long release",
                                                        since=now - timedelta(days=1))

    assert _run_ids(results) == [run.id]


async def test_release_results_cap_the_runs_per_test(results_service, release_manager_service, release, group,
                                                     monkeypatch):
    monkeypatch.setattr("argus.backend.service.results_service.MAX_RUNS_PER_TEST", 1)
    now = datetime.now(timezone.utc)
    test, _ = await _generic_run_with_result(release_manager_service, release, group, "Capped Release Table",
                                             started=now - timedelta(hours=2))
    _, newest = await _generic_run_with_result(release_manager_service, release, group, "Capped Release Table",
                                               started=now - timedelta(hours=1), test=test)

    [group_result] = await results_service.get_release_results(release=release.name, table_filter="capped release")

    [test_result] = group_result["tests"]
    assert test_result["runs_truncated"] is True
    assert [run["run_id"] for run in test_result["runs"]] == [newest.id]


async def test_release_results_hide_hidden_columns(results_service, release_manager_service, release, group):
    await _generic_run_with_result(release_manager_service, release, group, "Hidden Release Table",
                                   datetime.now(timezone.utc))

    def columns(results):
        return {cell["column"] for group in results for test in group["tests"]
                for run in test["runs"] for cell in run["cells"]}

    assert columns(await results_service.get_release_results(
        release=release.name, table_filter="hidden release")) == {"ops"}
    assert columns(await results_service.get_release_results(
        release=release.name, table_filter="hidden release", include_hidden=True)) == {"ops", "debug"}

    tables = {t["name"]: t["columns"] for t in await results_service.get_release_result_tables(release.name)}
    assert tables["Hidden Release Table"] == ["ops"]
    tables = {t["name"]: t["columns"]
              for t in await results_service.get_release_result_tables(release.name, include_hidden=True)}
    assert tables["Hidden Release Table"] == ["ops", "debug"]


async def test_release_results_reject_an_unknown_release_id(results_service):
    with pytest.raises(DataValidationError):
        await results_service.get_release_results(release=str(uuid4()), table_filter="release")


async def test_release_results_reject_an_empty_table_filter(results_service, release):
    with pytest.raises(DataValidationError):
        await results_service.get_release_results(release=release.name, table_filter="  ")


def test_release_results_endpoint_accepts_lowercase_status(api_client, release, release_run):
    resp = api_client.get(f"{API_PREFIX}/results/release/{release.name}",
                          params={"table": "release", "status[]": "error"})

    tables = [group["table"] for group in resp.json()["response"]]
    assert LatencyTable.Meta.name in tables
    assert ThroughputTable.Meta.name not in tables


def test_release_results_endpoint_unknown_release(api_client):
    resp = api_client.get(f"{API_PREFIX}/results/release/no-such-release", params={"table": "x"})

    assert resp.json()["status"] == "error"
