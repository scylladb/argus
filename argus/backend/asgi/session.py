"""Flask-compatible session support for the FastAPI side of the strangler.

During the migration both frameworks serve routes in the same browsing
session, so they must share one session cookie. This middleware reuses
Flask's own SecureCookieSessionInterface serializer (same SECRET_KEY, salt
and payload format), making the cookie byte-compatible in both directions:
sessions created by the Flask login flow are readable here, and vice versa.

The session dict is exposed as ``request.scope["session"]`` / Starlette's
``request.session``. The cookie is only (re)written when a handler actually
mutates the session, so requests that fall through to the Flask mount keep
Flask in charge of its own cookie handling.
"""
import logging

from flask import Flask
from flask.sessions import SecureCookieSessionInterface
from itsdangerous import BadSignature

LOGGER = logging.getLogger(__name__)


class FlaskSessionMiddleware:
    def __init__(self, app, flask_app: Flask):
        self.app = app
        interface = SecureCookieSessionInterface()
        self.serializer = interface.get_signing_serializer(flask_app)
        self.cookie_name = flask_app.config.get("SESSION_COOKIE_NAME") or "session"
        self.max_age = int(flask_app.permanent_session_lifetime.total_seconds())
        self.cookie_path = flask_app.config.get("SESSION_COOKIE_PATH") or "/"
        self.cookie_secure = bool(flask_app.config.get("SESSION_COOKIE_SECURE"))

    def _load(self, scope) -> dict:
        cookies = {}
        for name, value in scope["headers"]:
            if name == b"cookie":
                for chunk in value.decode("latin-1").split(";"):
                    key, _, val = chunk.strip().partition("=")
                    cookies[key] = val
        raw = cookies.get(self.cookie_name)
        if not raw or self.serializer is None:
            return {}
        try:
            return dict(self.serializer.loads(raw, max_age=self.max_age))
        except BadSignature:
            return {}

    def _cookie_header(self, session: dict) -> bytes:
        if session:
            value = self.serializer.dumps(dict(session))
            cookie = f"{self.cookie_name}={value}; HttpOnly; Path={self.cookie_path}"
        else:
            cookie = (f"{self.cookie_name}=; HttpOnly; Path={self.cookie_path}; "
                      "Expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=0")
        if self.cookie_secure:
            cookie += "; Secure"
        return cookie.encode("latin-1")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        initial = self._load(scope)
        scope["session"] = dict(initial)

        async def send_wrapper(message):
            if message["type"] == "http.response.start" and scope["session"] != initial:
                headers = list(message.setdefault("headers", []))
                headers.append((b"set-cookie", self._cookie_header(scope["session"])))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)
