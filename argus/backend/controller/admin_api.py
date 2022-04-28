import logging
from uuid import UUID
from flask import (
    Blueprint,
    request,
    Request,
)
from flask.json import jsonify
from argus.backend.service.release_manager import ReleaseManagerService
from argus.backend.controller.auth import login_required, check_roles
from argus.db.models import UserRoles

# pylint: disable=broad-except
bp = Blueprint('admin_api', __name__, url_prefix='/api/v1')
LOGGER = logging.getLogger(__name__)


def get_payload(client_request: Request):
    if not client_request.is_json:
        raise Exception(
            "Content-Type mismatch, expected application/json, got:", client_request.content_type)
    request_payload = client_request.get_json()

    return request_payload


@bp.route("/", methods=["GET"])
@check_roles(UserRoles.Admin)
@login_required
def index():
    return jsonify({
        "version": "v1"
    })


@bp.route("/release/create", methods=["POST"])
@check_roles(UserRoles.Admin)
@login_required
def create_release():
    res = {
        "status": "ok"
    }
    try:
        payload = get_payload(request)
        release = ReleaseManagerService().create_release(**payload)
        res["response"] = {
            "new_release": dict(release.items())
        }
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/release/set_perpetual", methods=["POST"])
@check_roles(UserRoles.Admin)
@login_required
def set_release_perpetual():
    res = {
        "status": "ok"
    }
    try:
        payload = get_payload(request)
        result = ReleaseManagerService().set_release_perpetuality(**payload)
        res["response"] = {
            "updated": result
        }
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/release/set_state", methods=["POST"])
@check_roles(UserRoles.Admin)
@login_required
def set_release_state():
    res = {
        "status": "ok"
    }
    try:
        payload = get_payload(request)
        result = ReleaseManagerService().set_release_state(**payload)
        res["response"] = {
            "updated": result
        }
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/release/set_dormant", methods=["POST"])
@check_roles(UserRoles.Admin)
@login_required
def set_release_dormancy():
    res = {
        "status": "ok"
    }
    try:
        payload = get_payload(request)
        result = ReleaseManagerService().set_release_dormancy(**payload)
        res["response"] = {
            "updated": result
        }
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/group/create", methods=["POST"])
@check_roles(UserRoles.Admin)
@login_required
def create_group():
    res = {
        "status": "ok"
    }
    try:
        payload = get_payload(request)
        group = ReleaseManagerService().create_group(**payload)
        res["response"] = {
            "new_group": dict(group.items())
        }
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/group/update", methods=["POST"])
@check_roles(UserRoles.Admin)
@login_required
def update_group():
    res = {
        "status": "ok"
    }
    try:
        payload = get_payload(request)
        result = ReleaseManagerService().update_group(**payload)
        res["response"] = {
            "updated": result
        }
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/group/delete", methods=["POST"])
@check_roles(UserRoles.Admin)
@login_required
def delete_group():
    res = {
        "status": "ok"
    }
    try:
        payload = get_payload(request)
        result = ReleaseManagerService().delete_group(**payload)
        res["response"] = {
            "deleted": result
        }
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/test/create", methods=["POST"])
@check_roles(UserRoles.Admin)
@login_required
def create_test():
    res = {
        "status": "ok"
    }
    try:
        payload = get_payload(request)
        test = ReleaseManagerService().create_test(**payload)
        res["response"] = {
            "new_test": dict(test.items())
        }
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/test/update", methods=["POST"])
@check_roles(UserRoles.Admin)
@login_required
def update_test():
    res = {
        "status": "ok"
    }
    try:
        payload = get_payload(request)
        result = ReleaseManagerService().update_test(**payload)
        res["response"] = {
            "updated": result
        }
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/test/batch_move", methods=["POST"])
@check_roles(UserRoles.Admin)
@login_required
def batch_move_tests():
    res = {
        "status": "ok"
    }
    try:
        payload = get_payload(request)
        result = ReleaseManagerService().batch_move_tests(**payload)
        res["response"] = {
            "moved": result
        }
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/test/delete", methods=["POST"])
@check_roles(UserRoles.Admin)
@login_required
def delete_test():
    res = {
        "status": "ok"
    }
    try:
        payload = get_payload(request)
        result = ReleaseManagerService().delete_test(**payload)
        res["response"] = {
            "deleted": result
        }
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/releases/get", methods=["GET"])
@check_roles(UserRoles.Admin)
@login_required
def get_releases():
    res = {
        "status": "ok"
    }
    try:
        releases = ReleaseManagerService().get_releases()
        res["response"] = [dict(r.items()) for r in releases]
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/groups/get", methods=["GET"])
@check_roles(UserRoles.Admin)
@login_required
def get_groups_for_release():
    res = {
        "status": "ok"
    }
    try:
        release_id = request.args.get("releaseId")
        if not release_id:
            raise Exception("ReleaseId not provided in the request")
        groups = ReleaseManagerService().get_groups(release_id=UUID(release_id))
        res["response"] = [dict(g.items()) for g in groups]
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/tests/get", methods=["GET"])
@check_roles(UserRoles.Admin)
@login_required
def get_tests_for_group():
    res = {
        "status": "ok"
    }
    try:
        group_id = request.args.get("groupId")
        if not group_id:
            raise Exception("GroupId not provided in the request")
        tests = ReleaseManagerService().get_tests(group_id=UUID(group_id))
        res["response"] = [dict(t.items()) for t in tests]
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)
