from uuid import uuid4

import pytest
from datetime import datetime

from argus.backend.plugins.sct.udt import PackageVersion
from argus.backend.service.results_service import (
    get_sorted_data_for_column_and_row,
    get_min_max_y,
    coerce_values_to_axis_boundaries,
    create_chart_options,
    create_datasets_for_column,
    create_release_datasets,
    create_limit_dataset,
    calculate_limits,
    calculate_graph_ticks, _identify_most_changed_package, _split_results_by_release,
    BestResult, RunsDetails
)
from argus.backend.models.result import ArgusGenericResultMetadata, ArgusGenericResultData, ColumnMetadata, ValidationRules


@pytest.fixture
def package_data():
    return [
        PackageVersion(name='scylla-server', version='2024.3.0~dev',
                       date='20241018', revision_id='c3e2bc', build_id='b974e8'),
        PackageVersion(name='scylla-manager-server', version='3.2.8', date='20240517', revision_id='', build_id='')
    ]


def test_identify_main_package_should_return_most_frequent_package(package_data):
    packages_list = package_data * 5 + \
        [PackageVersion(name='java-driver', version='3.11.5.3', date='null', revision_id='', build_id='')]
    main_package = _identify_most_changed_package(packages_list)
    assert main_package == 'scylla-server'


def test_split_results_by_versions_should_group_correctly(package_data):
    packages = {
        str(uuid4()): package_data,
        str(uuid4()): [
            PackageVersion(name='scylla-server', version='2024.2.0~dev', date='20241018', revision_id='c3e2bc', build_id='b974e8')],
        str(uuid4()): [PackageVersion(name='scylla-server', version='2024.2.0', date='20241018', revision_id='', build_id='')]
    }
    main_package = 'scylla-server'
    versions_map = _split_results_by_release(packages, main_package)
    print(versions_map)
    assert len(versions_map) == 2
    assert '2024.2' in versions_map
    assert 'dev' in versions_map


def test_get_sorted_data_for_column_and_row():
    run_id1 = uuid4()
    run_id2 = uuid4()
    run_id3 = uuid4()
    data = [
        ArgusGenericResultData(run_id=run_id2, column="col1", row="row1", value=1.5, status="PASS",
                               sut_timestamp=datetime(2023, 10, 23)),
        ArgusGenericResultData(run_id=run_id3, column="col1", row="row1", value=2.5, status="PASS",
                               sut_timestamp=datetime(2023, 10, 24)),
        ArgusGenericResultData(run_id=run_id1, column="col1", row="row1", value=0.5, status="PASS",
                               sut_timestamp=datetime(2023, 10, 22)),
    ]
    packages = {
        run_id1: [PackageVersion(name='pkg1', version='1.0', date='', revision_id='', build_id='')],
        run_id2: [PackageVersion(name='pkg1', version='1.1', date='', revision_id='', build_id=''),
                  PackageVersion(name='pkg2', version='1.0', date='', revision_id='', build_id='')],
        run_id3: [PackageVersion(name='pkg1', version='1.1', date='', revision_id='', build_id=''),
                  PackageVersion(name='pkg2', version='1.1', date='20241111', revision_id='', build_id='')],
    }
    runs_details = RunsDetails(ignored=[], packages=packages)
    result = get_sorted_data_for_column_and_row(data, "col1", "row1", runs_details, main_package="pkg1")
    expected = [
        {"x": "2023-10-22T00:00:00Z", "y": 0.5, "changes": ["pkg1: 1.0"]},
        {"x": "2023-10-23T00:00:00Z", "y": 1.5, "changes": ["pkg1: 1.1", "pkg2: None -> 1.0"]},
        {"x": "2023-10-24T00:00:00Z", "y": 2.5, "changes": ['pkg1: 1.1', "pkg2: 1.0 -> 1.1 (20241111)"]},
    ]
    result_data = [{"x": item["x"], "y": item["y"], "changes": item["changes"]} for item in result]
    assert result_data == expected


def test_get_min_max_y():
    datasets = [
        {
            "data": [
                {"x": "2023-10-20T00:00:00Z", "y": 1.0},
                {"x": "2023-10-21T00:00:00Z", "y": 2.0},
                {"x": "2023-10-25T00:00:00Z", "y": 3.4},
                {"x": "2023-10-26T00:00:00Z", "y": 3.9},
                {"x": "2023-10-26T00:00:00Z", "y": 4.0},
                {"x": "2023-10-27T00:00:00Z", "y": 100.0},
            ]
        }
    ]
    min_y, max_y = get_min_max_y(datasets)
    assert min_y == 1
    assert max_y == 6


def test_coerce_values_to_axis_boundries():
    datasets = [
        {
            "data": [
                {"x": "2023-10-22T00:00:00Z", "y": 1.0},
                {"x": "2023-10-23T00:00:00Z", "y": 2.0},
                {"x": "2023-10-24T00:00:00Z", "y": 3.0},
                {"x": "2023-10-25T00:00:00Z", "y": 4.0},
                {"x": "2023-10-26T00:00:00Z", "y": 100.0},
                {"x": "2023-10-21T00:00:00Z", "y": -50.0},
            ]
        }
    ]
    min_y = 0
    max_y = 6
    coerce_values_to_axis_boundaries(datasets, min_y, max_y)
    data = datasets[0]["data"]
    assert data[0]["y"] == 1.0
    assert data[4]["y"] == 6
    assert data[4]["ori"] == 100.0
    assert data[5]["y"] == 0
    assert data[5]["ori"] == -50.0


def test_create_chart_options():
    table = ArgusGenericResultMetadata(name="Test Table", description="Test Description",
                                       columns_meta=[ColumnMetadata(name="col1", unit="ms",
                                                                    type="NUMBER", higher_is_better=True)],
                                       rows_meta=["row1"], validation_rules={})
    column = table.columns_meta[0]
    options = create_chart_options(table, column, min_y=0, max_y=10)
    assert options["plugins"]["title"]["text"] == "Test Table - col1"
    assert options["scales"]["y"]["title"]["text"] == "[ms]"
    assert options["scales"]["y"]["min"] == 0
    assert options["scales"]["y"]["max"] == 10


def test_create_datasets_for_column():
    table = ArgusGenericResultMetadata(
        name="Test Table",
        description="Test Description",
        columns_meta=[ColumnMetadata(name="col1", unit="ms", type="NUMBER", higher_is_better=True)],
        rows_meta=["row1", "row2"],
        validation_rules={}
    )
    data = [
        ArgusGenericResultData(run_id=uuid4(), column="col1", row="row1", value=1.5,
                               status="PASS", sut_timestamp=datetime(2023, 10, 23)),
        ArgusGenericResultData(run_id=uuid4(), column="col1", row="row1", value=2.5,
                               status="PASS", sut_timestamp=datetime(2023, 10, 24)),
        ArgusGenericResultData(run_id=uuid4(), column="col1", row="row2", value=3.5,
                               status="PASS", sut_timestamp=datetime(2023, 10, 25)),
    ]
    best_results = {}
    releases_map = {"2024.2": [point.run_id for point in data][:1], "2024.3": [point.run_id for point in data][2:]}
    column = table.columns_meta[0]
    runs_details = RunsDetails(ignored=[], packages={})
    datasets = create_datasets_for_column(table, data, best_results, releases_map,
                                          column, runs_details, main_package="pkg1")
    assert len(datasets) == 2
    labels = [dataset["label"] for dataset in datasets]
    assert "2024.2 - row1" in labels
    assert "2024.3 - row2" in labels


def test_create_release_datasets():
    points = [
        {"x": "2023-10-23T00:00:00Z", "y": 1.5, "id": "run1"},
        {"x": "2023-10-24T00:00:00Z", "y": 2.5, "id": "run2"},
        {"x": "2023-10-25T00:00:00Z", "y": 3.5, "id": "run3"},
    ]
    row = "row1"
    releases_map = {"2024.2": ["run1", "run2"], "2024.3": ["run3"]}
    line_color = 'rgba(255, 0, 0, 1.0)'
    datasets = create_release_datasets(points, row, releases_map, line_color)
    assert len(datasets) == 2
    assert datasets[0]["label"] == "2024.2 - row1"
    assert datasets[1]["label"] == "2024.3 - row1"


def test_create_limit_dataset():
    points = [
        {"x": "2023-10-23T00:00:00Z", "y": 1.5, "id": "run1"},
        {"x": "2023-10-24T00:00:00Z", "y": 2.5, "id": "run2"},
        {"x": "2023-10-25T00:00:00Z", "y": 3.5, "id": "run3"},
    ]
    column = ColumnMetadata(name="col1", unit="ms", type="NUMBER", higher_is_better=True)
    row = "row1"
    best_results = {
        "col1:row1": [BestResult(key="col1:row1", value=2.0, result_date=datetime(2023, 10, 24), run_id="run2")]
    }
    table = ArgusGenericResultMetadata(name="Test Table", description="Test Description",
                                       columns_meta=[column], rows_meta=[row], validation_rules={
                                           "col1": [{"fixed_limit": 1.8, "best_pct": 10, "best_abs": 0.2, "valid_from": datetime(2023, 10, 23)}]
                                       })
    line_color = 'rgba(255, 0, 0, 1.0)'
    is_fixed_limit_drawn = False
    limit_dataset = create_limit_dataset(points, column, row, best_results, table, line_color, is_fixed_limit_drawn)
    assert limit_dataset is not None
    assert limit_dataset["label"] == "error threshold"
    assert limit_dataset["data"]


def test_calculate_limits():
    points = [
        {"x": "2023-10-23T00:00:00Z", "y": 1.5},
        {"x": "2023-10-24T00:00:00Z", "y": 2.5},
        {"x": "2023-10-25T00:00:00Z", "y": 3.5},
    ]
    best_results = [BestResult(key="col1:row1", value=2.0, result_date=datetime(2023, 10, 24), run_id="run2")]
    validation_rules_list = [ValidationRules(valid_from=datetime(
        2023, 10, 23), best_pct=10, best_abs=0.2, fixed_limit=1.8)]
    higher_is_better = True
    updated_points = calculate_limits(points, best_results, validation_rules_list, higher_is_better)
    for point in updated_points:
        assert 'limit' in point


def test_calculate_graph_ticks_with_data_returns_min_max_ticks():
    graphs = [
        {
            "data": {
                "datasets": [
                    {"data": [{"x": "2023-10-22T00:00:00Z", "y": 1.0}, {"x": "2023-10-23T00:00:00Z", "y": 2.0}]}
                ]
            }
        },
        {
            "data": {
                "datasets": [
                    {"data": [{"x": "2023-10-24T00:00:00Z", "y": 3.0}, {"x": "2023-10-25T00:00:00Z", "y": 4.0}]}
                ]
            }
        }
    ]
    ticks = calculate_graph_ticks(graphs)
    assert ticks["min"] == "2023-10-22"
    assert ticks["max"] == "2023-10-25"


def test_calculate_graph_ticks_without_data_does_not_fail():
    graphs = [
        {
            "data": {
                "datasets": [
                    {"data": []}
                ]
            }
        },
        {
            "data": {
                "datasets": [
                    {"data": []}
                ]
            }
        }
    ]
    ticks = calculate_graph_ticks(graphs)
    assert ticks == {}
