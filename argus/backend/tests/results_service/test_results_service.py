from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from argus.backend.models.result import ArgusGenericResultMetadata, ArgusGenericResultData, ColumnMetadata, ArgusGraphView
from argus.backend.plugins.sct.testrun import SCTTestRun
from argus.backend.plugins.sct.udt import PackageVersion
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


def test_get_tests_by_version_groups_runs_correctly(argus_db):
    test_id1 = uuid4()
    test_id2 = uuid4()
    run_id1 = uuid4()
    run_id2 = uuid4()
    run_id3 = uuid4()
    run_id4 = uuid4()
    pkg_v4_0 = PackageVersion(name='scylla', version='4.0', date='2021-01-01', revision_id='', build_id='')
    pkg_v4_1 = PackageVersion(name='scylla', version='4.1', date='2021-02-01', revision_id='', build_id='')

    SCTTestRun(
        id=run_id1,
        build_id='build_id1',
        test_id=test_id1,
        test_method='test_method1',  # Changed to 'test_method'
        investigation_status='',
        packages=[pkg_v4_0]
    ).save()
    SCTTestRun(
        id=run_id2,
        build_id='build_id1',
        test_id=test_id1,
        test_method='test_method2',  # Changed to 'test_method'
        investigation_status='ignored',
        packages=[pkg_v4_0]
    ).save()
    SCTTestRun(
        id=run_id3,
        build_id='build_id1',
        test_id=test_id2,
        test_method='test_method1',  # Changed to 'test_method'
        investigation_status='',
        packages=[pkg_v4_0]
    ).save()
    SCTTestRun(
        id=run_id4,
        build_id='build_id1',
        test_id=test_id2,
        test_method='test_method1',  # Changed to 'test_method'
        investigation_status='',
        packages=[pkg_v4_1]
    ).save()

    sut_package_name = 'scylla'
    test_ids = [test_id1, test_id2]
    service = ResultsService()
    service._exclude_disabled_tests = lambda x: x
    result = service.get_tests_by_version(sut_package_name, test_ids)

    expected_result = {'test_info': {str(test_id1): {'build_id': 'build_id1',
                                                     'name': None},
                                     str(test_id2): {'build_id': 'build_id1',
                                                     'name': None}},
                       'versions': {'4.0-2021-01-01-': {
                           str(test_id1): {'test_method1': {'run_id': str(run_id1),
                                                            'started_by': None,
                                                            'status': 'created'}},
                           str(test_id2): {'test_method1': {'run_id': str(run_id3),
                                                            'started_by': None,
                                                            'status': 'created'}}},
                           '4.1-2021-02-01-': {str(test_id2): {
                               'test_method1': {'run_id': str(run_id4),
                                                'started_by': None,
                                                'status': 'created'}}}}}
    assert result == expected_result


def test_create_update_argus_graph_view_should_create() -> None:
    service = ResultsService()
    test_id = uuid4()
    service.create_argus_graph_view(test_id, "MyView", "MyDescription")
    result = service.get_argus_graph_views(test_id)[0]
    assert result is not None
    assert result.name == "MyView"
    assert result.description == "MyDescription"
    assert result.graphs == {}


def test_create_update_argus_graph_view_should_update() -> None:
    service = ResultsService()
    test_id = uuid4()
    graph_view = service.create_argus_graph_view(test_id, "OldName", "OldDesc")
    service.update_argus_graph_view(test_id, graph_view.id, "NewName", "NewDesc", {"graph2": "new_data"})
    updated = service.get_argus_graph_views(test_id)[0]
    assert updated.name == "NewName"
    assert updated.description == "NewDesc"
    assert updated.graphs == {"graph2": "new_data"}


def test_get_argus_graph_views_should_return_list() -> None:
    service = ResultsService()
    test_id = uuid4()
    service.create_argus_graph_view(test_id, "View1", "Desc1")
    service.create_argus_graph_view(test_id, "View2", "Desc2")
    views = service.get_argus_graph_views(test_id)
    assert len(views) == 2
