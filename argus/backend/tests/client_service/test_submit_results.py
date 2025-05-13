from dataclasses import asdict, dataclass
from typing import Any

import pytest

from argus.backend.error_handlers import DataValidationError
from argus.backend.tests.conftest import get_fake_test_run
from argus.client.generic_result import GenericResultTable, ColumnMetadata, ResultType, ValidationRule, Status


@dataclass
class SampleCell:
    column: str
    row: str
    value: Any
    status: Status = Status.UNSET


class SampleTable(GenericResultTable):
    class Meta:
        name = "Test Table"
        description = "Test Table Description"
        sut_package_name = "test_package"
        Columns = [
            ColumnMetadata(name="metric1", unit="ms", type=ResultType.FLOAT, higher_is_better=False),
            ColumnMetadata(name="metric2", unit="ms", type=ResultType.INTEGER, higher_is_better=False),
        ]
        ValidationRules = {
            "metric1": ValidationRule(fixed_limit=100),
            "metric2": ValidationRule(fixed_limit=200),
        }


def test_submit_results_responds_ok_if_all_cells_pass(fake_test, client_service):
    run_type, run = get_fake_test_run(test=fake_test)
    results = SampleTable()
    results.sut_timestamp = 123
    sample_data = [
        SampleCell(column="metric1", row="row1", value=99.99),
        SampleCell(column="metric2", row="row1", value=199.99),
    ]
    for cell in sample_data:
        results.add_result(column=cell.column, row=cell.row, value=cell.value, status=cell.status)
    client_service.submit_run(run_type, asdict(run))
    response = client_service.submit_results(run_type, run.run_id, results.as_dict())
    assert results.as_dict()["meta"]["sut_package_name"] == "test_package"
    assert response["status"] == "ok"
    assert response["message"] == "Results submitted"


def test_submit_results_responds_with_error_when_cell_fails_validation(fake_test, client_service):
    run_type, run = get_fake_test_run(test=fake_test)
    results = SampleTable()
    results.sut_timestamp = 123
    sample_data = [
        SampleCell(column="metric1", row="row1", value=100.01),  # Exceeds fixed_limit
        SampleCell(column="metric2", row="row1", value=50),
    ]
    for cell in sample_data:
        results.add_result(column=cell.column, row=cell.row, value=cell.value, status=cell.status)
    client_service.submit_run(run_type, asdict(run))
    with pytest.raises(DataValidationError):
        client_service.submit_results(run_type, run.run_id, results.as_dict())


def test_submit_results_responds_with_error_when_cell_has_error(fake_test, client_service):
    run_type, run = get_fake_test_run(test=fake_test)
    results = SampleTable()
    results.sut_timestamp = 123
    sample_data = [
        SampleCell(column="metric1", row="row1", value=88, status=Status.ERROR),  # hardcoded error
        SampleCell(column="metric2", row="row1", value=50),
    ]
    for cell in sample_data:
        results.add_result(column=cell.column, row=cell.row, value=cell.value, status=cell.status)
    client_service.submit_run(run_type, asdict(run))
    with pytest.raises(DataValidationError):
        client_service.submit_results(run_type, run.run_id, results.as_dict())
