from datetime import datetime
from uuid import uuid4

from argus.backend.models.result import ArgusGenericResultMetadata, ColumnMetadata, ArgusGenericResultData, ValidationRules
from argus.backend.service.results_service import create_chartjs, BestResult, RunsDetails


def test_create_chartjs_without_validation_rules_should_create_chart_without_limits_series():
    table = ArgusGenericResultMetadata(
        test_id=uuid4(),
        name='Test Table',
        columns_meta=[
            ColumnMetadata(name='col1', unit='ms', type='FLOAT', higher_is_better=False)
        ],
        rows_meta=['row1'],
        validation_rules={}
    )
    data = [
        ArgusGenericResultData(
            test_id=table.test_id,
            name=table.name,
            run_id=uuid4(),
            column='col1',
            row='row1',
            sut_timestamp=datetime(2021, 1, 1),
            value=100.0,
            status='UNSET'
        )
    ]
    best_results = {
        'col1:row1': [BestResult(key='col1:row1', value=100.0, result_date=datetime(2021, 1, 1), run_id=str(uuid4()))]
    }
    releases_map = {"1.0": [point.run_id for point in data]}
    runs_details = RunsDetails(ignored=[], packages={})
    graphs = create_chartjs(table, data, best_results, releases_map, runs_details, main_package="pkg1")
    assert len(graphs) == 1
    assert len(graphs[0]['data']['datasets']) == 1  # no limits series


def test_create_chartjs_without_best_results_should_not_fail():
    table = ArgusGenericResultMetadata(
        test_id=uuid4(),
        name='Test Table',
        columns_meta=[
            ColumnMetadata(name='col1', unit='ms', type='FLOAT')
        ],
        rows_meta=['row1'],
        validation_rules={}
    )
    data = [
        ArgusGenericResultData(
            test_id=table.test_id,
            name=table.name,
            run_id=uuid4(),
            column='col1',
            row='row1',
            sut_timestamp=datetime(2021, 1, 1),
            value=100.0,
            status='UNSET'
        )
    ]
    best_results = {}
    releases_map = {"1.0": [point.run_id for point in data]}
    runs_details = RunsDetails(ignored=[], packages={})
    graphs = create_chartjs(table, data, best_results, releases_map, runs_details, main_package="pkg1")
    assert len(graphs) == 1
    assert len(graphs[0]['data']['datasets']) == 1  # no limits series


def test_create_chartjs_with_validation_rules_should_add_limit_series():
    table = ArgusGenericResultMetadata(
        test_id=uuid4(),
        name='Test Table',
        columns_meta=[
            ColumnMetadata(name='col1', unit='ms', type='FLOAT', higher_is_better=False)
        ],
        rows_meta=['row1'],
        validation_rules={
            'col1': [ValidationRules(valid_from=datetime(2021, 1, 1), best_pct=5.0, best_abs=None, fixed_limit=None)]
        }
    )
    data = [
        ArgusGenericResultData(
            test_id=table.test_id,
            name=table.name,
            run_id=uuid4(),
            column='col1',
            row='row1',
            sut_timestamp=datetime(2021, 2, 1),
            value=95.0,
            status='UNSET'
        )
    ]
    best_results = {
        'col1:row1': [BestResult(key='col1:row1', value=100.0, result_date=datetime(2021, 1, 1), run_id=str(uuid4()))]
    }
    releases_map = {"1.0": [point.run_id for point in data]}
    runs_details = RunsDetails(ignored=[], packages={})
    graphs = create_chartjs(table, data, best_results, releases_map, runs_details, main_package="pkg1")
    assert 'limit' in graphs[0]['data']['datasets'][0]['data'][0]


def test_chartjs_with_multiple_best_results_and_validation_rules_should_adjust_limits_for_each_point():
    table = ArgusGenericResultMetadata(
        test_id=uuid4(),
        name='Test Table',
        columns_meta=[
            ColumnMetadata(name='col1', unit='ms', type='FLOAT', higher_is_better=False)
        ],
        rows_meta=['row1'],
        validation_rules={
            'col1': [
                ValidationRules(valid_from=datetime(2021, 1, 1), best_pct=5.0, best_abs=None, fixed_limit=None),
                ValidationRules(valid_from=datetime(2021, 3, 1), best_pct=None, best_abs=2.0, fixed_limit=None)
            ]
        }
    )
    data = [
        ArgusGenericResultData(
            test_id=table.test_id,
            name=table.name,
            run_id=uuid4(),
            column='col1',
            row='row1',
            sut_timestamp=datetime(2021, 2, 1),
            value=95.0,
            status='UNSET'
        ),
        ArgusGenericResultData(
            test_id=table.test_id,
            name=table.name,
            run_id=uuid4(),
            column='col1',
            row='row1',
            sut_timestamp=datetime(2021, 4, 1),
            value=90.0,
            status='UNSET'
        )
    ]
    best_results = {
        'col1:row1': [
            BestResult(key='col1:row1', value=100.0, result_date=datetime(2021, 1, 1), run_id=str(uuid4())),
            BestResult(key='col1:row1', value=94.0, result_date=datetime(2021, 3, 1), run_id=str(uuid4()))
        ]
    }
    releases_map = {"1.0": [point.run_id for point in data]}
    runs_details = RunsDetails(ignored=[], packages={})
    graphs = create_chartjs(table, data, best_results, releases_map, runs_details, main_package="pkg1")
    datasets = graphs[0]['data']['datasets']
    limits = [point.get('limit') for dataset in datasets for point in dataset['data'] if 'limit' in point]
    assert len(limits) == 2
    assert limits[0] == 105.0
    assert limits[1] == 96.0


def test_create_chartjs_no_data_should_not_fail():
    table = ArgusGenericResultMetadata(
        test_id=uuid4(),
        name='Empty Table',
        columns_meta=[],
        rows_meta=[],
        validation_rules={}
    )
    data = []
    best_results = {}
    releases_map = {"1.0": []}
    runs_details = RunsDetails(ignored=[], packages={})
    graphs = create_chartjs(table, data, best_results, releases_map, runs_details, main_package="pkg1")
    assert len(graphs) == 0


def test_create_chartjs_multiple_columns_and_rows():
    table = ArgusGenericResultMetadata(
        test_id=uuid4(),
        name='Complex Table',
        columns_meta=[
            ColumnMetadata(name='col1', unit='ms', type='FLOAT', higher_is_better=False),
            ColumnMetadata(name='col2', unit='%', type='FLOAT', higher_is_better=True)
        ],
        rows_meta=['row1', 'row2'],
        validation_rules={
            'col1': [ValidationRules(valid_from=datetime(2021, 1, 1), best_pct=5.0, best_abs=None, fixed_limit=None)]
        }
    )
    data = [
        ArgusGenericResultData(
            test_id=table.test_id,
            name=table.name,
            run_id=uuid4(),
            column='col1',
            row='row1',
            sut_timestamp=datetime(2021, 1, 1),
            value=100.0,
            status='UNSET'
        ),
        ArgusGenericResultData(
            test_id=table.test_id,
            name=table.name,
            run_id=uuid4(),
            column='col2',
            row='row2',
            sut_timestamp=datetime(2021, 1, 2),
            value=50.0,
            status='UNSET'
        )
    ]
    best_results = {
        'col1:row1': [
            BestResult(key='col1:row1', value=100.0, result_date=datetime(2021, 1, 1), run_id=str(uuid4())),
        ],
        'col2:row2': [
            BestResult(key='col2:row2', value=50.0, result_date=datetime(2021, 1, 2), run_id=str(uuid4())),
        ]
    }
    releases_map = {"1.0": [point.run_id for point in data]}
    runs_details = RunsDetails(ignored=[], packages={})
    graphs = create_chartjs(table, data, best_results, releases_map, runs_details, main_package="pkg1")
    assert len(graphs) == 2
    assert len(graphs[0]['data']['datasets']) == 2  # should have also limits dataset
    assert len(graphs[1]['data']['datasets']) == 1  # no limits series
