import functools
import os
import hashlib
from datetime import datetime
from uuid import UUID
from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for, current_app
)
from werkzeug.security import check_password_hash, generate_password_hash
from argus.backend.models import User

bp = Blueprint('auth', __name__, url_prefix='/auth')


@bp.route('/register', methods=('GET', 'POST'))
def register():
    return redirect(url_for("auth.login"))
    # if request.method == 'POST':
    #     username = request.form['username']
    #     password = request.form['password']
    #     error = None

    #     if not username:
    #         error = 'Username is required.'
    #     elif not password:
    #         error = 'Password is required.'

    #     if error is None:
    #         try:
    #             user = User()
    #             user.username = username
    #             user.password = generate_password_hash(password)
    #             user.roles = ["ROLE_USER"]
    #             user.registration_date = datetime.now()
    #             user.email = "place@holder"
    #             user.save()
    #         except Exception as exc:
    #             error = f"Failure registering {username}:\n{exc}"
    #         else:
    #             return redirect(url_for("auth.login"))

    #     flash(error)

    # return render_template('auth/register.html.j2')


@bp.route('/login', methods=('GET', 'POST'))
def login():
    token = hashlib.sha256((os.urandom(64))).hexdigest()
    session["csrf_token"] = token

    if request.method == 'POST':
        username = request.form["username"]
        password = request.form["password"]
        error = None
        user = User.get(username=username)
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
        g.user = None
    else:
        try:
            g.user = User.get(id=UUID(user_id))
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
