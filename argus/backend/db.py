import asyncio
from functools import cached_property
import logging
from typing import Optional
from cassandra.policies import WhiteListRoundRobinPolicy
from cassandra import ConsistencyLevel
from cassandra.cluster import ExecutionProfile, EXEC_PROFILE_DEFAULT, Cluster
from cassandra.cqlengine import connection
from cassandra.auth import PlainTextAuthProvider
from coodie.drivers import register_driver
from coodie.drivers.cassandra import CassandraDriver
from argus.backend.util.config import Config

from cassandra.cluster import UserTypeDoesNotExist

from argus.backend.models.web import USED_MODELS, USED_TYPES

LOGGER = logging.getLogger(__name__)


def await_all_pages(driver_future) -> asyncio.Future:
    """Resolve a driver ResponseFuture with every page of its result.

    The driver hands a callback one page at a time; the coodie bridge keeps
    only the first. Callbacks stay registered across pages, so one
    registration walks them all.
    """
    loop = asyncio.get_running_loop()
    done: asyncio.Future = loop.create_future()
    rows: list = []

    def on_page(page):
        if page is not None:
            rows.extend(page)
        if driver_future.has_more_pages:
            driver_future.start_fetching_next_page()
        else:
            loop.call_soon_threadsafe(done.set_result, rows)

    def on_error(exc):
        loop.call_soon_threadsafe(done.set_exception, exc)

    driver_future.add_callbacks(on_page, on_error)
    return done


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

    def _wrap_future(self, driver_future) -> asyncio.Future:
        return await_all_pages(driver_future)


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
            config = cls.APP_INSTANCE.config
            cls.APP_INSTANCE.shutdown()
            return cls.get(config)

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

    async def sync_core_tables(self):
        for udt_type in USED_TYPES:
            LOGGER.info("Syncing type: %s..", udt_type.__name__)
            await udt_type.sync_type_async()
        self.register_coodie_udts()
        LOGGER.info("Core Types synchronized.")

        for document in USED_MODELS:
            LOGGER.info("Syncing model: %s..", document.__name__)
            await document.sync_table()

        LOGGER.info("Core Models synchronized.")

    def sync_additional_schema(self):
        LOGGER.info("Syncing additional rules...")
        for model in USED_MODELS:
            if rule_func := getattr(model, "_sync_additional_rules", None):
                rule_func(self.session)
        LOGGER.info("Syncing additional rules done.")
