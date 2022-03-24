import logging
from uuid import UUID
from flask import (
    Blueprint,
    request
)
from flask.json import jsonify
from argus.backend.argus_service import ArgusService
from argus.backend.auth import login_required

# pylint: disable=broad-except

bp = Blueprint('api', __name__, url_prefix='/api/v1')
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


@bp.route("/releases")
@login_required
def releases():
    service = ArgusService()
    all_releases = service.get_releases()
    return jsonify({
        "status": "ok",
        "response": [dict(d.items()) for d in all_releases]
    })


@bp.route("/release/activity", methods=["POST"])
@login_required
def release_activity():
    res = {
        "status": "ok"
    }
    try:
        if not request.is_json:
            raise Exception(
                "Content-Type mismatch, expected application/json, got:", request.content_type)
        request_payload = request.get_json()
        service = ArgusService()
        res["response"] = service.fetch_release_activity(request_payload)
    except Exception as exc:
        LOGGER.error("Something happened during request %s", request)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/release/planner/data", methods=["POST"])
@login_required
def release_planner_data():
    res = {
        "status": "ok"
    }
    try:
        if not request.is_json:
            raise Exception(
                "Content-Type mismatch, expected application/json, got:", request.content_type)
        request_payload = request.get_json()
        service = ArgusService()
        res["response"] = service.get_planner_data(request_payload)
    except Exception as exc:
        LOGGER.error("Something happened during request %s", request)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


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
        LOGGER.error("Something happened during request %s", request)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/release/schedules", methods=["POST"])
@login_required
def release_schedules():
    res = {
        "status": "ok"
    }
    try:
        if not request.is_json:
            raise Exception(
                "Content-Type mismatch, expected application/json, got:", request.content_type)
        request_payload = request.get_json()
        service = ArgusService()
        res["response"] = service.get_schedules_for_release(request_payload)
    except Exception as exc:
        LOGGER.error("Something happened during request %s", request)
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
        LOGGER.error("Something happened during request %s", request)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/release/schedules/today/assignees", methods=["POST"])
@login_required
def release_schedules_today_assignees():
    res = {
        "status": "ok"
    }
    try:
        if not request.is_json:
            raise Exception(
                "Content-Type mismatch, expected application/json, got:", request.content_type)
        request_payload = request.get_json()
        service = ArgusService()
        res["response"] = service.get_assignees(request_payload)
    except Exception as exc:
        LOGGER.error("Something happened during request %s", request)
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
        request_payload = request.get_json()
        service = ArgusService()
        res["response"] = service.submit_new_schedule(request_payload)
    except Exception as exc:
        LOGGER.error("Something happened during request %s", request)
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
        LOGGER.error("Something happened during request %s", request)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/release/issues", methods=["POST"])
@login_required
def release_issues():
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
        LOGGER.error("Something happened during request %s", request)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/release_groups", methods=["POST"])
@login_required
def release_groups():
    res = {
        "status": "ok"
    }
    try:
        if not request.is_json:
            raise Exception(
                "Content-Type mismatch, expected application/json, got:", request.content_type)
        request_payload = request.get_json()
        service = ArgusService()
        groups = service.get_groups_for_release(
            UUID(request_payload["release"]["id"]))
        res["response"] = [dict(g.items()) for g in groups]
    except Exception as exc:
        LOGGER.error("Something happened during request %s", request)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/tests", methods=["POST"])
@login_required
def tests():
    res = {
        "status": "ok"
    }
    try:
        if not request.is_json:
            raise Exception(
                "Content-Type mismatch, expected application/json, got:", request.content_type)
        request_payload = request.get_json()
        service = ArgusService()
        release_group_tests = service.get_tests_for_release_group(
            group_id=request_payload["group"]["id"])
        res["response"] = {"tests": [dict(t.items()) for t in release_group_tests]}
    except Exception as exc:
        LOGGER.error("Something happened during request %s", request)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/tests/last_status", methods=["POST"])
@login_required
def tests_last_status():
    res = {
        "status": "ok"
    }
    try:
        if not request.is_json:
            raise Exception(
                "Content-Type mismatch, expected application/json, got:", request.content_type)
        request_payload = request.get_json()
        service = ArgusService()
        res["response"] = service.get_test_last_run_status(request_payload)
    except Exception as exc:
        LOGGER.error("Something happened during request %s", request)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/test_runs", methods=["POST"])
@login_required
def test_runs():
    res = {
        "status": "ok"
    }
    try:
        if not request.is_json:
            raise Exception(
                "Content-Type mismatch, expected application/json, got:", request.content_type)
        request_payload = request.get_json()
        service = ArgusService()
        release_group_runs = service.get_runs_by_name_for_release_group(
            release_name=request_payload["release"],
            test_name=request_payload["test_name"],
            limit=request_payload.get("limit", 10)
        )
        res["response"] = release_group_runs
    except Exception as exc:
        LOGGER.error("Something happened during request %s", request)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/test_run", methods=["POST"])
@login_required
def test_run():
    res = {
        "status": "ok"
    }
    try:
        if not request.is_json:
            raise Exception(
                "Content-Type mismatch, expected application/json, got:", request.content_type)
        request_payload = request.get_json()
        service = ArgusService()
        loaded_run = service.load_test_run(
            test_run_id=UUID(request_payload["test_id"]))
        res["response"] = loaded_run.serialize()
    except Exception as exc:
        LOGGER.error("Something happened during request %s", request)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/test_run/comments", methods=["POST"])
@login_required
def test_run_comments():
    res = {
        "status": "ok"
    }
    try:
        if not request.is_json:
            raise Exception(
                "Content-Type mismatch, expected application/json, got:", request.content_type)
        request_payload = request.get_json()
        service = ArgusService()
        comments = service.get_comments(
            test_id=UUID(request_payload["test_id"]))
        res["response"] = [dict(c.items()) for c in comments]
    except Exception as exc:
        LOGGER.error("Something happened during request %s", request)
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
        LOGGER.error("Something happened during request %s", request)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/users", methods=["POST"])
@login_required
def user_info():
    res = {
        "status": "ok"
    }
    try:
        if not request.is_json:
            raise Exception(
                "Content-Type mismatch, expected application/json, got:", request.content_type)
        service = ArgusService()
        result = service.get_user_info()
        res["response"] = result
    except Exception as exc:
        LOGGER.error("Something happened during request %s", request)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/stats", methods=["POST"])
@login_required
def run_stats():
    res = {
        "status": "ok"
    }
    try:
        if not request.is_json:
            raise Exception(
                "Content-Type mismatch, expected application/json, got:", request.content_type)
        request_payload = request.get_json()
        service = ArgusService()
        res["response"] = service.collect_stats(request_payload)
    except Exception as exc:
        LOGGER.error("Something happened during request %s", request)
        LOGGER.error("Details: ", exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/test_runs/poll", methods=["POST"])
@login_required
def test_runs_poll():
    res = {
        "status": "ok"
    }
    try:
        if not request.is_json:
            raise Exception(
                "Content-Type mismatch, expected application/json, got:", request.content_type)
        request_payload = request.get_json()
        service = ArgusService()
        res["response"] = service.poll_test_runs(request_payload)
    except Exception as exc:
        LOGGER.error("Something happened during request %s", request)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/test_run/poll", methods=["POST"])
@login_required
def test_run_poll_single():
    res = {
        "status": "ok"
    }
    try:
        if not request.is_json:
            raise Exception(
                "Content-Type mismatch, expected application/json, got:", request.content_type)
        request_payload = request.get_json()
        service = ArgusService()
        res["response"] = service.poll_test_runs_single(request_payload)
    except Exception as exc:
        LOGGER.error("Something happened during request %s", request)
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
        LOGGER.error("Something happened during request %s", request)
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
        LOGGER.error("Something happened during request %s", request)
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
        LOGGER.error("Something happened during request %s", request)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/test_run/activity", methods=["POST"])
@login_required
def test_run_activity():
    res = {
        "status": "ok"
    }
    try:
        if not request.is_json:
            raise Exception(
                "Content-Type mismatch, expected application/json, got:", request.content_type)
        request_payload = request.get_json()
        service = ArgusService()
        res["response"] = service.fetch_run_activity(request_payload)
    except Exception as exc:
        LOGGER.error("Something happened during request %s", request)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/release/create", methods=["POST"])
@login_required
def release_create():
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
        LOGGER.error("Something happened during request %s", request)
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
        LOGGER.error("Something happened during request %s", request)
        LOGGER.error("Details: ", exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/issues/get", methods=["POST"])
@login_required
def issues_get():
    res = {
        "status": "ok"
    }
    try:
        if not request.is_json:
            raise Exception(
                "Content-Type mismatch, expected application/json, got:", request.content_type)
        request_payload = request.get_json()
        service = ArgusService()
        res["response"] = service.get_github_issues(request_payload)
    except Exception as exc:
        LOGGER.error("Something happened during request %s", request)
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
        LOGGER.error("Something happened during request %s", request)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/issues/state", methods=["POST"])
@login_required
def issues_state():
    res = {
        "status": "ok"
    }
    try:
        if not request.is_json:
            raise Exception(
                "Content-Type mismatch, expected application/json, got:", request.content_type)
        request_payload = request.get_json()
        service = ArgusService()
        res["response"] = service.get_github_issue_state(request_payload)
    except Exception as exc:
        LOGGER.error("Something happened during request %s", request)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)
