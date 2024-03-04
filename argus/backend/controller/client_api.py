from flask import Blueprint, request

from argus.backend.error_handlers import handle_api_exception
from argus.backend.service.user import api_login_required
from argus.backend.service.client_service import ClientService
from argus.backend.util.common import get_payload
from argus.backend.plugins.loader import AVAILABLE_PLUGINS

bp = Blueprint("client_api", __name__, url_prefix="/client")
bp.register_error_handler(Exception, handle_api_exception)
for plugin in AVAILABLE_PLUGINS.values():
    if plugin.controller:
        bp.register_blueprint(plugin.controller)


@bp.route("/testrun/<string:run_type>/submit", methods=["POST"])
@api_login_required
def submit_run(run_type: str):
    payload = get_payload(request)
    result = ClientService().submit_run(run_type=run_type, request_data=payload)
    return {
        "status": "ok",
        "response": result
    }


@bp.route("/testrun/<string:run_type>/<string:run_id>/heartbeat", methods=["POST"])
@api_login_required
def run_heartbeat(run_type: str, run_id: str):
    result = ClientService().heartbeat(run_type=run_type, run_id=run_id)
    return {
        "status": "ok",
        "response": result
    }


@bp.route("/testrun/<string:run_type>/<string:run_id>/get_status")
@api_login_required
def run_get_status(run_type: str, run_id: str):
    result = ClientService().get_run_status(run_type=run_type, run_id=run_id)
    return {
        "status": "ok",
        "response": result
    }


@bp.route("/testrun/<string:run_type>/<string:run_id>/set_status", methods=["POST"])
@api_login_required
def run_set_status(run_type: str, run_id: str):
    payload = get_payload(request)
    result = ClientService().update_run_status(run_type=run_type, run_id=run_id, new_status=payload["new_status"])
    return {
        "status": "ok",
        "response": result
    }


@bp.route("/testrun/<string:run_type>/<string:run_id>/update_product_version", methods=["POST"])
@api_login_required
def run_update_product_version(run_type: str, run_id: str):
    payload = get_payload(request)
    result = ClientService().submit_product_version(
        run_type=run_type, run_id=run_id, version=payload["product_version"])
    return {
        "status": "ok",
        "response": result
    }


@bp.route("/testrun/<string:run_type>/<string:run_id>/logs/submit", methods=["POST"])
@api_login_required
def run_submit_logs(run_type: str, run_id: str):
    payload = get_payload(request)
    result = ClientService().submit_logs(run_type=run_type, run_id=run_id, logs=payload["logs"])
    return {
        "status": "ok",
        "response": result
    }


@bp.route("/testrun/<string:run_type>/<string:run_id>/finalize", methods=["POST"])
@api_login_required
def run_finalize(run_type: str, run_id: str):
    try:
        payload = get_payload(request)
    except Exception:
        payload = None
    result = ClientService().finish_run(run_type=run_type, run_id=run_id, payload=payload)
    return {
        "status": "ok",
        "response": result
    }
