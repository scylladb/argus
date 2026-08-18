import os
import hashlib

from fastapi import APIRouter, Depends, Form, Header, Request
from flask import Blueprint
from starlette.responses import RedirectResponse
from werkzeug.security import check_password_hash
from coodie.exceptions import DocumentNotFound

from argus.backend.models.web import User, UserRoles
from argus.backend.rendering import flash, render_template, url_for
from argus.backend.service.user import (
    UserService,
    UserServiceException,
    load_logged_in_user,
    load_user,
    ui_current_user,
    ui_require_roles,
)

router = APIRouter(prefix="/auth")


def _authenticated_redirect(asgi_request: Request) -> RedirectResponse:
    if redirect_target := asgi_request.session.pop("redirect_target", None):
        return RedirectResponse(redirect_target, status_code=302)
    return RedirectResponse(url_for(asgi_request, "main.home"), status_code=302)


@router.get("/register", name="auth.register")
@router.post("/register", name="auth.register")
def register(asgi_request: Request):
    return RedirectResponse(url_for(asgi_request, "auth.login"), status_code=302)


@router.get("/login", name="auth.login")
def login(asgi_request: Request, user: User | None = Depends(load_user)):
    if user:
        return _authenticated_redirect(asgi_request)

    token = hashlib.sha256(os.urandom(64)).hexdigest()
    asgi_request.session["csrf_token"] = token
    config = asgi_request.app.state.flask_app.config
    return render_template(
        asgi_request, "auth/login.html.j2",
        csrf_token=token,
        github_cid=config.get("GITHUB_CLIENT_ID", "NO_CLIENT_ID"),
        github_scopes=config.get("GITHUB_SCOPES", "user:email read:user read:org"),
    )


@router.post("/login", name="auth.login")
def login_post(asgi_request: Request, username: str = Form(...), password: str = Form(...),
               user: User | None = Depends(load_user)):
    if user:
        return _authenticated_redirect(asgi_request)

    token = hashlib.sha256(os.urandom(64)).hexdigest()
    asgi_request.session["csrf_token"] = token
    config = asgi_request.app.state.flask_app.config
    try:
        if "password" not in config.get("LOGIN_METHODS", []):
            raise UserServiceException("Password Login is disabled")
        try:
            account: User = User.get(username=username)
        except DocumentNotFound:
            raise UserServiceException("User not found")

        if not check_password_hash(account.password, password):
            raise UserServiceException("Incorrect Password")

        asgi_request.session.clear()
        asgi_request.session["user_id"] = str(account.id)
        asgi_request.session["csrf_token"] = token
    except UserServiceException as exc:
        flash(asgi_request, next(iter(exc.args), "No message"), category="error")

    return RedirectResponse(url_for(asgi_request, "main.home"), status_code=302)


@router.post("/login/cf", name="auth.cf_login")
def cf_login(asgi_request: Request,
             cf_access_jwt: str | None = Header(None, alias="Cf-Access-Jwt-Assertion")):
    config = asgi_request.app.state.flask_app.config
    res = UserService().cf_login_or_register(cf_access_jwt, asgi_request.session, config)
    if not res["redirect_optional"]:
        return RedirectResponse(url_for(asgi_request, res["redirect_to"]), status_code=302)
    if redirect_target := asgi_request.session.pop("redirect_target", None):
        return RedirectResponse(redirect_target, status_code=302)
    return RedirectResponse(url_for(asgi_request, res["redirect_to"]), status_code=302)


@router.post("/profile/api/token/generate", name="auth.generate_api_token")
def generate_api_token(asgi_request: Request, user: User = Depends(ui_current_user)):
    new_token = UserService().generate_token(user)
    asgi_request.session["token_generated"] = new_token
    return RedirectResponse(url_for(asgi_request, "main.profile"), status_code=302)


@router.get("/admin/impersonate", name="auth.switch_user")
def switch_user(asgi_request: Request, user: User = Depends(ui_require_roles(UserRoles.Admin))):
    users = UserService().get_users_privileged(service_only=True)
    return render_template(asgi_request, "auth/user_switch.html.j2", users=users)


@router.post("/admin/impersonate", name="auth.switch_user")
def switch_user_post(asgi_request: Request, user_id: str | None = Form(None),
                     user: User = Depends(ui_require_roles(UserRoles.Admin))):
    if not user_id:
        flash(asgi_request, "No user id", category="error")
        return RedirectResponse(url_for(asgi_request, "main.profile"), status_code=302)
    UserService().set_user_impersonation(user_id, asgi_request.session, user)
    return RedirectResponse(url_for(asgi_request, "main.profile"), status_code=302)


@router.post("/admin/impersonate/stop", name="auth.stop_impersonation")
def stop_impersonation(asgi_request: Request, user: User = Depends(ui_current_user)):
    UserService().stop_user_impersonation(asgi_request.session)
    return RedirectResponse(url_for(asgi_request, "main.profile"), status_code=302)


@router.post("/logout", name="auth.logout")
def logout(asgi_request: Request):
    asgi_request.session.clear()
    asgi_request.session["manual_logout"] = True
    return RedirectResponse(url_for(asgi_request, "auth.login"), status_code=302)


# The routes above are served by FastAPI; these view-less rules keep the
# endpoints buildable through Flask's url_for until the Flask app is retired.
bp = Blueprint('auth', __name__, url_prefix='/auth')
for _rule, _endpoint in (
    ("/register", "register"),
    ("/login", "login"),
    ("/login/cf", "cf_login"),
    ("/profile/api/token/generate", "generate_api_token"),
    ("/admin/impersonate", "switch_user"),
    ("/admin/impersonate/stop", "stop_impersonation"),
    ("/logout", "logout"),
):
    bp.add_url_rule(_rule, _endpoint, None)

bp.before_app_request(load_logged_in_user)
