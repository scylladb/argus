"""Coverage for the include-hidden escape hatch on the results fetch path.

Columns submitted with ``visible=False`` (SCT does this for the adaptive-timeout
datasets) are filtered out server-side by default.  ``include_hidden`` bypasses
that filter for a single request, both on the service and on the endpoint that
the ``argus run results --show-hidden`` CLI command calls.
"""
from dataclasses import asdict, dataclass
from typing import Any
from uuid import UUID

import pytest

from argus.backend.tests.conftest import get_fake_test_run, fake_test
from argus.client.generic_result import ColumnMetadata, ResultType, Status, StaticGenericResultTable

API_PREFIX = "/api/v1"

VISIBLE_COLUMN = "visible col"
HIDDEN_COLUMN = "hidden col"


class HiddenColumnTable(StaticGenericResultTable):
    class Meta:
        name = "Hidden Column Table"
        description = "Table mixing visible and hidden columns"
        Columns = [
            ColumnMetadata(name=VISIBLE_COLUMN, unit="ms", type=ResultType.FLOAT),
            ColumnMetadata(name=HIDDEN_COLUMN, unit="ms", type=ResultType.FLOAT, visible=False),
        ]


@dataclass
class SampleCell:
    column: str
    row: str
    value: Any
    status: Status = Status.UNSET


SAMPLE_CELLS = [
    SampleCell(column=VISIBLE_COLUMN, row="row", value=10),
    SampleCell(column=HIDDEN_COLUMN, row="row", value=20),
]


@pytest.fixture
def run_with_hidden_column(client_service, fake_test, release, group):
    """Submit a run carrying one visible and one hidden column."""
    run_type, run = get_fake_test_run(test=fake_test)
    results = HiddenColumnTable()
    results.sut_timestamp = 123
    for cell in SAMPLE_CELLS:
        results.add_result(column=cell.column, row=cell.row, value=cell.value, status=cell.status)
    client_service.submit_run(run_type, asdict(run))
    client_service.submit_results(run_type, run.run_id, results.as_dict())
    return UUID(run.run_id)


def _table_data(run_results):
    return run_results[0][HiddenColumnTable.Meta.name]


def test_hidden_columns_excluded_by_default(results_service, fake_test, run_with_hidden_column):
    table = _table_data(results_service.get_run_results(fake_test.id, run_with_hidden_column))

    # The service returns column metadata as UDT objects; the endpoint encodes them as dicts.
    assert [col.name for col in table["columns"]] == [VISIBLE_COLUMN]
    assert set(table["table_data"]["row"]) == {VISIBLE_COLUMN}


def test_hidden_columns_included_when_requested(results_service, fake_test, run_with_hidden_column):
    table = _table_data(
        results_service.get_run_results(fake_test.id, run_with_hidden_column, include_hidden=True))

    assert [col.name for col in table["columns"]] == [VISIBLE_COLUMN, HIDDEN_COLUMN]
    assert table["table_data"]["row"][HIDDEN_COLUMN]["value"] == 20


def test_fetch_results_endpoint_hides_columns_by_default(api_client, fake_test, run_with_hidden_column):
    resp = api_client.get(f"{API_PREFIX}/run/{fake_test.id}/{run_with_hidden_column}/fetch_results")

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"
    table = _table_data(resp.json()["tables"])
    assert [col["name"] for col in table["columns"]] == [VISIBLE_COLUMN]


def test_fetch_results_endpoint_includes_hidden_columns_on_request(api_client, fake_test, run_with_hidden_column):
    resp = api_client.get(
        f"{API_PREFIX}/run/{fake_test.id}/{run_with_hidden_column}/fetch_results",
        params={"includeHidden": "true"},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"
    table = _table_data(resp.json()["tables"])
    assert [col["name"] for col in table["columns"]] == [VISIBLE_COLUMN, HIDDEN_COLUMN]
    assert table["table_data"]["row"][HIDDEN_COLUMN]["value"] == 20
