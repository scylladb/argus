from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from flask import Blueprint

from argus.backend.models.web import ArgusTest, ArgusUserView, User
from argus.backend.service.results_service import ResultsService
from argus.backend.service.user import api_current_user
from argus.backend.util.encoders import ArgusJSONResponse

router = APIRouter(prefix="/widgets")


@router.get("/graphs/graph_views", name="api.view_api.graphs.get_graph_views")
def get_graph_views(view_id: UUID = Query(...),
                    start_date: datetime | None = Query(None),
                    end_date: datetime | None = Query(None),
                    user: User = Depends(api_current_user)):
    view: ArgusUserView = ArgusUserView.get(id=view_id)
    service = ResultsService()
    response = {}
    tests_details = {}

    for test_id in view.tests:
        test_uuid = test_id
        graph_views = service.get_argus_graph_views(test_uuid)
        if graph_views:
            test_name = ArgusTest.get(id=test_uuid).name
            tests_details[str(test_id)] = {"name": test_name}
        view_data = []

        for graph_view in graph_views:
            # Get unique table names from all graphs in the view
            table_names = set()
            for graph_name in graph_view.graphs.keys():
                table_name = graph_name.rsplit(" - ", 1)[0]
                table_names.add(table_name)

            # Get graphs data for these tables
            start_dt = start_date.astimezone(timezone.utc) if start_date else None
            end_dt = end_date.astimezone(timezone.utc) if end_date else None
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

        response[str(test_id)] = view_data

    return ArgusJSONResponse({
        "status": "ok",
        "response": response,
        "tests_details": tests_details
    })


# The route above is served by FastAPI; this view-less rule keeps the
# endpoint buildable through Flask's url_for until the Flask app is retired.
bp = Blueprint("graphs", __name__, url_prefix="/widgets")
bp.add_url_rule("/graphs/graph_views", "get_graph_views", None)
