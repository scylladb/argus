import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends, Query
from flask import Blueprint
from pydantic import BaseModel
from starlette.responses import PlainTextResponse

from argus.backend.models.web import User, UserRoles
from argus.backend.service.tunnel_service import TunnelService, TunnelServiceException
from argus.backend.service.user import allow_ssh_tunnel_server_scope, api_current_user, require_roles
from argus.backend.util.encoders import ArgusJSONResponse

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/ssh")


class RegisterTunnelRequest(BaseModel):
    public_key: str | None = None
    ttl_seconds: int | None = None


@router.post("/tunnel", name="api.client_api.ssh_api.register_tunnel")
def register_tunnel(payload: RegisterTunnelRequest, user: User = Depends(api_current_user)):
    """
    Register a client SSH public key and obtain proxy tunnel connection details.

    Request JSON body
    -----------------
    public_key  : str  — OpenSSH-format ed25519 (or other) public key (required)
    ttl_seconds : int  — optional key lifetime in seconds.
                         Must be within [3600, 2592000] (1h..30d).
                         Default is 86400 (24h).
    """
    result = TunnelService().register_tunnel(
        user=user,
        public_key=payload.public_key,
        ttl_seconds=payload.ttl_seconds,
    )
    return ArgusJSONResponse({"status": "ok", "response": asdict(result)})


@router.get("/tunnel", name="api.client_api.ssh_api.get_tunnel_connection")
def get_tunnel_connection(proxy_host: str | None = Query(None),
                          user: User = Depends(api_current_user)):
    result = TunnelService().get_tunnel_connection(
        user_id=user.id,
        proxy_host=proxy_host,
    )
    return ArgusJSONResponse({"status": "ok", "response": asdict(result)})


@router.get("/tunnel/keys", name="api.client_api.ssh_api.get_user_keys")
def get_user_keys(tunnel_id: str | None = Query(None), user: User = Depends(api_current_user)):
    """
    Return SSH keys owned by the authenticated user.

    Optional query params:
    - tunnel_id: UUID of a specific tunnel to scope keys
    """
    result = TunnelService().list_keys(tunnel_id=tunnel_id, user_id=user.id)
    return ArgusJSONResponse({"status": "ok", "response": [asdict(row) for row in result]})


@router.get("/keys", name="api.client_api.ssh_api.get_authorized_keys")
@allow_ssh_tunnel_server_scope
def get_authorized_keys(fingerprint: str | None = Query(None),
                        user: User = Depends(require_roles([UserRoles.SSHTunnelServer, UserRoles.Admin]))):
    """
    Return non-expired SSH public keys in OpenSSH ``authorized_keys`` format
    (plain text, one key per line).

    This endpoint is called by the proxy host's ``AuthorizedKeysCommand``
    (via ``argus ssh keys list``) on every SSH connection attempt.

    Optional query params:
    - fingerprint: ``SHA256:...`` of the key the client offered, taken from the
      sshd ``%f`` token. Scopes the response to that one key. Proxy hosts that
      still run the old wrapper omit it and get the full list.
    """
    try:
        keys_text = TunnelService().get_authorized_keys(fingerprint=fingerprint)
    except TunnelServiceException as exc:
        # Answer in plain text. The shared JSON error handler replies 200, and
        # sshd would then read the JSON body as an authorized_keys file.
        LOGGER.warning("Rejected authorized_keys request: %s", exc)
        return PlainTextResponse("", status_code=400)
    except Exception:  # noqa: BLE001
        # Same reason. A driver error, a timeout, or a missing secondary index
        # must not reach sshd as a 200 with a JSON body.
        LOGGER.exception("authorized_keys lookup failed")
        return PlainTextResponse("", status_code=500)
    return PlainTextResponse(keys_text)


# The routes above are served by FastAPI; these view-less rules keep the
# endpoints buildable through Flask's url_for until the Flask app is retired.
bp = Blueprint("ssh_api", __name__, url_prefix="/ssh")
for _rule, _endpoint in (
    ("/tunnel", "register_tunnel"),
    ("/tunnel", "get_tunnel_connection"),
    ("/tunnel/keys", "get_user_keys"),
    ("/keys", "get_authorized_keys"),
):
    bp.add_url_rule(_rule, _endpoint, None)
