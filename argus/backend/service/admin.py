

from argus.backend.db import ScyllaCluster


class AdminService:
    def __init__(self, database_session=None):
        self.session = database_session if database_session else ScyllaCluster.get_session()
        self.database = ScyllaCluster.get()
