import pytest

from argus.client.base import ArgusClientError

from argus.client.generic.cli import cli as generic_cli
from argus.client.driver_matrix_tests.cli import cli as driver_matrix_cli

def test_driver_matrix_submit_run(requests_mock):
    requests_mock.post(
        "https://argus.scylladb.com/api/v1/client/testrun/driver-matrix-tests/submit",
        json={"status": "ok"},
        status_code=200
    )
    ctx = driver_matrix_cli.make_context(info_name="cli", args=['submit-run',
                                                            '--api-key', '1234',
                                                            '--id', '1234',
                                                            '--build-id', 'scylla-master/group/job',
                                                            '--build-url', 'https://jenkins.com'])
    with ctx:
        driver_matrix_cli.invoke(ctx)

def test_driver_matrix_submit_driver(tmp_path, requests_mock):
    requests_mock.post(
        "https://argus.scylladb.com/api/v1/client/driver_matrix/result/submit",
        json={"status": "ok"},
        status_code=200
    )
    metadata_path = tmp_path / 'metadata.json'
    metadata_path.write_text('{"driver_name": "test-driver", "driver_type": "test-type", "junit_result": "result.xml"}', encoding='utf-8')

    results_path = tmp_path / 'result.xml'
    results_path.write_text('<testsuite><testcase name="test_case"/></testsuite>', encoding='utf-8')
    ctx = driver_matrix_cli.make_context(info_name="cli", args=['submit-driver',
                                                             '--api-key', '1234',
                                                             '--id', '1234',
                                                             '--metadata-path', metadata_path])
    with ctx:
        driver_matrix_cli.invoke(ctx)

def test_driver_matrix_finish_run(requests_mock):
    requests_mock.post(
        "https://argus.scylladb.com/api/v1/client/testrun/driver-matrix-tests/1234/finalize",
        json={"status": "ok"},
        status_code=200
    )
    ctx = driver_matrix_cli.make_context(info_name="cli", args=['finish-run',
                                                            '--api-key', '1234',
                                                            '--id', '1234',
                                                            '--status', 'passed'])
    with ctx:
        driver_matrix_cli.invoke(ctx)
