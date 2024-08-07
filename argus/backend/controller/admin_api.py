import logging
from uuid import UUID
from flask import (
    Blueprint,
    request,
    Request,
)
from argus.backend.error_handlers import handle_api_exception
from argus.backend.service.release_manager import ReleaseEditPayload, ReleaseManagerService
from argus.backend.service.user import UserService, api_login_required, check_roles
from argus.backend.models.web import User, UserRoles

bp = Blueprint('admin_api', __name__, url_prefix='/api/v1')
LOGGER = logging.getLogger(__name__)
bp.register_error_handler(Exception, handle_api_exception)


def get_payload(client_request: Request):
    if not client_request.is_json:
        raise Exception(
            "Content-Type mismatch, expected application/json, got:", client_request.content_type)
    request_payload = client_request.get_json()

    return request_payload


@bp.route("/", methods=["GET"])
@check_roles(UserRoles.Admin)
@api_login_required
def index():
    return {
        "version": "v1"
    }


@bp.route("/release/create", methods=["POST"])
@check_roles(UserRoles.Admin)
@api_login_required
def create_release():
    payload = get_payload(request)
    release = ReleaseManagerService().create_release(**payload)

    return {
        "status": "ok",
        "response": {
            "new_release": release
        }
    }


@bp.route("/release/set_perpetual", methods=["POST"])
@check_roles(UserRoles.Admin)
@api_login_required
def set_release_perpetual():
    payload = get_payload(request)
    result = ReleaseManagerService().set_release_perpetuality(**payload)
    return {
        "status": "ok",
        "response": {
            "updated": result
        }
    }


@bp.route("/release/set_state", methods=["POST"])
@check_roles(UserRoles.Admin)
@api_login_required
def set_release_state():
    payload = get_payload(request)
    result = ReleaseManagerService().set_release_state(**payload)

    return {
        "status": "ok",
        "response": {
            "updated": result
        }
    }


@bp.route("/release/set_dormant", methods=["POST"])
@check_roles(UserRoles.Admin)
@api_login_required
def set_release_dormancy():
    payload = get_payload(request)
    result = ReleaseManagerService().set_release_dormancy(**payload)

    return {
        "status": "ok",
        "response": {
            "updated": result
        }
    }


@bp.route("/release/edit", methods=["POST"])
@check_roles(UserRoles.Admin)
@api_login_required
def edit_release():
    payload: ReleaseEditPayload = get_payload(request)
    result = ReleaseManagerService().edit_release(payload)

    return {
        "status": "ok",
        "response": {
            "updated": result
        }
    }


@bp.route("/release/delete", methods=["POST"])
@check_roles(UserRoles.Admin)
@api_login_required
def delete_release():
    payload = get_payload(request)
    result = ReleaseManagerService().delete_release(release_id=payload["releaseId"])

    return {
        "status": "ok",
        "response": {
            "deleted": result
        }
    }


@bp.route("/group/create", methods=["POST"])
@check_roles(UserRoles.Admin)
@api_login_required
def create_group():
    payload = get_payload(request)
    group = ReleaseManagerService().create_group(**payload)

    return {
        "status": "ok",
        "response": {
            "new_group": group
        }
    }


@bp.route("/group/update", methods=["POST"])
@check_roles(UserRoles.Admin)
@api_login_required
def update_group():
    payload = get_payload(request)
    result = ReleaseManagerService().update_group(**payload)
    return {
        "status": "ok",
        "response": {
            "updated": result
        }
    }


@bp.route("/group/delete", methods=["POST"])
@check_roles(UserRoles.Admin)
@api_login_required
def delete_group():
    payload = get_payload(request)
    result = ReleaseManagerService().delete_group(**payload)

    return {
        "status": "ok",
        "response": {
            "deleted": result
        }
    }


@bp.route("/test/create", methods=["POST"])
@check_roles(UserRoles.Admin)
@api_login_required
def create_test():
    payload = get_payload(request)
    test = ReleaseManagerService().create_test(**payload)
    return {
        "status": "ok",
        "response": {
            "new_test": test
        }
    }


@bp.route("/test/update", methods=["POST"])
@check_roles(UserRoles.Admin)
@api_login_required
def update_test():
    payload = get_payload(request)
    result = ReleaseManagerService().update_test(**payload)
    return {
        "status": "ok",
        "response": {
            "updated": result
        }
    }


@bp.route("/test/batch_move", methods=["POST"])
@check_roles(UserRoles.Admin)
@api_login_required
def batch_move_tests():
    payload = get_payload(request)
    result = ReleaseManagerService().batch_move_tests(**payload)
    return {
        "status": "ok",
        "response": {
            "moved": result
        }
    }


@bp.route("/test/delete", methods=["POST"])
@check_roles(UserRoles.Admin)
@api_login_required
def delete_test():
    payload = get_payload(request)
    result = ReleaseManagerService().delete_test(**payload)

    return {
        "status": "ok",
        "response": {
            "deleted": result
        }
    }


@bp.route("/releases/get", methods=["GET"])
@check_roles(UserRoles.Admin)
@api_login_required
def get_releases():
    releases = ReleaseManagerService().get_releases()
    return {
        "status": "ok",
        "response": releases
    }


@bp.route("/groups/get", methods=["GET"])
@check_roles(UserRoles.Admin)
@api_login_required
def get_groups_for_release():
    release_id = request.args.get("releaseId")
    if not release_id:
        raise Exception("ReleaseId not provided in the request")
    groups = ReleaseManagerService().get_groups(release_id=UUID(release_id))

    return {
        "status": "ok",
        "response": groups
    }


@bp.route("/tests/get", methods=["GET"])
@check_roles(UserRoles.Admin)
@api_login_required
def get_tests_for_group():
    group_id = request.args.get("groupId")
    if not group_id:
        raise Exception("GroupId not provided in the request")
    tests = ReleaseManagerService().get_tests(group_id=UUID(group_id))
    return {
        "status": "ok",
        "response": tests
    }


@bp.route("/release/test/state/toggle", methods=["POST"])
@check_roles(UserRoles.Admin)
@api_login_required
def quick_toggle_test_enabled():
    
    payload = get_payload(request)
    res = ReleaseManagerService().toggle_test_enabled(test_id=payload["entityId"], new_state=payload["state"])
    return {
        "status": "ok",
        "response": res
    }


@bp.route("/release/group/state/toggle", methods=["POST"])
@check_roles(UserRoles.Admin)
@api_login_required
def quick_toggle_group_enabled():
    
    payload = get_payload(request)
    res = ReleaseManagerService().toggle_group_enabled(group_id=payload["entityId"], new_state=payload["state"])
    return {
        "status": "ok",
        "response": res
    }


@bp.route("/users", methods=["GET"])
@check_roles(UserRoles.Admin)
@api_login_required
def user_info():
    result = UserService().get_users_privileged()

    return {
        "status": "ok",
        "response": result
    }


@bp.route("/user/<string:user_id>/email/set", methods=["POST"])
@check_roles(UserRoles.Admin)
@api_login_required
def user_change_email(user_id: str):
    payload = get_payload(request)

    user = User.get(id=user_id)
    result = UserService().update_email(user=user, new_email=payload["newEmail"])

    return {
        "status": "ok",
        "response": result
    }


@bp.route("/user/<string:user_id>/delete", methods=["POST"])
@check_roles(UserRoles.Admin)
@api_login_required
def user_delete(user_id: str):
    result = UserService().delete_user(user_id=user_id)

    return {
        "status": "ok",
        "response": result
    }


@bp.route("/user/<string:user_id>/password/set", methods=["POST"])
@check_roles(UserRoles.Admin)
@api_login_required
def user_change_password(user_id: str):
    payload = get_payload(request)

    user = User.get(id=user_id)
    result = UserService().update_password(user=user, old_password="", new_password=payload["newPassword"], force=True)

    return {
        "status": "ok",
        "response": result
    }

@bp.route("/user/<string:user_id>/admin/toggle", methods=["POST"])
@check_roles(UserRoles.Admin)
@api_login_required
def user_toggle_admin(user_id: str):
    result = UserService().toggle_admin(user_id=user_id)

    return {
        "status": "ok",
        "response": result
    }
