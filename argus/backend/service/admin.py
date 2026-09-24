from argus.backend.db import ScyllaCluster


class AdminService:
    def __init__(self):
        self.database = ScyllaCluster.get()
