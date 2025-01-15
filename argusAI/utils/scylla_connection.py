import logging
from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
from cassandra.policies import WhiteListRoundRobinPolicy
from cassandra.auth import PlainTextAuthProvider
from cassandra.query import SimpleStatement, ConsistencyLevel
from argus.backend.util.config import Config

logger = logging.getLogger(__name__)

class ScyllaConnection:
    def __init__(self):
        """Initialize ScyllaDB connection with longer timeouts."""
        self.config = Config.load_yaml_config()
        self.cluster = None
        self.session = None
        self.execution_profile = None
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

            # Initialize the cluster with longer timeouts
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
            logger.info("Successfully initialized ScyllaDB connection")
        except Exception as e:
            logger.error(f"Failed to initialize ScyllaDB connection: {e}")
            raise

    def execute(self, query: str, params: tuple = None, fetch_size=10):
        """Execute a query using the session."""
        try:
            logger.debug(f"Executing query: {query}")
            logger.debug(f"With params: {params}")
            logger.debug(f"Param types: {[type(p) for p in params] if params else None}")
            
            statement = SimpleStatement(query, consistency_level=ConsistencyLevel.QUORUM, fetch_size=fetch_size)
            return self.session.execute(statement, params)
        except Exception as e:
            logger.error(f"Failed to execute query: {query}. Error: {e}")
            logger.error(f"Error type: {type(e)}")
            logger.error(f"Params: {params}")
            raise

    def shutdown(self):
        """Properly shut down the ScyllaDB session and cluster."""
        try:
            if self.session:
                self.session.shutdown()
            if self.cluster:
                self.cluster.shutdown()
            logger.info("ScyllaDB connection shut down successfully")
        except Exception as e:
            logger.warning(f"Error shutting down ScyllaDB connection: {e}")
        finally:
            self.session = None
            self.cluster = None
