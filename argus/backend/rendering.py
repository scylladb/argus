"""Template rendering for FastAPI-served UI pages.

A single ``Jinja2Templates`` instance over the repo-root ``templates/``
(filters from template_filters.py, the argus JSON encoder behind
``tojson``). A context processor supplies the globals templates rely on:
``url_for`` builds from the app's named routes, ``g`` carries the request's
user, ``session`` is the request session, and flash messages live under
``_flashes`` in it.

``register_app`` is called by create_app so code that renders outside any
request (notification/email bodies, background jobs) can build URLs and
read config through the same environment.
"""
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote, urlencode

from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader
from starlette.convertors import PathConvertor
from starlette.routing import NoMatchFound

from argus.backend.template_filters import export_filters
from argus.backend.util.encoders import ArgusJSONProvider

FLASHES_SESSION_KEY = "_flashes"
TEMPLATES_DIR = Path(__file__).parents[2] / "templates"

_asgi_app: FastAPI | None = None


def _autoescape(template_name: str | None) -> bool:
    # Flask parity: only bare markup extensions are escaped — the *.j2
    # templates were written for an unescaped environment.
    if template_name is None:
        return True
    return template_name.endswith((".html", ".htm", ".xml", ".xhtml", ".svg"))


def _default_context(asgi_request: Request) -> dict:
    return {
        "session": asgi_request.session,
        "g": SimpleNamespace(user=getattr(asgi_request.state, "user", None)),
        "config": asgi_request.app.state.config,
        "url_for": lambda endpoint, **values: build_url(asgi_request.app, endpoint, **values),
        "get_flashed_messages": lambda **kwargs: get_flashed_messages(asgi_request, **kwargs),
    }


def _build_environment() -> Environment:
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=_autoescape)
    env.policies["json.dumps_kwargs"] = {"sort_keys": True, "default": ArgusJSONProvider.default}
    for filter_func in export_filters():
        env.filters[filter_func.filter_name] = filter_func
    return env


templates = Jinja2Templates(env=_build_environment(), context_processors=[_default_context])


def register_app(app: FastAPI) -> None:
    """Called by create_app: makes the app (routes for url_for) and its config
    available to code that renders outside any request."""
    global _asgi_app
    _asgi_app = app


def _iter_routes(routes):
    """Walk the route tree — FastAPI wraps app-level include_router calls in
    lazy _IncludedRouter entries instead of flattening them."""
    for route in routes:
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            yield from _iter_routes(original_router.routes)
        else:
            yield route


def build_url(app: FastAPI, endpoint: str, **values) -> str:
    """Build a URL from the app's named routes; values that are not path
    params become the query string (Flask's append_unknown behavior).

    The route scan only discovers each candidate's path-param names — the
    URL itself comes from app.url_path_for, which resolves include prefixes.
    Same-named routes may differ in path params (Flask allowed multiple
    rules per endpoint): the most specific rule the values satisfy wins.
    """
    candidates = [route for route in _iter_routes(app.routes) if getattr(route, "name", None) == endpoint]
    for route in sorted(candidates, key=lambda route: len(route.param_convertors), reverse=True):
        convertors = route.param_convertors
        if not convertors.keys() <= values.keys():
            continue
        path_params = {}
        for name, convertor in convertors.items():
            value = str(values[name])
            if not isinstance(convertor, PathConvertor):
                # Flask's string converter percent-encoded slashes when
                # building; starlette asserts on them instead.
                value = quote(value, safe="")
            path_params[name] = value
        path = app.url_path_for(endpoint, **path_params)
        query = {name: value for name, value in values.items() if name not in convertors}
        return f"{path}?{urlencode(query)}" if query else str(path)
    raise NoMatchFound(endpoint, values)


def url_for(asgi_request: Request, endpoint: str, **values) -> str:
    return build_url(asgi_request.app, endpoint, **values)


def render_background_template(template_name: str, **context) -> str:
    """Render a template outside any request context (notification and email
    bodies). url_for and config come from the registered app."""
    if _asgi_app is None:
        raise RuntimeError("register_app was not called — no application to build URLs from")
    template = templates.get_template(template_name)
    return template.render(
        url_for=lambda endpoint, **values: build_url(_asgi_app, endpoint, **values),
        config=_asgi_app.state.config,
        **context,
    )


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
