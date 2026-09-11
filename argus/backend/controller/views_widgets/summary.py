from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query

from argus.backend.models.web import ArgusUserView, User
from argus.backend.service.results_service import ResultsService
from argus.backend.service.user import api_current_user
from argus.backend.util.concurrency import map_concurrently
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


SUMMARY_KEY_METRICS = [
    "P99 read", "P99 write", "duration", "Throughput write", "Throughput read", "allocs_per_op",
    "cpu_cycles_per_op", "instructions_per_op", "logallocs_per_op",
]


@router.post("/summary/runs_results", name="api.view_api.summary.get_runs_results")
def get_runs_results(versioned_runs: dict = Body(...), user: User = Depends(api_current_user)):
    service = ResultsService()

    # This fans out per *run*, not per test, so the sequential cost was the sum
    # over every (test, method) pair in the view -- the widest fan-out of any
    # widget. Flatten to one task per run and issue them concurrently.
    targets = [
        (test_id, method, run["run_id"])
        for test_id, test_methods in versioned_runs.items()
        for method, run in test_methods.items()
    ]

    def fetch(target: tuple[str, str, str]):
        test_id, _, run_id = target
        return service.get_run_results(UUID(test_id), UUID(run_id), key_metrics=SUMMARY_KEY_METRICS)

    # Seeded from versioned_runs rather than from the results, so a test with
    # no methods still yields an empty dict exactly as the nested loops did.
    response = {test_id: {} for test_id in versioned_runs}
    for (test_id, method, run_id), tables in zip(targets, map_concurrently(fetch, targets)):
        response[test_id][method] = {run_id: tables}
    return APIResponse({
        "status": "ok",
        "response": response,
    })
