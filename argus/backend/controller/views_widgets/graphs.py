from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from argus.backend.models.web import ArgusTest, ArgusUserView, User
from argus.backend.service.results_service import ResultsService
from argus.backend.service.user import api_current_user
from argus.backend.util.concurrency import map_concurrently
from argus.backend.util.encoders import APIResponse

router = APIRouter(prefix="/widgets")


@router.get("/graphs/graph_views", name="api.view_api.graphs.get_graph_views")
def get_graph_views(view_id: UUID = Query(...),
                    start_date: datetime | None = Query(None),
                    end_date: datetime | None = Query(None),
                    user: User = Depends(api_current_user)):
    view: ArgusUserView = ArgusUserView.get(id=view_id)
    service = ResultsService()
    start_dt = start_date.astimezone(timezone.utc) if start_date else None
    end_dt = end_date.astimezone(timezone.utc) if end_date else None

    def collect(test_uuid) -> tuple[list, str | None]:
        """Graph views for one test, plus its name when it has any."""
        graph_views = service.get_argus_graph_views(test_uuid)
        test_name = ArgusTest.get(id=test_uuid).name if graph_views else None
        view_data = []

        for graph_view in graph_views:
            # Get unique table names from all graphs in the view
            table_names = set()
            for graph_name in graph_view.graphs.keys():
                table_name = graph_name.rsplit(" - ", 1)[0]
                table_names.add(table_name)

            # Get graphs data for these tables
            graphs, ticks, releases_filters = service.get_test_graphs(
                test_id=test_uuid,
                start_date=start_dt,
                end_date=end_dt,
                table_names=list(table_names)
            )

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

        return view_data, test_name

    # get_test_graphs is the heaviest per-test read of any widget, and results
    # are partitioned by test_id, so fan out across the view's tests instead of
    # paying the sum of them. Order is preserved.
    response = {}
    tests_details = {}
    for test_id, (view_data, test_name) in zip(view.tests, map_concurrently(collect, view.tests)):
        response[str(test_id)] = view_data
        if test_name is not None:
            tests_details[str(test_id)] = {"name": test_name}

    return APIResponse({
        "status": "ok",
        "response": response,
        "tests_details": tests_details
    })
