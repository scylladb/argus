import atexit
from flask import Flask, g, render_template
from flask_login.login_manager import LoginManager
from werkzeug.security import generate_password_hash
from argus.backend.db import ScyllaCluster
from argus.backend import auth, main, api
from argus.backend.models import User
from argus.backend.argus_service import ArgusService
from argus.backend.collectors import PollingDataCollector
from yaml import safe_load
from uuid import UUID
from datetime import datetime


def create_app(config=None) -> Flask:
    app = Flask(__name__)
    with open("argus_web.yaml", "rt", encoding="utf-8") as f:
        config_mapping = safe_load(f.read())
    app.config.from_mapping(config_mapping)
    if config:
        app.config.from_mapping(config)
    ScyllaCluster.get().attach_to_app(app)
    PollingDataCollector.get()
    atexit.register(PollingDataCollector.destroy)
    app.register_blueprint(auth.bp)
    app.register_blueprint(main.bp)
    app.register_blueprint(api.bp)

    @app.template_filter('from_timestamp')
    def from_timestamp_filter(timestamp: int):
        return datetime.fromtimestamp(timestamp)

    return app
