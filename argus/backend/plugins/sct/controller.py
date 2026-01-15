from flask import Blueprint, request

from argus.backend.error_handlers import handle_api_exception
from argus.backend.plugins.sct.testrun import SCTEventSeverity
from argus.backend.service.user import api_login_required
from argus.backend.plugins.sct.service import SCTService, SCTServiceException
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
        backend=payload["backend"],
        name=payload.get("name")
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
    """
        Legacy endpoint. Deprecated
        Submit a structure of EventsBySeverity that will be saved
        onto SCTTestRun
    """
    payload = get_payload(request)
    result = SCTService.submit_events(run_id=run_id, events=payload["events"])
    return {
        "status": "ok",
        "response": result
    }


@bp.route("/<string:run_id>/events/get", methods=["GET"])
@api_login_required
def sct_events_get(run_id: str):
    limit = int(request.args.get("limit", 100))
    before = request.args.get("before")
    severities = request.args.getlist("severity")
    result = SCTService.get_events(run_id=run_id, limit=limit, before=before, severities=severities)
    return {
        "status": "ok",
        "response": result
    }


@bp.route("/<string:run_id>/events/<string:severity>/get", methods=["GET"])
@api_login_required
def sct_events_get_by_severity(run_id: str, severity: str):
    limit = int(request.args.get("limit", 100))
    before = request.args.get("before")
    result = SCTService.get_events(run_id=run_id, limit=limit, before=before, severities=[SCTEventSeverity(severity)])
    return {
        "status": "ok",
        "response": result
    }


@bp.route("/<string:run_id>/events/<string:severity>/count", methods=["GET"])
@api_login_required
def sct_events_count_by_severity(run_id: str, severity: str):
    result = SCTService.count_events_by_severity(run_id=run_id, severity=SCTEventSeverity(severity))
    return {
        "status": "ok",
        "response": result
    }


@bp.route("/<string:run_id>/event/submit", methods=["POST"])
@api_login_required
def sct_event_submit(run_id: str):
    """
        Submit an event or a collection of events
    """
    payload = get_payload(request)
    event_data = payload["data"]
    if isinstance(event_data, list):
        result = all([SCTService.submit_event(run_id=run_id, raw_event=e) for e in event_data])
    else:
        result = SCTService.submit_event(run_id=run_id, raw_event=event_data)
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


@bp.route("/release/<path:release_name>/kernels", methods=["GET"])
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

@bp.route("/<string:run_id>/config/submit", methods=["POST"])
@api_login_required
def sct_submit_config(run_id: str):
    payload = get_payload(request)
    result = SCTService.submit_config(run_id, config_name=payload["name"], config_content=payload["content"])
    return {
        "status": "ok",
        "response": result
    }


@bp.route("/<string:run_id>/config/<string:name>/get", methods=["GET"])
@api_login_required
def sct_get_config(run_id: str, name: str):
    result = SCTService.get_config_store(run_id, name)
    return {
        "status": "ok",
        "response": result
    }


@bp.route("/<string:run_id>/config/all", methods=["GET"])
@api_login_required
def sct_get_all_configs(run_id: str):
    result = SCTService.get_all_configs(run_id)
    return {
        "status": "ok",
        "response": result
    }


@bp.route("/<string:run_id>/stress_cmd/submit", methods=["POST"])
@api_login_required
def sct_add_stress_cmd(run_id: str):
    payload = get_payload(request)
    result = SCTService.add_stress_command(run_id, cmd=payload["cmd"], loader_name=payload["loader_name"], log_name=payload["log_name"])
    return {
        "status": "ok",
        "response": result
    }


@bp.route("/<string:run_id>/stress_cmd/get", methods=["GET"])
@api_login_required
def sct_get_all_stress_cmds(run_id: str):
    result = SCTService.get_stress_commands(run_id)
    return {
        "status": "ok",
        "response": result
    }


@bp.route("/<string:run_id>/similar_events", methods=["GET"])
@api_login_required
def sct_get_similar_events(run_id: str):
    result = SCTService.get_similar_events(run_id=run_id)
    return {
        "status": "ok",
        "response": result
    }


@bp.route("/<string:run_id>/event/similar", methods=["POST"])
@api_login_required
def sct_get_similar_events_realtime(run_id: str):
    """Get similar events for a specific event using real-time vector search"""
    payload = get_payload(request)
    severity = payload.get("severity")
    ts = payload.get("ts")
    limit = int(payload.get("limit", 100))

    err_message = ""
    if not severity and not ts:
        err_message = "Missing required parameters: severity and ts"
    elif not severity:
        err_message = "Missing required parameter: severity"
    elif not ts:
        err_message = "Missing required parameter: ts"
    if err_message:
        raise SCTServiceException(err_message)


    result = SCTService.get_similar_events_realtime(
        run_id=run_id,
        severity=severity,
        ts=ts,
        limit=limit
    )
    return {
        "status": "ok",
        "response": result
    }


@bp.route("/similar_runs_info", methods=["POST"])
@api_login_required
def sct_get_similar_runs_info():
    """Get build IDs and issues for a list of run IDs"""
    data = request.get_json()
    if not data or "run_ids" not in data:
        return {
            "status": "error",
            "response": "Missing run_ids parameter"
        }, 400

    run_ids = data["run_ids"]
    if not isinstance(run_ids, list):
        return {
            "status": "error",
            "response": "run_ids must be a list"
        }, 400

    result = SCTService.get_similar_runs_info(run_ids=run_ids)
    return {
        "status": "ok",
        "response": result
    }
