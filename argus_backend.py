import logging
from contextlib import asynccontextmanager

import cassandra.cluster
from a2wsgi import WSGIMiddleware
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from flask import Flask
from jwt import PyJWKClient

from argus.backend.cli import cli_bp
from argus.backend.controller import admin, api, auth, main
from argus.backend.db import ScyllaCluster
from argus.backend.error_handlers import (
    APIException,
    AuthorizationError,
    DBErrorHandler,
    UIRedirect,
    api_exception_handler,
    authorization_error_handler,
    redirecting_exception_handler,
    ui_redirect_handler,
)
from argus.backend.metrics import build_instrumentator, init_flask_metrics
from argus.backend.service.user import UserServiceException, cache_ssh_tunnel_server_allowed_endpoints
from argus.backend.service.views import UserViewException
from argus.backend.session import FlaskSessionMiddleware
from argus.backend.template_filters import export_filters
from argus.backend.util.config import Config
from argus.backend.util.encoders import ArgusJSONProvider
from argus.backend.util.logsetup import setup_application_logging

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


@asynccontextmanager
async def lifespan(_: FastAPI):
    # The Scylla connection is established when the Flask app is built above;
    # closing it here lets gunicorn recycle workers cleanly.
    yield
    ScyllaCluster.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Argus",
        lifespan=lifespan,
        # UI parity with the Flask app: no schema/docs endpoints (yet)
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
    )
    flask_app = start_server()
    app.state.flask_app = flask_app
    wsgi_fallback = WSGIMiddleware(flask_app)
    app.add_middleware(FlaskSessionMiddleware, flask_app=flask_app)
    # Fall-through requests are recorded by the Flask hooks, not here.
    build_instrumentator(skip_endpoints=(wsgi_fallback,)).instrument(app)
    app.add_exception_handler(AuthorizationError, authorization_error_handler)
    app.add_exception_handler(APIException, api_exception_handler)
    app.add_exception_handler(RequestValidationError, api_exception_handler)
    app.add_exception_handler(UIRedirect, ui_redirect_handler)
    app.add_exception_handler(UserServiceException, redirecting_exception_handler("main.profile"))
    app.add_exception_handler(UserViewException, redirecting_exception_handler("main.views"))
    app.add_exception_handler(Exception, api_exception_handler)

    # Migrated APIRouters are included here, before the mounts, so they take
    # precedence over the Flask fall-through.
    app.include_router(auth.router)
    app.include_router(main.router)
    app.include_router(api.router)

    app.mount("/s", StaticFiles(directory="public"), name="static")
    # Everything not handled above falls through to Flask.
    app.mount("/", wsgi_fallback)
    return app
