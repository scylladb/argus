from flask import Blueprint, request

from argus.backend.error_handlers import handle_api_exception
from argus.backend.plugins.driver_matrix_tests.raw_types import DriverMatrixSubmitEnvRequest, DriverMatrixSubmitFailureRequest, DriverMatrixSubmitResultRequest
from argus.backend.service.user import api_login_required
from argus.backend.plugins.driver_matrix_tests.service import DriverMatrixService
from argus.backend.util.common import get_payload

bp = Blueprint("driver_matrix_api", __name__, url_prefix="/driver_matrix")
bp.register_error_handler(Exception, handle_api_exception)


@bp.route("/test_report", methods=["GET"])
@api_login_required
def driver_matrix_test_report():

    build_id = request.args.get("buildId")
    if not build_id:
        raise Exception("No build id provided")
    

    result = DriverMatrixService().tested_versions_report(build_id=build_id)
    return {
        "status": "ok",
        "response": result
    }

@bp.route("/result/submit", methods=["POST"])
@api_login_required
def submit_result():
    payload = get_payload(request)
    request_data = DriverMatrixSubmitResultRequest(**payload)

    result = DriverMatrixService().submit_driver_result(driver_name=request_data.driver_name, driver_type=request_data.driver_type, run_id=request_data.run_id, raw_xml=request_data.raw_xml)
    return {
        "status": "ok",
        "response": result
    }


@bp.route("/result/fail", methods=["POST"])
@api_login_required
def submit_failure():
    payload = get_payload(request)
    request_data = DriverMatrixSubmitFailureRequest(**payload)

    result = DriverMatrixService().submit_driver_failure(driver_name=request_data.driver_name, driver_type=request_data.driver_type, run_id=request_data.run_id, failure_reason=request_data.failure_reason)
    return {
        "status": "ok",
        "response": result
    }

@bp.route("/env/submit", methods=["POST"])
@api_login_required
def submit_env():
    payload = get_payload(request)
    request_data = DriverMatrixSubmitEnvRequest(**payload)

    result = DriverMatrixService().submit_env_info(run_id=request_data.run_id, raw_env=request_data.raw_env)
    return {
        "status": "ok",
        "response": result
    }
