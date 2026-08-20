"""Argus maintenance commands.

Run from the repository root:

    uv run python -m argus.backend.cli sync-models
    uv run python -m argus.backend.cli refresh-issues
    uv run python -m argus.backend.cli scan-jenkins
"""
import logging

import click

from argus.backend.db import ScyllaCluster
from argus.backend.plugins.loader import all_plugin_models, all_plugin_types
from argus.backend.service.build_system_monitor import JenkinsMonitor
from argus.backend.service.github_service import GithubService
from argus.backend.service.jira_service import JiraService
from argus.backend.util.config import Config
from argus.backend.util.logsetup import setup_application_logging

LOGGER = logging.getLogger(__name__)


@click.group()
def cli():
    config = Config.load_yaml_config()
    setup_application_logging(log_level=config["APP_LOG_LEVEL"])
    ScyllaCluster.get(config)


@cli.command("sync-models")
def sync_models_command():
    main_ks = ScyllaCluster.get().config["SCYLLA_KEYSPACE_NAME"]
    sync_models(main_ks)


def sync_models(main_ks: str):
    cluster = ScyllaCluster.get()
    cluster.sync_core_tables()
    LOGGER.info("Synchronizing plugin types...")
    for user_type in all_plugin_types():
        LOGGER.info("Synchronizing plugin type %s...", user_type.__name__)
        user_type.sync_type()
    cluster.register_coodie_udts()
    LOGGER.info("Synchronizing plugin models...")
    for model in all_plugin_models(True):
        LOGGER.info("Synchronizing plugin model %s...", model.__name__)
        model.sync_table()

    LOGGER.info("Plugins ready.")
    cluster.sync_additional_schema()
    click.echo("All models synchronized.")


def refresh_issues():
    ScyllaCluster.get()
    gh = GithubService()
    j = JiraService()
    gh.refresh_stale_issues()
    j.refresh_stale_issues()


@cli.command("refresh-issues")
def refresh_issues_command():
    refresh_issues()


@cli.command("scan-jenkins")
def scan_jenkins_command():
    monitor = JenkinsMonitor()
    monitor.collect()
    click.echo("Done.")


if __name__ == "__main__":
    cli()
