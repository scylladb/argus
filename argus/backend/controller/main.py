import logging
from uuid import UUID
from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for, make_response
)
from argus.backend.controller.notifications import bp as notifications_bp
from argus.backend.controller.team_ui import bp as teams_bp
from argus.backend.service.argus_service import ArgusService
from argus.backend.models.web import WebFileStorage
from argus.backend.service.user import UserService, login_required

LOGGER = logging.getLogger(__name__)

bp = Blueprint('main', __name__)
bp.register_blueprint(notifications_bp)
bp.register_blueprint(teams_bp)


@bp.route("/test_runs")
@login_required
def test_runs():
    return render_template("test_runs.html.j2")


@bp.route("/test_run/<string:run_id>")
@login_required
def test_run(run_id: UUID):
    return render_template("test_run.html.j2", id=run_id)


@bp.route("/test/<string:test_id>/runs")
@login_required
def runs(test_id: UUID):
    additional_runs = request.args.getlist("additionalRuns[]")
    return render_template("standalone_test_with_runs.html.j2", test_id=test_id, additional_runs=additional_runs)


@bp.route("/")
def home():
    return redirect(url_for("main.run_dashboard"))


@bp.route("/run_dashboard")
@bp.route("/workspace")
@login_required
def run_dashboard():
    return render_template('dashboard.html.j2')


@bp.route("/releases")
@login_required
def releases():
    service = ArgusService()
    all_releases = service.get_releases()
    return render_template("releases.html.j2", releases=all_releases)


@bp.route("/alert_debug")
@login_required
def alert_debug():
    alert_type = request.args.get("type", "success")
    message = request.args.get("message", "No message provided")
    flash(message=message, category=alert_type)
    return render_template("flash_debug.html.j2")


@bp.route("/dashboard/<string:release_name>")
@login_required
def release_dashboard(release_name: str):
    service = ArgusService()
    release, release_groups, release_tests = service.get_data_for_release_dashboard(
        release_name=release_name)
    data_json = {
        "release": dict(release.items()),
        "groups": [dict(group.items()) for group in release_groups],
        "tests": [dict(test.items()) for test in release_tests],
    }
    return render_template("release_dashboard.html.j2", release_name=release_name, data=data_json)


@bp.route("/release/<string:name>/scheduler")
@login_required
def release_scheduler(name: str):
    service = ArgusService()
    release, release_groups, release_tests = service.get_data_for_release_dashboard(
        release_name=name)
    data_json = {
        "release": dict(release.items()),
        "groups": [dict(group.items()) for group in release_groups],
        "tests": [dict(test.items()) for test in release_tests],
    }
    return render_template("release_schedule.html.j2", release_name=name, data=data_json)


@bp.route("/release/<string:name>/duty")
@login_required
def duty_planner(name: str):
    service = ArgusService()
    release, release_groups, release_tests = service.get_data_for_release_dashboard(
        release_name=name)
    data_json = {
        "release": dict(release.items()),
        "groups": [dict(group.items()) for group in release_groups],
        "tests": [dict(test.items()) for test in release_tests],
    }
    return render_template("duty_planner.html.j2", release_name=name, data=data_json)


@bp.route("/error/")
def error():
    return render_template("error.html.j2", type=request.args.get("type", 400))


@bp.route("/profile/")
@login_required
def profile():
    first_run = session.pop("first_run_info", None)
    token_generated = session.pop("token_generated", None)

    return render_template("profile.html.j2", first_run=first_run, token_generated=token_generated)


@bp.route("/profile/oauth/github", methods=["GET"])
def profile_oauth_github_callback():
    req_state = request.args.get('state', '')
    if req_state != session["csrf_token"]:
        return redirect(url_for("main.error", type=403))

    req_code = request.args.get("code", "WTF")
    service = UserService()
    try:
        first_run_info = service.github_callback(req_code)
    except Exception as exc:  # pylint: disable=broad-except
        flash(message=exc.args[0], category="error")
        return redirect(url_for("main.error", type=403))
    if first_run_info:
        session["first_run_info"] = first_run_info

    if path := session.pop("redirect_target"):
        return redirect(path)
    return redirect(url_for("main.profile"))


@bp.route("/storage/picture/<string:picture_id>")
@login_required
def get_picture(picture_id: str):
    res = make_response()
    try:
        picture = WebFileStorage.get(id=picture_id)
        with open(picture.filepath, "rb") as file:
            res.set_data(file.read())
        res.content_type = "image/*"
        res.status = 200
    except FileNotFoundError:  # pylint: disable=broad-except
        res.status = 404
        res.content_type = "text/plain"
        res.set_data("404 NOT FOUND")

    res.cache_control.max_age = 86400
    res.cache_control.public = True
    return res


@bp.route("/profile/update/picture", methods=["POST"])
@login_required
def upload_file():
    req_file = request.files.get("filedata")
    picture_data = req_file.stream.read()
    picture_name = req_file.filename
    if not req_file.content_type.startswith("image/"):
        flash(
            message=f"Expected image/*, got {req_file.content_type}", category="error")
        return redirect(url_for("main.profile"))
    if not picture_data:
        flash(message="No picture provided", category="error")
        return redirect(url_for("main.profile"))

    service = UserService()
    filename, filepath = service.save_profile_picture_to_disk(
        picture_name, picture_data, g.user.username)
    service.update_profile_picture(filename, filepath)

    return redirect(url_for("main.profile"))


@bp.route("/profile/update/name", methods=["POST"])
@login_required
def update_full_name():
    new_name = request.values.get("new_name")
    if not new_name:
        flash(message="Incorrect new name", category="error")
    else:
        service = UserService()
        service.update_name(g.user, new_name)
        flash("Successfully changed name!", category="success")
    return redirect(url_for("main.profile"))


@bp.route("/profile/update/email", methods=["POST"])
@login_required
def update_email():
    new_email = request.values.get("new_email")
    if not new_email:
        flash("Incorrect new email", category="error")
    else:
        service = UserService()
        service.update_email(g.user, new_email)
        flash("Successfully changed email!", category="success")
    return redirect(url_for("main.profile"))


@bp.route("/profile/update/password", methods=["POST"])
@login_required
def update_password():
    old_password = request.values.get("old_password")
    new_password = request.values.get("new_password")
    new_password_confirm = request.values.get("new_password_confirm")
    if not old_password:
        flash("Old password wasn't provided", category="error")
        return redirect(url_for("main.profile"))
    if not new_password:
        flash("New password wasn't provided", category="error")
        return redirect(url_for("main.profile"))

    if not new_password == new_password_confirm:
        flash("New password doesn't match confirmation!", category="error")
        return redirect(url_for("main.profile"))

    service = UserService()
    try:
        service.update_password(
            g.user, old_password=old_password, new_password=new_password)
    except Exception:  # pylint: disable=broad-except
        flash("Old password is incorrect", category="error")
        return redirect(url_for("main.profile"))

    flash("Successfully changed password!")
    return redirect(url_for("main.profile"))


@bp.route("/profile/jobs", methods=["GET"])
@login_required
def profile_jobs():
    return render_template("profile_jobs.html.j2")


@bp.route("/profile/schedules", methods=["GET"])
@login_required
def profile_schedules():
    service = ArgusService()
    schedules = service.get_schedules_for_user(g.user)
    return render_template("profile_schedules.html.j2", schedules=schedules)
