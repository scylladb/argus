import logging
from uuid import UUID
from flask import (
    Blueprint,
    request
)
from argus.backend.error_handlers import handle_api_exception
from argus.backend.models.web import User
from argus.backend.service.argus_service import ArgusService
from argus.backend.service.user import api_login_required
from argus.backend.util.common import get_payload
from argus.backend.service.team_manager_service import TeamManagerService

bp = Blueprint('team_api', __name__, url_prefix='/team')
LOGGER = logging.getLogger(__name__)
bp.register_error_handler(Exception, handle_api_exception)


@bp.route("/create", methods=["POST"])
@api_login_required
def team_create():
    payload = get_payload(request)
    result = TeamManagerService().create_team(
        name=payload["name"], 
        leader=UUID(payload["leader"]),
        members=[UUID(m) for m in payload["members"]],
    )

    return {
        "status": "ok",
        "response": result
    }


@bp.route("/<string:team_id>/get")
@api_login_required
def team_get(team_id: str):
    result = TeamManagerService().get_team_by_id(UUID(team_id))

    return {
        "status": "ok",
        "response": result
    }


@bp.route("/<string:team_id>/delete", methods=["DELETE"])
@api_login_required
def team_delete(team_id: str):
    TeamManagerService().delete_team(UUID(team_id))

    return {
        "status": "ok",
        "response": {
            "team_id": team_id,
            "status": "deleted",
        }
    }

@bp.route("/<string:team_id>/edit", methods=["POST"])
@api_login_required
def team_edit(team_id: str):
    payload = get_payload(request)
    team = TeamManagerService().edit_team(
        team_id=UUID(payload["id"]),
        name=payload["name"],
        members=[UUID(m) for m in payload["members"]],
    )

    return {
        "status": "ok",
        "response": {
            "team_id": team_id,
            "status": "updated",
            "team": team,
        }
    }

@bp.route("/<string:team_id>/motd/edit", methods=["POST"])
@api_login_required
def team_edit_motd(team_id: str):
    payload = get_payload(request)
    TeamManagerService().edit_team_motd(
        team_id=UUID(payload["id"]),
        message=payload["motd"],
    )

    return {
        "status": "ok",
        "response": {
            "team_id": team_id,
            "status": "updated",
        }
    }

@bp.route("/user/<string:user_id>/teams")
@api_login_required
def user_teams(user_id: str):
    result = TeamManagerService().get_users_teams(user_id=UUID(user_id))

    return {
        "status": "ok",
        "response": result
    }


@bp.route("/user/<string:user_id>/jobs")
@api_login_required
def user_jobs(user_id: str):
    user = User.get(id=UUID(user_id))
    result = list(ArgusService().get_jobs_for_user(user))

    return {
        "status": "ok",
        "response": result
    }


@bp.route("/leader/<string:user_id>/teams")
@api_login_required
def leader_teams(user_id: str):
    result = TeamManagerService().get_teams_for_user(user_id=UUID(user_id))

    return {
        "status": "ok",
        "response": result
    }
