import logging
import click
from flask import Blueprint, current_app
from flask.cli import with_appcontext
from cassandra.cqlengine.management import sync_table, sync_type
from argus.backend.db import ScyllaCluster
from argus.backend.plugins.loader import all_plugin_models, all_plugin_types
from argus.backend.service.build_system_monitor import JenkinsMonitor
from argus.backend.service.github_service import GithubService
from argus.backend.service.jira_service import JiraService

cli_bp = Blueprint("cli", __name__)
LOGGER = logging.getLogger(__name__)


@cli_bp.cli.add_command
@click.command('sync-models')
@with_appcontext
def sync_models_command():
    sync_models(current_app.config["SCYLLA_KEYSPACE_NAME"])


def sync_models(ks: str = None):
    cluster = ScyllaCluster.get()
    cluster.sync_core_tables()
    LOGGER.info("Synchronizing plugin types...")
    for user_type in all_plugin_types():
        LOGGER.info("Synchronizing plugin type %s...", user_type.__name__)
        ks = getattr(user_type, "__keyspace__" , ks)
        sync_type(ks_name=ks, type_model=user_type)
    LOGGER.info("Synchronizing plugin models...")
    for model in all_plugin_models(True):
        LOGGER.info("Synchronizing plugin model %s...", model.__name__)
        ks = getattr(model, "__keyspace__" , ks)
        sync_table(model=model, keyspaces=[ks])

    LOGGER.info("Plugins ready.")
    cluster.sync_additional_schema()
    click.echo("All models synchronized.")


def refresh_issues():
    ScyllaCluster.get()
    gh = GithubService()
    j = JiraService()
    gh.refresh_stale_issues()
    j.refresh_stale_issues()


@cli_bp.cli.add_command
@click.command('refresh-issues')
@with_appcontext
def refresh_issues_command():
    refresh_issues()


@cli_bp.cli.add_command
@click.command('scan-jenkins')
@with_appcontext
def scan_jenkins_command():
    monitor = JenkinsMonitor()
    monitor.collect()
    click.echo("Done.")
