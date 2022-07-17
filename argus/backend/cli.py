import click
from flask import Blueprint
from flask.cli import with_appcontext
from argus.backend.db import ScyllaCluster
from argus.backend.service.build_system_monitor import JenkinsMonitor

cli_bp = Blueprint("cli", __name__)


@cli_bp.cli.add_command
@click.command('sync-models')
@with_appcontext
def sync_models_command():
    cluster = ScyllaCluster.get()
    cluster.sync_models()
    click.echo("Models synchronized.")


@cli_bp.cli.add_command
@click.command('scan-jenkins')
@with_appcontext
def scan_jenkins_command():
    monitor = JenkinsMonitor()
    monitor.collect()
    click.echo("Done.")
