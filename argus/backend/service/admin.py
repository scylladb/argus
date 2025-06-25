
import logging
from flask import current_app

from argus.backend.db import ScyllaCluster
from argus.backend.util.config import Config

LOGGER = logging.getLogger(__name__ )

class AdminService:
    def __init__(self, database_session=None):
        self.session = database_session if database_session else ScyllaCluster.get_session()
        self.database = ScyllaCluster.get()

    def reload_config(self):
        current_app.config.from_mapping(Config.load_yaml_config(True))
        self.database.config = Config.load_yaml_config() # TODO: Restart database connection on change
        return True
