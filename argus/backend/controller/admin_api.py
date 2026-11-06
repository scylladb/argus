import logging
from dataclasses import asdict
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel, Field

from argus.backend.models.web import User, UserRoles
from argus.backend.service.chat.config import ChatConfigService, DefaultModel
from argus.backend.service.chat.identity import PICTURE_LIMIT, ChatIdentityService, identity_json
from argus.backend.service.chat.mcp import McpServerService
from argus.backend.service.chat.skills import SkillService, template_json
from argus.backend.service.release_manager import ReleaseManagerService
from argus.backend.service.tunnel_service import TunnelService
from argus.backend.service.user import UserService, require_roles
from argus.backend.util.common import NoneIfEmpty
from argus.backend.util.encoders import APIResponse

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")

admin_user = require_roles(UserRoles.Admin)


class CreateReleaseRequest(BaseModel):
    release_name: str
    pretty_name: str
    perpetual: bool


class SetReleasePerpetualRequest(BaseModel):
    release_id: UUID
    perpetual: bool


class SetReleaseStateRequest(BaseModel):
    release_id: UUID
    state: bool


class SetReleaseDormancyRequest(BaseModel):
    release_id: UUID
    dormant: bool


MAX_RELEASE_PRIORITY = 2**31 - 1


class EditReleaseRequest(BaseModel):
    id: UUID
    pretty_name: str | None = None
    description: str | None = None
    valid_version_regex: str | None = None
    enabled: bool
    perpetual: bool
    dormant: bool
    priority: Annotated[int, Field(ge=0, le=MAX_RELEASE_PRIORITY)] | None = None


class DeleteReleaseRequest(BaseModel):
    releaseId: UUID


class CreateGroupRequest(BaseModel):
    group_name: str
    pretty_name: str
    build_system_id: str
    release_id: UUID


class UpdateGroupRequest(BaseModel):
    group_id: UUID
    name: str
    pretty_name: str
    enabled: bool
    build_system_id: str


class DeleteGroupRequest(BaseModel):
    group_id: UUID
    delete_tests: bool = True
    new_group_id: Annotated[UUID | None, NoneIfEmpty] = None


class CreateTestRequest(BaseModel):
    test_name: str
    pretty_name: str
    build_id: str
    build_url: str
    group_id: UUID
    release_id: UUID
    plugin_name: str


class UpdateTestRequest(BaseModel):
    test_id: UUID
    name: str
    pretty_name: str
    plugin_name: str
    enabled: bool
    build_system_id: str
    build_system_url: str
    group_id: UUID


class BatchMoveTestsRequest(BaseModel):
    new_group_id: UUID
    tests: list[UUID]


class DeleteTestRequest(BaseModel):
    test_id: UUID


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
async def index(user: User = Depends(admin_user)):
    return APIResponse({
        "version": "v1"
    })


@router.post("/release/create", name="admin.admin_api.create_release")
async def create_release(payload: CreateReleaseRequest, user: User = Depends(admin_user)):
    release = await ReleaseManagerService().create_release(**payload.model_dump())

    return APIResponse({
        "status": "ok",
        "response": {
            "new_release": release
        }
    })


@router.post("/release/set_perpetual", name="admin.admin_api.set_release_perpetual")
async def set_release_perpetual(payload: SetReleasePerpetualRequest, user: User = Depends(admin_user)):
    result = await ReleaseManagerService().set_release_perpetuality(**payload.model_dump())
    return APIResponse({
        "status": "ok",
        "response": {
            "updated": result
        }
    })


@router.post("/release/set_state", name="admin.admin_api.set_release_state")
async def set_release_state(payload: SetReleaseStateRequest, user: User = Depends(admin_user)):
    result = await ReleaseManagerService().set_release_state(**payload.model_dump())

    return APIResponse({
        "status": "ok",
        "response": {
            "updated": result
        }
    })


@router.post("/release/set_dormant", name="admin.admin_api.set_release_dormancy")
async def set_release_dormancy(payload: SetReleaseDormancyRequest, user: User = Depends(admin_user)):
    result = await ReleaseManagerService().set_release_dormancy(**payload.model_dump())

    return APIResponse({
        "status": "ok",
        "response": {
            "updated": result
        }
    })


@router.post("/release/edit", name="admin.admin_api.edit_release")
async def edit_release(payload: EditReleaseRequest, user: User = Depends(admin_user)):
    result = await ReleaseManagerService().edit_release(payload.model_dump())

    return APIResponse({
        "status": "ok",
        "response": {
            "updated": result
        }
    })


@router.post("/release/delete", name="admin.admin_api.delete_release")
async def delete_release(payload: DeleteReleaseRequest, user: User = Depends(admin_user)):
    result = await ReleaseManagerService().delete_release(release_id=payload.releaseId)

    return APIResponse({
        "status": "ok",
        "response": {
            "deleted": result
        }
    })


@router.post("/group/create", name="admin.admin_api.create_group")
async def create_group(payload: CreateGroupRequest, user: User = Depends(admin_user)):
    group = await ReleaseManagerService().create_group(**payload.model_dump())

    return APIResponse({
        "status": "ok",
        "response": {
            "new_group": group
        }
    })


@router.post("/group/update", name="admin.admin_api.update_group")
async def update_group(payload: UpdateGroupRequest, user: User = Depends(admin_user)):
    result = await ReleaseManagerService().update_group(**payload.model_dump())
    return APIResponse({
        "status": "ok",
        "response": {
            "updated": result
        }
    })


@router.post("/group/delete", name="admin.admin_api.delete_group")
async def delete_group(payload: DeleteGroupRequest, user: User = Depends(admin_user)):
    result = await ReleaseManagerService().delete_group(**payload.model_dump())

    return APIResponse({
        "status": "ok",
        "response": {
            "deleted": result
        }
    })


@router.post("/test/create", name="admin.admin_api.create_test")
async def create_test(payload: CreateTestRequest, user: User = Depends(admin_user)):
    test = await ReleaseManagerService().create_test(**payload.model_dump())
    return APIResponse({
        "status": "ok",
        "response": {
            "new_test": test
        }
    })


@router.post("/test/update", name="admin.admin_api.update_test")
async def update_test(payload: UpdateTestRequest, user: User = Depends(admin_user)):
    result = await ReleaseManagerService().update_test(**payload.model_dump())
    return APIResponse({
        "status": "ok",
        "response": {
            "updated": result
        }
    })


@router.post("/test/batch_move", name="admin.admin_api.batch_move_tests")
async def batch_move_tests(payload: BatchMoveTestsRequest, user: User = Depends(admin_user)):
    result = await ReleaseManagerService().batch_move_tests(**payload.model_dump())
    return APIResponse({
        "status": "ok",
        "response": {
            "moved": result
        }
    })


@router.post("/test/delete", name="admin.admin_api.delete_test")
async def delete_test(payload: DeleteTestRequest, user: User = Depends(admin_user)):
    result = await ReleaseManagerService().delete_test(**payload.model_dump())

    return APIResponse({
        "status": "ok",
        "response": {
            "deleted": result
        }
    })


@router.get("/releases/get", name="admin.admin_api.get_releases")
async def get_releases(user: User = Depends(admin_user)):
    releases = await ReleaseManagerService().get_releases()
    return APIResponse({
        "status": "ok",
        "response": releases
    })


@router.get("/groups/get", name="admin.admin_api.get_groups_for_release")
async def get_groups_for_release(release_id: UUID = Query(..., alias="releaseId"),
                           user: User = Depends(admin_user)):
    groups = await ReleaseManagerService().get_groups(release_id=release_id)

    return APIResponse({
        "status": "ok",
        "response": groups
    })


@router.get("/tests/get", name="admin.admin_api.get_tests_for_group")
async def get_tests_for_group(group_id: UUID = Query(..., alias="groupId"),
                        user: User = Depends(admin_user)):
    tests = await ReleaseManagerService().get_tests(group_id=group_id)
    return APIResponse({
        "status": "ok",
        "response": tests
    })


@router.post("/release/test/state/toggle", name="admin.admin_api.quick_toggle_test_enabled")
async def quick_toggle_test_enabled(payload: ToggleEntityStateRequest, user: User = Depends(admin_user)):
    res = await ReleaseManagerService().toggle_test_enabled(test_id=payload.entityId, new_state=payload.state)
    return APIResponse({
        "status": "ok",
        "response": res
    })


@router.post("/release/group/state/toggle", name="admin.admin_api.quick_toggle_group_enabled")
async def quick_toggle_group_enabled(payload: ToggleEntityStateRequest, user: User = Depends(admin_user)):
    res = await ReleaseManagerService().toggle_group_enabled(group_id=payload.entityId, new_state=payload.state)
    return APIResponse({
        "status": "ok",
        "response": res
    })


@router.get("/users", name="admin.admin_api.user_info")
async def user_info(user: User = Depends(admin_user)):
    result = await UserService().get_users_privileged()

    return APIResponse({
        "status": "ok",
        "response": result
    })


@router.post("/user/{user_id}/email/set", name="admin.admin_api.user_change_email")
async def user_change_email(user_id: UUID, payload: UserEmailChangeRequest,
                      user: User = Depends(admin_user)):
    target = await User.get(id=user_id)
    result = await UserService().update_email(user=target, new_email=payload.newEmail)

    return APIResponse({
        "status": "ok",
        "response": result
    })


@router.post("/user/{user_id}/delete", name="admin.admin_api.user_delete")
async def user_delete(user_id: UUID, user: User = Depends(admin_user)):
    result = await UserService().delete_user(user_id=user_id, current_user=user)

    return APIResponse({
        "status": "ok",
        "response": result
    })


@router.post("/user/{user_id}/password/set", name="admin.admin_api.user_change_password")
async def user_change_password(user_id: UUID, payload: UserPasswordChangeRequest,
                         user: User = Depends(admin_user)):
    target = await User.get(id=user_id)
    result = await UserService().update_password(user=target, old_password="",
                                                 new_password=payload.newPassword, force=True)

    return APIResponse({
        "status": "ok",
        "response": result
    })


@router.post("/user/{user_id}/admin/toggle", name="admin.admin_api.user_toggle_admin")
async def user_toggle_admin(user_id: UUID, user: User = Depends(admin_user)):
    result = await UserService().toggle_admin(user_id=user_id, current_user=user)

    return APIResponse({
        "status": "ok",
        "response": result
    })


@router.get("/proxy-tunnel/config", name="admin.admin_api.get_proxy_tunnel_config")
async def get_proxy_tunnel_config(tunnel_id: Annotated[UUID | None, NoneIfEmpty, Query()] = None,
                            user: User = Depends(admin_user)):
    config = await TunnelService().get_proxy_tunnel_config(tunnel_id=tunnel_id)
    return APIResponse({
        "status": "ok",
        "response": asdict(config) if config else None,
    })


@router.get("/proxy-tunnel/configs", name="admin.admin_api.list_proxy_tunnel_configs")
async def list_proxy_tunnel_configs(active_only: bool | None = Query(None),
                              user: User = Depends(admin_user)):
    configs = await TunnelService().list_proxy_tunnel_configs(active_only=active_only)
    return APIResponse({
        "status": "ok",
        "response": [asdict(row) for row in configs],
    })


@router.post("/proxy-tunnel/config", name="admin.admin_api.save_proxy_tunnel_config")
async def save_proxy_tunnel_config(payload: ProxyTunnelConfigRequest,
                             user: User = Depends(admin_user)):
    config = await TunnelService().save_proxy_tunnel_config(payload.model_dump(exclude_unset=True))
    return APIResponse({
        "status": "ok",
        "response": asdict(config),
    })


@router.delete("/proxy-tunnel/config/{tunnel_id}", name="admin.admin_api.delete_proxy_tunnel_config")
async def delete_proxy_tunnel_config(tunnel_id: UUID, payload: dict | None = Body(None),
                               user: User = Depends(admin_user)):
    delete_user_flag = bool((payload or {}).get("delete_user", False))
    await TunnelService().delete_proxy_tunnel_config(tunnel_id, delete_user=delete_user_flag)
    return APIResponse({"status": "ok", "response": {"deleted": True, "user_deleted": delete_user_flag}})


@router.post("/proxy-tunnel/config/{tunnel_id}/active", name="admin.admin_api.set_proxy_tunnel_config_active")
async def set_proxy_tunnel_config_active(tunnel_id: UUID, payload: ProxyTunnelActiveRequest,
                                   user: User = Depends(admin_user)):
    config = await TunnelService().set_proxy_tunnel_config_active(tunnel_id, payload.is_active)
    return APIResponse({
        "status": "ok",
        "response": asdict(config),
    })


@router.get("/ssh/keys", name="admin.admin_api.list_ssh_keys")
async def list_ssh_keys(user: User = Depends(admin_user)):
    keys = await TunnelService().list_keys()
    return APIResponse({
        "status": "ok",
        "response": [asdict(row) for row in keys],
    })


@router.delete("/ssh/keys/{key_id}", name="admin.admin_api.delete_ssh_key")
async def delete_ssh_key(key_id: UUID, user: User = Depends(admin_user)):
    await TunnelService().delete_key(key_id)
    return APIResponse({
        "status": "ok",
        "response": {
            "deleted": True,
        },
    })


class ChatConnectionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._-]+$")
    endpoint: str = Field(min_length=1)
    token: str | None = None


class ChatToolTestRequest(BaseModel):
    model: str = Field(min_length=1)


class ChatActiveIdentityRequest(BaseModel):
    connection: str | None = None


class ChatMcpServerRequest(BaseModel):
    name: str = Field(min_length=1, max_length=32)
    url: str = Field(min_length=1)
    transport: str = "streamable_http"
    headers: dict[str, str] | None = None
    enabled: bool = True


class ChatMcpModesRequest(BaseModel):
    modes: dict[str, str]


class ChatTemplateRequest(BaseModel):
    template: str = Field(min_length=1)


class ChatSkillRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = ""
    content: str = Field(min_length=1)
    mode: str = "always"


class ChatDefaultRequest(BaseModel):
    connection: str = Field(min_length=1)
    model: str = Field(min_length=1)
    context_window: int = Field(gt=0)
    tools: bool
    vision: bool = False


@router.get("/chat/connections", name="admin.admin_api.chat_connections")
async def chat_connections(user: User = Depends(admin_user)):
    connections, default = await ChatConfigService().connections()
    identities, active = await ChatIdentityService().identities()
    return APIResponse({
        "status": "ok",
        "response": {
            "connections": [asdict(connection) for connection in connections],
            "default": asdict(default) if default else None,
            "identities": [identity_json(identity) for identity in identities],
            "active_identity": active,
        },
    })


@router.post("/chat/connection", name="admin.admin_api.chat_save_connection")
async def chat_save_connection(payload: ChatConnectionRequest, user: User = Depends(admin_user)):
    connection = await ChatConfigService().save_connection(payload.name, payload.endpoint, payload.token, user)
    return APIResponse({"status": "ok", "response": asdict(connection)})


@router.delete("/chat/connection/{name}", name="admin.admin_api.chat_delete_connection")
async def chat_delete_connection(name: str, user: User = Depends(admin_user)):
    await ChatConfigService().delete_connection(name)
    await ChatIdentityService().delete(name)
    return APIResponse({"status": "ok", "response": {"deleted": name}})


@router.get("/chat/connection/{name}/models", name="admin.admin_api.chat_probe_models")
async def chat_probe_models(name: str, user: User = Depends(admin_user)):
    models = await ChatConfigService().probe(name)
    return APIResponse({"status": "ok", "response": [asdict(model) for model in models]})


@router.post("/chat/connection/{name}/test_tools", name="admin.admin_api.chat_test_tools")
async def chat_test_tools(name: str, payload: ChatToolTestRequest, user: User = Depends(admin_user)):
    result = await ChatConfigService().test_tools(name, payload.model)
    return APIResponse({"status": "ok", "response": asdict(result)})


@router.post("/chat/default", name="admin.admin_api.chat_set_default")
async def chat_set_default(payload: ChatDefaultRequest, user: User = Depends(admin_user)):
    default = await ChatConfigService().set_default(DefaultModel(**payload.model_dump()), user)
    return APIResponse({"status": "ok", "response": asdict(default)})


@router.post("/chat/connection/{name}/identity", name="admin.admin_api.chat_save_identity")
async def chat_save_identity(name: str, assistant_name: str = Form(...), picture: UploadFile | None = File(None),
                             remove_picture: bool = Form(False), user: User = Depends(admin_user)):
    data = await picture.read(PICTURE_LIMIT + 1) if picture else None
    identity = await ChatIdentityService().save(name, assistant_name, data, remove_picture, user)
    return APIResponse({"status": "ok", "response": identity_json(identity)})


@router.delete("/chat/connection/{name}/identity", name="admin.admin_api.chat_delete_identity")
async def chat_delete_identity(name: str, user: User = Depends(admin_user)):
    await ChatIdentityService().delete(name)
    return APIResponse({"status": "ok", "response": {"deleted": name}})


@router.post("/chat/identity/active", name="admin.admin_api.chat_set_active_identity")
async def chat_set_active_identity(payload: ChatActiveIdentityRequest, user: User = Depends(admin_user)):
    identity = await ChatIdentityService().set_active(payload.connection)
    return APIResponse({"status": "ok", "response": identity_json(identity)})


@router.get("/chat/prompt", name="admin.admin_api.chat_prompt")
async def chat_prompt(user: User = Depends(admin_user)):
    return APIResponse({"status": "ok", "response": template_json(await SkillService().prompt_setup())})


@router.put("/chat/prompt", name="admin.admin_api.chat_save_prompt")
async def chat_save_prompt(payload: ChatTemplateRequest, user: User = Depends(admin_user)):
    return APIResponse({"status": "ok", "response": template_json(await SkillService().save_template(
        payload.template, user))})


@router.delete("/chat/prompt", name="admin.admin_api.chat_reset_prompt")
async def chat_reset_prompt(user: User = Depends(admin_user)):
    return APIResponse({"status": "ok", "response": template_json(await SkillService().reset_template(user))})


@router.get("/chat/skills", name="admin.admin_api.chat_skills")
async def chat_skills(user: User = Depends(admin_user)):
    setup = await SkillService().prompt_setup()
    return APIResponse({"status": "ok", "response": [asdict(skill) for skill in setup.skills]})


@router.post("/chat/skill", name="admin.admin_api.chat_save_skill")
async def chat_save_skill(payload: ChatSkillRequest, user: User = Depends(admin_user)):
    skill = await SkillService().save_skill(payload.name, payload.description, payload.content, payload.mode, user)
    return APIResponse({"status": "ok", "response": asdict(skill)})


@router.delete("/chat/skill/{name}", name="admin.admin_api.chat_delete_skill")
async def chat_delete_skill(name: str, user: User = Depends(admin_user)):
    await SkillService().delete_skill(name)
    return APIResponse({"status": "ok", "response": {"deleted": name}})


@router.get("/chat/mcp", name="admin.admin_api.chat_mcp_servers")
async def chat_mcp_servers(user: User = Depends(admin_user)):
    servers = await McpServerService().servers()
    return APIResponse({"status": "ok", "response": [asdict(server) for server in servers]})


@router.post("/chat/mcp/server", name="admin.admin_api.chat_save_mcp_server")
async def chat_save_mcp_server(payload: ChatMcpServerRequest, user: User = Depends(admin_user)):
    server = await McpServerService().save(payload.name, payload.url, payload.transport, payload.headers,
                                           payload.enabled, user)
    return APIResponse({"status": "ok", "response": asdict(server)})


@router.delete("/chat/mcp/server/{name}", name="admin.admin_api.chat_delete_mcp_server")
async def chat_delete_mcp_server(name: str, user: User = Depends(admin_user)):
    await McpServerService().delete(name)
    return APIResponse({"status": "ok", "response": {"deleted": name}})


@router.post("/chat/mcp/server/{name}/probe", name="admin.admin_api.chat_probe_mcp_server")
async def chat_probe_mcp_server(name: str, user: User = Depends(admin_user)):
    return APIResponse({"status": "ok", "response": asdict(await McpServerService().probe(name))})


@router.post("/chat/mcp/server/{name}/tools", name="admin.admin_api.chat_mcp_tool_modes")
async def chat_mcp_tool_modes(name: str, payload: ChatMcpModesRequest, user: User = Depends(admin_user)):
    return APIResponse({"status": "ok", "response": asdict(await McpServerService().set_modes(name,
                                                                                               payload.modes))})
