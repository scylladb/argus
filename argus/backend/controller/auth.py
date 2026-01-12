import os
import hashlib
from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for, current_app
)
from werkzeug.security import check_password_hash
from argus.backend.models.web import User, UserRoles
from argus.backend.service.user import UserService, UserServiceException, check_roles, load_logged_in_user, login_required

bp = Blueprint('auth', __name__, url_prefix='/auth')


@bp.route('/register', methods=('GET', 'POST'))
def register():
    return redirect(url_for("auth.login"))


@bp.route('/login', methods=('GET', 'POST'))
def login():
    if g.user:
        if redirect_target := session.pop("redirect_target", None):
            return redirect(redirect_target)
        return redirect(url_for("main.home"))

    token = hashlib.sha256((os.urandom(64))).hexdigest()
    session["csrf_token"] = token

    if request.method == 'POST':
        try:
            if "password" not in current_app.config.get("LOGIN_METHODS", []):
                raise UserServiceException("Password Login is disabled")
            username = request.form["username"]
            password = request.form["password"]

            try:
                user: User = User.get(username=username)
            except User.DoesNotExist:
                raise UserServiceException("User not found")

            if not check_password_hash(user.password, password):
                raise UserServiceException("Incorrect Password")

            session.clear()
            session["user_id"] = str(user.id)
            session["csrf_token"] = token
        except UserServiceException as exc:
            flash(next(iter(exc.args), "No message"), category="error")

        return redirect(url_for('main.home'))

    return render_template('auth/login.html.j2',
                           csrf_token=token,
                           github_cid=current_app.config.get("GITHUB_CLIENT_ID", "NO_CLIENT_ID"),
                           github_scopes=current_app.config.get("GITHUB_SCOPES", "user:email read:user read:org")
                           )


@bp.route("/login/cf", methods=("POST",))
def cf_login():
    if not UserService().cf_login():
        flash("Error logging in", category="error")
        session["manual_logout"] = True
        return redirect(url_for("auth.login"))

    if redirect_target := session.pop("redirect_target", None):
        return redirect(redirect_target)
    return redirect(url_for("main.home"))


@bp.route("/profile/api/token/generate", methods=("POST",))
@login_required
def generate_api_token():
    new_token = UserService().generate_token(g.user)
    session["token_generated"] = new_token
    return redirect(url_for('main.profile'))


@bp.route('/admin/impersonate', methods=("POST","GET"))
@check_roles(UserRoles.Admin)
def switch_user():

    if request.method == 'POST':
        try:
            user_id = request.form["user_id"]
        except KeyError:
            flash("No user id", category="error")
            return redirect(url_for('main.profile'))
        UserService().set_user_impersonation(user_id)
        return redirect(url_for('main.profile'))

    users = UserService().get_users_privileged()

    return render_template('auth/user_switch.html.j2', users=users)


@bp.route('/admin/impersonate/stop', methods=("POST",))
def stop_impersonation():

    UserService().stop_user_impersonation()
    return redirect(url_for('main.profile'))



@bp.route('/logout', methods=("POST",))
def logout():
    session.clear()
    session["manual_logout"] = True
    return redirect(url_for('auth.login'))


bp.before_app_request(load_logged_in_user)
