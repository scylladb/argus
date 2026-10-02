"""Coverage for columns that a run does not fill.

The table metadata is shared by all runs of a test, so it can define a column
that one run sends no cells for. The results fetch path shows a column only
when the run has at least one cell in it. The ``argus run results`` CLI
command calls the same endpoint, so the same rule applies there.
"""
from dataclasses import asdict
from uuid import UUID

import pytest

from argus.backend.tests.conftest import get_fake_test_run, fake_test
from argus.client.generic_result import ColumnMetadata, ResultType, Status, StaticGenericResultTable

API_PREFIX = "/api/v1"

P90_COLUMN = "P90 write"
P95_COLUMN = "P95 write"


class LatencyTable(StaticGenericResultTable):
    class Meta:
        name = "Latency Table"
        description = "Table with an optional percentile column"
        Columns = [
            ColumnMetadata(name=P90_COLUMN, unit="ms", type=ResultType.FLOAT),
            ColumnMetadata(name=P95_COLUMN, unit="ms", type=ResultType.FLOAT),
        ]


@pytest.fixture
def submit_cells(client_service, fake_test, release, group):
    """Submit a run of ``fake_test`` with the given ``(column, row, value)`` cells."""
    async def submit(cells: list[tuple[str, str, float]]) -> UUID:
        run_type, run = get_fake_test_run(test=fake_test)
        results = LatencyTable()
        results.sut_timestamp = 123
        for column, row, value in cells:
            results.add_result(column=column, row=row, value=value, status=Status.UNSET)
        await client_service.submit_run(run_type, asdict(run))
        await client_service.submit_results(run_type, run.run_id, results.as_dict())
        return UUID(run.run_id)
    return submit


def _table_data(run_results):
    return run_results[0][LatencyTable.Meta.name]


async def test_column_without_cells_is_not_returned(results_service, fake_test, submit_cells):
    run_with_p95 = await submit_cells([(P90_COLUMN, "row", 1.0), (P95_COLUMN, "row", 2.0)])
    run_without_p95 = await submit_cells([(P90_COLUMN, "row", 1.0)])

    with_p95 = _table_data(await results_service.get_run_results(fake_test.id, run_with_p95))
    without_p95 = _table_data(await results_service.get_run_results(fake_test.id, run_without_p95))

    assert [col.name for col in with_p95["columns"]] == [P90_COLUMN, P95_COLUMN]
    assert [col.name for col in without_p95["columns"]] == [P90_COLUMN]
    assert set(without_p95["table_data"]["row"]) == {P90_COLUMN}


async def test_column_with_cells_in_some_rows_is_returned(results_service, fake_test, submit_cells):
    run_id = await submit_cells([(P90_COLUMN, "row a", 1.0), (P95_COLUMN, "row a", 2.0), (P90_COLUMN, "row b", 3.0)])

    table = _table_data(await results_service.get_run_results(fake_test.id, run_id))

    assert [col.name for col in table["columns"]] == [P90_COLUMN, P95_COLUMN]
    assert set(table["table_data"]["row b"]) == {P90_COLUMN}


async def test_fetch_results_endpoint_omits_column_without_cells(api_client, fake_test, submit_cells):
    run_id = await submit_cells([(P90_COLUMN, "row", 1.0)])

    resp = api_client.get(f"{API_PREFIX}/run/{fake_test.id}/{run_id}/fetch_results")

    assert resp.status_code == 200, resp.text
    table = _table_data(resp.json()["tables"])
    assert [col["name"] for col in table["columns"]] == [P90_COLUMN]
