import logging
import os
from flask import Flask, request
from prometheus_flask_exporter import NO_PREFIX
from argus.backend.metrics import METRICS
from argus.backend.template_filters import export_filters
from argus.backend.controller import admin, api, main
from argus.backend.cli import cli_bp
from argus.backend.util.logsetup import setup_application_logging
from argus.backend.util.encoders import ArgusJSONProvider
from argus.backend.db import ScyllaCluster
from argus.backend.controller import auth
from argus.backend.util.config import Config

LOGGER = logging.getLogger(__name__)


def register_metrics():
    METRICS.export_defaults(group_by="endpoint", prefix=NO_PREFIX)
    METRICS.register_default(
        METRICS.counter(
            "http_request_by_endpoint_total",
            "Total Requests made",
            labels={
                "endpoint": lambda: request.endpoint,
                "method": lambda: request.method,
                "status": lambda response: response.status,
            },
        )
    )


def start_server(config=None) -> Flask:
    app = Flask(__name__, static_url_path="/s/", static_folder="public")
    METRICS.init_app(app)
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        with app.app_context():
            METRICS.register_endpoint("/metrics")
    app.json_provider_class = ArgusJSONProvider
    app.json = ArgusJSONProvider(app)
    app.jinja_env.policies["json.dumps_kwargs"]["default"] = app.json.default
    app.config.from_mapping(Config.load_yaml_config())
    if config:
        app.config.from_mapping(config)

    setup_application_logging(log_level=app.config["APP_LOG_LEVEL"])
    app.logger.info("Starting Scylla Cluster connection...")
    ScyllaCluster.get(app.config).attach_to_app(app)

    app.logger.info("Loading filters...")
    for filter_func in export_filters():
        app.add_template_filter(filter_func, name=filter_func.filter_name)

    app.logger.info("Registering blueprints...")
    app.register_blueprint(auth.bp)
    app.register_blueprint(main.bp)
    app.register_blueprint(api.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(cli_bp)
    with app.app_context():
        try:
            register_metrics()
        except ValueError:
            pass

    app.logger.info("Ready.")
    return app


argus_app = start_server()
