from uuid import UUID

from flask import Blueprint, request, g

from argus.backend.models.web import ArgusUserView
from argus.backend.service.results_service import ResultsService
from argus.backend.service.user import api_login_required
from argus.backend.util.common import get_payload

bp = Blueprint("summary", __name__, url_prefix="/widgets")


@bp.route("/summary/versioned_runs", methods=["GET"])
@api_login_required
def get_versioned_runs():
    view_id = UUID(request.args.get("view_id"))
    view: ArgusUserView = ArgusUserView.get(id=view_id)
    service = ResultsService()
    versioned_runs = service.get_tests_by_version("scylla-server", view.tests)
    return {
        "status": "ok",
        "response": versioned_runs,
    }


@bp.route("/summary/runs_results", methods=["POST"])
@api_login_required
def get_runs_results():
    versioned_runs = get_payload(request)
    service = ResultsService()
    response = {}
    for test_id, test_methods in versioned_runs.items():
        response[test_id] = {}
        for method, run in test_methods.items():
            response[test_id][method] = {}
            run_id = run['run_id']
            response[test_id][method][run_id] = service.get_run_results(UUID(test_id), UUID(run_id), key_metrics=[
                "P99 read", "P99 write", "duration", "Throughput write", "Throughput read", "allocs_per_op",
                "cpu_cycles_per_op", "instructions_per_op", "logallocs_per_op"])
    return {
        "status": "ok",
        "response": response,
    }
