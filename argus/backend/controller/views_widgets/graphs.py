import asyncio
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from argus.backend.models.result import ArgusGraphView
from argus.backend.models.web import ArgusTest, ArgusUserView, User
from argus.backend.service.results_service import ResultsService
from argus.backend.service.user import api_current_user
from argus.backend.util.common import gather_limited
from argus.backend.util.encoders import APIResponse

router = APIRouter(prefix="/widgets")


def _table_names(graph_view: ArgusGraphView) -> list[str]:
    return list({graph_name.rsplit(" - ", 1)[0] for graph_name in graph_view.graphs.keys()})


@router.get("/graphs/graph_views", name="api.view_api.graphs.get_graph_views")
async def get_graph_views(view_id: UUID = Query(...),
                    start_date: datetime | None = Query(None),
                    end_date: datetime | None = Query(None),
                    user: User = Depends(api_current_user)):
    view: ArgusUserView = await ArgusUserView.get(id=view_id)
    service = ResultsService()
    start_dt = start_date.astimezone(timezone.utc) if start_date else None
    end_dt = end_date.astimezone(timezone.utc) if end_date else None

    async def collect_test(test_id: UUID) -> tuple[dict | None, list[dict]]:
        graph_views = await service.get_argus_graph_views(test_id)
        if not graph_views:
            return None, []
        test, *graph_results = await asyncio.gather(
            ArgusTest.get(id=test_id),
            *(service.get_test_graphs(test_id=test_id, start_date=start_dt, end_date=end_dt,
                                      table_names=_table_names(graph_view)) for graph_view in graph_views))
        view_data = []
        for graph_view, (graphs, ticks, releases_filters) in zip(graph_views, graph_results):
            # filter out graphs that are not in the graph views
            graphs = [graph for graph in graphs if graph["options"]
                      ["plugins"]["title"]["text"] in graph_view.graphs.keys()]
            if graphs:
                view_data.append({
                    "id": str(graph_view.id),
                    "name": graph_view.name,
                    "description": graph_view.description,
                    "graphs": graphs,
                    "ticks": ticks,
                    "releases_filters": releases_filters
                })
        return {"name": test.name}, view_data

    per_test = await gather_limited(collect_test(test_id) for test_id in view.tests)
    response = {}
    tests_details = {}
    for test_id, (details, view_data) in zip(view.tests, per_test):
        if details is not None:
            tests_details[str(test_id)] = details
        response[str(test_id)] = view_data

    return APIResponse({
        "status": "ok",
        "response": response,
        "tests_details": tests_details
    })
