import functools
import os
import base64
from uuid import UUID
from time import time
from hashlib import sha384

from flask import flash, g, redirect, request, session, url_for

from argus.backend.db import ScyllaCluster
from argus.backend.error_handlers import APIException
from argus.backend.models.web import User, UserRoles
from argus.backend.util.common import FlaskView


class UserService:
    # pylint: disable=no-self-use
    def __init__(self) -> None:
        self.cluster = ScyllaCluster.get()
        self.session = self.cluster.session

    @staticmethod
    def check_roles(roles: list[UserRoles] | UserRoles, user: User) -> bool:
        if isinstance(roles, str):
            return roles in user.roles
        elif isinstance(roles, list):
            for role in roles:
                if role in user.roles:
                    return True
        return False

    def generate_token(self, user: User):
        token_digest = f"{user.username}-{int(time())}-{base64.encodebytes(os.urandom(128)).decode(encoding='utf-8')}"
        new_token = base64.encodebytes(sha384(token_digest.encode(encoding="utf-8")
                                              ).digest()).decode(encoding="utf-8").strip()
        user.api_token = new_token
        user.save()
        return new_token


def login_required(view: FlaskView):
    @functools.wraps(view)
    def wrapped_view(*args, **kwargs):
        if g.user is None and not getattr(view, "api_view", False):
            flash(message='Unauthorized, please login', category='error')
            return redirect(url_for('auth.login'))
        elif g.user is None and getattr(view, "api_view", True):
            return {
                "status": "error",
                "message": "Authorization required"
            }, 403

        return view(*args, **kwargs)

    return wrapped_view


def api_login_required(view: FlaskView):
    view.api_view = True
    return login_required(view)


def check_roles(needed_roles: list[str] | str = None):
    def inner(view: FlaskView):
        @functools.wraps(view)
        def wrapped_view(*args, **kwargs):
            if not UserService.check_roles(needed_roles, g.user):
                flash(message='Not authorized to access this area', category='error')
                return redirect(url_for('main.home'))

            return view(*args, **kwargs)

        return wrapped_view
    return inner


def load_logged_in_user():
    user_id = session.get('user_id')
    auth_header = request.headers.get("Authorization")

    if user_id:
        try:
            g.user = User.get(id=UUID(user_id))  # pylint: disable=assigning-non-slot
            return
        except User.DoesNotExist:
            session.clear()

    if auth_header:
        try:
            auth_schema, *auth_data = auth_header.split()
            if auth_schema == "token":
                token = auth_data[0]
                g.user = User.get(api_token=token)
                return
        except IndexError as exception:
            raise APIException("Malformed authorization header") from exception
        except User.DoesNotExist as exception:
            raise APIException("User not found for supplied token") from exception
    g.user = None  # pylint: disable=assigning-non-slot
