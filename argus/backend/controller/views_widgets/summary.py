from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query

from argus.backend.models.web import ArgusUserView, User
from argus.backend.service.results_service import ResultsService
from argus.backend.service.user import api_current_user
from argus.backend.util.common import gather_limited
from argus.backend.util.encoders import APIResponse

router = APIRouter(prefix="/widgets")

KEY_METRICS = ["P99 read", "P99 write", "duration", "Throughput write", "Throughput read", "allocs_per_op",
               "cpu_cycles_per_op", "instructions_per_op", "logallocs_per_op"]


@router.get("/summary/versioned_runs", name="api.view_api.summary.get_versioned_runs")
async def get_versioned_runs(view_id: UUID = Query(...), user: User = Depends(api_current_user)):
    view: ArgusUserView = await ArgusUserView.get(id=view_id)
    service = ResultsService()
    versioned_runs = await service.get_tests_by_version("scylla-server", view.tests)
    return APIResponse({
        "status": "ok",
        "response": versioned_runs,
    })


@router.post("/summary/runs_results", name="api.view_api.summary.get_runs_results")
async def get_runs_results(versioned_runs: dict = Body(...), user: User = Depends(api_current_user)):
    service = ResultsService()
    triples = [(test_id, method, run['run_id'])
               for test_id, test_methods in versioned_runs.items() for method, run in test_methods.items()]
    results = await gather_limited(
        service.get_run_results(UUID(test_id), UUID(run_id), key_metrics=KEY_METRICS) for test_id, _, run_id in triples)
    response = {test_id: {method: {} for method in test_methods} for test_id, test_methods in versioned_runs.items()}
    for (test_id, method, run_id), result in zip(triples, results):
        response[test_id][method][run_id] = result
    return APIResponse({
        "status": "ok",
        "response": response,
    })
