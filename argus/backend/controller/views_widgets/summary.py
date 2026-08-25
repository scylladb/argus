from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query

from argus.backend.models.web import ArgusUserView, User
from argus.backend.service.results_service import ResultsService
from argus.backend.service.user import api_current_user
from argus.backend.util.encoders import APIResponse

router = APIRouter(prefix="/widgets")


@router.get("/summary/versioned_runs", name="api.view_api.summary.get_versioned_runs")
def get_versioned_runs(view_id: UUID = Query(...), user: User = Depends(api_current_user)):
    view: ArgusUserView = ArgusUserView.get(id=view_id)
    service = ResultsService()
    versioned_runs = service.get_tests_by_version("scylla-server", view.tests)
    return APIResponse({
        "status": "ok",
        "response": versioned_runs,
    })


@router.post("/summary/runs_results", name="api.view_api.summary.get_runs_results")
def get_runs_results(versioned_runs: dict = Body(...), user: User = Depends(api_current_user)):
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
    return APIResponse({
        "status": "ok",
        "response": response,
    })
