import logging
from dataclasses import asdict, dataclass
from typing import Any

import pytest

from argus.backend.error_handlers import DataValidationError
from argus.backend.plugins.sct.testrun import SCTTestRun
from argus.backend.tests.conftest import get_fake_test_run, fake_test
from argus.common.enums import TestInvestigationStatus
from argus.client.generic_result import ColumnMetadata, ResultType, ValidationRule, Status, StaticGenericResultTable

LOGGER = logging.getLogger(__name__)


class SampleTable(StaticGenericResultTable):
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
                           "l_is_better": ValidationRule(best_pct=50, best_abs=5),
                           "duration col name": ValidationRule(fixed_limit=590)
                           }


@dataclass
class SampleCell:
    column: str
    row: str
    value: Any
    status: Status = Status.UNSET


def test_can_track_best_result(fake_test, client_service, results_service, release, group):
    run_type, run = get_fake_test_run(test=fake_test)
    results = SampleTable()
    results.sut_timestamp = 123
    sample_data = [
        SampleCell(column="h_is_better", row="row", value=10),
        SampleCell(column="l_is_better", row="row", value=10),
        SampleCell(column="duration col name", row="row", value=10),
    ]
    for cell in sample_data:
        results.add_result(column=cell.column, row=cell.row, value=cell.value, status=cell.status)
    client_service.submit_run(run_type, asdict(run))
    client_service.submit_results(run_type, run.run_id, results.as_dict())
    best_results = results_service.get_best_results(fake_test.id, results.name)
    # all results should be tracked as best - first submission
    for cell in sample_data:
        key = f"{cell.column}:{cell.row}"
        assert best_results[key][-1].value == cell.value
        assert str(best_results[key][-1].run_id) == run.run_id
    result_date_h = best_results["h_is_better:row"][-1].result_date  # save the result date for later comparison
    result_date_duration = best_results["duration col name:row"][-1].result_date
    # second submission with better results
    run_type, run = get_fake_test_run(test=fake_test)
    results = SampleTable()
    results.sut_timestamp = 124
    sample_data = [
        SampleCell(column="h_is_better", row="row", value=15),  # Improved
        SampleCell(column="l_is_better", row="row", value=5),  # Improved
        SampleCell(column="duration col name", row="row", value=10),  # Same
    ]
    for cell in sample_data:
        results.add_result(column=cell.column, row=cell.row, value=cell.value, status=cell.status)
    client_service.submit_run(run_type, asdict(run))
    client_service.submit_results(run_type, run.run_id, results.as_dict())
    best_results = results_service.get_best_results(fake_test.id, results.name)
    # best results should be updated
    assert best_results["h_is_better:row"][-1].value == 15
    assert best_results["h_is_better:row"][-1].result_date > result_date_h  # result date should be updated
    assert best_results["l_is_better:row"][-1].value == 5
    assert best_results["duration col name:row"][-1].value == 10
    # result date should not change as was not updated
    assert best_results["duration col name:row"][-1].result_date == result_date_duration


def test_can_enable_best_results_tracking(fake_test, client_service, results_service, release, group):
    """
    best results tracking can be enabled by setting higher_is_better in ColumnMetadata to bool value
    enabling best results tracking for a text column should not break the system
    """
    run_type, run = get_fake_test_run(test=fake_test)
    results = SampleTable()
    results.sut_timestamp = 123
    sample_data = [
        SampleCell(column="h_is_better", row="row", value=10),
        SampleCell(column="l_is_better", row="row", value=10),
        SampleCell(column="duration col name", row="row", value=10),
        SampleCell(column="non tracked col name", row="row", value=10),
    ]
    for cell in sample_data:
        results.add_result(column=cell.column, row=cell.row, value=cell.value, status=cell.status)
    client_service.submit_run(run_type, asdict(run))
    client_service.submit_results(run_type, run.run_id, results.as_dict())
    best_results = results_service.get_best_results(fake_test.id, results.name)
    assert 'non tracked col name:row' not in best_results  # non tracked column should not be tracked

    class TrackingAllSampleTable(StaticGenericResultTable):
        class Meta:
            name = "Test Table Name"
            description = "Test Table Description"
            Columns = [ColumnMetadata(name="h_is_better", unit="ms", type=ResultType.FLOAT, higher_is_better=True),
                       ColumnMetadata(name="l_is_better", unit="ms", type=ResultType.INTEGER, higher_is_better=False),
                       ColumnMetadata(name="duration col name", unit="s",
                                      type=ResultType.DURATION, higher_is_better=False),
                       ColumnMetadata(name="non tracked col name", unit="",
                                      type=ResultType.FLOAT, higher_is_better=True),
                       ColumnMetadata(name="text col name", unit="", type=ResultType.TEXT, higher_is_better=True),
                       ]

        ValidationRules = {"h_is_better": ValidationRule(best_abs=4),
                           "l_is_better": ValidationRule(best_pct=50, best_abs=5),
                           "duration col name": ValidationRule(fixed_limit=590)
                           }

    run_type, run = get_fake_test_run(test=fake_test)
    results = TrackingAllSampleTable()
    results.sut_timestamp = 124
    sample_data = [
        SampleCell(column="h_is_better", row="row", value=15),  # Improved
        SampleCell(column="l_is_better", row="row", value=5),  # Improved
        SampleCell(column="duration col name", row="row", value=10),  # Same
        SampleCell(column="non tracked col name", row="row", value=10),
        SampleCell(column="text col name", row="row", value="10"),
    ]
    for cell in sample_data:
        results.add_result(column=cell.column, row=cell.row, value=cell.value, status=cell.status)
    client_service.submit_run(run_type, asdict(run))
    client_service.submit_results(run_type, run.run_id, results.as_dict())
    best_results = results_service.get_best_results(fake_test.id, results.name)
    assert best_results["h_is_better:row"][-1].value == 15
    assert best_results["l_is_better:row"][-1].value == 5
    assert best_results["duration col name:row"][-1].value == 10
    assert best_results["non tracked col name:row"][-1].value == 10
    assert 'text col name:row' not in best_results  # text column should not be tracked


def test_ignored_runs_are_not_considered_in_best_results(fake_test, client_service, results_service, release, group):
    run_type, run = get_fake_test_run(test=fake_test)
    results = SampleTable()
    results.sut_timestamp = 123
    sample_data = [
        SampleCell(column="h_is_better", row="row", value=100),
        SampleCell(column="l_is_better", row="row", value=10),
    ]
    for cell in sample_data:
        results.add_result(column=cell.column, row=cell.row, value=cell.value, status=cell.status)
    client_service.submit_run(run_type, asdict(run))
    client_service.submit_results(run_type, run.run_id, results.as_dict())
    run_type, run2 = get_fake_test_run(test=fake_test)
    sample_data = [
        SampleCell(column="h_is_better", row="row", value=200),
        SampleCell(column="l_is_better", row="row", value=5),
    ]
    for cell in sample_data:
        results.add_result(column=cell.column, row=cell.row, value=cell.value, status=cell.status)
    client_service.submit_run(run_type, asdict(run2))
    with pytest.raises(DataValidationError):
        client_service.submit_results(run_type, run2.run_id, results.as_dict())

    # ignore the second run
    run_model = SCTTestRun.get(id=run2.run_id)
    run_model.investigation_status = TestInvestigationStatus.IGNORED.value
    run_model.save()

    best_results = results_service.get_best_results(fake_test.id, results.name)

    assert best_results["h_is_better:row"][-1].value == 100  # should not consider the second run
    assert str(best_results["h_is_better:row"][-1].run_id) == run.run_id
    assert best_results["l_is_better:row"][-1].value == 10   # should not consider the second run
    assert str(best_results["l_is_better:row"][-1].run_id) == run.run_id
