import logging
import cassandra.cluster
from flask import Flask
from argus.backend.error_handlers import DBErrorHandler
from argus.backend.metrics import init_flask_metrics
from argus.backend.template_filters import export_filters
from argus.backend.controller import admin, api, main
from argus.backend.cli import cli_bp
from argus.backend.util.logsetup import setup_application_logging
from argus.backend.util.encoders import ArgusJSONProvider
from argus.backend.db import ScyllaCluster
from argus.backend.controller import auth
from argus.backend.util.config import Config
from jwt import PyJWKClient
from argus.backend.service.user import cache_ssh_tunnel_server_allowed_endpoints

LOGGER = logging.getLogger(__name__)


def start_server(config=None) -> Flask:
    app = Flask(__name__, static_url_path="/s/", static_folder="public")
    init_flask_metrics(app)
    app.json_provider_class = ArgusJSONProvider
    app.json = ArgusJSONProvider(app)
    app.jinja_env.policies["json.dumps_kwargs"]["default"] = app.json.default
    app.config.from_mapping(Config.load_yaml_config())
    if config:
        app.config.from_mapping(config)

    if "cf" in app.config.get("LOGIN_METHODS", []):
        cf_domain = app.config.get("CLOUDFLARE_ACCESS_TEAM_DOMAIN")
        if cf_domain:
            app.config["CLOUDFLARE_ACCESS_JWK_CLIENT"] = PyJWKClient(
                f"https://{cf_domain}/cdn-cgi/access/certs",
                cache_keys=True,
                lifespan=3600,
                timeout=5,
            )
        else:
            LOGGER.warning("Cloudflare Access enabled but CLOUDFLARE_ACCESS_TEAM_DOMAIN is missing")

    setup_application_logging(log_level=app.config["APP_LOG_LEVEL"])
    app.logger.info("Starting Scylla Cluster connection...")
    app.register_error_handler(cassandra.cluster.NoHostAvailable, DBErrorHandler.handle_db_errors)
    app.register_error_handler(cassandra.cluster.NoConnectionsAvailable, DBErrorHandler.handle_db_errors)
    ScyllaCluster.get(app.config)
    ScyllaCluster.attach_to_app(app)

    app.logger.info("Loading filters...")
    for filter_func in export_filters():
        app.add_template_filter(filter_func, name=filter_func.filter_name)

    app.logger.info("Registering blueprints...")
    app.register_blueprint(auth.bp)
    app.register_blueprint(main.bp)
    app.register_blueprint(api.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(cli_bp)
    cache_ssh_tunnel_server_allowed_endpoints(app)

    app.logger.info("Ready.")
    return app


argus_app = start_server()
