import logging
from typing import Union, Any
from cassandra.auth import AuthProvider

LOGGER = logging.getLogger(__name__)


class MockPreparedStatement:
    def __init__(self, query: str):
        self.log = logging.getLogger(self.__class__.__name__)
        self.query_string = query
        self.parameters = None

    def bind(self, parameters: Union[tuple, list]):
        self.parameters = parameters

    def query(self):
        return self.query_string


class MockCluster():
    MOCK_NO_CONNECTION = False

    def __init__(self, contact_points: tuple[str] = None, auth_provider: AuthProvider = None, load_balancing_policy=None,
                 execution_profiles=None, *args, **kwargs):
        self.contact_points = contact_points
        self.log = logging.getLogger(self.__class__.__name__)
        self.sessions = []
        self.load_balancing_policy = load_balancing_policy
        self.auth_provider = auth_provider
        self.execution_profiles = execution_profiles

    def connect(self):
        self.log.info("Connecting to cluster: %s", self.contact_points)
        if self.MOCK_NO_CONNECTION:
            raise OSError("timed out")
        session = MockSession(hosts=self.contact_points, cluster=self)
        self.sessions.append(session)
        return session

    def shutdown(self):
        for sess in self.sessions:
            sess.shutdown()
        return True


class MockSession():
    MOCK_RESULT_SET = None
    MOCK_CURRENT_KEYSPACE = None
    MOCK_LAST_QUERY: Any = None

    def __init__(self, hosts=None, cluster=None, *args, **kwargs):
        self.hosts = hosts
        self.cluster = cluster
        self.log = logging.getLogger(self.__class__.__name__)
        self.executed_queries = []
        self.prepared_statements = []
        self.keyspace = None
        self.is_shutdown = False

    def shutdown(self):
        self.log.info("Shutting down session %s... ", hex(id(self)))
        self.is_shutdown = True

    def prepare(self, query: str):
        self.log.info("Prepare statement added: %s", query)
        self.prepared_statements.append(query)
        return MockPreparedStatement(query)

    def execute(self, query: Union[str, MockPreparedStatement], parameters: Union[tuple, list] = None, execution_profile="default", timeout=0):
        self.log.info("Executing query %s with parameters: %s, using profile %s", query, parameters, execution_profile)
        self.executed_queries.append((query, parameters))
        self.__class__.MOCK_LAST_QUERY = (query, parameters)
        return self.MOCK_RESULT_SET

    def set_keyspace(self, keyspace: str):
        self.log.info("Setting keyspace to %s", keyspace)
        self.keyspace = keyspace
        self.__class__.MOCK_CURRENT_KEYSPACE = keyspace
