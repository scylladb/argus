from flask import Blueprint, request

from argus.backend.error_handlers import handle_api_exception
from argus.backend.service.user import api_login_required
from argus.backend.plugins.driver_matrix_tests.service import DriverMatrixService

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
