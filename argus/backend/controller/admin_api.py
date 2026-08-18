import logging
from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query
from flask import Blueprint
from pydantic import BaseModel

from argus.backend.error_handlers import handle_api_exception
from argus.backend.models.web import User, UserRoles
from argus.backend.service.release_manager import ReleaseManagerService
from argus.backend.service.tunnel_service import TunnelService
from argus.backend.service.user import UserService, require_roles
from argus.backend.util.encoders import ArgusJSONResponse

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")

admin_user = require_roles(UserRoles.Admin)


class CreateReleaseRequest(BaseModel):
    release_name: str
    pretty_name: str
    perpetual: bool


class SetReleasePerpetualRequest(BaseModel):
    release_id: str
    perpetual: bool


class SetReleaseStateRequest(BaseModel):
    release_id: str
    state: bool


class SetReleaseDormancyRequest(BaseModel):
    release_id: str
    dormant: bool


class EditReleaseRequest(BaseModel):
    id: str
    pretty_name: str
    description: str | None = None
    valid_version_regex: str | None = None
    enabled: bool
    perpetual: bool
    dormant: bool


class DeleteReleaseRequest(BaseModel):
    releaseId: str


class CreateGroupRequest(BaseModel):
    group_name: str
    pretty_name: str
    build_system_id: str
    release_id: str


class UpdateGroupRequest(BaseModel):
    group_id: str
    name: str
    pretty_name: str
    enabled: bool
    build_system_id: str


class DeleteGroupRequest(BaseModel):
    group_id: str
    delete_tests: bool = True
    new_group_id: str = ""


class CreateTestRequest(BaseModel):
    test_name: str
    pretty_name: str
    build_id: str
    build_url: str
    group_id: str
    release_id: str
    plugin_name: str


class UpdateTestRequest(BaseModel):
    test_id: str
    name: str
    pretty_name: str
    plugin_name: str
    enabled: bool
    build_system_id: str
    build_system_url: str
    group_id: str


class BatchMoveTestsRequest(BaseModel):
    new_group_id: str
    tests: list[str]


class DeleteTestRequest(BaseModel):
    test_id: str


class ToggleEntityStateRequest(BaseModel):
    entityId: UUID
    state: bool


class UserEmailChangeRequest(BaseModel):
    newEmail: str


class UserPasswordChangeRequest(BaseModel):
    newPassword: str


class ProxyTunnelConfigRequest(BaseModel):
    host: str | None = None
    port: int | None = None
    proxy_user: str | None = None
    target_host: str | None = None
    target_port: int | None = None
    host_key_fingerprint: str | None = None
    is_active: bool | None = None


class ProxyTunnelActiveRequest(BaseModel):
    is_active: bool


@router.get("/", name="admin.admin_api.index")
def index(user: User = Depends(admin_user)):
    return ArgusJSONResponse({
        "version": "v1"
    })


@router.post("/release/create", name="admin.admin_api.create_release")
def create_release(payload: CreateReleaseRequest, user: User = Depends(admin_user)):
    release = ReleaseManagerService().create_release(**payload.model_dump())

    return ArgusJSONResponse({
        "status": "ok",
        "response": {
            "new_release": release
        }
    })


@router.post("/release/set_perpetual", name="admin.admin_api.set_release_perpetual")
def set_release_perpetual(payload: SetReleasePerpetualRequest, user: User = Depends(admin_user)):
    result = ReleaseManagerService().set_release_perpetuality(**payload.model_dump())
    return ArgusJSONResponse({
        "status": "ok",
        "response": {
            "updated": result
        }
    })


@router.post("/release/set_state", name="admin.admin_api.set_release_state")
def set_release_state(payload: SetReleaseStateRequest, user: User = Depends(admin_user)):
    result = ReleaseManagerService().set_release_state(**payload.model_dump())

    return ArgusJSONResponse({
        "status": "ok",
        "response": {
            "updated": result
        }
    })


@router.post("/release/set_dormant", name="admin.admin_api.set_release_dormancy")
def set_release_dormancy(payload: SetReleaseDormancyRequest, user: User = Depends(admin_user)):
    result = ReleaseManagerService().set_release_dormancy(**payload.model_dump())

    return ArgusJSONResponse({
        "status": "ok",
        "response": {
            "updated": result
        }
    })


@router.post("/release/edit", name="admin.admin_api.edit_release")
def edit_release(payload: EditReleaseRequest, user: User = Depends(admin_user)):
    result = ReleaseManagerService().edit_release(payload.model_dump())

    return ArgusJSONResponse({
        "status": "ok",
        "response": {
            "updated": result
        }
    })


@router.post("/release/delete", name="admin.admin_api.delete_release")
def delete_release(payload: DeleteReleaseRequest, user: User = Depends(admin_user)):
    result = ReleaseManagerService().delete_release(release_id=payload.releaseId)

    return ArgusJSONResponse({
        "status": "ok",
        "response": {
            "deleted": result
        }
    })


@router.post("/group/create", name="admin.admin_api.create_group")
def create_group(payload: CreateGroupRequest, user: User = Depends(admin_user)):
    group = ReleaseManagerService().create_group(**payload.model_dump())

    return ArgusJSONResponse({
        "status": "ok",
        "response": {
            "new_group": group
        }
    })


@router.post("/group/update", name="admin.admin_api.update_group")
def update_group(payload: UpdateGroupRequest, user: User = Depends(admin_user)):
    result = ReleaseManagerService().update_group(**payload.model_dump())
    return ArgusJSONResponse({
        "status": "ok",
        "response": {
            "updated": result
        }
    })


@router.post("/group/delete", name="admin.admin_api.delete_group")
def delete_group(payload: DeleteGroupRequest, user: User = Depends(admin_user)):
    result = ReleaseManagerService().delete_group(**payload.model_dump())

    return ArgusJSONResponse({
        "status": "ok",
        "response": {
            "deleted": result
        }
    })


@router.post("/test/create", name="admin.admin_api.create_test")
def create_test(payload: CreateTestRequest, user: User = Depends(admin_user)):
    test = ReleaseManagerService().create_test(**payload.model_dump())
    return ArgusJSONResponse({
        "status": "ok",
        "response": {
            "new_test": test
        }
    })


@router.post("/test/update", name="admin.admin_api.update_test")
def update_test(payload: UpdateTestRequest, user: User = Depends(admin_user)):
    result = ReleaseManagerService().update_test(**payload.model_dump())
    return ArgusJSONResponse({
        "status": "ok",
        "response": {
            "updated": result
        }
    })


@router.post("/test/batch_move", name="admin.admin_api.batch_move_tests")
def batch_move_tests(payload: BatchMoveTestsRequest, user: User = Depends(admin_user)):
    result = ReleaseManagerService().batch_move_tests(**payload.model_dump())
    return ArgusJSONResponse({
        "status": "ok",
        "response": {
            "moved": result
        }
    })


@router.post("/test/delete", name="admin.admin_api.delete_test")
def delete_test(payload: DeleteTestRequest, user: User = Depends(admin_user)):
    result = ReleaseManagerService().delete_test(**payload.model_dump())

    return ArgusJSONResponse({
        "status": "ok",
        "response": {
            "deleted": result
        }
    })


@router.get("/releases/get", name="admin.admin_api.get_releases")
def get_releases(user: User = Depends(admin_user)):
    releases = ReleaseManagerService().get_releases()
    return ArgusJSONResponse({
        "status": "ok",
        "response": releases
    })


@router.get("/groups/get", name="admin.admin_api.get_groups_for_release")
def get_groups_for_release(release_id: UUID = Query(..., alias="releaseId"),
                           user: User = Depends(admin_user)):
    groups = ReleaseManagerService().get_groups(release_id=release_id)

    return ArgusJSONResponse({
        "status": "ok",
        "response": groups
    })


@router.get("/tests/get", name="admin.admin_api.get_tests_for_group")
def get_tests_for_group(group_id: UUID = Query(..., alias="groupId"),
                        user: User = Depends(admin_user)):
    tests = ReleaseManagerService().get_tests(group_id=group_id)
    return ArgusJSONResponse({
        "status": "ok",
        "response": tests
    })


@router.post("/release/test/state/toggle", name="admin.admin_api.quick_toggle_test_enabled")
def quick_toggle_test_enabled(payload: ToggleEntityStateRequest, user: User = Depends(admin_user)):
    res = ReleaseManagerService().toggle_test_enabled(test_id=payload.entityId, new_state=payload.state)
    return ArgusJSONResponse({
        "status": "ok",
        "response": res
    })


@router.post("/release/group/state/toggle", name="admin.admin_api.quick_toggle_group_enabled")
def quick_toggle_group_enabled(payload: ToggleEntityStateRequest, user: User = Depends(admin_user)):
    res = ReleaseManagerService().toggle_group_enabled(group_id=payload.entityId, new_state=payload.state)
    return ArgusJSONResponse({
        "status": "ok",
        "response": res
    })


@router.get("/users", name="admin.admin_api.user_info")
def user_info(user: User = Depends(admin_user)):
    result = UserService().get_users_privileged()

    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.post("/user/{user_id}/email/set", name="admin.admin_api.user_change_email")
def user_change_email(user_id: UUID, payload: UserEmailChangeRequest,
                      user: User = Depends(admin_user)):
    target = User.get(id=user_id)
    result = UserService().update_email(user=target, new_email=payload.newEmail)

    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.post("/user/{user_id}/delete", name="admin.admin_api.user_delete")
def user_delete(user_id: str, user: User = Depends(admin_user)):
    result = UserService().delete_user(user_id=user_id, current_user=user)

    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.post("/user/{user_id}/password/set", name="admin.admin_api.user_change_password")
def user_change_password(user_id: UUID, payload: UserPasswordChangeRequest,
                         user: User = Depends(admin_user)):
    target = User.get(id=user_id)
    result = UserService().update_password(user=target, old_password="",
                                           new_password=payload.newPassword, force=True)

    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.post("/user/{user_id}/admin/toggle", name="admin.admin_api.user_toggle_admin")
def user_toggle_admin(user_id: str, user: User = Depends(admin_user)):
    result = UserService().toggle_admin(user_id=user_id, current_user=user)

    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.get("/proxy-tunnel/config", name="admin.admin_api.get_proxy_tunnel_config")
def get_proxy_tunnel_config(tunnel_id: str | None = Query(None),
                            user: User = Depends(admin_user)):
    config = TunnelService().get_proxy_tunnel_config(tunnel_id=tunnel_id)
    return ArgusJSONResponse({
        "status": "ok",
        "response": asdict(config) if config else None,
    })


@router.get("/proxy-tunnel/configs", name="admin.admin_api.list_proxy_tunnel_configs")
def list_proxy_tunnel_configs(active_only: bool | None = Query(None),
                              user: User = Depends(admin_user)):
    configs = TunnelService().list_proxy_tunnel_configs(active_only=active_only)
    return ArgusJSONResponse({
        "status": "ok",
        "response": [asdict(row) for row in configs],
    })


@router.post("/proxy-tunnel/config", name="admin.admin_api.save_proxy_tunnel_config")
def save_proxy_tunnel_config(payload: ProxyTunnelConfigRequest,
                             user: User = Depends(admin_user)):
    config = TunnelService().save_proxy_tunnel_config(payload.model_dump(exclude_unset=True))
    return ArgusJSONResponse({
        "status": "ok",
        "response": asdict(config),
    })


@router.delete("/proxy-tunnel/config/{tunnel_id}", name="admin.admin_api.delete_proxy_tunnel_config")
def delete_proxy_tunnel_config(tunnel_id: UUID, payload: dict | None = Body(None),
                               user: User = Depends(admin_user)):
    delete_user_flag = bool((payload or {}).get("delete_user", False))
    TunnelService().delete_proxy_tunnel_config(tunnel_id, delete_user=delete_user_flag)
    return ArgusJSONResponse({"status": "ok", "response": {"deleted": True, "user_deleted": delete_user_flag}})


@router.post("/proxy-tunnel/config/{tunnel_id}/active", name="admin.admin_api.set_proxy_tunnel_config_active")
def set_proxy_tunnel_config_active(tunnel_id: UUID, payload: ProxyTunnelActiveRequest,
                                   user: User = Depends(admin_user)):
    config = TunnelService().set_proxy_tunnel_config_active(tunnel_id, payload.is_active)
    return ArgusJSONResponse({
        "status": "ok",
        "response": asdict(config),
    })


@router.get("/ssh/keys", name="admin.admin_api.list_ssh_keys")
def list_ssh_keys(user: User = Depends(admin_user)):
    keys = TunnelService().list_keys()
    return ArgusJSONResponse({
        "status": "ok",
        "response": [asdict(row) for row in keys],
    })


@router.delete("/ssh/keys/{key_id}", name="admin.admin_api.delete_ssh_key")
def delete_ssh_key(key_id: UUID, user: User = Depends(admin_user)):
    TunnelService().delete_key(key_id)
    return ArgusJSONResponse({
        "status": "ok",
        "response": {
            "deleted": True,
        },
    })


# The routes above are served by FastAPI; these view-less rules keep the
# endpoints buildable through Flask's url_for until the Flask app is retired.
bp = Blueprint('admin_api', __name__, url_prefix='/api/v1')
bp.register_error_handler(Exception, handle_api_exception)

for _rule, _endpoint in (
    ("/", "index"),
    ("/release/create", "create_release"),
    ("/release/set_perpetual", "set_release_perpetual"),
    ("/release/set_state", "set_release_state"),
    ("/release/set_dormant", "set_release_dormancy"),
    ("/release/edit", "edit_release"),
    ("/release/delete", "delete_release"),
    ("/group/create", "create_group"),
    ("/group/update", "update_group"),
    ("/group/delete", "delete_group"),
    ("/test/create", "create_test"),
    ("/test/update", "update_test"),
    ("/test/batch_move", "batch_move_tests"),
    ("/test/delete", "delete_test"),
    ("/releases/get", "get_releases"),
    ("/groups/get", "get_groups_for_release"),
    ("/tests/get", "get_tests_for_group"),
    ("/release/test/state/toggle", "quick_toggle_test_enabled"),
    ("/release/group/state/toggle", "quick_toggle_group_enabled"),
    ("/users", "user_info"),
    ("/user/<string:user_id>/email/set", "user_change_email"),
    ("/user/<string:user_id>/delete", "user_delete"),
    ("/user/<string:user_id>/password/set", "user_change_password"),
    ("/user/<string:user_id>/admin/toggle", "user_toggle_admin"),
    ("/proxy-tunnel/config", "get_proxy_tunnel_config"),
    ("/proxy-tunnel/config", "save_proxy_tunnel_config"),
    ("/proxy-tunnel/configs", "list_proxy_tunnel_configs"),
    ("/proxy-tunnel/config/<string:tunnel_id>", "delete_proxy_tunnel_config"),
    ("/proxy-tunnel/config/<string:tunnel_id>/active", "set_proxy_tunnel_config_active"),
    ("/ssh/keys", "list_ssh_keys"),
    ("/ssh/keys/<string:key_id>", "delete_ssh_key"),
):
    bp.add_url_rule(_rule, _endpoint, None)
