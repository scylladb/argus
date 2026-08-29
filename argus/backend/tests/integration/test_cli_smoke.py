"""Smoke tests for the shipped console scripts against the live server.

These exercise the exact entrypoints CI jobs call (``argus-client-generic``,
``argus-driver-matrix-client``), end to end: click parsing, client
construction, HTTP, and the response contract.
"""

import json
import logging
import uuid
from contextlib import contextmanager

import pytest
from click.testing import CliRunner

from argus.client.driver_matrix_tests.cli import cli as driver_matrix_cli
from argus.client.generic.cli import cli as generic_cli

pytestmark = pytest.mark.docker_required


@contextmanager
def _logging_disabled():
    """pytest's live logging (log_cli) suspends global capture on every
    record, and the suspension rebinds sys.stdout -- dropping the wrapper
    CliRunner.isolation() installed (click keeps no other reference to it),
    which closes the captured stream mid-invoke. No records may be emitted
    while an invoke is in flight, from any thread.
    """
    logging.disable(logging.CRITICAL)
    try:
        yield
    finally:
        logging.disable(logging.NOTSET)


def _invoke(runner: CliRunner, cli, args: list[str]):
    with _logging_disabled():
        return runner.invoke(cli, args, catch_exceptions=False)


def _common_args(live_server, api_token, tmp_path) -> list[str]:
    return [
        "--api-key", api_token,
        "--base-url", live_server,
        "--log-dir", str(tmp_path),
        "--no-use-tunnel",
    ]


def test_generic_cli_submit_and_finish(live_server, api_token, tmp_path, generic_test):
    runner = CliRunner()
    run_id = str(uuid.uuid4())
    common = _common_args(live_server, api_token, tmp_path)

    result = _invoke(runner, generic_cli, [
        "submit", *common,
        "--id", run_id,
        "--build-id", generic_test.build_system_id,
        "--build-url", "http://example.com/job/3/",
        "--started-by", "e2e_cli_user",
    ])
    assert result.exit_code == 0, result.output

    result = _invoke(runner, generic_cli, [
        "finish", *common,
        "--id", run_id,
        "--status", "passed",
        "--scylla-version", "6.2.0",
    ])
    assert result.exit_code == 0, result.output


def test_generic_cli_trigger_jobs(live_server, api_token, tmp_path, mock_jenkins_service):
    runner = CliRunner()
    job_info = tmp_path / "job_info.json"
    job_info.write_text(json.dumps({"common_params": {}, "params": []}))

    result = _invoke(runner, generic_cli, [
        "trigger-jobs", *_common_args(live_server, api_token, tmp_path),
        "--plan-id", str(uuid.uuid1()),
        "--job-info-file", str(job_info),
    ])
    assert result.exit_code == 0, result.output


def test_driver_matrix_cli_full_flow(live_server, api_token, tmp_path, driver_matrix_test):
    runner = CliRunner()
    run_id = str(uuid.uuid4())
    common = _common_args(live_server, api_token, tmp_path)

    result = _invoke(runner, driver_matrix_cli, [
        "submit-run", *common,
        "--id", run_id,
        "--build-id", driver_matrix_test.build_system_id,
        "--build-url", "http://example.com/job/42/",
    ])
    assert result.exit_code == 0, result.output

    junit = tmp_path / "TEST-cliDriver-1.0.xml"
    junit.write_text(
        '<testsuites timestamp="2026-08-29T00:00:00" time="0.10">'
        '<testsuite name="suite-1" tests="1" failures="0" errors="0" '
        'skipped="0" disabled="0" passed="1" time="0.10">'
        '<testcase name="case-1" classname="cls" time="0.05"/>'
        '</testsuite></testsuites>'
    )
    metadata = tmp_path / "metadata.json"
    metadata.write_text(json.dumps({
        "driver_name": junit.name,
        "driver_type": "cpp",
        "junit_result": junit.name,
    }))
    result = _invoke(runner, driver_matrix_cli, [
        "submit-driver", *common,
        "--id", run_id,
        "--metadata-path", str(metadata),
    ])
    assert result.exit_code == 0, result.output

    result = _invoke(runner, driver_matrix_cli, [
        "finish-run", *common,
        "--id", run_id,
        "--status", "passed",
    ])
    assert result.exit_code == 0, result.output
