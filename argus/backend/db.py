import logging
from typing import Optional
import click
from flask import g, Flask
from flask.cli import with_appcontext
# pylint: disable=no-name-in-module
from cassandra.policies import WhiteListRoundRobinPolicy
from cassandra.cluster import Session
from cassandra import ConsistencyLevel
from cassandra.cluster import ExecutionProfile, EXEC_PROFILE_DEFAULT, Cluster
from cassandra.cluster import PreparedStatement
from cassandra.cqlengine.management import sync_table, sync_type
from cassandra.cqlengine import connection
from cassandra.query import dict_factory
from cassandra.auth import PlainTextAuthProvider

from argus.db.config import FileConfig
from argus.db.models import USED_MODELS, USED_TYPES
from argus.db.interface import ArgusDatabase
from argus.db.testrun import TestRun

DB_CONFIG = FileConfig()
CLUSTER: Cluster | None = None
LOGGER = logging.getLogger(__name__)


class ScyllaCluster:
    # pylint: disable=too-many-instance-attributes
    APP_INSTANCE: Optional['ScyllaCluster'] = None

    def __init__(self, config=None):
        if not config:
            config = FileConfig()
        self.config = config
        self.auth_provider = PlainTextAuthProvider(username=config.username, password=config.password)
        self.lb_policy = WhiteListRoundRobinPolicy(hosts=config.contact_points)
        self.execution_profile = ExecutionProfile(
            load_balancing_policy=self.lb_policy, consistency_level=ConsistencyLevel.QUORUM)
        connection.setup(hosts=config.contact_points, default_keyspace=config.keyspace_name,
                         auth_provider=self.auth_provider,
                         protocol_version=4,
                         execution_profiles={EXEC_PROFILE_DEFAULT: self.execution_profile})
        self.cluster: Cluster = connection.get_cluster(connection='default')
        self.session = self.cluster.connect(keyspace=self.config.keyspace_name)
        self.prepared_statements = {}
        self.argus_interface = ArgusDatabase(config=FileConfig())
        self.read_exec_profile = ExecutionProfile(
            consistency_level=ConsistencyLevel.ONE,
            row_factory=dict_factory,
            load_balancing_policy=self.lb_policy
        )
        self.read_named_tuple_exec_profile = ExecutionProfile(
            consistency_level=ConsistencyLevel.ONE,
            load_balancing_policy=self.lb_policy
        )
        self.cluster.add_execution_profile("read_fast", self.read_exec_profile)
        self.cluster.add_execution_profile("read_fast_named_tuple", self.read_named_tuple_exec_profile)
        TestRun.set_argus(self.argus_interface)

    @classmethod
    def get(cls, config: FileConfig = None) -> 'ScyllaCluster':
        if cls.APP_INSTANCE:
            return cls.APP_INSTANCE

        cls.APP_INSTANCE = cls(config)
        return cls.APP_INSTANCE

    @classmethod
    def shutdown(cls):
        if cls.APP_INSTANCE:
            cls.APP_INSTANCE.cluster.shutdown()
            cls.APP_INSTANCE = None

    def prepare(self, query: str) -> PreparedStatement:
        if not (statement := self.prepared_statements.get(query)):
            LOGGER.info("Unprepared statement %s, preparing...", query)
            statement = self.session.prepare(query=query)
            self.prepared_statements[query] = statement
        return statement

    def sync_models(self):
        for udt in USED_TYPES:
            sync_type(ks_name=self.config.keyspace_name, type_model=udt)
        for model in USED_MODELS:
            sync_table(model)

    def create_session(self) -> Session:
        return self.session

    def shutdown_session(self, session: Session):
        pass

    @classmethod
    def get_session(cls):
        cluster = cls.get()
        if 'scylla_session' not in g:
            g.scylla_session = cluster.create_session()  # pylint: disable=assigning-non-slot
        return g.scylla_session

    @classmethod
    def close_session(cls, error=None):  # pylint: disable=unused-argument
        cluster = cls.get()
        session: Session = g.pop("scylla_session", None)
        if session:
            cluster.shutdown_session(session)

    @click.command('sync-models')
    @with_appcontext
    @staticmethod
    def sync_models_command():
        cluster = ScyllaCluster.get()
        cluster.sync_models()
        click.echo("Models synchronized.")

    @classmethod
    def attach_to_app(cls, app: Flask):
        app.teardown_appcontext(cls.close_session)
        app.cli.add_command(cls.sync_models_command)
