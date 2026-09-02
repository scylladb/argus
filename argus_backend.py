import logging

import cassandra.cluster
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from jwt import PyJWKClient
from starlette.middleware.sessions import SessionMiddleware

from argus.backend.controller import admin, api, auth, main
from argus.backend.db import ScyllaCluster
from argus.backend.error_handlers import (
    APIException,
    AuthorizationError,
    UIRedirect,
    api_exception_handler,
    authorization_error_handler,
    db_error_handler,
    redirecting_exception_handler,
    ui_redirect_handler,
)
from argus.backend.metrics import build_instrumentator, build_metrics_router
from argus.backend.rendering import register_app
from argus.backend.service.user import UserServiceException, api_current_user
from argus.backend.service.views import UserViewException
from argus.backend.util.config import Config
from argus.backend.util.logsetup import RequestLogContextMiddleware, setup_application_logging

LOGGER = logging.getLogger(__name__)

SESSION_LIFETIME = 31 * 24 * 60 * 60  # Flask's permanent_session_lifetime default


def create_app(config=None) -> FastAPI:
    app_config = dict(Config.load_yaml_config())
    if config:
        app_config.update(config)

    if "cf" in app_config.get("LOGIN_METHODS", []):
        cf_domain = app_config.get("CLOUDFLARE_ACCESS_TEAM_DOMAIN")
        if cf_domain:
            app_config["CLOUDFLARE_ACCESS_JWK_CLIENT"] = PyJWKClient(
                f"https://{cf_domain}/cdn-cgi/access/certs",
                cache_keys=True,
                lifespan=3600,
                timeout=5,
            )
        else:
            LOGGER.warning("Cloudflare Access enabled but CLOUDFLARE_ACCESS_TEAM_DOMAIN is missing")

    setup_application_logging(log_level=app_config["APP_LOG_LEVEL"])
    LOGGER.info("Starting Scylla Cluster connection...")
    ScyllaCluster.get(app_config)

    app = FastAPI(
        title="Argus",
        # UI parity with the Flask app: no schema/docs endpoints (yet)
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
    )
    app.state.config = app_config
    register_app(app)

    app.add_middleware(
        SessionMiddleware,
        secret_key=app_config["SECRET_KEY"],
        session_cookie=app_config.get("SESSION_COOKIE_NAME") or "session",
        max_age=SESSION_LIFETIME,
        https_only=bool(app_config.get("SESSION_COOKIE_SECURE")),
    )
    app.add_middleware(RequestLogContextMiddleware)
    build_instrumentator().instrument(app)
    app.add_exception_handler(AuthorizationError, authorization_error_handler)
    app.add_exception_handler(APIException, api_exception_handler)
    app.add_exception_handler(RequestValidationError, api_exception_handler)
    app.add_exception_handler(UIRedirect, ui_redirect_handler)
    app.add_exception_handler(UserServiceException, redirecting_exception_handler("main.profile"))
    app.add_exception_handler(UserViewException, redirecting_exception_handler("main.views"))
    app.add_exception_handler(cassandra.cluster.NoHostAvailable, db_error_handler)
    app.add_exception_handler(cassandra.cluster.NoConnectionsAvailable, db_error_handler)
    app.add_exception_handler(Exception, api_exception_handler)

    app.include_router(auth.router)
    app.include_router(main.router)
    app.include_router(api.router)
    app.include_router(admin.router)
    app.include_router(build_metrics_router(current_user_dependency=api_current_user))

    app.mount("/s", StaticFiles(directory="public"), name="static")
    LOGGER.info("Ready.")
    return app
