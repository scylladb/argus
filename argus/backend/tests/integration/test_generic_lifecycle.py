"""Generic-plugin run lifecycle through the real ArgusGenericClient."""

import uuid

import pytest

from argus.common.enums import TestStatus

pytestmark = pytest.mark.docker_required


def test_generic_lifecycle(generic_client, generic_test):
    run_id = str(uuid.uuid4())

    generic_client.submit_generic_run(
        build_id=generic_test.build_system_id,
        run_id=run_id,
        started_by="e2e_generic_user",
        build_url="http://example.com/job/9/",
        sub_type="pytest",
        # GenericRun only accepts full <version>-<YYYYMMDD>.<commit> strings;
        # anything else is silently ignored.
        scylla_version="6.2.0-20260829.abcdef123",
    )

    # GenericRun.submit_run persists the run as RUNNING right away.
    assert generic_client.get_status(run_type="generic", run_id=run_id) is TestStatus.RUNNING

    run = generic_client.get_run(run_type="generic", run_id=run_id)
    assert str(run["id"]) == run_id
    assert run["build_id"] == generic_test.build_system_id
    assert run["scylla_version"] == "6.2.0"

    generic_client.finalize_generic_run(run_id=run_id, status=TestStatus.PASSED,
                                        scylla_version="6.2.0-20260829.abcdef123")

    assert generic_client.get_status(run_type="generic", run_id=run_id) is TestStatus.PASSED
    run = generic_client.get_run(run_type="generic", run_id=run_id)
    assert run["end_time"] is not None
