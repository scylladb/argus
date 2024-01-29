import logging
from uuid import UUID
import requests
from flask import (
    Blueprint,
    g,
    request
)
from flask.json import jsonify
from argus.backend.error_handlers import handle_api_exception
from argus.backend.controller.notification_api import bp as notifications_bp
from argus.backend.controller.client_api import bp as client_bp
from argus.backend.controller.testrun_api import bp as testrun_bp
from argus.backend.controller.team import bp as team_bp
from argus.backend.service.argus_service import ArgusService
from argus.backend.service.user import UserService, api_login_required
from argus.backend.service.stats import ReleaseStatsCollector
from argus.backend.models.web import ArgusRelease, ArgusGroup, ArgusTest, User, UserOauthToken
from argus.backend.util.common import get_payload

bp = Blueprint('api', __name__, url_prefix='/api/v1')
bp.register_blueprint(notifications_bp)
bp.register_blueprint(client_bp)
bp.register_blueprint(testrun_bp)
bp.register_blueprint(team_bp)
bp.register_error_handler(Exception, handle_api_exception)
LOGGER = logging.getLogger(__name__)


@bp.route("/version")
def app_version():
    service = ArgusService()
    argus_version = service.get_version()
    return jsonify({
        "status": "ok",
        "response": {
            "commit_id": argus_version
        }
    })


@bp.route("/profile/github/token")
@api_login_required
def get_github_oauth_token():
    user_tokens = UserOauthToken.filter(user_id=g.user.id).all()
    token = None
    for tok in user_tokens:
        if tok.kind == "github":
            token = tok.token
            break
    if not token:
        raise Exception("Github token not found")

    res = jsonify({
        "status": "ok",
        "response": token
    })
    res.cache_control.max_age = 300

    return res


@bp.route("/releases")
@api_login_required
def releases():
    service = ArgusService()
    force_all = request.args.get("all", False)
    all_releases = service.get_releases()
    response = jsonify({
        "status": "ok",
        "response": [dict(d.items()) for d in all_releases if d.enabled or force_all]
    })

    response.cache_control.max_age = 60
    return response


@bp.route("/release/activity", methods=["GET"])
@api_login_required
def release_activity():
    release_name = request.args.get("releaseName")
    if not release_name:
        raise Exception("Release name not specified in the request")
    service = ArgusService()
    activity_data = service.fetch_release_activity(release_name)

    return jsonify({
        "status": "ok",
        "response": activity_data
    })


@bp.route("/release/planner/data", methods=["GET"])
@api_login_required
def release_planner_data():

    release_id = request.args.get("releaseId")
    if not release_id:
        raise Exception("Release Id not specified")
    service = ArgusService()
    planner_data = service.get_planner_data(release_id)
    return jsonify({
        "status": "ok",
        "response": planner_data
    })


@bp.route("/release/<string:release_id>/versions")
@api_login_required
def release_versions(release_id: str):
    release_id = UUID(release_id)
    service = ArgusService()
    distinct_versions = service.get_distinct_release_versions(release_id=release_id)

    return jsonify({
        "status": "ok",
        "response": distinct_versions
    })


@bp.route("/release/planner/comment/get/test")
def get_planner_comment_by_test():
    test_id = request.args.get("id")
    if not test_id:
        raise Exception("TestId was not specified")
    service = ArgusService()
    planner_comments_by_test = service.get_planner_comment_by_test(UUID(test_id))

    response = jsonify({
        "status": "ok",
        "response": planner_comments_by_test
    })
    response.cache_control.max_age = 60
    return response


@bp.route("/release/schedules/comment/update", methods=["POST"])
@api_login_required
def release_schedules_comment_update():
    if not request.is_json:
        raise Exception(
            "Content-Type mismatch, expected application/json, got:", request.content_type)
    request_payload = request.get_json()
    service = ArgusService()
    comment_update_result = service.update_schedule_comment(request_payload)

    return jsonify({
        "status": "ok",
        "response": comment_update_result
    })


@bp.route("/release/schedules", methods=["GET"])
@api_login_required
def release_schedules():
    release = request.args.get("releaseId")
    if not release:
        raise Exception("No releaseId provided")
    service = ArgusService()
    release_schedules_data = service.get_schedules_for_release(release)

    return jsonify({
        "status": "ok",
        "response": release_schedules_data
    })


@bp.route("/release/schedules/assignee/update", methods=["POST"])
@api_login_required
def release_schedules_assignee_update():
    if not request.is_json:
        raise Exception(
            "Content-Type mismatch, expected application/json, got:", request.content_type)
    request_payload = request.get_json()
    service = ArgusService()
    assignee_update_status = service.update_schedule_assignees(request_payload)

    return jsonify({
        "status": "ok",
        "response": assignee_update_status
    })


@bp.route("/release/assignees/groups", methods=["GET"])
@api_login_required
def group_assignees():
    release_id = request.args.get("releaseId")
    if not release_id:
        raise Exception("Missing releaseId")
    service = ArgusService()
    group_assignees_list = service.get_groups_assignees(release_id)

    return jsonify({
        "status": "ok",
        "response": group_assignees_list
    })


@bp.route("/release/assignees/tests", methods=["GET"])
@api_login_required
def tests_assignees():
    group_id = request.args.get("groupId")
    if not group_id:
        raise Exception("Missing groupId")
    service = ArgusService()
    tests_assignees_list = service.get_tests_assignees(group_id)

    return jsonify({
        "status": "ok",
        "response": tests_assignees_list
    })


@bp.route("/release/schedules/submit", methods=["POST"])
@api_login_required
def release_schedules_submit():
    if not request.is_json:
        raise Exception(
            "Content-Type mismatch, expected application/json, got:", request.content_type)
    payload = request.get_json()
    service = ArgusService()
    schedule_submit_result = service.submit_new_schedule(
        release=payload["releaseId"],
        start_time=payload["start"],
        end_time=payload["end"],
        tests=payload["tests"],
        groups=payload["groups"],
        assignees=payload["assignees"],
        tag=payload["tag"],
    )

    return jsonify({
        "status": "ok",
        "response": schedule_submit_result
    })


@bp.route("/release/schedules/delete", methods=["POST"])
@api_login_required
def release_schedules_delete():
    if not request.is_json:
        raise Exception(
            "Content-Type mismatch, expected application/json, got:", request.content_type)
    request_payload = request.get_json()
    service = ArgusService()
    schedule_delete_result = service.delete_schedule(request_payload)

    return jsonify({
        "status": "ok",
        "response": schedule_delete_result
    })


@bp.route("/groups", methods=["GET"])
@api_login_required
def argus_groups():
    release_id = request.args.get("releaseId")
    if not release_id:
        raise Exception("No releaseId provided")

    force_all = request.args.get("all", False)
    service = ArgusService()
    groups = service.get_groups(UUID(release_id))
    result_groups = [dict(g.items()) for g in groups if g.enabled or force_all]

    response = jsonify({
        "status": "ok",
        "response": result_groups
    })
    response.cache_control.max_age = 60
    return response


@bp.route("/tests", methods=["GET"])
@api_login_required
def argus_tests():
    group_id = request.args.get("groupId")
    if not group_id:
        raise Exception("No groupId provided")
    force_all = request.args.get("all", False)
    service = ArgusService()
    tests = service.get_tests(group_id=group_id)
    result_tests = [dict(t.items()) for t in tests if t.enabled or force_all]

    response = jsonify({
        "status": "ok",
        "response": result_tests
    })
    response.cache_control.max_age = 60
    return response


@bp.route("/release/<string:release_id>/details", methods=["GET"])
@api_login_required
def get_release_details(release_id: str):
    release = ArgusRelease.get(id=UUID(release_id))
    response = jsonify({
        "status": "ok",
        "response": release,
    })
    response.cache_control.max_age = 60
    return response


@bp.route("/group/<string:group_id>/details", methods=["GET"])
@api_login_required
def get_group_details(group_id: str):
    group = ArgusGroup.get(id=UUID(group_id))
    response = jsonify({
        "status": "ok",
        "response": group,
    })
    response.cache_control.max_age = 60
    return response


@bp.route("/test/<string:test_id>/details", methods=["GET"])
@api_login_required
def get_test_details(test_id: str):
    test = ArgusTest.get(id=UUID(test_id))
    response = jsonify({
        "status": "ok",
        "response": test
    })
    response.cache_control.max_age = 60
    return response


@bp.route("/test/<string:test_id>/set_plugin", methods=["POST"])
@api_login_required
def set_test_plugin(test_id: str):
    payload = get_payload(request)

    current_user: User = g.user
    test: ArgusTest = ArgusTest.get(id=UUID(test_id))
    test.plugin_name = payload["plugin_name"]
    test.save()

    return {
        "status": "ok",
        "response": test
    }


@bp.route("/test-info", methods=["GET"])
@api_login_required
def test_info():
    test_id = request.args.get("testId")
    if not test_id:
        raise Exception("No testId provided")
    service = ArgusService()
    info = service.get_test_info(test_id=UUID(test_id))

    return {
        "status": "ok",
        "response": info
    }


@bp.route("/test_run/comment/get", methods=["GET"])  # TODO: remove
@api_login_required
def get_test_run_comment():
    comment_id = request.args.get("commentId")
    if not comment_id:
        raise Exception("commentId wasn't specified in the request")
    service = ArgusService()
    comment = service.get_comment(comment_id=UUID(comment_id))
    return jsonify({
        "status": "ok",
        "response": comment if comment else False
    })


@bp.route("/users", methods=["GET"])
@api_login_required
def user_info():
    result = UserService().get_users()

    return jsonify({
        "status": "ok",
        "response": result
    })


@bp.route("/release/stats/v2", methods=["GET"])
@api_login_required
def release_stats_v2():
    request.query_string.decode(encoding="UTF-8")
    release = request.args.get("release")
    limited = bool(int(request.args.get("limited")))
    version = request.args.get("productVersion", None)
    include_no_version = bool(int(request.args.get("includeNoVersion", True)))
    force = bool(int(request.args.get("force")))
    stats = ReleaseStatsCollector(
        release_name=release, release_version=version).collect(limited=limited, force=force, include_no_version=include_no_version)

    res = jsonify({
        "status": "ok",
        "response": stats
    })
    res.cache_control.max_age = 300
    return res


@bp.route("/test_runs/poll", methods=["GET"])
@api_login_required
def test_runs_poll():
    limit = request.args.get("limit")
    if not limit:
        limit = 10
    else:
        limit = int(limit)
    test_id = UUID(request.args.get('testId'))
    additional_runs = [UUID(run) for run in request.args.getlist('additionalRuns[]')]
    service = ArgusService()
    runs = service.poll_test_runs(test_id=test_id, additional_runs=additional_runs, limit=limit)

    return jsonify({
        "status": "ok",
        "response": runs
    })


@bp.route("/test_run/poll", methods=["GET"])
@api_login_required
def test_run_poll_single():
    runs = request.args.get("runs", "")
    runs = [UUID(r) for r in runs.split(",") if r]
    service = ArgusService()
    test_runs = service.poll_test_runs_single(runs=runs)

    return jsonify({
        "status": "ok",
        "response": test_runs
    })


@bp.route("/release/create", methods=["POST"])
@api_login_required
def release_create():
    if not request.is_json:
        raise Exception(
            "Content-Type mismatch, expected application/json, got:", request.content_type)
    request_payload = request.get_json()
    service = ArgusService()
    result = service.create_release(request_payload)

    return jsonify({
        "status": "ok",
        "response": result
    })


@bp.route("/artifact/resolveSize")
@api_login_required
def resolve_artifact_size():
    link = request.args.get("l")
    if not link:
        raise Exception("No link provided")

    res = requests.head(link)

    if res.status_code != 200:
        raise Exception("Error requesting resource")

    length = res.headers.get("Content-Length")
    if length:
        length = int(length)

    return {
        "status": "ok",
        "response": {
            "artifactSize": length,
        }
    }


@bp.route("/user/jobs")
@api_login_required
def user_jobs():
    service = ArgusService()
    result = list(service.get_jobs_for_user(user=g.user))

    return {
        "status": "ok",
        "response": result
    }
