import json
import logging
from uuid import UUID
from flask import (
    Blueprint,
    g,
    make_response,
    request
)
from flask.json import jsonify
from argus.backend.controller.notification_api import bp as notifications_bp
from argus.backend.service.argus_service import ArgusService
from argus.backend.controller.auth import login_required
from argus.db.models import UserOauthToken

# pylint: disable=broad-except

bp = Blueprint('api', __name__, url_prefix='/api/v1')
bp.register_blueprint(notifications_bp)
LOGGER = logging.getLogger(__name__)


@bp.route("/version")
def version():
    service = ArgusService()
    argus_version = service.get_version()
    return jsonify({
        "status": "ok",
        "response": {
            "commit_id": argus_version
        }
    })


@bp.route("/profile/github/token")
@login_required
def get_github_oauth_token():
    res = {
        "status": "ok"
    }
    try:
        user_tokens = UserOauthToken.filter(user_id=g.user.id).all()
        for tok in user_tokens:
            if tok.kind == "github":
                res["response"] = tok.token
                break
        if not res.get("response"):
            raise Exception("Github token not found")
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    res = jsonify(res)
    res.cache_control.max_agGITHUB_ACCESS_TOKENe = 300

    return res


@bp.route("/releases")
@login_required
def releases():
    service = ArgusService()
    force_all = request.args.get("all", False)
    all_releases = service.get_releases()
    response = jsonify({
        "status": "ok",
        "response": [dict(d.items()) for d in all_releases if d.enabled or force_all]
    })

    response.cache_control.max_age = 300
    return response


@bp.route("/release/activity", methods=["GET"])
@login_required
def release_activity():
    res = {
        "status": "ok"
    }
    try:
        release_name = request.args.get("releaseName")
        if not release_name:
            raise Exception("Release name not specified in the request")
        service = ArgusService()
        res["response"] = service.fetch_release_activity(release_name)
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/release/planner/data", methods=["GET"])
@login_required
def release_planner_data():
    res = {
        "status": "ok"
    }
    try:
        release_id = request.args.get("releaseId")
        if not release_id:
            raise Exception("Release Id not specified")
        service = ArgusService()
        res["response"] = service.get_planner_data(release_id)
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/release/planner/comment/get/test")
def get_planner_comment_by_test():
    res = {
        "status": "ok"
    }
    try:
        test_id = request.args.get("id")
        if not test_id:
            raise Exception("TestId was not specified")
        service = ArgusService()
        res["response"] = service.get_planner_comment_by_test(UUID(test_id))
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }

    response = jsonify(res)
    response.cache_control.max_age = 1200
    return response


@bp.route("/release/schedules/comment/update", methods=["POST"])
@login_required
def release_schedules_comment_update():
    res = {
        "status": "ok"
    }
    try:
        if not request.is_json:
            raise Exception(
                "Content-Type mismatch, expected application/json, got:", request.content_type)
        request_payload = request.get_json()
        service = ArgusService()
        res["response"] = service.update_schedule_comment(request_payload)
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/release/schedules", methods=["GET"])
@login_required
def release_schedules():
    res = {
        "status": "ok"
    }
    try:
        release = request.args.get("releaseId")
        if not release:
            raise Exception("No releaseId provided")
        service = ArgusService()
        res["response"] = service.get_schedules_for_release(release)
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/release/schedules/assignee/update", methods=["POST"])
@login_required
def release_schedules_assignee_update():
    res = {
        "status": "ok"
    }
    try:
        if not request.is_json:
            raise Exception(
                "Content-Type mismatch, expected application/json, got:", request.content_type)
        request_payload = request.get_json()
        service = ArgusService()
        res["response"] = service.update_schedule_assignees(request_payload)
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/release/assignees/groups", methods=["GET"])
@login_required
def group_assignees():
    res = {
        "status": "ok"
    }
    try:
        release_id = request.args.get("releaseId")
        if not release_id:
            raise Exception("Missing releaseId")
        service = ArgusService()
        res["response"] = service.get_groups_assignees(release_id)
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/release/assignees/tests", methods=["GET"])
@login_required
def tests_assignees():
    res = {
        "status": "ok"
    }
    try:
        group_id = request.args.get("groupId")
        if not group_id:
            raise Exception("Missing groupId")
        service = ArgusService()
        res["response"] = service.get_tests_assignees(group_id)
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/release/schedules/submit", methods=["POST"])
@login_required
def release_schedules_submit():
    res = {
        "status": "ok"
    }
    try:
        if not request.is_json:
            raise Exception(
                "Content-Type mismatch, expected application/json, got:", request.content_type)
        j = request.get_json()
        service = ArgusService()
        res["response"] = service.submit_new_schedule(release=j["releaseId"], start_time=j["start"], end_time=j["end"],
                                                      tests=j["tests"], groups=j["groups"], assignees=j["assignees"], tag=j["tag"])
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/release/schedules/delete", methods=["POST"])
@login_required
def release_schedules_delete():
    res = {
        "status": "ok"
    }
    try:
        if not request.is_json:
            raise Exception(
                "Content-Type mismatch, expected application/json, got:", request.content_type)
        request_payload = request.get_json()
        service = ArgusService()
        res["response"] = service.delete_schedule(request_payload)
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/release/issues", methods=["POST"])
@login_required
def release_issues():
    # TODO: Unused
    res = {
        "status": "ok"
    }
    try:
        if not request.is_json:
            raise Exception(
                "Content-Type mismatch, expected application/json, got:", request.content_type)
        request_payload = request.get_json()
        service = ArgusService()
        res["response"] = service.fetch_release_issues(request_payload)
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/groups", methods=["GET"])
@login_required
def groups():
    res = {
        "status": "ok"
    }
    try:
        force_all = request.args.get("all", False)
        service = ArgusService()
        groups = service.get_groups()
        res["response"] = [dict(g.items()) for g in groups if g.enabled or force_all]
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    response = jsonify(res)
    response.cache_control.max_age = 300
    return response


@bp.route("/tests", methods=["GET"])
@login_required
def tests():
    res = {
        "status": "ok"
    }
    try:
        force_all = request.args.get("all", False)
        service = ArgusService()
        tests = service.get_tests()
        res["response"] = [dict(t.items()) for t in tests if t.enabled or force_all]
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    response = jsonify(res)
    response.cache_control.max_age = 300
    return response


@bp.route("/test_run", methods=["GET"])
@login_required
def test_run():
    res = {
        "status": "ok"
    }
    try:
        run_id = request.args.get("runId")
        service = ArgusService()
        loaded_run = service.load_test_run(
            test_run_id=UUID(run_id))
        res["response"] = loaded_run
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/test_run/comments", methods=["GET"])
@login_required
def test_run_comments():
    res = {
        "status": "ok"
    }
    try:
        test_id = request.args.get("testId")
        if not test_id:
            raise Exception("TestId wasn't specified in the request")
        service = ArgusService()
        comments = service.get_comments(test_id=UUID(test_id))
        res["response"] = [dict(c.items()) for c in comments]
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/test_run/comment/get", methods=["GET"])
@login_required
def get_test_run_comment():
    res = {
        "status": "ok"
    }
    try:
        comment_id = request.args.get("commentId")
        if not comment_id:
            raise Exception("commentId wasn't specified in the request")
        service = ArgusService()
        comment = service.get_comment(comment_id=UUID(comment_id))
        res["response"] = dict(comment.items()) if comment else False
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/test_run/comments/submit", methods=["POST"])
@login_required
def test_run_submit_comment():
    res = {
        "status": "ok"
    }
    try:
        if not request.is_json:
            raise Exception(
                "Content-Type mismatch, expected application/json, got:", request.content_type)
        request_payload = request.get_json()
        service = ArgusService()
        result = service.post_comment(payload=request_payload)
        res["response"] = [dict(c.items()) for c in result]
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/test_run/comments/update", methods=["POST"])
@login_required
def test_run_update_comment():
    res = {
        "status": "ok"
    }
    try:
        if not request.is_json:
            raise Exception(
                "Content-Type mismatch, expected application/json, got:", request.content_type)
        request_payload = request.get_json()
        service = ArgusService()
        result = service.update_comment(payload=request_payload)
        res["response"] = [dict(c.items()) for c in result]
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/test_run/comments/delete", methods=["POST"])
@login_required
def test_run_delete_comment():
    res = {
        "status": "ok"
    }
    try:
        if not request.is_json:
            raise Exception(
                "Content-Type mismatch, expected application/json, got:", request.content_type)
        request_payload = request.get_json()
        service = ArgusService()
        result = service.delete_comment(payload=request_payload)
        res["response"] = [dict(c.items()) for c in result]
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/users", methods=["GET"])
@login_required
def user_info():
    res = {
        "status": "ok"
    }
    try:
        result = ArgusService().get_user_info()
        res["response"] = result
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/release/stats", methods=["GET"])
@login_required
def release_stats():
    res = {
        "status": "ok"
    }
    try:
        request.query_string.decode(encoding="UTF-8")
        release = request.args.get("release")
        limited = bool(int(request.args.get("limited")))
        force = bool(int(request.args.get("force")))
        res["response"] = ArgusService().collect_stats(release, limited, force)
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        LOGGER.error("Details: ", exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    res = jsonify(res)
    res.cache_control.max_age = 60
    return res


@bp.route("/test_runs/poll", methods=["GET"])
@login_required
def test_runs_poll():
    res = {
        "status": "ok"
    }
    try:
        limit = request.args.get("limit")
        if not limit:
            limit = 10
        else:
            limit = int(limit)
        runs = request.args.get('runs')
        runs = runs.split(',')
        service = ArgusService()
        res["response"] = service.poll_test_runs(runs=runs, limit=limit)
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/test_run/poll", methods=["GET"])
@login_required
def test_run_poll_single():
    res = {
        "status": "ok"
    }
    try:
        runs = request.args.get("runs", "")
        runs = [UUID(r) for r in runs.split(",") if r]
        service = ArgusService()
        res["response"] = service.poll_test_runs_single(runs=runs)
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/test_run/change_status", methods=["POST"])
@login_required
def test_run_change_status():
    res = {
        "status": "ok"
    }
    try:
        if not request.is_json:
            raise Exception(
                "Content-Type mismatch, expected application/json, got:", request.content_type)
        request_payload = request.get_json()
        service = ArgusService()
        res["response"] = service.toggle_test_status(request_payload)
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/test_run/change_investigation_status", methods=["POST"])
@login_required
def test_run_change_investigation_status():
    res = {
        "status": "ok"
    }
    try:
        if not request.is_json:
            raise Exception(
                "Content-Type mismatch, expected application/json, got:", request.content_type)
        request_payload = request.get_json()
        service = ArgusService()
        res["response"] = service.toggle_test_investigation_status(request_payload)
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/test_run/change_assignee", methods=["POST"])
@login_required
def test_run_change_assignee():
    res = {
        "status": "ok"
    }
    try:
        if not request.is_json:
            raise Exception(
                "Content-Type mismatch, expected application/json, got:", request.content_type)
        request_payload = request.get_json()
        service = ArgusService()
        res["response"] = service.change_assignee(request_payload)
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/test_run/activity", methods=["GET"])
@login_required
def test_run_activity():
    res = {
        "status": "ok"
    }
    try:
        run_id = request.args.get("runId")
        if not run_id:
            raise Exception("RunId not provided in the request")
        else:
            run_id = UUID(run_id)
        service = ArgusService()
        res["response"] = service.fetch_run_activity(run_id=run_id)
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/release/create", methods=["POST"])
@login_required
def release_create():
    # TODO: Old
    res = {
        "status": "ok"
    }
    try:
        if not request.is_json:
            raise Exception(
                "Content-Type mismatch, expected application/json, got:", request.content_type)
        request_payload = request.get_json()
        service = ArgusService()
        res["response"] = service.create_release(request_payload)
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/issues/submit", methods=["POST"])
@login_required
def issues_submit():
    res = {
        "status": "ok"
    }
    try:
        if not request.is_json:
            raise Exception(
                "Content-Type mismatch, expected application/json, got:", request.content_type)
        request_payload = request.get_json()
        service = ArgusService()
        res["response"] = service.submit_github_issue(request_payload)
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        LOGGER.error("Details: ", exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/issues/get", methods=["GET"])
@login_required
def issues_get():
    res = {
        "status": "ok"
    }
    try:
        filter_key = request.args.get("filterKey")
        if not filter_key:
            raise Exception("Filter key not provided in the request")
        key_value = request.args.get("id")
        if not key_value:
            raise Exception("Id wasn't provided in the request")
        else:
            key_value = UUID(key_value)
        aggregate_by_issue = request.args.get("aggregateByIssue")
        aggregate_by_issue = bool(int(aggregate_by_issue)) if aggregate_by_issue else False
        service = ArgusService()
        res["response"] = service.get_github_issues(filter_key=filter_key,
                                                    filter_id=key_value,
                                                    aggregate_by_issue=aggregate_by_issue)
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/issues/delete", methods=["POST"])
@login_required
def issues_delete():
    res = {
        "status": "ok"
    }
    try:
        if not request.is_json:
            raise Exception(
                "Content-Type mismatch, expected application/json, got:", request.content_type)
        request_payload = request.get_json()
        service = ArgusService()
        res["response"] = service.delete_github_issue(request_payload)
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)
