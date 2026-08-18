from fastapi import APIRouter, FastAPI
from pytest import fixture
from starlette.routing import Mount


def _include_router_before_fallback(app: FastAPI, router: APIRouter, **kwargs) -> None:
    """Include a router so its routes match before the Flask fall-through.

    Starlette matches ``app.routes`` in order and the "/" WSGI mount matches
    everything, so a router included after ``create_app()`` (as these tests
    do for their probe routes) must be moved in front of the first mount to
    be reachable. Real migrated routers don't need this — they are included
    inside create_app, before the mounts.
    """
    before = len(app.routes)
    app.include_router(router, **kwargs)
    added = app.routes[before:]
    del app.routes[before:]
    first_mount = next(
        (index for index, route in enumerate(app.routes) if isinstance(route, Mount)),
        len(app.routes),
    )
    app.routes[first_mount:first_mount] = added


@fixture(scope="session")
def include_router_before_fallback():
    return _include_router_before_fallback
