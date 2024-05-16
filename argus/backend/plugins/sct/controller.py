from flask import Blueprint, request

from argus.backend.error_handlers import handle_api_exception
from argus.backend.service.user import api_login_required
from argus.backend.plugins.sct.service import SCTService
from argus.backend.util.common import get_payload

bp = Blueprint("sct_api", __name__, url_prefix="/sct")
bp.register_error_handler(Exception, handle_api_exception)


@bp.route("/<string:run_id>/packages/submit", methods=["POST"])
@api_login_required
def sct_submit_packages(run_id: str):
    payload = get_payload(request)
    result = SCTService.submit_packages(run_id=run_id, packages=payload["packages"])
    return {
        "status": "ok",
        "response": result
    }


@bp.route("/<string:run_id>/screenshots/submit", methods=["POST"])
@api_login_required
def sct_submit_screenshots(run_id: str):
    payload = get_payload(request)
    result = SCTService.submit_screenshots(run_id=run_id, screenshot_links=payload["screenshot_links"])
    return {
        "status": "ok",
        "response": result
    }


@bp.route("/<string:run_id>/sct_runner/set", methods=["POST"])
@api_login_required
def sct_set_runner(run_id: str):
    payload = get_payload(request)
    result = SCTService.set_sct_runner(
        run_id=run_id,
        public_ip=payload["public_ip"],
        private_ip=payload["private_ip"],
        region=payload["region"],
        backend=payload["backend"]
    )
    return {
        "status": "ok",
        "response": result
    }


@bp.route("/<string:run_id>/resource/create", methods=["POST"])
@api_login_required
def sct_resource_create(run_id: str):
    payload = get_payload(request)
    result = SCTService.create_resource(run_id=run_id, resource_details=payload["resource"])
    return {
        "status": "ok",
        "response": result
    }


@bp.route("/<string:run_id>/resource/<string:resource_name>/terminate", methods=["POST"])
@api_login_required
def sct_resource_terminate(run_id: str, resource_name: str):
    payload = get_payload(request)
    result = SCTService.terminate_resource(run_id=run_id, resource_name=resource_name, reason=payload["reason"])
    return {
        "status": "ok",
        "response": result
    }


@bp.route("/<string:run_id>/resource/<string:resource_name>/shards", methods=["POST"])
@api_login_required
def sct_resource_update_shards(run_id: str, resource_name: str):
    payload = get_payload(request)
    result = SCTService.update_resource_shards(run_id=run_id, resource_name=resource_name, new_shards=payload["shards"])
    return {
        "status": "ok",
        "response": result
    }


@bp.route("/<string:run_id>/resource/<string:resource_name>/update", methods=["POST"])
@api_login_required
def sct_resource_update(run_id: str, resource_name: str):
    payload = get_payload(request)
    result = SCTService.update_resource(run_id=run_id, resource_name=resource_name, update_data=payload["update_data"])
    return {
        "status": "ok",
        "response": result
    }


@bp.route("/<string:run_id>/nemesis/submit", methods=["POST"])
@api_login_required
def sct_nemesis_submit(run_id: str):
    payload = get_payload(request)
    result = SCTService.submit_nemesis(run_id=run_id, nemesis_details=payload["nemesis"])
    return {
        "status": "ok",
        "response": result
    }


@bp.route("/<string:run_id>/nemesis/finalize", methods=["POST"])
@api_login_required
def sct_nemesis_finalize(run_id: str):
    payload = get_payload(request)
    result = SCTService.finalize_nemesis(run_id=run_id, nemesis_details=payload["nemesis"])
    return {
        "status": "ok",
        "response": result
    }


@bp.route("/<string:run_id>/events/submit", methods=["POST"])
@api_login_required
def sct_events_submit(run_id: str):
    payload = get_payload(request)
    result = SCTService.submit_events(run_id=run_id, events=payload["events"])
    return {
        "status": "ok",
        "response": result
    }


@bp.route("/<string:run_id>/gemini/submit", methods=["POST"])
@api_login_required
def sct_gemini_results_submit(run_id: str):
    payload = get_payload(request)
    result = SCTService.submit_gemini_results(run_id=run_id, gemini_data=payload["gemini_data"])
    return {
        "status": "ok",
        "response": result
    }

@bp.route("/<string:run_id>/performance/submit", methods=["POST"])
@api_login_required
def sct_performance_results_submit(run_id: str):
    payload = get_payload(request)
    result = SCTService.submit_performance_results(run_id=run_id, performance_results=payload["performance_results"])
    return {
        "status": "ok",
        "response": result
    }

@bp.route("/<string:run_id>/performance/history", methods=["GET"])
@api_login_required
def sct_get_performance_history(run_id: str):
    result = SCTService.get_performance_history_for_test(run_id=run_id)
    return {
        "status": "ok",
        "response": result
    }


@bp.route("/release/<string:release_name>/kernels", methods=["GET"])
@api_login_required
def sct_get_kernel_report(release_name: str):
    result = SCTService.get_scylla_version_kernels_report(release_name=release_name)
    return {
        "status": "ok",
        "response": result
    }


@bp.route("/<string:run_id>/junit/submit", methods=["POST"])
@api_login_required
def sct_submit_junit_report(run_id: str):
    payload = get_payload(request)
    result = SCTService.junit_submit(run_id, payload["file_name"], payload["content"])
    return {
        "status": "ok",
        "response": result
    }

@bp.route("/<string:run_id>/junit/get_all", methods=["GET"])
@api_login_required
def sct_get_junit_reports(run_id: str):
    result = SCTService.junit_get_all(run_id)
    return {
        "status": "ok",
        "response": result
    }
