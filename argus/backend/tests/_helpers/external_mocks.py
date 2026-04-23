"""External-service mock fixtures for controller integration tests.

These fixtures patch the highest stable boundary per integration so tests
exercise real controller + Flask plumbing while never touching the network.

Usage::

    def test_something(flask_client, mock_issue_service):
        mock_issue_service.return_value.submit.return_value = {"id": "abc"}
        flask_client.post("/api/v1/issues/submit", json={...})
        mock_issue_service.return_value.submit.assert_called_once()
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# IssueService (covers PyGithub + Jira together)
# ---------------------------------------------------------------------------
# Patched at every controller import site so the underlying GithubService and
# JiraService constructors (and their HTTP clients) never run.

_ISSUE_SERVICE_PATCH_TARGETS = (
    "argus.backend.controller.testrun_api.IssueService",
)


@pytest.fixture
def mock_issue_service():
    """Replace ``IssueService`` in controller modules with a MagicMock.

    Yields the patched class mock. ``mock.return_value`` is the per-call
    instance used by the controller; configure ``submit``/``get``/``delete``
    on ``mock.return_value`` as needed.
    """
    instance = MagicMock(name="IssueServiceInstance")
    # Sensible defaults so tests that don't customize still get JSON-serializable
    # responses.
    instance.submit.return_value = {"id": "00000000-0000-0000-0000-000000000000"}
    instance.submit_for_sct_event.return_value = {"id": "00000000-0000-0000-0000-000000000000"}
    instance.get.return_value = []
    instance.delete.return_value = True

    patchers = [patch(target, return_value=instance) for target in _ISSUE_SERVICE_PATCH_TARGETS]
    mocks = [p.start() for p in patchers]
    try:
        # Return the first mock; ``.return_value`` is shared across all targets
        # because we passed the same instance.
        yield mocks[0]
    finally:
        for p in patchers:
            p.stop()


# ---------------------------------------------------------------------------
# UserService.github_callback  (OAuth login)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_github_callback():
    """Patch ``UserService.github_callback`` to return canned ``first_run_info``.

    Default return is ``None`` (existing user, no first-run banner). Override
    via ``mock_github_callback.return_value = {...}``.
    """
    with patch("argus.backend.service.user.UserService.github_callback") as m:
        m.return_value = None
        yield m


# ---------------------------------------------------------------------------
# JenkinsService (testrun_api Jenkins routes + planner trigger)
# ---------------------------------------------------------------------------

_JENKINS_PATCH_TARGETS = (
    "argus.backend.controller.testrun_api.JenkinsService",
    "argus.backend.service.planner_service.JenkinsService",
)


@pytest.fixture
def mock_jenkins_service():
    """Replace ``JenkinsService`` at every import site with a MagicMock.

    Default return values mirror the typical happy-path responses so tests can
    customize only the bits they care about.
    """
    instance = MagicMock(name="JenkinsServiceInstance")
    instance.retrieve_job_parameters.return_value = []
    instance.build_job.return_value = 12345  # queue item id
    instance.get_queue_info.return_value = {"why": None, "url": "http://jenkins.test/job/1/"}
    instance.latest_build.return_value = {"number": 1}
    instance.get_advanced_settings.return_value = {}
    instance.clone_job.return_value = "cloned/job/path"
    instance.verify_job_settings.return_value = True
    instance.get_clone_targets.return_value = []
    instance.get_clone_groups.return_value = []
    instance.change_advanced_settings.return_value = True

    patchers = [patch(target, return_value=instance) for target in _JENKINS_PATCH_TARGETS]
    mocks = [p.start() for p in patchers]
    try:
        yield mocks[0]
    finally:
        for p in patchers:
            p.stop()


# ---------------------------------------------------------------------------
# TestRunService S3 methods (log/screenshot proxies)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_s3():
    """Patch ``TestRunService`` S3-touching methods to avoid real AWS calls.

    Returns a ``SimpleNamespace`` with attributes for each patched method so
    tests can inspect call arguments / customize return values.
    """
    with (
        patch("argus.backend.service.testrun.TestRunService.get_log") as get_log,
        patch("argus.backend.service.testrun.TestRunService.proxy_stored_s3_image") as proxy_img,
        patch("argus.backend.service.testrun.TestRunService.resolve_artifact_size") as resolve_size,
        patch("argus.backend.service.testrun.TestRunService.proxy_s3_file") as proxy_file,
    ):
        get_log.return_value = "https://test-bucket.s3.amazonaws.com/log/example.log?signed"
        proxy_img.return_value = "https://test-bucket.s3.amazonaws.com/screenshots/example.png?signed"
        resolve_size.return_value = 1024
        proxy_file.return_value = b"fake-s3-content"
        yield SimpleNamespace(
            get_log=get_log,
            proxy_stored_s3_image=proxy_img,
            resolve_artifact_size=resolve_size,
            proxy_s3_file=proxy_file,
        )


# ---------------------------------------------------------------------------
# Cloudflare Access JWT
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_cf_access_payload():
    """Patch ``_get_cf_access_payload`` to return a fabricated JWT payload.

    Default email is ``"tester@scylladb.com"`` (passes the @scylladb.com gate).
    Override via ``mock_cf_access_payload.return_value = {"email": "..."}``.
    """
    with patch("argus.backend.service.user._get_cf_access_payload") as m:
        m.return_value = {"email": "tester@scylladb.com"}
        yield m
