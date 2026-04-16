import logging

from flask import Blueprint, Response, g, request

from argus.backend.error_handlers import APIException
from argus.backend.error_handlers import handle_api_exception
from argus.backend.service.tunnel_service import TunnelService
from argus.backend.service.user import api_login_required

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
                         Must be within [86400, 2592000] (24h..30d).
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
    payload = request.get_json() or {}
    public_key = payload.get("public_key")
    ttl_seconds = payload.get("ttl_seconds")

    result = TunnelService().register_tunnel(
        user=g.user,
        public_key=public_key,
        ttl_seconds=ttl_seconds,
    )
    return {"status": "ok", "response": result}


@bp.route("/tunnel", methods=["GET"])
@api_login_required
def get_tunnel_connection():
    result = TunnelService().get_tunnel_connection()
    return {"status": "ok", "response": result}


@bp.route("/keys", methods=["GET"])
@api_login_required
def get_authorized_keys():
    """
    Return all non-expired SSH public keys in OpenSSH ``authorized_keys``
    format (plain text, one key per line).

    This endpoint is called by the proxy host's ``AuthorizedKeysCommand``
    (via ``argus-cli ssh-keys``) on every SSH connection attempt.
    """
    if not g.user or not g.user.is_service_user():
        raise APIException("Only service users can fetch SSH authorized keys")

    keys_text = TunnelService().get_authorized_keys(service_user_id=g.user.id)
    return Response(keys_text, mimetype="text/plain")
