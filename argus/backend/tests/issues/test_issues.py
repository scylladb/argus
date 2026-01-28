from dataclasses import asdict
from datetime import datetime, UTC
import json
import logging
from time import sleep
from uuid import uuid4

from flask.testing import FlaskClient
import pytest

from argus.backend.models.github_issue import GithubIssue
from argus.backend.models.jira import JiraIssue
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


def test_submit_github_issue_link_for_existing_issue(client_service: ClientService, sct_service: SCTService, testrun_service: TestRunService, fake_test: ArgusTest, issue_service: IssueService):
    run_type, run_req = get_fake_test_run(fake_test)
    client_service.submit_run(run_type, asdict(run_req))
    run: SCTTestRun = testrun_service.get_run(run_type, run_req.run_id)
    i = GithubIssue()
    uid = uuid4()
    i.user_id = uid
    i.type = "issues"
    i.owner = "scylladb"
    i.repo = "argus"
    i.number = 1
    i.state = "open"
    i.title = "Example Issue"
    i.url = "https://github.com/scylladb/argus/issues/1"
    i.save()

    result = issue_service.submit(issue_url="https://github.com/scylladb/argus/issues/1", test_id=run.test_id, run_id=run.id)

    assert result["title"] == "Example Issue"

    issue_with_links = issue_service.get("run_id", run.id, True)
    assert len(issue_with_links) == 1
    assert len(issue_with_links[0]["links"]) == 1


def test_submit_jira_issue_link_for_existing_issue(client_service: ClientService, sct_service: SCTService, testrun_service: TestRunService, fake_test: ArgusTest, issue_service: IssueService):
    run_type, run_req = get_fake_test_run(fake_test)
    client_service.submit_run(run_type, asdict(run_req))
    run: SCTTestRun = testrun_service.get_run(run_type, run_req.run_id)
    i = JiraIssue()
    uid = uuid4()
    i.user_id = uid
    i.key = "SCYLLADB-1"
    i.state = "todo"
    i.summary = "Example Issue"
    i.project = "SCYLLADB"
    i.permalink = "https://scylladb.atlassian.net/browse/SCYLLADB-1"
    i.save()

    result = issue_service.submit(issue_url="https://scylladb.atlassian.net/browse/SCYLLADB-1", test_id=run.test_id, run_id=run.id)

    assert result["summary"] == "Example Issue"

    issue_with_links = issue_service.get("run_id", run.id, True)
    assert len(issue_with_links) == 1
    assert len(issue_with_links[0]["links"]) == 1
