from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from argus.backend.models.web import User
from argus.backend.service.results_service import ResultsService
from argus.backend.service.user import api_current_user
from argus.backend.util.common import NoneIfEmpty
from argus.backend.util.encoders import APIResponse

router = APIRouter(prefix="/results")

OptionalDate = Annotated[datetime | None, NoneIfEmpty]


def _utc(value: datetime | None) -> datetime | None:
    return value.astimezone(timezone.utc) if value else None


@router.get("/release/{release}/tables", name="api.results.release_tables")
async def release_tables(release: str, user: User = Depends(api_current_user)):
    tables = await ResultsService().get_release_result_tables(release=release)
    return APIResponse({"status": "ok", "response": tables})


@router.get("/release/{release}", name="api.results.release_results")
async def release_results(release: str,
                          table: str = Query(...),
                          statuses: list[str] = Query(default=[], alias="status[]"),
                          since: Annotated[OptionalDate, Query()] = None,
                          until: Annotated[OptionalDate, Query()] = None,
                          sut_since: Annotated[OptionalDate, Query(alias="sutSince")] = None,
                          sut_until: Annotated[OptionalDate, Query(alias="sutUntil")] = None,
                          user: User = Depends(api_current_user)):
    results = await ResultsService().get_release_results(
        release=release, table_filter=table, statuses=statuses, since=_utc(since), until=_utc(until),
        sut_since=_utc(sut_since), sut_until=_utc(sut_until))
    return APIResponse({"status": "ok", "response": results})
