"""Template rendering for FastAPI-served UI pages.

Reuses the Flask app's jinja environment (same loader, filters and json
policies) while shadowing the Flask context globals templates rely on:
``url_for`` builds from the Flask url_map — migrated routes keep view-less
rules there, so both frameworks build every URL from one source of truth —
``g`` carries the request's user, ``session`` is the shared session dict,
and flash messages use Flask's ``_flashes`` session format, so they cross
the framework boundary in both directions.
"""
from types import SimpleNamespace

from fastapi import Request
from flask import Flask
from starlette.responses import HTMLResponse

FLASHES_SESSION_KEY = "_flashes"


def url_for(asgi_request: Request, endpoint: str, **values) -> str:
    """Build a URL for any endpoint — migrated or not — from the Flask url_map."""
    flask_app: Flask = asgi_request.app.state.flask_app
    adapter = flask_app.url_map.bind("localhost")
    return adapter.build(endpoint, values, append_unknown=True)


def flash(asgi_request: Request, message: str, category: str = "message") -> None:
    flashes = asgi_request.session.get(FLASHES_SESSION_KEY, [])
    asgi_request.session[FLASHES_SESSION_KEY] = [*flashes, (category, message)]


def get_flashed_messages(asgi_request: Request, with_categories: bool = False,
                         category_filter: tuple = ()) -> list:
    flashes = asgi_request.session.pop(FLASHES_SESSION_KEY, [])
    if category_filter:
        flashes = [flash_ for flash_ in flashes if flash_[0] in category_filter]
    if not with_categories:
        return [message for _, message in flashes]
    return flashes


def render_template(asgi_request: Request, template_name: str, **context) -> HTMLResponse:
    flask_app: Flask = asgi_request.app.state.flask_app
    template = flask_app.jinja_env.get_template(template_name)
    html = template.render(
        request=asgi_request,
        session=asgi_request.session,
        g=SimpleNamespace(user=getattr(asgi_request.state, "user", None)),
        config=flask_app.config,
        url_for=lambda endpoint, **values: url_for(asgi_request, endpoint, **values),
        get_flashed_messages=lambda **kwargs: get_flashed_messages(asgi_request, **kwargs),
        **context,
    )
    return HTMLResponse(html)
