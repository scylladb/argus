import logging
import click
from flask import Blueprint
from flask.cli import with_appcontext
from cassandra.cqlengine.management import sync_table, sync_type
from argus.backend.db import ScyllaCluster
from argus.backend.plugins.loader import all_plugin_models, all_plugin_types
from argus.backend.service.build_system_monitor import JenkinsMonitor

cli_bp = Blueprint("cli", __name__)
LOGGER = logging.getLogger(__name__)


@cli_bp.cli.add_command
@click.command('sync-models')
@with_appcontext
def sync_models_command():
    cluster = ScyllaCluster.get()
    cluster.sync_core_tables()
    LOGGER.info("Synchronizing plugin types...")
    for user_type in all_plugin_types():
        LOGGER.info("Synchronizing plugin type %s...", user_type.__name__)
        sync_type(ks_name=cluster.config["SCYLLA_KEYSPACE_NAME"], type_model=user_type)
    LOGGER.info("Synchronizing plugin models...")
    for model in all_plugin_models(True):
        LOGGER.info("Synchronizing plugin model %s...", model.__name__)
        sync_table(model=model, keyspaces=[cluster.config["SCYLLA_KEYSPACE_NAME"]])

    LOGGER.info("Plugins ready.")
    click.echo("All models synchronized.")


@cli_bp.cli.add_command
@click.command('scan-jenkins')
@with_appcontext
def scan_jenkins_command():
    monitor = JenkinsMonitor()
    monitor.collect()
    click.echo("Done.")
