import logging
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from argus.backend.models.web import User
from argus.backend.service.argus_service import ArgusService
from argus.backend.service.team_manager_service import TeamManagerService
from argus.backend.service.user import api_current_user
from argus.backend.util.encoders import APIResponse

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/team")


class TeamCreateRequest(BaseModel):
    name: str
    leader: UUID
    members: list[UUID]


class TeamEditRequest(BaseModel):
    id: UUID
    name: str
    members: list[UUID]


class TeamMotdEditRequest(BaseModel):
    id: UUID
    motd: str


@router.post("/create", name="api.team_api.team_create")
def team_create(payload: TeamCreateRequest, user: User = Depends(api_current_user)):
    result = TeamManagerService().create_team(
        name=payload.name,
        leader=payload.leader,
        members=payload.members,
    )

    return APIResponse({
        "status": "ok",
        "response": result
    })


@router.get("/{team_id}/get", name="api.team_api.team_get")
def team_get(team_id: UUID, user: User = Depends(api_current_user)):
    result = TeamManagerService().get_team_by_id(team_id)

    return APIResponse({
        "status": "ok",
        "response": result
    })


@router.delete("/{team_id}/delete", name="api.team_api.team_delete")
def team_delete(team_id: UUID, user: User = Depends(api_current_user)):
    TeamManagerService().delete_team(team_id, user)

    return APIResponse({
        "status": "ok",
        "response": {
            "team_id": str(team_id),
            "status": "deleted",
        }
    })


@router.post("/{team_id}/edit", name="api.team_api.team_edit")
def team_edit(team_id: UUID, payload: TeamEditRequest, user: User = Depends(api_current_user)):
    team = TeamManagerService().edit_team(
        team_id=payload.id,
        name=payload.name,
        members=payload.members,
        user=user,
    )

    return APIResponse({
        "status": "ok",
        "response": {
            "team_id": str(team_id),
            "status": "updated",
            "team": team,
        }
    })


@router.post("/{team_id}/motd/edit", name="api.team_api.team_edit_motd")
def team_edit_motd(team_id: UUID, payload: TeamMotdEditRequest,
                   user: User = Depends(api_current_user)):
    TeamManagerService().edit_team_motd(
        team_id=payload.id,
        message=payload.motd,
        user=user,
    )

    return APIResponse({
        "status": "ok",
        "response": {
            "team_id": str(team_id),
            "status": "updated",
        }
    })


@router.get("/user/{user_id}/teams", name="api.team_api.user_teams")
def user_teams(user_id: UUID, user: User = Depends(api_current_user)):
    result = TeamManagerService().get_users_teams(user_id=user_id)

    return APIResponse({
        "status": "ok",
        "response": result
    })


@router.get("/user/{user_id}/jobs", name="api.team_api.user_jobs")
def user_jobs(user_id: UUID, user: User = Depends(api_current_user)):
    target = User.get(id=user_id)
    result = list(ArgusService().get_jobs_for_user(target))

    return APIResponse({
        "status": "ok",
        "response": result
    })


@router.get("/leader/{user_id}/teams", name="api.team_api.leader_teams")
def leader_teams(user_id: UUID, user: User = Depends(api_current_user)):
    result = TeamManagerService().get_teams_for_user(user_id=user_id)

    return APIResponse({
        "status": "ok",
        "response": result
    })
