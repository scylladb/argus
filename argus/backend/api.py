import time
import json
import logging
from uuid import UUID

from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for
)
from flask.json import jsonify
from argus.backend.argus_service import ArgusService
from argus.backend.auth import login_required

bp = Blueprint('api', __name__, url_prefix='/api/v1')
LOGGER = logging.getLogger(__name__)


@bp.route("/releases")
@login_required
def releases():
    service = ArgusService()
    releases = service.get_releases()
    service.terminate_session()
    return jsonify({
        "status": "ok",
        "response": [dict(d.items()) for d in releases]
    })


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
        service.terminate_session()
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
        tests = service.get_tests_for_release_group(
            group_id=request_payload["group"]["id"])
        res["response"] = {"tests": [dict(t.items()) for t in tests]}
        service.terminate_session()
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
        test_runs = service.get_runs_by_name_for_release_group(
            release_name=request_payload["release"], test_name=request_payload["test_name"], limit=request_payload.get("limit", 10))
        res["response"] = test_runs
        service.terminate_session()
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
        test_run, _ = service.load_test_run(
            test_run_id=UUID(request_payload["test_id"]))
        res["response"] = test_run.serialize()
        service.terminate_session()
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
        res["response"] = comments.to_json()
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
        res["response"] = result.to_json()
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
        request_payload = request.get_json()
        service = ArgusService()
        result = service.get_user_info(payload=request_payload)
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
