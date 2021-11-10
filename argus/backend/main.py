import time
from uuid import UUID

from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for
)
from argus.backend.argus_service import ArgusService
from argus.backend.auth import login_required

bp = Blueprint('main', __name__)

@bp.route("/test_runs")
@login_required
def test_runs():
    results = ArgusService().get_test_table()
    return render_template("test_runs.html.j2", test_runs=results, timestamp=int(time.time()))


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
    service.terminate_session()
    return render_template("releases.html.j2", releases=releases)


@bp.route("/release/<string:name>")
@login_required
def release(name: str):
    service = ArgusService()
    groups = service.get_groups_for_release(release_name=name)
    service.terminate_session()
    return render_template("groups.html.j2", groups=groups, release_name=name)


@bp.route("/release/<string:name>/<string:group>")
@login_required
def runs(name: str, group: str):
    service = ArgusService()
    show_all = request.args.get("show_all")
    limit = 9999 if bool(show_all) else 10
    runs = service.get_runs_for_release_group(release_name=name, group_name=group, limit=limit)
    service.terminate_session()
    return render_template("runs.html.j2", runs=runs, requested_all=bool(all))


@bp.route("/release/<string:name>/<string:group>/tests")
@login_required
def tests(name: str, group: str):
    service = ArgusService()
    tests, _ = service.get_tests_for_release_group(release_name=name, group_name=group)
    service.terminate_session()
    return render_template("tests.html.j2", tests=tests, release_name=name, group_name=group)

@bp.route("/release/<string:name>/<string:group>/<string:test>")
@login_required
def runs_by_name(name: str, group: str, test: str):
    service = ArgusService()
    show_all = request.args.get("show_all")
    limit = 9999 if bool(show_all) else 10
    runs = service.get_runs_by_name_for_release_group(test_name=test, release_name=name, group_name=group, limit=limit)
    service.terminate_session()
    return render_template("runs.html.j2", runs=runs, requested_all=bool(all))

