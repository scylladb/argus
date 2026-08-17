"""Auth dependencies mirroring the Flask decorators in service/user.py.

Resolution order is identical to load_logged_in_user: ``Authorization:
token`` header first, then the session's ``user_id``, else anonymous.
``api_current_user`` is the FastAPI counterpart of ``@api_login_required``
(the UI redirect flavor arrives with the server-rendered pages migration);
``require_roles`` mirrors ``@check_roles`` for API views.

Response shapes and status codes match the Flask decorators exactly.
"""
import logging
from uuid import UUID

from fastapi import Depends, Request
from starlette.responses import JSONResponse

from coodie.exceptions import DocumentNotFound

from argus.backend.error_handlers import APIException
from argus.backend.models.web import User, UserRoles
from argus.backend.service.user import UserService, is_ssh_tunnel_server_user

LOGGER = logging.getLogger(__name__)


class AuthorizationError(Exception):
    """Raised by auth dependencies; rendered by authorization_error_handler."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def authorization_error_handler(request: Request, exc: AuthorizationError) -> JSONResponse:
    return JSONResponse({"status": "error", "message": exc.message}, status_code=403)


def load_user(request: Request) -> User | None:
    """Resolve the request's user; sets request.state.user as a side effect."""
    user = None
    auth_header = request.headers.get("Authorization")
    if auth_header:
        try:
            auth_schema, *auth_data = auth_header.split()
            if auth_schema == "token":
                user = User.get(api_token=auth_data[0])
        except IndexError as exception:
            raise APIException("Malformed authorization header") from exception
        except DocumentNotFound as exception:
            raise APIException("User not found for supplied token") from exception

    if not user and (user_id := request.session.get("user_id")):
        try:
            user = User.get(id=UUID(user_id))
        except DocumentNotFound:
            request.session.clear()

    request.state.user = user
    return user


def api_current_user(request: Request, user: User | None = Depends(load_user)) -> User:
    """FastAPI counterpart of @api_login_required."""
    if user is None:
        raise AuthorizationError("Authorization required")
    if is_ssh_tunnel_server_user(user) and not _is_tunnel_scope_allowed(request):
        raise AuthorizationError("Authorization required")
    return user


def require_roles(needed_roles: list[UserRoles] | UserRoles):
    """FastAPI counterpart of @check_roles for API views."""

    def dependency(user: User = Depends(api_current_user)) -> User:
        if not UserService.check_roles(needed_roles, user):
            raise AuthorizationError("Forbidden")
        return user

    return dependency


def allow_ssh_tunnel_server_scope(route_func):
    """Route marker mirroring the Flask decorator of the same name."""
    route_func.allow_ssh_tunnel_server_scope = True
    return route_func


def _is_tunnel_scope_allowed(request: Request) -> bool:
    endpoint = request.scope.get("endpoint")
    return bool(getattr(endpoint, "allow_ssh_tunnel_server_scope", False))
