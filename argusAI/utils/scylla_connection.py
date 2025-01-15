import logging
from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
from cassandra.policies import WhiteListRoundRobinPolicy
from cassandra.auth import PlainTextAuthProvider
from cassandra.query import ConsistencyLevel
from cassandra.protocol import PreparedQueryNotFound
from argus.backend.util.config import Config

LOGGER = logging.getLogger(__name__)

class ScyllaConnection:
    def __init__(self):
        """Initialize ScyllaDB connection with longer timeouts and prepared statement cache."""
        self.config = Config.load_yaml_config()
        self.cluster = None
        self.session = None
        self.execution_profile = None
        self.prepared_statements = {}
        self._initialize_connection()

    def _initialize_connection(self):
        """Initialize the ScyllaDB cluster and session with longer timeouts."""
        try:
            if self.cluster and self.session:
                self.shutdown()

            auth_provider = PlainTextAuthProvider(
                username=self.config["SCYLLA_USERNAME"],
                password=self.config["SCYLLA_PASSWORD"]
            )

            lb_policy = WhiteListRoundRobinPolicy(hosts=self.config["SCYLLA_CONTACT_POINTS"])

            self.execution_profile = ExecutionProfile(
                load_balancing_policy=lb_policy,
                consistency_level=ConsistencyLevel.QUORUM,
                request_timeout=30.0
            )

            self.cluster = Cluster(
                contact_points=self.config["SCYLLA_CONTACT_POINTS"],
                auth_provider=auth_provider,
                protocol_version=4,
                execution_profiles={EXEC_PROFILE_DEFAULT: self.execution_profile},
                idle_heartbeat_interval=180,
                idle_heartbeat_timeout=160,
                connect_timeout=20,
                control_connection_timeout=20
            )

            self.session = self.cluster.connect(keyspace=self.config["SCYLLA_KEYSPACE_NAME"])
            LOGGER.info("Successfully initialized ScyllaDB connection")
        except Exception as e:
            LOGGER.error(f"Failed to initialize ScyllaDB connection: {e}")
            raise

    def execute(self, query: str, params: tuple = None, fetch_size=10):
        """Execute a query, handling unprepared statements by re-preparing if needed."""
        try:
            if query not in self.prepared_statements:
                prepared = self.session.prepare(query)
                prepared.consistency_level = ConsistencyLevel.QUORUM
                prepared.fetch_size = fetch_size
                self.prepared_statements[query] = prepared
                LOGGER.debug(f"Prepared and cached new statement: {query}")

            prepared_statement = self.prepared_statements[query]
            return self.session.execute(prepared_statement, params)
        except PreparedQueryNotFound as e:
            # Handle case where the prepared statement is no longer valid on the server
            LOGGER.warning(f"Prepared statement for query '{query}' is unprepared, re-preparing: {e}")
            try:
                # Re-prepare the statement and update the cache
                prepared = self.session.prepare(query)
                prepared.consistency_level = ConsistencyLevel.QUORUM
                prepared.fetch_size = fetch_size
                self.prepared_statements[query] = prepared
                LOGGER.info(f"Successfully re-prepared statement: {query}")
                return self.session.execute(prepared, params)
            except Exception as reprepare_e:
                LOGGER.error(f"Failed to re-prepare query: {query}. Error: {reprepare_e}")
                raise
        except Exception as e:
            LOGGER.error(f"Failed to execute query: {query}. Error: {e}")
            LOGGER.error(f"Error type: {type(e)}")
            LOGGER.error(f"Params: {params}")

    def shutdown(self):
        """Properly shut down the ScyllaDB session and cluster."""
        try:
            if self.session:
                self.session.shutdown()
            if self.cluster:
                self.cluster.shutdown()
            LOGGER.info("ScyllaDB connection shut down successfully")
        except Exception as e:
            LOGGER.warning(f"Error shutting down ScyllaDB connection: {e}")
        finally:
            self.session = None
            self.cluster = None
            self.prepared_statements.clear()
