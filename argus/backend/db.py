from functools import cached_property
import logging
from typing import Optional
from flask import current_app, g, Flask
from cassandra.policies import WhiteListRoundRobinPolicy
from cassandra import ConsistencyLevel
from cassandra.cluster import ExecutionProfile, EXEC_PROFILE_DEFAULT, Cluster
from cassandra.cluster import PreparedStatement
from cassandra.cqlengine import connection
from cassandra.query import dict_factory
from cassandra.auth import PlainTextAuthProvider
from coodie.drivers import register_driver
from coodie.drivers.cassandra import CassandraDriver
from argus.backend.util.config import Config

from cassandra.cluster import UserTypeDoesNotExist

from argus.backend.models.web import USED_MODELS, USED_TYPES

LOGGER = logging.getLogger(__name__)


class ArgusCoodieDriver(CassandraDriver):
    """CassandraDriver for sessions whose cluster uses execution profiles.

    The upstream constructor assigns ``session.row_factory``, which the
    cassandra driver forbids on profile-configured clusters (ValueError).
    Rows already come back as dicts here: cqlengine's ``setup_session``
    sets ``dict_factory`` on the default execution profile.
    """

    def __init__(self, session, default_keyspace: str | None = None):
        try:
            super().__init__(session, default_keyspace=default_keyspace)
        except ValueError:
            if getattr(self, "_session", None) is not session:
                # row_factory assignment moved before attribute setup in a
                # future coodie version; the instance is unusable.
                raise


class ScyllaCluster:
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
                         execution_profiles={EXEC_PROFILE_DEFAULT: self.execution_profile},
                         retry_connect=True)
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
        # Reuse cqlengine's already-open session: opening a new one here would
        # replay registered UDTs against a possibly not-yet-synced schema
        # (Cluster._session_register_user_types raises on fresh databases).
        self.coodie_driver = ArgusCoodieDriver(
            session=connection.get_session(connection='default'),
            default_keyspace=self.config["SCYLLA_KEYSPACE_NAME"])
        register_driver("default", self.coodie_driver, default=True)
        self.register_coodie_udts()

    def register_coodie_udts(self):
        """Map coodie UserType classes to their CQL types so the driver
        materializes UDT values as model instances on read.

        Types missing from schema metadata (fresh database, before sync)
        are skipped; sync_core_tables re-registers after creating them.
        """
        from argus.backend.plugins.loader import all_plugin_types

        for udt in [*USED_TYPES, *all_plugin_types()]:
            ks = getattr(udt.Settings, "keyspace", "") or self.config["SCYLLA_KEYSPACE_NAME"]
            try:
                self.cluster.register_user_type(ks, udt.type_name(), udt)
            except UserTypeDoesNotExist:
                LOGGER.info("UDT %s not in schema yet, deferring registration", udt.type_name())

    @cached_property
    def session(self):
        return self.cluster.connect(keyspace=self.config["SCYLLA_KEYSPACE_NAME"])

    @classmethod
    def reconnect(cls):
        if cls.APP_INSTANCE:
            old_statements = cls.APP_INSTANCE.prepared_statements
            cls.close_session()
            cls.APP_INSTANCE.shutdown()
            app = current_app
            new_instance = cls.get(app.config)
            for query, _ in old_statements.items():
                new_instance.prepare(query)
            return new_instance

        return cls.get()

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
        for udt_type in USED_TYPES:
            LOGGER.info("Syncing type: %s..", udt_type.__name__)
            udt_type.sync_type()
        self.register_coodie_udts()
        LOGGER.info("Core Types synchronized.")

        for document in USED_MODELS:
            LOGGER.info("Syncing model: %s..", document.__name__)
            document.sync_table()

        LOGGER.info("Core Models synchronized.")

    def sync_additional_schema(self):
        LOGGER.info("Syncing additional rules...")
        for model in USED_MODELS:
            if rule_func := getattr(model, "_sync_additional_rules", None):
                rule_func(self.session)
        LOGGER.info("Syncing additional rules done.")

    @classmethod
    def get_session(cls):
        return cls.get().session

    @classmethod
    def close_session(cls, error=None):
        g.pop("scylla_session", None)

    @classmethod
    def attach_to_app(cls, app: Flask):
        app.teardown_appcontext(cls.close_session)
