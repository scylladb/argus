import logging
from dataclasses import asdict
from typing import TypedDict

from flask import Blueprint, Response, g, request

from argus.backend.error_handlers import handle_api_exception
from argus.backend.models.web import UserRoles
from argus.backend.service.tunnel_service import TunnelService, TunnelServiceException
from argus.backend.service.user import allow_ssh_tunnel_server_scope, api_login_required, check_roles


class RegisterTunnelPayload(TypedDict, total=False):
    public_key: str
    ttl_seconds: int

bp = Blueprint("ssh_api", __name__, url_prefix="/ssh")
bp.register_error_handler(Exception, handle_api_exception)

LOGGER = logging.getLogger(__name__)


@bp.route("/tunnel", methods=["POST"])
@api_login_required
def register_tunnel():
    """
    Register a client SSH public key and obtain proxy tunnel connection details.

    Request JSON body
    -----------------
    public_key  : str  — OpenSSH-format ed25519 (or other) public key (required)
    ttl_seconds : int  — optional key lifetime in seconds.
                         Must be within [3600, 2592000] (1h..30d).
                         Default is 86400 (24h).

    Response
    --------
    {
        "status": "ok",
        "response": {
            "key_id":               "<uuid>",
            "proxy_host":           "proxy.example.com",
            "proxy_port":           22,
            "proxy_user":           "argus-proxy",
            "target_host":          "10.0.0.5",
            "target_port":          8080,
            "host_key_fingerprint": "SHA256:...",
            "expires_at":           "2026-04-16T12:00:00Z"
        }
    }
    """
    payload: RegisterTunnelPayload = request.get_json() or {}
    public_key = payload.get("public_key")
    ttl_seconds = payload.get("ttl_seconds")

    result = TunnelService().register_tunnel(
        user=g.user,
        public_key=public_key,
        ttl_seconds=ttl_seconds,
    )
    return {"status": "ok", "response": asdict(result)}


@bp.route("/tunnel", methods=["GET"])
@api_login_required
def get_tunnel_connection():
    result = TunnelService().get_tunnel_connection(
        user_id=g.user.id,
        proxy_host=request.args.get("proxy_host"),
    )
    return {"status": "ok", "response": asdict(result)}


@bp.route("/tunnel/keys", methods=["GET"])
@api_login_required
def get_user_keys():
    """
    Return SSH keys owned by the authenticated user.

    Optional query params:
    - tunnel_id: UUID of a specific tunnel to scope keys
    """
    tunnel_id = request.args.get("tunnel_id")
    result = TunnelService().list_keys(tunnel_id=tunnel_id, user_id=g.user.id)
    return {"status": "ok", "response": [asdict(row) for row in result]}


@bp.route("/keys", methods=["GET"])
@allow_ssh_tunnel_server_scope
@api_login_required
@check_roles([UserRoles.SSHTunnelServer, UserRoles.Admin])
def get_authorized_keys():
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
        keys_text = TunnelService().get_authorized_keys(fingerprint=request.args.get("fingerprint"))
    except TunnelServiceException as exc:
        # Answer in plain text. The shared JSON error handler replies 200, and
        # sshd would then read the JSON body as an authorized_keys file.
        LOGGER.warning("Rejected authorized_keys request: %s", exc)
        return Response("", mimetype="text/plain", status=400)
    except Exception:  # noqa: BLE001
        # Same reason. A driver error, a timeout, or a missing secondary index
        # must not reach sshd as a 200 with a JSON body.
        LOGGER.exception("authorized_keys lookup failed")
        return Response("", mimetype="text/plain", status=500)
    return Response(keys_text, mimetype="text/plain")
