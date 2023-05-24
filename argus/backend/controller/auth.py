import os
import hashlib
from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for, current_app
)
from werkzeug.security import check_password_hash
from argus.backend.models.web import User
from argus.backend.service.user import UserService, load_logged_in_user, login_required

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
                           github_scopes=current_app.config.get("GITHUB_SCOPES", "user:email read:user read:org repo")
                           )


@bp.route("/profile/api/token/generate", methods=("POST",))
@login_required
def generate_api_token():
    new_token = UserService().generate_token(g.user)
    session["token_generated"] = new_token
    return redirect(url_for('main.profile'))


@bp.route('/logout', methods=("POST",))
def logout():
    session.clear()
    return redirect(url_for('auth.login'))


bp.before_app_request(load_logged_in_user)
