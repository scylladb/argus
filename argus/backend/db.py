from functools import cached_property
import logging
from typing import Optional
from flask import g, Flask
# pylint: disable=no-name-in-module
from cassandra.policies import WhiteListRoundRobinPolicy
from cassandra import ConsistencyLevel
from cassandra.cluster import ExecutionProfile, EXEC_PROFILE_DEFAULT, Cluster
from cassandra.cluster import PreparedStatement
from cassandra.cqlengine.management import sync_table, sync_type
from cassandra.cqlengine import connection
from cassandra.query import dict_factory
from cassandra.auth import PlainTextAuthProvider
from argus.backend.util.config import Config

from argus.backend.models.web import USED_MODELS, USED_TYPES

LOGGER = logging.getLogger(__name__)


class ScyllaCluster:
    # pylint: disable=too-many-instance-attributes
    APP_INSTANCE: Optional['ScyllaCluster'] = None

    def __init__(self, config=None):
        if not config:
            config = Config.load_yaml_config()
        self.config = config
        self.auth_provider = PlainTextAuthProvider(
            username=config["SCYLLA_USERNAME"], password=config["SCYLLA_PASSWORD"])
        self.lb_policy = WhiteListRoundRobinPolicy(hosts=config["SCYLLA_CONTACT_POINTS"])
        self.execution_profile = ExecutionProfile(
            load_balancing_policy=self.lb_policy, consistency_level=ConsistencyLevel.QUORUM)
        connection.setup(hosts=config["SCYLLA_CONTACT_POINTS"], default_keyspace=config["SCYLLA_KEYSPACE_NAME"],
                         auth_provider=self.auth_provider,
                         protocol_version=4,
                         execution_profiles={EXEC_PROFILE_DEFAULT: self.execution_profile})
        self.cluster: Cluster = connection.get_cluster(connection='default')
        self.prepared_statements = {}
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

    @cached_property
    def session(self):
        return self.cluster.connect(keyspace=self.config["SCYLLA_KEYSPACE_NAME"])

    @classmethod
    def get(cls, config: Config = None) -> 'ScyllaCluster':
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

    def sync_core_tables(self):
        for udt in USED_TYPES:
            LOGGER.info("Syncing type: %s..", udt.__name__)
            sync_type(ks_name=self.config["SCYLLA_KEYSPACE_NAME"], type_model=udt)
        LOGGER.info("Core Types synchronized.")
        for model in USED_MODELS:
            LOGGER.info("Syncing model: %s..", model.__name__)
            sync_table(model, keyspaces=[self.config["SCYLLA_KEYSPACE_NAME"]])
        LOGGER.info("Core Models synchronized.")

    @classmethod
    def get_session(cls):
        cluster = cls.get()
        if 'scylla_session' not in g:
            g.scylla_session = cluster.session  # pylint: disable=assigning-non-slot
        return g.scylla_session

    @classmethod
    def close_session(cls, error=None):  # pylint: disable=unused-argument
        g.pop("scylla_session", None)

    @classmethod
    def attach_to_app(cls, app: Flask):
        app.teardown_appcontext(cls.close_session)
