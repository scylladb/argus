import functools
import os
import hashlib
from uuid import UUID
from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for, current_app
)
from werkzeug.security import check_password_hash
from argus.db.models import User

bp = Blueprint('auth', __name__, url_prefix='/auth')


@bp.route('/register', methods=('GET', 'POST'))
def register():
    return redirect(url_for("auth.login"))


@bp.route('/login', methods=('GET', 'POST'))
def login():
    token = hashlib.sha256((os.urandom(64))).hexdigest()
    session["csrf_token"] = token

    if request.method == 'POST':
        username = request.form["username"]
        password = request.form["password"]
        error = None
        try:
            user = User.get(username=username)
        except User.DoesNotExist:
            user = None

        if not user:
            error = "User not found"
        elif not check_password_hash(user.password, password):
            error = "Incorrect Password"

        if not error:
            session.clear()
            session["user_id"] = str(user.id)
            session["csrf_token"] = token
        flash(error, category="error")
        return redirect(url_for('main.home'))

    return render_template('auth/login.html.j2',
                           csrf_token=token,
                           github_cid=current_app.config.get("GITHUB_CLIENT_ID", "NO_CLIENT_ID"),
                           github_scopes="user:email read:user read:org"
                           )


@bp.before_app_request
def load_logged_in_user():
    user_id = session.get('user_id')

    if user_id is None:
        g.user = None  # pylint: disable=assigning-non-slot
    else:
        try:
            g.user = User.get(id=UUID(user_id))  # pylint: disable=assigning-non-slot
        except User.DoesNotExist:
            session.clear()


@bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('main.home'))


def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            flash(message='Unauthorized, please login', category='error')
            return redirect(url_for('auth.login'))

        return view(**kwargs)

    return wrapped_view


def check_roles(needed_roles: list[str] | str = None):
    def inner(view):
        @functools.wraps(view)
        def wrapped_view(**kwargs):
            def check_roles(roles, user):
                if isinstance(roles, str):
                    return roles in user.roles
                elif isinstance(roles, list):
                    for role in roles:
                        if role in user.roles:
                            return True
                return False

            if not check_roles(needed_roles, g.user):
                flash(message='Not authorized to access this area', category='error')
                return redirect(url_for('main.home'))

            return view(**kwargs)

        return wrapped_view
    return inner
