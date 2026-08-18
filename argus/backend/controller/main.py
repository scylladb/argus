import datetime
import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from flask import Blueprint
from starlette.responses import RedirectResponse, Response

from argus.backend.controller.notifications import bp as notifications_bp
from argus.backend.controller.team_ui import bp as teams_bp
from argus.backend.error_handlers import handle_profile_exception, handle_view_not_found
from argus.backend.models.web import ArgusRelease, User, WebFileStorage
from argus.backend.rendering import flash, render_template, url_for
from argus.backend.service.argus_service import ArgusService
from argus.backend.service.planner_service import PlanningService
from argus.backend.service.testrun import TestRunService
from argus.backend.service.user import UserService, UserServiceException, ui_current_user
from argus.backend.service.views import UserViewException, UserViewService

LOGGER = logging.getLogger(__name__)

router = APIRouter()


def _profile_redirect(asgi_request: Request) -> RedirectResponse:
    return RedirectResponse(url_for(asgi_request, "main.profile"), status_code=302)


def _error_redirect(asgi_request: Request, error_type: int) -> RedirectResponse:
    return RedirectResponse(url_for(asgi_request, "main.error", type=error_type), status_code=302)


@router.get("/test_runs", name="main.test_runs")
def test_runs(asgi_request: Request, user: User = Depends(ui_current_user)):
    return render_template(asgi_request, "test_runs.html.j2")


@router.get("/test_run/{run_id}", name="main.test_run")
def test_run(asgi_request: Request, run_id: UUID, user: User = Depends(ui_current_user)):
    return render_template(asgi_request, "test_run.html.j2", id=run_id)


@router.get("/test/{test_id}/runs", name="main.runs")
def runs(asgi_request: Request, test_id: UUID,
         additional_runs: list[str] = Query(default=[], alias="additionalRuns[]"),
         user: User = Depends(ui_current_user)):
    return render_template(asgi_request, "standalone_test_with_runs.html.j2",
                           test_id=test_id, additional_runs=additional_runs)


@router.get("/tests/{plugin_name}/{run_id}", name="main.get_run_by_plugin")
@router.get("/tests/{plugin_name}/{run_id}/{tab}", name="main.get_run_by_plugin")
def get_run_by_plugin(asgi_request: Request, plugin_name: str, run_id: str, tab: str = "details",
                      user: User = Depends(ui_current_user)):
    try:
        run_id = UUID(run_id)
    except ValueError:
        flash(asgi_request, message=f"Invalid UUID: {run_id}", category="error")
        return _error_redirect(asgi_request, 404)
    run = TestRunService().get_run(plugin_name, run_id)
    if not run:
        flash(asgi_request, f"Run {plugin_name}/{run_id} not found.", "error")
        return _error_redirect(asgi_request, 404)
    return render_template(asgi_request, "run_view_by_plugin.html.j2", run=run, tab=tab)


@router.get("/test/{build_id:path}/{build_number:int}/{tab}", name="main.get_run_by_build")
@router.get("/test/{build_id:path}/{build_number:int}", name="main.get_run_by_build")
def get_run_by_build(asgi_request: Request, build_id: str, build_number: int, tab: str = "details",
                     user: User = Depends(ui_current_user)):
    # Resolve a run from its build_system_id + Jenkins build number. This gives
    # a stable, clickable link that can be produced the moment a build starts —
    # even during the brief window before its run_id exists — and resolves once
    # the run has been reported to Argus.
    run = TestRunService().get_run_by_build_number(build_id, build_number)
    if not run:
        flash(asgi_request, f"Run {build_id} #{build_number} not found.", "error")
        return _error_redirect(asgi_request, 404)
    return render_template(asgi_request, "run_view_by_plugin.html.j2", run=run, tab=tab)


@router.get("/", name="main.home")
def home(asgi_request: Request):
    return RedirectResponse(url_for(asgi_request, "main.run_dashboard"), status_code=302)


@router.get("/run_dashboard", name="main.run_dashboard")
@router.get("/workspace", name="main.run_dashboard")
def run_dashboard(asgi_request: Request, user: User = Depends(ui_current_user)):
    return render_template(asgi_request, "dashboard.html.j2")


@router.get("/releases", name="main.releases")
def releases(asgi_request: Request, user: User = Depends(ui_current_user)):
    service = ArgusService()
    all_releases = service.get_releases()
    return render_template(asgi_request, "releases.html.j2", releases=all_releases)


@router.get("/views", name="main.views")
def views(asgi_request: Request, user: User = Depends(ui_current_user)):
    service = UserViewService()
    all_views = service.get_all_views()
    return render_template(asgi_request, "views.html.j2",
                           views=sorted(all_views, key=lambda view: view.created or datetime.datetime.fromtimestamp(0),
                                        reverse=True))


@router.get("/view/{view_name}", name="main.view_dashboard")
def view_dashboard(asgi_request: Request, view_name: str, user: User = Depends(ui_current_user)):
    service = UserViewService()
    view = service.get_view_by_name(view_name=view_name)
    data_json = view
    view.widget_settings = json.loads(view.widget_settings)
    return render_template(asgi_request, "view_dashboard.html.j2", data=data_json)


@router.get("/plan/{plan_id}", name="main.plan_dashboard")
def plan_dashboard(asgi_request: Request, plan_id: str, user: User = Depends(ui_current_user)):
    service = PlanningService()
    plan = service.get_plan(plan_id=plan_id)
    data_json = plan
    return render_template(asgi_request, "plan_dashboard.html.j2", data=data_json)


@router.get("/alert_debug", name="main.alert_debug")
def alert_debug(asgi_request: Request, alert_type: str = Query("success", alias="type"),
                message: str = Query("No message provided"),
                user: User = Depends(ui_current_user)):
    flash(asgi_request, message=message, category=alert_type)
    return render_template(asgi_request, "flash_debug.html.j2")


@router.get("/dashboard/{release_name:path}", name="main.release_dashboard")
def release_dashboard(asgi_request: Request, release_name: str, user: User = Depends(ui_current_user)):
    service = ArgusService()
    release, release_groups, release_tests = service.get_data_for_release_dashboard(
        release_name=release_name)
    data_json = {
        "release": release.model_dump(),
        "groups": [group.model_dump() for group in release_groups],
        "tests": [test.model_dump() for test in release_tests],
    }
    return render_template(asgi_request, "release_dashboard.html.j2", release_name=release_name, data=data_json)


@router.get("/release/{name}/scheduler", name="main.release_scheduler")
def release_scheduler(asgi_request: Request, name: str, user: User = Depends(ui_current_user)):
    service = ArgusService()
    release, release_groups, release_tests = service.get_data_for_release_dashboard(
        release_name=name)
    data_json = {
        "release": release.model_dump(),
        "groups": [group.model_dump() for group in release_groups],
        "tests": [test.model_dump() for test in release_tests],
    }
    return render_template(asgi_request, "release_schedule.html.j2", release_name=name, data=data_json)


@router.get("/release/by-id/{id}/planner", name="main.release_planner_by_id")
def release_planner_by_id(asgi_request: Request, id: UUID, user: User = Depends(ui_current_user)):
    release = ArgusRelease.get(id=id)
    return RedirectResponse(
        url_for(asgi_request, "main.release_planner", name=release.name), status_code=302)


@router.get("/release/{name}/planner", name="main.release_planner")
def release_planner(asgi_request: Request, name: str, user: User = Depends(ui_current_user)):
    service = PlanningService()
    planner_data = service.release_planner(name)
    return render_template(asgi_request, "release_planner.html.j2",
                           release_name=planner_data["release"].name, planner_data=planner_data)


@router.get("/release/{name}/duty", name="main.duty_planner")
def duty_planner(asgi_request: Request, name: str, user: User = Depends(ui_current_user)):
    service = ArgusService()
    release, release_groups, release_tests = service.get_data_for_release_dashboard(
        release_name=name)
    data_json = {
        "release": release.model_dump(),
        "groups": [group.model_dump() for group in release_groups],
        "tests": [test.model_dump() for test in release_tests],
    }
    return render_template(asgi_request, "duty_planner.html.j2", release_name=name, data=data_json)


@router.get("/error/", name="main.error")
def error(asgi_request: Request, error_type: str = Query("400", alias="type")):
    return render_template(asgi_request, "error.html.j2", type=error_type)


@router.get("/profile/", name="main.profile")
def profile(asgi_request: Request, user: User = Depends(ui_current_user)):
    first_run = asgi_request.session.pop("first_run_info", None)
    token_generated = asgi_request.session.pop("token_generated", None)

    return render_template(asgi_request, "profile.html.j2", first_run=first_run,
                           token_generated=token_generated)


@router.get("/profile/create", name="main.profile_user_create")
def profile_user_create(asgi_request: Request):
    if not asgi_request.session.get("registration_allowed", False):
        raise UserServiceException("Registration is not allowed at the moment.")
    return render_template(asgi_request, "create_user.html.j2", feedback={})


@router.post("/profile/create", name="main.profile_user_create")
def profile_user_create_post(asgi_request: Request, username: str = Form(...),
                             email: str = Form(...), full_name: str = Form(...),
                             avatar: UploadFile | None = File(None)):
    session = asgi_request.session
    if not session.get("registration_allowed", False):
        raise UserServiceException("Registration is not allowed at the moment.")
    if session.get("lock_user_email") and email != session.get("oauth_email"):
        raise UserServiceException("Email changed while being locked to oauth one.")
    result = UserService().create_user(
        username=username, email=email, full_name=full_name,
        avatar=(avatar.filename, avatar.file.read()) if avatar else None)
    if result["created"]:
        session.clear()
        session["user_id"] = str(result["user"].id)
        session["first_run_info"] = {
            "password": result["temp_password"],
            "first_login": True
        }
        return _profile_redirect(asgi_request)

    return render_template(asgi_request, "create_user.html.j2", feedback=result.get("form_feedback", {}))


@router.get("/profile/oauth/github", name="main.profile_oauth_github_callback")
def profile_oauth_github_callback(asgi_request: Request, state: str = Query(""),
                                  code: str = Query("WTF")):
    if state != asgi_request.session.get("csrf_token"):
        return _error_redirect(asgi_request, 403)

    service = UserService()
    try:
        first_run_info = service.github_callback(code, asgi_request.app.state.flask_app.config)
    except Exception as exc:
        LOGGER.error("An error occured in callback", exc_info=True)
        flash(asgi_request, message=exc.args[0], category="error")
        return _error_redirect(asgi_request, 403)
    if first_run_info:
        asgi_request.session["first_run_info"] = first_run_info

    if path := asgi_request.session.pop("redirect_target", None):
        return RedirectResponse(path, status_code=302)
    return _profile_redirect(asgi_request)


@router.get("/storage/picture/{picture_id}", name="main.get_picture")
def get_picture(asgi_request: Request, picture_id: UUID, user: User = Depends(ui_current_user)):
    headers = {"Cache-Control": "public, max-age=86400"}
    try:
        picture = WebFileStorage.get(id=picture_id)
        with open(picture.filepath, "rb") as file:
            return Response(file.read(), status_code=200, media_type="image/*", headers=headers)
    except FileNotFoundError:
        return Response("404 NOT FOUND", status_code=404, media_type="text/plain", headers=headers)


@router.post("/profile/update/picture", name="main.upload_file")
def upload_file(asgi_request: Request, filedata: UploadFile | None = File(None),
                user: User = Depends(ui_current_user)):
    if not filedata or not filedata.content_type.startswith("image/"):
        flash(asgi_request,
              message=f"Expected image/*, got {filedata.content_type if filedata else 'nothing'}",
              category="error")
        return _profile_redirect(asgi_request)
    picture_data = filedata.file.read()
    if not picture_data:
        flash(asgi_request, message="No picture provided", category="error")
        return _profile_redirect(asgi_request)

    service = UserService()
    filename, filepath = service.save_profile_picture_to_disk(
        filedata.filename, picture_data, user.username)
    service.update_profile_picture(filename, filepath, user)

    return _profile_redirect(asgi_request)


@router.post("/profile/update/name", name="main.update_full_name")
def update_full_name(asgi_request: Request, new_name: str | None = Form(None),
                     user: User = Depends(ui_current_user)):
    if not new_name:
        flash(asgi_request, message="Incorrect new name", category="error")
    else:
        service = UserService()
        service.update_name(user, new_name)
        flash(asgi_request, "Successfully changed name!", category="success")
    return _profile_redirect(asgi_request)


@router.post("/profile/update/username", name="main.update_user_name")
def update_user_name(asgi_request: Request, new_username: str | None = Form(None),
                     user: User = Depends(ui_current_user)):
    if not new_username:
        flash(asgi_request, message="Missing username in payload", category="error")
    else:
        service = UserService()
        service.change_username(user, new_username)
        flash(asgi_request, "Successfully changed username!", category="success")
    return _profile_redirect(asgi_request)


@router.post("/profile/update/email", name="main.update_email")
def update_email(asgi_request: Request, new_email: str | None = Form(None),
                 user: User = Depends(ui_current_user)):
    if not asgi_request.session.get("original_user") and not user.is_admin():
        flash(asgi_request, "Not authorized to change email.")
        return _profile_redirect(asgi_request)
    if not new_email:
        flash(asgi_request, "Incorrect new email", category="error")
    else:
        service = UserService()
        service.update_email(user, new_email)
        flash(asgi_request, "Successfully changed email!", category="success")
    return _profile_redirect(asgi_request)


@router.post("/profile/update/password", name="main.update_password")
def update_password(asgi_request: Request, old_password: str | None = Form(None),
                    new_password: str | None = Form(None),
                    new_password_confirm: str | None = Form(None),
                    user: User = Depends(ui_current_user)):
    if not old_password:
        flash(asgi_request, "Old password wasn't provided", category="error")
        return _profile_redirect(asgi_request)
    if not new_password:
        flash(asgi_request, "New password wasn't provided", category="error")
        return _profile_redirect(asgi_request)

    if not new_password == new_password_confirm:
        flash(asgi_request, "New password doesn't match confirmation!", category="error")
        return _profile_redirect(asgi_request)

    service = UserService()
    try:
        service.update_password(user, old_password=old_password, new_password=new_password)
    except Exception:
        flash(asgi_request, "Old password is incorrect", category="error")
        return _profile_redirect(asgi_request)

    flash(asgi_request, "Successfully changed password!")
    return _profile_redirect(asgi_request)


@router.get("/profile/jobs", name="main.profile_jobs")
def profile_jobs(asgi_request: Request, user: User = Depends(ui_current_user)):
    return render_template(asgi_request, "profile_jobs.html.j2")


@router.get("/profile/schedules", name="main.profile_schedules")
def profile_schedules(asgi_request: Request, user: User = Depends(ui_current_user)):
    service = ArgusService()
    schedules = service.get_schedules_for_user(user)
    return render_template(asgi_request, "profile_schedules.html.j2", schedules=schedules)


# The routes above are served by FastAPI; these view-less rules keep the
# endpoints buildable through Flask's url_for until the Flask app is retired.
bp = Blueprint('main', __name__)
bp.register_error_handler(UserServiceException, handle_profile_exception)
bp.register_error_handler(UserViewException, handle_view_not_found)
bp.register_blueprint(notifications_bp)
bp.register_blueprint(teams_bp)

for _rule, _endpoint in (
    ("/test_runs", "test_runs"),
    ("/test_run/<string:run_id>", "test_run"),
    ("/test/<string:test_id>/runs", "runs"),
    ("/tests/<string:plugin_name>/<string:run_id>", "get_run_by_plugin"),
    ("/test/<path:build_id>/<int:build_number>", "get_run_by_build"),
    ("/", "home"),
    ("/workspace", "run_dashboard"),
    ("/releases", "releases"),
    ("/views", "views"),
    ("/view/<string:view_name>", "view_dashboard"),
    ("/plan/<string:plan_id>", "plan_dashboard"),
    ("/alert_debug", "alert_debug"),
    ("/dashboard/<path:release_name>", "release_dashboard"),
    ("/release/<string:name>/scheduler", "release_scheduler"),
    ("/release/by-id/<string:id>/planner", "release_planner_by_id"),
    ("/release/<string:name>/planner", "release_planner"),
    ("/release/<string:name>/duty", "duty_planner"),
    ("/error/", "error"),
    ("/profile/", "profile"),
    ("/profile/create", "profile_user_create"),
    ("/profile/oauth/github", "profile_oauth_github_callback"),
    ("/storage/picture/<string:picture_id>", "get_picture"),
    ("/profile/update/picture", "upload_file"),
    ("/profile/update/name", "update_full_name"),
    ("/profile/update/username", "update_user_name"),
    ("/profile/update/email", "update_email"),
    ("/profile/update/password", "update_password"),
    ("/profile/jobs", "profile_jobs"),
    ("/profile/schedules", "profile_schedules"),
):
    bp.add_url_rule(_rule, _endpoint, None)
