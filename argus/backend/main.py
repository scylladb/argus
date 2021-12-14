import base64
from datetime import datetime
import os
import hashlib
import datetime
import time
import json
from uuid import UUID
import requests
from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for, current_app, make_response
)
from cassandra.cqlengine.models import _DoesNotExist
from werkzeug.security import generate_password_hash
from argus.backend.argus_service import ArgusService
from argus.backend.models import UserOauthToken, User, WebFileStorage
from argus.backend.auth import login_required

bp = Blueprint('main', __name__)


@bp.route("/test_runs")
@login_required
def test_runs():
    return render_template("test_runs.html.j2")


@bp.route("/test_run/<string:id>")
@login_required
def test_run(id: UUID):
    return render_template("test_run.html.j2", id=id)


@bp.route("/")
def home():
    return redirect(url_for("main.run_dashboard"))


@bp.route("/run_dashboard")
@login_required
def run_dashboard():
    return render_template('dashboard.html.j2')


@bp.route("/releases")
@login_required
def releases():
    service = ArgusService()
    releases = service.get_releases()
    return render_template("releases.html.j2", releases=releases)


@bp.route("/alert_debug")
@login_required
def alert_debug():
    type = request.args.get("type", "success")
    message = request.args.get("message", "No message provided")
    flash(message=message, category=type)
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


@bp.route("/release/<string:name>/<string:group>")
@login_required
def runs(name: str, group: str):
    service = ArgusService()
    show_all = request.args.get("show_all")
    limit = 9999 if bool(show_all) else 10
    runs = service.get_runs_for_release_group(
        release_name=name, group_name=group, limit=limit)
    service.terminate_session()
    return render_template("runs.html.j2", runs=runs, requested_all=bool(all))


@bp.route("/release/<string:name>/<string:group>/tests")
@login_required
def tests(name: str, group: str):
    service = ArgusService()
    tests, _ = service.get_tests_for_release_group(
        release_name=name, group_name=group)
    service.terminate_session()
    return render_template("tests.html.j2", tests=tests, release_name=name, group_name=group)


@bp.route("/release/<string:name>/<string:group>/<string:test>")
@login_required
def runs_by_name(name: str, group: str, test: str):
    service = ArgusService()
    show_all = request.args.get("show_all")
    limit = 9999 if bool(show_all) else 10
    runs = service.get_runs_by_name_for_release_group(
        test_name=test, release_name=name, group_name=group, limit=limit)
    service.terminate_session()
    return render_template("runs.html.j2", runs=runs, requested_all=bool(all))


@bp.route("/error/")
def error():
    return render_template("error.html.j2", type=request.args.get("type", 400))


@bp.route("/profile/")
@login_required
def profile():
    return render_template("profile.html.j2")


@bp.route("/profile/oauth/github", methods=["GET"])
def profile_oauth_github_callback():
    req_state = request.args.get('state', '')
    if req_state != session["csrf_token"]:
        return redirect(url_for("main.error", type=403))

    req_code = request.args.get("code", "WTF")
    service = ArgusService()
    service.github_callback(req_code)

    return redirect(url_for("main.profile"))


@bp.route("/storage/picture/<string:id>")
@login_required
def get_picture(id: str):
    res = make_response()
    try:
        picture = WebFileStorage.get(id=id)
        with open(picture.filepath, "rb") as file:
            res.set_data(file.read())
        res.content_type = "image/*"
        res.status = 200
    except:
        res.status = 404
        res.content_type = "text/plain"
        res.set_data("404 NOT FOUND")

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

    service = ArgusService()
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
        service = ArgusService()
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
        service = ArgusService()
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

    if not (new_password == new_password_confirm):
        flash("New password doesn't match confirmation!", category="error")
        return redirect(url_for("main.profile"))

    service = ArgusService()
    try:
        service.update_password(
            g.user, old_password=old_password, new_password=new_password)
    except:
        flash("Old password is incorrect", category="error")
        return redirect(url_for("main.profile"))

    flash("Successfully changed password!")
    return redirect(url_for("main.profile"))


@bp.route("/profile/jobs", methods=["GET"])
@login_required
def profile_jobs():
    return redirect(url_for("main.profile"))


@bp.route("/profile/schedules", methods=["GET"])
@login_required
def profile_schedules():
    return redirect(url_for("main.profile"))
