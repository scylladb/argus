from unittest.mock import patch

import pytest

from argus.backend.service.health.checks import NginxHealthCheck
from argus.backend.service.health.runner import build_runner

FULL_CONFIG = {
    "SCYLLA_CONTACT_POINTS": ["127.0.0.1"],
    "AWS_CLIENT_ID": "id",
    "AWS_CLIENT_SECRET": "secret",
    "S3_ALLOWED_BUCKETS": ["argus-logs", "argus-images"],
    "JENKINS_URL": "https://jenkins.test",
    "JENKINS_USER": "tester",
    "JENKINS_API_TOKEN": "jenkins-token",
    "GITHUB_ENABLED": True,
    "GITHUB_ACCESS_TOKEN": "github-token",
    "JIRA_ENABLED": True,
    "JIRA_SERVER": "https://jira.test",
    "JIRA_EMAIL": "tester@scylladb.com",
    "JIRA_TOKEN": "jira-token",
}


def registered(config) -> dict[str, str]:
    snapshot = build_runner(config).snapshot()
    assert snapshot.service == "argus"
    return {check.name: str(check.severity) for check in snapshot.checks}


def test_full_config_registers_every_dependency():
    assert registered(FULL_CONFIG) == {
        "scylla": "critical",
        "nginx": "important",
        "ssh_key_lookup": "important",
        "s3:argus-logs": "important",
        "s3:argus-images": "important",
        "jenkins_api": "important",
        "github_api": "important",
        "jira_api": "important",
    }


def test_config_without_integrations_registers_the_local_checks():
    config = {
        "SCYLLA_CONTACT_POINTS": ["127.0.0.1"],
        "GITHUB_ENABLED": False,
        "JIRA_ENABLED": False,
    }
    assert set(registered(config)) == {"scylla", "nginx", "ssh_key_lookup"}


def test_enabled_integration_without_credentials_is_not_registered():
    config = dict(FULL_CONFIG, GITHUB_ACCESS_TOKEN="", JIRA_SERVER="", JENKINS_URL="")
    assert not {"github_api", "jira_api", "jenkins_api"} & set(registered(config))


@pytest.mark.parametrize(
    ("config", "url"),
    [
        ({}, "http://127.0.0.1/s/argus.png"),
        ({"HEALTH_NGINX_URL": "http://127.0.0.1:8000/s/argus.png"}, "http://127.0.0.1:8000/s/argus.png"),
    ],
)
def test_nginx_check_probes_the_configured_url(config, url):
    with patch("argus.backend.service.health.runner.NginxHealthCheck", wraps=NginxHealthCheck) as nginx:
        build_runner(config)
    nginx.assert_called_once_with(url)
