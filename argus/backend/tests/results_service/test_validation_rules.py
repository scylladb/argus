import logging
from dataclasses import asdict, dataclass
from typing import Any
from uuid import UUID

import pytest

from argus.backend.error_handlers import DataValidationError
from argus.backend.tests.conftest import get_fake_test_run, fake_test
from argus.client.generic_result import GenericResultTable, ColumnMetadata, ResultType, ValidationRule, Status

LOGGER = logging.getLogger(__name__)


class SampleTable(GenericResultTable):
    class Meta:
        name = "Test Table Name"
        description = "Test Table Description"
        Columns = [ColumnMetadata(name="h_is_better", unit="ms", type=ResultType.FLOAT, higher_is_better=True),
                   ColumnMetadata(name="l_is_better", unit="ms", type=ResultType.INTEGER, higher_is_better=False),
                   ColumnMetadata(name="duration col name", unit="s", type=ResultType.DURATION, higher_is_better=False),
                   ColumnMetadata(name="non tracked col name", unit="", type=ResultType.FLOAT),
                   ColumnMetadata(name="text col name", unit="", type=ResultType.TEXT),
                   ]
        ValidationRules = {"h_is_better": ValidationRule(best_abs=4),
                           "l_is_better": ValidationRule(best_pct=50),
                           "duration col name": ValidationRule(fixed_limit=590)
                           }


@dataclass
class SampleCell:
    column: str
    row: str
    value: Any
    status: Status = Status.UNSET


def results_to_dict(results):
    actual_cells = {}
    table_data = results['Test Table Name']['table_data']

    for row_key, row_data in table_data.items():
        for col_name, col_data in row_data.items():
            if col_name not in actual_cells:
                actual_cells[col_name] = {}
            actual_cells[col_name][row_key] = {
                'value': col_data['value'],
                'status': col_data['status']
            }
    return actual_cells


def test_can_track_validation_rules_changes(fake_test, client_service, results_service, release, group):
    run_type, run = get_fake_test_run(test=fake_test)
    results = SampleTable()
    results.sut_timestamp = 123
    sample_data = [
        SampleCell(column="h_is_better", row="row", value=10),
        SampleCell(column="l_is_better", row="row", value=100),
        SampleCell(column="duration col name", row="row", value=10),
        SampleCell(column="non tracked col name", row="row", value=10),
        SampleCell(column="text col name", row="row", value="a value"),
    ]
    for cell in sample_data:
        results.add_result(column=cell.column, row=cell.row, value=cell.value, status=cell.status)
    client_service.submit_run(run_type, asdict(run))
    client_service.submit_results(run_type, run.run_id, results.as_dict())
    run_results = results_service.get_run_results(fake_test.id, UUID(run.run_id))
    actual_cells = results_to_dict(run_results[0])
    # all results should be marked as passed
    for cell in sample_data:
        if cell.column == "text col name" or cell.column == "non tracked col name":
            assert actual_cells[cell.column][cell.row]['value'] == cell.value
            assert actual_cells[cell.column][cell.row]['status'] == "UNSET"
        else:
            assert actual_cells[cell.column][cell.row]['value'] == cell.value
            assert actual_cells[cell.column][cell.row]['status'] == "PASS"

    # test validation rules are applied correctly
    run_type, run = get_fake_test_run(test=fake_test)
    results = SampleTable()
    results.sut_timestamp = 124
    sample_data = [
        SampleCell(column="h_is_better", row="row", value=6),
        SampleCell(column="l_is_better", row="row", value=150),
        SampleCell(column="duration col name", row="row", value=600),
        SampleCell(column="non tracked col name", row="row", value=12),
        SampleCell(column="text col name", row="row", value="a value"),
    ]
    for cell in sample_data:
        results.add_result(column=cell.column, row=cell.row, value=cell.value, status=cell.status)
    client_service.submit_run(run_type, asdict(run))
    with pytest.raises(DataValidationError):
        client_service.submit_results(run_type, run.run_id, results.as_dict())
    run_results = results_service.get_run_results(fake_test.id, UUID(run.run_id))
    actual_cells = results_to_dict(run_results[0])
    for cell in sample_data:
        if cell.column == "text col name" or cell.column == "non tracked col name":
            assert actual_cells[cell.column][cell.row][
                'value'] == cell.value, f"Expected {cell.value} but got {actual_cells[cell.column][cell.row]['value']}"
            assert actual_cells[cell.column][cell.row][
                'status'] == "UNSET", f"Expected ERROR for {cell.column} but got {actual_cells[cell.column][cell.row]['status']}"
        else:
            assert actual_cells[cell.column][cell.row][
                'value'] == cell.value, f"Expected {cell.value} but got {actual_cells[cell.column][cell.row]['value']}"
            assert actual_cells[cell.column][cell.row][
                'status'] == "ERROR", f"Expected ERROR for {cell.column} but got {actual_cells[cell.column][cell.row]['status']}"

    # new best result appears
    run_type, run = get_fake_test_run(test=fake_test)
    results = SampleTable()
    results.sut_timestamp = 125
    sample_data = [
        SampleCell(column="h_is_better", row="row", value=100),
        SampleCell(column="l_is_better", row="row", value=50),
        SampleCell(column="duration col name", row="row", value=10),
        SampleCell(column="non tracked col name", row="row", value=12),
        SampleCell(column="text col name", row="row", value="a value"),
    ]
    for cell in sample_data:
        results.add_result(column=cell.column, row=cell.row, value=cell.value, status=cell.status)
    client_service.submit_run(run_type, asdict(run))
    client_service.submit_results(run_type, run.run_id, results.as_dict())
    run_results = results_service.get_run_results(fake_test.id, UUID(run.run_id))
    actual_cells = results_to_dict(run_results[0])
    for cell in sample_data:
        if cell.column == "text col name" or cell.column == "non tracked col name":
            assert actual_cells[cell.column][cell.row][
                'value'] == cell.value, f"Expected {cell.value} but got {actual_cells[cell.column][cell.row]['value']}"
            assert actual_cells[cell.column][cell.row][
                'status'] == "UNSET", f"Expected PASS for {cell.column} but got {actual_cells[cell.column][cell.row]['status']}"
        else:
            assert actual_cells[cell.column][cell.row][
                'value'] == cell.value, f"Expected {cell.value} but got {actual_cells[cell.column][cell.row]['value']}"
            assert actual_cells[cell.column][cell.row][
                'status'] == "PASS", f"Expected PASS for {cell.column} but got {actual_cells[cell.column][cell.row]['status']}"

    # validation should be now with new best results
    run_type, run = get_fake_test_run(test=fake_test)
    results = SampleTable()
    results.sut_timestamp = 126
    sample_data = [
        SampleCell(column="h_is_better", row="row", value=95),
        SampleCell(column="l_is_better", row="row", value=75),
        SampleCell(column="duration col name", row="row", value=590),
        SampleCell(column="non tracked col name", row="row", value=12),
        SampleCell(column="text col name", row="row", value="a value"),
    ]
    for cell in sample_data:
        results.add_result(column=cell.column, row=cell.row, value=cell.value, status=cell.status)
    client_service.submit_run(run_type, asdict(run))
    with pytest.raises(DataValidationError):
        client_service.submit_results(run_type, run.run_id, results.as_dict())
    run_results = results_service.get_run_results(fake_test.id, UUID(run.run_id))
    actual_cells = results_to_dict(run_results[0])
    for cell in sample_data:
        if cell.column == "text col name" or cell.column == "non tracked col name":
            assert actual_cells[cell.column][cell.row][
                'value'] == cell.value, f"Expected {cell.value} but got {actual_cells[cell.column][cell.row]['value']}"
            assert actual_cells[cell.column][cell.row][
                'status'] == "UNSET", f"Expected ERROR for {cell.column} but got {actual_cells[cell.column][cell.row]['status']}"
        else:
            assert actual_cells[cell.column][cell.row][
                'value'] == cell.value, f"Expected {cell.value} but got {actual_cells[cell.column][cell.row]['value']}"
            assert actual_cells[cell.column][cell.row][
                'status'] == "ERROR", f"Expected ERROR for {cell.column} but got {actual_cells[cell.column][cell.row]['status']}"

    # applying new validation rules should be taken into account for next results, new rules are less strict
    # duration col name rule is removed and 'non tracked col name' has new fixed limit
    class NewRulesSampleTable(SampleTable):
        class Meta:
            name = "Test Table Name"
            description = "Test Table Description"
            Columns = [ColumnMetadata(name="h_is_better", unit="ms", type=ResultType.FLOAT, higher_is_better=True),
                       ColumnMetadata(name="l_is_better", unit="ms", type=ResultType.INTEGER, higher_is_better=False),
                       ColumnMetadata(name="duration col name", unit="s",
                                      type=ResultType.DURATION, higher_is_better=False),
                       ColumnMetadata(name="non tracked col name", unit="",
                                      type=ResultType.FLOAT, higher_is_better=True),
                       ColumnMetadata(name="text col name", unit="", type=ResultType.TEXT),
                       ]
            ValidationRules = {"h_is_better": ValidationRule(best_abs=100),
                               "l_is_better": ValidationRule(best_pct=90),
                               "non tracked col name": ValidationRule(fixed_limit=100)  # new rule, removed old one too
                               }
    run_type, run = get_fake_test_run(test=fake_test)
    results = NewRulesSampleTable()
    results.sut_timestamp = 122
    sample_data = [
        SampleCell(column="h_is_better", row="row", value=95),
        SampleCell(column="l_is_better", row="row", value=75),
        SampleCell(column="duration col name", row="row", value=691),
        SampleCell(column="non tracked col name", row="row", value=101),
        SampleCell(column="text col name", row="row", value="a value"),
    ]
    for cell in sample_data:
        results.add_result(column=cell.column, row=cell.row, value=cell.value, status=cell.status)
    client_service.submit_run(run_type, asdict(run))
    client_service.submit_results(run_type, run.run_id, results.as_dict())
    run_results = results_service.get_run_results(fake_test.id, UUID(run.run_id))
    actual_cells = results_to_dict(run_results[0])
    for cell in sample_data:
        if cell.column == "text col name":
            assert actual_cells[cell.column][cell.row][
                'value'] == cell.value, f"Expected {cell.value} but got {actual_cells[cell.column][cell.row]['value']}"
            assert actual_cells[cell.column][cell.row][
                'status'] == "UNSET", f"Expected UNSET for {cell.column} but got {actual_cells[cell.column][cell.row]['status']}"
        else:
            assert actual_cells[cell.column][cell.row][
                'value'] == cell.value, f"Expected {cell.value} but got {actual_cells[cell.column][cell.row]['value']}"
            assert actual_cells[cell.column][cell.row][
                'status'] == "PASS", f"Expected PASS for {cell.column} but got {actual_cells[cell.column][cell.row]['status']}"
