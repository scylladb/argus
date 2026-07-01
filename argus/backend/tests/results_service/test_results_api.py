from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from argus.backend.models.result import ArgusGenericResultData, ArgusGenericResultMetadata, ColumnMetadata


@pytest.fixture
def cross_test_table(argus_db):
    """Two tests reporting the same (per-invocation unique) table name.

    The name is randomized because the underlying keyspace is session-scoped
    and shared across every test in this file, and catalog/search scan the
    whole table with no test_id restriction.
    """
    test_id_a = uuid4()
    test_id_b = uuid4()
    table_name = f"ApiCrossTestTable-{uuid4()}"

    ArgusGenericResultMetadata(
        test_id=test_id_a,
        name=table_name,
        columns_meta=[ColumnMetadata(name="col1", unit="ms", type="FLOAT", higher_is_better=False)],
        rows_meta=["row1"],
        validation_rules={},
    ).save()
    ArgusGenericResultMetadata(
        test_id=test_id_b,
        name=table_name,
        columns_meta=[ColumnMetadata(name="col1", unit="ms", type="FLOAT", higher_is_better=False)],
        rows_meta=["row1"],
        validation_rules={},
    ).save()

    now = datetime.now(UTC)
    ArgusGenericResultData(
        test_id=test_id_a, name=table_name, run_id=uuid4(), column="col1", row="row1",
        sut_timestamp=now - timedelta(days=1), value=1.0, status="UNSET",
    ).save()
    ArgusGenericResultData(
        test_id=test_id_b, name=table_name, run_id=uuid4(), column="col1", row="row1",
        sut_timestamp=now, value=2.0, status="UNSET",
    ).save()

    return test_id_a, test_id_b, table_name


def test_results_catalog_endpoint_returns_names_across_tests(cross_test_table, flask_client):
    _, _, table_name = cross_test_table
    response = flask_client.get("/api/results/catalog")

    assert response.status_code == 200, response.text
    assert response.json["status"] == "ok"
    by_name = {entry["name"]: entry for entry in response.json["response"]}
    assert by_name[table_name]["test_count"] == 2
    assert by_name[table_name]["columns"][0]["name"] == "col1"


def test_results_search_endpoint_returns_cells_across_tests(cross_test_table, flask_client):
    test_id_a, test_id_b, table_name = cross_test_table
    response = flask_client.get(f"/api/results/search?name={table_name}&limit=10")

    assert response.status_code == 200, response.text
    assert response.json["status"] == "ok"
    cells = response.json["response"]["cells"]
    assert response.json["response"]["total"] == 2
    assert {cell["test_id"] for cell in cells} == {str(test_id_a), str(test_id_b)}


def test_results_search_endpoint_filters_by_status(cross_test_table, flask_client):
    _, _, table_name = cross_test_table
    response = flask_client.get(
        f"/api/results/search?name={table_name}&status[]=UNSET&limit=1")

    assert response.status_code == 200, response.text
    # "total" reflects the full matching set (2 UNSET cells), not just the
    # page returned once --limit truncates it down to 1.
    assert response.json["response"]["total"] == 2
    cells = response.json["response"]["cells"]
    assert len(cells) == 1
    assert cells[0]["status"] == "UNSET"
