from datetime import datetime, timezone
from typing import Annotated

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from starlette.responses import Response

from argus.backend.models.web import User
from argus.backend.service.results_service import DEFAULT_RUN_LIMIT, DEFAULT_TABLE_LIMIT, ResultsService
from argus.backend.service.user import api_current_user
from argus.backend.util.common import NoneIfEmpty
from argus.backend.util.encoders import APIResponse

router = APIRouter(prefix="/results")

OptionalDate = Annotated[datetime | None, NoneIfEmpty]


class CreateGraphViewRequest(BaseModel):
    testId: UUID
    name: str
    description: str


class UpdateGraphViewRequest(BaseModel):
    testId: UUID
    id: UUID
    name: str
    description: str
    graphs: dict[str, str]


def _utc(value: datetime | None) -> datetime | None:
    return value.astimezone(timezone.utc) if value else None


@router.get("/release/{release}/tables", name="api.results.release_tables")
async def release_tables(release: str, include_hidden: bool = Query(False, alias="includeHidden"),
                         user: User = Depends(api_current_user)):
    tables = await ResultsService().get_release_result_tables(release=release, include_hidden=include_hidden)
    return APIResponse({"status": "ok", "response": tables})


@router.get("/release/{release}", name="api.results.release_results")
async def release_results(release: str,
                          table: str = Query(...),
                          statuses: list[str] = Query(default=[], alias="status[]"),
                          since: Annotated[OptionalDate, Query()] = None,
                          until: Annotated[OptionalDate, Query()] = None,
                          sut_since: Annotated[OptionalDate, Query(alias="sutSince")] = None,
                          sut_until: Annotated[OptionalDate, Query(alias="sutUntil")] = None,
                          include_hidden: bool = Query(False, alias="includeHidden"),
                          columns: list[str] = Query(default=[], alias="columns[]"),
                          run_limit: int = Query(DEFAULT_RUN_LIMIT, alias="runLimit", ge=1),
                          table_limit: int = Query(DEFAULT_TABLE_LIMIT, alias="tableLimit", ge=1),
                          user: User = Depends(api_current_user)):
    results = await ResultsService().get_release_results(
        release=release, table_filter=table, statuses=[status.upper() for status in statuses], since=_utc(since), until=_utc(until),
        sut_since=_utc(sut_since), sut_until=_utc(sut_until), include_hidden=include_hidden, columns=columns,
        run_limit=run_limit, table_limit=table_limit)
    return APIResponse({"status": "ok", "response": results})


@router.get("/test", name="api.results.test_results")
@router.head("/test", name="api.results.test_results")
async def test_results(asgi_request: Request, test_id: UUID = Query(..., alias="testId"),
                       start_date: Annotated[OptionalDate, Query(alias="startDate")] = None,
                       end_date: Annotated[OptionalDate, Query(alias="endDate")] = None,
                       table_names: list[str] = Query(default=[], alias="tableNames[]"),
                       user: User = Depends(api_current_user)):
    service = ResultsService()
    if asgi_request.method == "HEAD":
        exists = await service.is_results_exist(test_id=test_id)
        return Response(status_code=200 if exists else 404)

    graphs, ticks, releases_filters = await service.get_test_graphs(
        test_id=test_id, start_date=_utc(start_date), end_date=_utc(end_date), table_names=table_names)
    graph_views = await service.get_argus_graph_views(test_id=test_id)

    return APIResponse({
        "status": "ok",
        "response": {"graphs": graphs, "ticks": ticks, "releases_filters": releases_filters,
                     "graph_views": graph_views}
    })


@router.post("/graph-view/create", name="api.results.create_graph_view")
async def create_graph_view(payload: CreateGraphViewRequest, user: User = Depends(api_current_user)):
    graph_view = await ResultsService().create_argus_graph_view(
        test_id=payload.testId, name=payload.name, description=payload.description)
    return APIResponse({"status": "ok", "response": graph_view})


@router.post("/graph-view/update", name="api.results.update_graph_view")
async def update_graph_view(payload: UpdateGraphViewRequest, user: User = Depends(api_current_user)):
    graph_view = await ResultsService().update_argus_graph_view(
        test_id=payload.testId, view_id=payload.id, name=payload.name,
        description=payload.description, graphs=payload.graphs)
    return APIResponse({"status": "ok", "response": graph_view})
