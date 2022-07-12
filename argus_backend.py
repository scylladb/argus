import logging
from pathlib import Path
from datetime import datetime
from flask import Flask
from yaml import safe_load
from argus.backend.controller import admin, api, main
from argus.backend.logsetup import setup_argus_logging
from argus.backend.encoders import ArgusJSONEncoder
from argus.db.models import User
from argus.backend.db import ScyllaCluster
from argus.backend.build_system_monitor import scan_jenkins_command
from argus.backend.controller import auth

setup_argus_logging()
LOGGER = logging.getLogger(__name__)

CONFIG_PATHS = [
    Path("./config/argus_web.yaml"),
    Path("argus_web.yaml"),
]


def locate_argus_web_config() -> Path:
    for config in CONFIG_PATHS:
        if config.exists():
            return config
        else:
            LOGGER.debug("Tried %s as config, not found.", config)

    raise Exception("Failed to locate web application config file!")


def start_server(config=None) -> Flask:
    app = Flask(__name__, static_url_path="/s/", static_folder="public")
    app.json_encoder = ArgusJSONEncoder
    config_path = locate_argus_web_config()
    with config_path.open(mode="rt", encoding="utf-8") as config_file:
        config_mapping = safe_load(config_file.read())
    app.config.from_mapping(config_mapping)
    if config:
        app.config.from_mapping(config)
    app.logger.info("Starting Scylla Cluster connection...")
    ScyllaCluster.get().attach_to_app(app)
    app.logger.info("Registering blueprints")
    app.register_blueprint(auth.bp)
    app.register_blueprint(main.bp)
    app.register_blueprint(api.bp)
    app.register_blueprint(admin.bp)
    app.cli.add_command(scan_jenkins_command)

    @app.template_filter('from_timestamp')
    def from_timestamp_filter(timestamp: int):
        return datetime.utcfromtimestamp(timestamp)

    @app.template_filter('safe_user')
    def safe_user(user: User):
        user_dict = dict(user.items())
        del user_dict["password"]
        return user_dict
    app.logger.info("Ready.")
    return app


argus_app = start_server()
