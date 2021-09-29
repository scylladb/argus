import logging
from typing import Union
from cassandra.auth import AuthProvider

LOGGER = logging.getLogger(__name__)


class MockPreparedStatement:
    def __init__(self, query: str):
        self.log = logging.getLogger(self.__class__.__name__)
        self.query = query
        self.parameters = None

    def bind(self, parameters: Union[tuple, list]):
        self.parameters = parameters


class MockCluster:
    def __init__(self, contact_points: tuple[str], auth_provider: AuthProvider):
        self.contact_points = contact_points
        self.log = logging.getLogger(self.__class__.__name__)
        self.sessions = list()
        self.auth_provider = auth_provider

    def connect(self):
        self.log.info("Connecting to cluster: %s", self.contact_points)
        session = MockSession()
        self.sessions.append(session)
        return session

    def shutdown(self):

        return True


class MockSession:
    MOCK_RESULT_SET = None

    def __init__(self):
        self.log = logging.getLogger(self.__class__.__name__)
        self.executed_queries = list()
        self.prepared_statements = list()
        self.keyspace = None
        self._is_running = True

    def shutdown(self):
        self.log.info("Shutting down session %s... ", hex(id(self)))
        self._is_running = False

    def prepare(self, query: str):
        self.log.info("Prepare statement added: %s", query)
        self.prepared_statements.append(query)
        return MockPreparedStatement(query)

    def execute(self, query: Union[str, MockPreparedStatement], parameters: Union[tuple, list]):
        self.log.info("Executing query %s with parameters: %s", query, parameters)
        self.executed_queries.append((query, parameters))
        return self.MOCK_RESULT_SET

    def set_keyspace(self, keyspace: str):
        self.log.info("Setting keyspace to %s", keyspace)
        self.keyspace = keyspace
