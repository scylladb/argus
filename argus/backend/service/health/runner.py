"""Build the health runner from the Argus web configuration."""

from importlib.metadata import PackageNotFoundError, version
from typing import Any

from qatools_health import HealthCheckRunner
from qatools_health.checks import GitHubApiHealthCheck, JenkinsApiHealthCheck, JiraApiHealthCheck

from argus.backend.service.health.checks import (
    NGINX_PROBE_URL,
    ArgusDatabase,
    NginxHealthCheck,
    S3BucketHealthCheck,
    ScyllaHealthCheck,
    SshKeyLookupHealthCheck,
)

SERVICE_NAME = "argus"


def argus_version() -> str:
    """Return the installed argus-alm version, or an empty string outside an install."""
    try:
        return version("argus-alm")
    except PackageNotFoundError:
        return ""


def build_runner(config: dict[str, Any]) -> HealthCheckRunner:
    """Register one check for each dependency the configuration names.

    ScyllaDB, nginx and the SSH key lookup are always registered. S3 gets one
    check per allowed bucket. Jenkins, GitHub and Jira are registered only
    when the configuration enables them and holds their credentials, so a
    missing integration has no series.
    """
    runner = HealthCheckRunner(service=SERVICE_NAME, version=argus_version())
    database = ArgusDatabase(config)

    runner.register(ScyllaHealthCheck(database))
    runner.register(NginxHealthCheck(config.get("HEALTH_NGINX_URL") or NGINX_PROBE_URL))
    runner.register(SshKeyLookupHealthCheck(database))

    for bucket in config.get("S3_ALLOWED_BUCKETS") or []:
        runner.register(
            S3BucketHealthCheck(
                bucket,
                access_key_id=config.get("AWS_CLIENT_ID"),
                secret_access_key=config.get("AWS_CLIENT_SECRET"),
            )
        )

    if config.get("JENKINS_URL"):
        runner.register(
            JenkinsApiHealthCheck(config["JENKINS_URL"], config.get("JENKINS_USER"), config.get("JENKINS_API_TOKEN"))
        )

    if config.get("GITHUB_ENABLED", True) and config.get("GITHUB_ACCESS_TOKEN"):
        runner.register(GitHubApiHealthCheck(config["GITHUB_ACCESS_TOKEN"]))

    if config.get("JIRA_ENABLED", True) and config.get("JIRA_SERVER"):
        runner.register(
            JiraApiHealthCheck(config["JIRA_SERVER"], config.get("JIRA_EMAIL"), config.get("JIRA_TOKEN"))
        )

    return runner
