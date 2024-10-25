from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from argus.backend.models.result import ArgusGenericResultMetadata, ArgusGenericResultData, ColumnMetadata
from argus.backend.service.results_service import ResultsService

@pytest.fixture
def setup_data(argus_db):
    test_id = uuid4()
    table = ArgusGenericResultMetadata(
        test_id=test_id,
        name='Test Table',
        columns_meta=[
            ColumnMetadata(name='col1', unit='ms', type='FLOAT', higher_is_better=False)
        ],
        rows_meta=['row1'],
        validation_rules={}
    )
    data = [
        ArgusGenericResultData(
            test_id=test_id,
            name=table.name,
            run_id=uuid4(),
            column='col1',
            row='row1',
            sut_timestamp=datetime.today() - timedelta(days=10),
            value=100.0,
            status='UNSET'
        ).save(),
        ArgusGenericResultData(
            test_id=test_id,
            name=table.name,
            run_id=uuid4(),
            column='col1',
            row='row1',
            sut_timestamp=datetime.today() - timedelta(days=5),
            value=150.0,
            status='UNSET'
        ).save(),
        ArgusGenericResultData(
            test_id=test_id,
            name=table.name,
            run_id=uuid4(),
            column='col1',
            row='row1',
            sut_timestamp=datetime.today() - timedelta(days=1),
            value=200.0,
            status='UNSET'
        ).save()
    ]
    return test_id, table, data


def test_results_service_should_return_results_within_date_range(setup_data):
    test_id, table, data = setup_data
    service = ResultsService()

    start_date = datetime.today() - timedelta(days=7)
    end_date = datetime.today() - timedelta(days=2)

    filtered_data = service._get_tables_data(
        test_id=test_id,
        table_name=table.name,
        ignored_runs=[],
        start_date=start_date,
        end_date=end_date
    )

    assert len(filtered_data) == 1
    assert filtered_data[0].value == 150.0

def test_results_service_should_return_no_results_outside_date_range(setup_data):
    test_id, table, data = setup_data
    service = ResultsService()

    start_date = datetime.today() - timedelta(days=20)
    end_date = datetime.today() - timedelta(days=15)

    filtered_data = service._get_tables_data(
        test_id=test_id,
        table_name=table.name,
        ignored_runs=[],
        start_date=start_date,
        end_date=end_date
    )

    assert len(filtered_data) == 0

def test_results_service_should_return_all_results_with_no_date_range(setup_data):
    test_id, table, data = setup_data
    service = ResultsService()

    filtered_data = service._get_tables_data(
        test_id=test_id,
        table_name=table.name,
        ignored_runs=[]
    )

    assert len(filtered_data) == 3
