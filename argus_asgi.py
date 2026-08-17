"""ASGI entrypoint: FastAPI shell around the Flask application.

Strangler-pattern setup for the FastAPI migration: FastAPI owns the server
(gunicorn + uvicorn workers) and static files, while every route is still
served by the Flask app through WSGIMiddleware. Blueprints migrate to
APIRouters one by one; whatever FastAPI doesn't handle falls through to Flask.

Run with: gunicorn -c gunicorn.conf.py argus_asgi:app
"""

from contextlib import asynccontextmanager

from a2wsgi import WSGIMiddleware
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from argus_backend import argus_app as flask_app
from argus.backend.db import ScyllaCluster


@asynccontextmanager
async def lifespan(_: FastAPI):
    # The Scylla connection is established when argus_backend is imported
    # (start_server); closing it here lets gunicorn recycle workers cleanly.
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
    app.mount("/s", StaticFiles(directory="public"), name="static")
    # Everything not handled above falls through to Flask.
    app.mount("/", WSGIMiddleware(flask_app))
    return app


app = create_app()
