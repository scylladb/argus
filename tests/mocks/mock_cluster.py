import logging
from typing import Union
from cassandra.auth import AuthProvider

LOGGER = logging.getLogger(__name__)


class MockPreparedStatement:
    def __init__(self, query: str):
        self.log = logging.getLogger(self.__class__.__name__)
        self.query_string = query
        self.parameters = None

    def bind(self, parameters: Union[tuple, list]):
        self.parameters = parameters


class MockCluster:
    MOCK_NO_CONNECTION = False

    def __init__(self, contact_points: tuple[str], auth_provider: AuthProvider, load_balancing_policy=None):
        self.contact_points = contact_points
        self.log = logging.getLogger(self.__class__.__name__)
        self.sessions = list()
        self.load_balancing_policy = load_balancing_policy
        self.auth_provider = auth_provider

    def connect(self):
        self.log.info("Connecting to cluster: %s", self.contact_points)
        if self.MOCK_NO_CONNECTION:
            raise OSError("timed out")
        session = MockSession()
        self.sessions.append(session)
        return session

    def shutdown(self):
        for sess in self.sessions:
            sess.shutdown()
        return True


class MockSession:
    MOCK_RESULT_SET = None
    MOCK_CURRENT_KEYSPACE = None
    MOCK_LAST_QUERY = None

    def __init__(self):
        self.log = logging.getLogger(self.__class__.__name__)
        self.executed_queries = list()
        self.prepared_statements = list()
        self.keyspace = None
        self.is_shutdown = False

    def shutdown(self):
        self.log.info("Shutting down session %s... ", hex(id(self)))
        self.is_shutdown = True

    def prepare(self, query: str):
        self.log.info("Prepare statement added: %s", query)
        self.prepared_statements.append(query)
        return MockPreparedStatement(query)

    def execute(self, query: Union[str, MockPreparedStatement], parameters: Union[tuple, list] = None):
        self.log.info("Executing query %s with parameters: %s", query, parameters)
        self.executed_queries.append((query, parameters))
        self.__class__.MOCK_LAST_QUERY = (query, parameters)
        return self.MOCK_RESULT_SET

    def set_keyspace(self, keyspace: str):
        self.log.info("Setting keyspace to %s", keyspace)
        self.keyspace = keyspace
        self.__class__.MOCK_CURRENT_KEYSPACE = keyspace
