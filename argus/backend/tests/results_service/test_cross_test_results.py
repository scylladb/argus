from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from argus.backend.models.result import ArgusGenericResultData, ArgusGenericResultMetadata, ColumnMetadata
from argus.backend.plugins.sct.testrun import SCTTestRun
from argus.backend.service.results_service import ResultsService


@pytest.fixture
def two_tests_same_table_name(argus_db):
    """Two distinct tests, both reporting a table with the same (per-invocation
    unique) name, plus a third test with a differently-named table, to
    exercise cross-test catalog/search without knowing any test_id up front.

    The table name is randomized per invocation because the underlying
    keyspace is shared (session-scoped) across every test in this file, and
    catalog/search scan the whole table with no test_id restriction.
    """
    test_id_a = uuid4()
    test_id_b = uuid4()
    test_id_c = uuid4()
    table_name = f"Latency-{uuid4()}"
    other_table_name = f"Throughput-{uuid4()}"

    ArgusGenericResultMetadata(
        test_id=test_id_a,
        name=table_name,
        columns_meta=[
            ColumnMetadata(name="p99", unit="ms", type="FLOAT", higher_is_better=False),
        ],
        rows_meta=["run1"],
        validation_rules={},
    ).save()
    ArgusGenericResultMetadata(
        test_id=test_id_b,
        name=table_name,
        columns_meta=[
            ColumnMetadata(name="p99", unit="ms", type="FLOAT", higher_is_better=False),
            ColumnMetadata(name="p999", unit="ms", type="FLOAT", higher_is_better=False),
        ],
        rows_meta=["run1"],
        validation_rules={},
    ).save()
    ArgusGenericResultMetadata(
        test_id=test_id_c,
        name=other_table_name,
        columns_meta=[
            ColumnMetadata(name="ops", unit="op/s", type="FLOAT", higher_is_better=True),
        ],
        rows_meta=["run1"],
        validation_rules={},
    ).save()

    now = datetime.now(UTC)
    ArgusGenericResultData(
        test_id=test_id_a, name=table_name, run_id=uuid4(), column="p99", row="run1",
        sut_timestamp=now - timedelta(days=5), value=10.0, status="UNSET",
    ).save()
    ArgusGenericResultData(
        test_id=test_id_b, name=table_name, run_id=uuid4(), column="p99", row="run1",
        sut_timestamp=now - timedelta(days=1), value=20.0, status="ERROR",
    ).save()
    ArgusGenericResultData(
        test_id=test_id_c, name=other_table_name, run_id=uuid4(), column="ops", row="run1",
        sut_timestamp=now - timedelta(days=10), value=1000.0, status="UNSET",
    ).save()

    return test_id_a, test_id_b, test_id_c, table_name, other_table_name


def test_catalog_groups_same_named_table_across_tests(two_tests_same_table_name):
    _, _, _, table_name, other_table_name = two_tests_same_table_name
    service = ResultsService()
    catalog = service.get_generic_result_catalog()

    by_name = {entry["name"]: entry for entry in catalog}
    assert by_name[table_name]["test_count"] == 2
    column_names = {col["name"] for col in by_name[table_name]["columns"]}
    assert column_names == {"p99", "p999"}
    assert by_name[other_table_name]["test_count"] == 1


def test_search_returns_cells_across_tests_without_a_test_id(two_tests_same_table_name):
    test_id_a, test_id_b, _, table_name, _ = two_tests_same_table_name
    service = ResultsService()
    result = service.search_generic_results(name=table_name)

    assert result["total"] == 2
    cells = result["cells"]
    assert len(cells) == 2
    test_ids = {cell["test_id"] for cell in cells}
    assert test_ids == {str(test_id_a), str(test_id_b)}
    assert all(cell["table"] == table_name for cell in cells)


def test_search_filters_by_status(two_tests_same_table_name):
    _, _, _, table_name, _ = two_tests_same_table_name
    service = ResultsService()
    result = service.search_generic_results(name=table_name, statuses=["ERROR"])

    assert result["total"] == 1
    assert result["cells"][0]["status"] == "ERROR"


def test_search_respects_limit_but_reports_true_total(two_tests_same_table_name):
    _, _, _, table_name, _ = two_tests_same_table_name
    service = ResultsService()
    result = service.search_generic_results(name=table_name, limit=1)

    assert result["total"] == 2
    assert len(result["cells"]) == 1


def test_search_filters_by_date_range(two_tests_same_table_name):
    _, test_id_b, _, table_name, _ = two_tests_same_table_name
    service = ResultsService()
    now = datetime.now(UTC)
    result = service.search_generic_results(name=table_name, after=now - timedelta(days=2))

    assert result["total"] == 1
    assert result["cells"][0]["test_id"] == str(test_id_b)


def test_search_excludes_cells_from_ignored_runs(fake_test):
    table_name = f"IgnoredRunsTable-{uuid4()}"
    ignored_run_id = uuid4()
    kept_run_id = uuid4()
    start_time = datetime.now(UTC)

    ArgusGenericResultMetadata(
        test_id=fake_test.id,
        name=table_name,
        columns_meta=[ColumnMetadata(name="col1", unit="ms", type="FLOAT", higher_is_better=False)],
        rows_meta=["row1"],
        validation_rules={},
    ).save()

    SCTTestRun(
        id=ignored_run_id, build_id="build1", test_id=fake_test.id, test_method="method1",
        investigation_status="ignored", packages=[], start_time=start_time,
    ).save()
    SCTTestRun(
        id=kept_run_id, build_id="build1", test_id=fake_test.id, test_method="method1",
        investigation_status="", packages=[], start_time=start_time + timedelta(milliseconds=1),
    ).save()

    ArgusGenericResultData(
        test_id=fake_test.id, name=table_name, run_id=ignored_run_id, column="col1", row="row1",
        sut_timestamp=start_time, value=1.0, status="UNSET",
    ).save()
    ArgusGenericResultData(
        test_id=fake_test.id, name=table_name, run_id=kept_run_id, column="col1", row="row1",
        sut_timestamp=start_time, value=2.0, status="UNSET",
    ).save()

    service = ResultsService()
    result = service.search_generic_results(name=table_name)

    assert result["total"] == 1
    assert result["cells"][0]["run_id"] == str(kept_run_id)


def test_search_sorts_cells_with_missing_sut_timestamp_without_crashing(fake_test):
    table_name = f"NullTimestampTable-{uuid4()}"

    ArgusGenericResultMetadata(
        test_id=fake_test.id,
        name=table_name,
        columns_meta=[ColumnMetadata(name="col1", unit="ms", type="FLOAT", higher_is_better=False)],
        rows_meta=["row1"],
        validation_rules={},
    ).save()

    ArgusGenericResultData(
        test_id=fake_test.id, name=table_name, run_id=uuid4(), column="col1", row="row1",
        sut_timestamp=None, value=1.0, status="UNSET",
    ).save()
    ArgusGenericResultData(
        test_id=fake_test.id, name=table_name, run_id=uuid4(), column="col1", row="row1",
        sut_timestamp=datetime.now(UTC), value=2.0, status="UNSET",
    ).save()

    service = ResultsService()
    result = service.search_generic_results(name=table_name)

    assert result["total"] == 2
