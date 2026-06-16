import logging
import os
import cassandra.cluster
from flask import Flask, request
from prometheus_flask_exporter import NO_PREFIX
from argus.backend.error_handlers import DBErrorHandler
from argus.backend.metrics import METRICS
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


def _categorize_user_agent(ua: str) -> str:  # noqa: PLR0911
    if not ua:
        return "unknown"
    if "argus-client-ssh-tunnel" in ua:
        return "argus-client-tunnel"
    if ua.startswith(("python-requests", "python-urllib")):
        return "argus-client"
    if ua.startswith("Go-http-client"):
        return "argus-cli-go"
    if "Mozilla" in ua:
        return "browser"
    if "curl" in ua:
        return "curl"
    return "other"


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
    METRICS.register_default(
        METRICS.counter(
            "http_request_by_ip_total",
            "Total requests by source IP",
            labels={
                "ip": lambda: request.remote_addr,
                "endpoint": lambda: request.endpoint,
            },
        )
    )
    METRICS.register_default(
        METRICS.counter(
            "http_request_ssh_tunnel_total",
            "Total requests by SSH tunnel presence",
            labels={
                "ssh_tunnel": lambda: "yes" if request.headers.get("X-SSH-Tunnel-Origin") else "no",
                "tunnel_established": lambda: "yes" if request.headers.get("X-Tunnel-Established-At") else "no",
                "endpoint": lambda: request.endpoint,
            },
        )
    )
    METRICS.register_default(
        METRICS.counter(
            "http_request_by_user_agent_total",
            "Total requests by user agent category",
            labels={
                "user_agent_category": lambda: _categorize_user_agent(request.headers.get("User-Agent", "")),
                "endpoint": lambda: request.endpoint,
            },
        )
    )
    METRICS.register_default(
        METRICS.counter(
            "http_request_tunnel_build_total",
            "Tunneled requests by Jenkins build/job id (X-Argus-Build-Id)",
            labels={
                "build_id": lambda: request.headers.get("X-Argus-Build-Id") or "unknown",
                "build_url": lambda: request.headers.get("X-Argus-Build-Url") or "",
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
    with app.app_context():
        try:
            register_metrics()
        except ValueError:
            pass

    app.logger.info("Ready.")
    return app


argus_app = start_server()
