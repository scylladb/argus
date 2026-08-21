from fastapi import APIRouter, FastAPI
from pytest import fixture
from starlette.routing import Mount


def _include_router_before_fallback(app: FastAPI, router: APIRouter, **kwargs) -> None:
    """Include a probe router ahead of the app's mounts.

    Starlette matches ``app.routes`` in order, so probe routes added after
    ``create_app()`` are moved in front of the first mount (/s static) to
    keep them from ever being shadowed.
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
