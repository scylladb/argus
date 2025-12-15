from dataclasses import asdict
from datetime import datetime, UTC
import json
import logging
from time import sleep

from flask.testing import FlaskClient
import pytest

from argus.backend.models.web import ArgusRelease, ArgusGroup, ArgusTest
from argus.backend.service.issue_service import IssueService
from argus.backend.plugins.sct.testrun import SCTEventSeverity, SCTTestRun
from argus.backend.service.client_service import ClientService
from argus.backend.plugins.sct.service import SCTService
from argus.backend.service.testrun import TestRunService
from argus.backend.tests.conftest import get_fake_test_run
from argus.backend.util.encoders import ArgusJSONEncoder
from argus.common.sct_types import RawEventPayload

LOGGER = logging.getLogger(__name__)


@pytest.mark.skip("Github Mock is not available")
def test_submit_github_issue(client_service: ClientService, sct_service: SCTService, testrun_service: TestRunService, fake_test: ArgusTest, issue_service: IssueService):
    run_type, run_req = get_fake_test_run(fake_test)
    client_service.submit_run(run_type, asdict(run_req))
    run: SCTTestRun = testrun_service.get_run(run_type, run_req.run_id)

    result = issue_service.submit(issue_url="https://github.com/scylladb/argus/issues/1", test_id=run.test_id, run_id=run.id)

    assert result["title"] == "Drop PyYAML as a dependency"


@pytest.mark.skip("Jira Mock is not available")
def test_submit_jira_issue(client_service: ClientService, sct_service: SCTService, testrun_service: TestRunService, fake_test: ArgusTest, issue_service: IssueService):
    run_type, run_req = get_fake_test_run(fake_test)
    client_service.submit_run(run_type, asdict(run_req))
    run: SCTTestRun = testrun_service.get_run(run_type, run_req.run_id)

    result = issue_service.submit(issue_url="https://scylladb.atlassian.net/browse/SCYLLADB-1", test_id=run.test_id, run_id=run.id)

    assert result["summary"] == "Change the default compression setting to dict"
