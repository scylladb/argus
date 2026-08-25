from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel, Field

from argus.backend.models.web import User
from argus.backend.plugins.sct.service import SCTService, SCTServiceException
from argus.backend.plugins.sct.testrun import SCTEventSeverity
from argus.backend.service.user import api_current_user
from argus.backend.util.encoders import APIResponse

router = APIRouter(prefix="/sct")


class PackagesSubmitRequest(BaseModel):
    packages: list[dict]


class ScreenshotsSubmitRequest(BaseModel):
    screenshot_links: list[str]


class SetRunnerRequest(BaseModel):
    public_ip: str
    private_ip: str
    region: str
    backend: str
    name: str | None = None


class ResourceCreateRequest(BaseModel):
    resource: dict


class ResourceTerminateRequest(BaseModel):
    reason: str


class ResourceShardsRequest(BaseModel):
    shards: int


class ResourceUpdateRequest(BaseModel):
    update_data: dict


class NemesisRequest(BaseModel):
    nemesis: dict


class EventsSubmitRequest(BaseModel):
    events: list[dict]


class EventSubmitRequest(BaseModel):
    data: dict | list[dict]


class GeminiResultsRequest(BaseModel):
    gemini_data: dict


class PerformanceResultsRequest(BaseModel):
    performance_results: dict


class JunitSubmitRequest(BaseModel):
    file_name: str
    content: str


class StressCommandRequest(BaseModel):
    cmd: str
    ts: float = Field(default_factory=lambda: datetime.now(UTC).timestamp())
    loader_name: str
    log_name: str


class SimilarEventRequest(BaseModel):
    severity: str | None = None
    ts: float | None = None
    limit: int = 100


class SimilarRunsInfoRequest(BaseModel):
    run_ids: list[str]


@router.post("/{run_id}/packages/submit", name="api.client_api.sct_api.sct_submit_packages")
def sct_submit_packages(run_id: str, payload: PackagesSubmitRequest,
                        user: User = Depends(api_current_user)):
    result = SCTService.submit_packages(run_id=run_id, packages=payload.packages)
    return APIResponse({
        "status": "ok",
        "response": result
    })


@router.post("/{run_id}/screenshots/submit", name="api.client_api.sct_api.sct_submit_screenshots")
def sct_submit_screenshots(run_id: str, payload: ScreenshotsSubmitRequest,
                           user: User = Depends(api_current_user)):
    result = SCTService.submit_screenshots(run_id=run_id, screenshot_links=payload.screenshot_links)
    return APIResponse({
        "status": "ok",
        "response": result
    })


@router.post("/{run_id}/sct_runner/set", name="api.client_api.sct_api.sct_set_runner")
def sct_set_runner(run_id: str, payload: SetRunnerRequest, user: User = Depends(api_current_user)):
    result = SCTService.set_sct_runner(
        run_id=run_id,
        public_ip=payload.public_ip,
        private_ip=payload.private_ip,
        region=payload.region,
        backend=payload.backend,
        name=payload.name
    )
    return APIResponse({
        "status": "ok",
        "response": result
    })


@router.get("/{run_id}/resource/all", name="api.client_api.sct_api.sct_resource_all")
def sct_resource_all(run_id: str, user: User = Depends(api_current_user)):
    result = SCTService.get_resources(run_id=run_id)
    return APIResponse({
        "status": "ok",
        "response": result
    })


@router.get("/{run_id}/resource/{name}/get", name="api.client_api.sct_api.sct_resource_get")
def sct_resource_get(run_id: str, name: str, user: User = Depends(api_current_user)):
    result = SCTService.get_resource(run_id=run_id, name=name)
    return APIResponse({
        "status": "ok",
        "response": result
    })


@router.post("/{run_id}/resource/create", name="api.client_api.sct_api.sct_resource_create")
def sct_resource_create(run_id: str, payload: ResourceCreateRequest,
                        user: User = Depends(api_current_user)):
    result = SCTService.create_resource(run_id=run_id, resource_details=payload.resource)
    return APIResponse({
        "status": "ok",
        "response": result
    })


@router.post("/{run_id}/resource/{resource_name}/terminate",
             name="api.client_api.sct_api.sct_resource_terminate")
def sct_resource_terminate(run_id: str, resource_name: str, payload: ResourceTerminateRequest,
                           user: User = Depends(api_current_user)):
    result = SCTService.terminate_resource(run_id=run_id, resource_name=resource_name,
                                           reason=payload.reason)
    return APIResponse({
        "status": "ok",
        "response": result
    })


@router.post("/{run_id}/resource/{resource_name}/shards",
             name="api.client_api.sct_api.sct_resource_update_shards")
def sct_resource_update_shards(run_id: str, resource_name: str, payload: ResourceShardsRequest,
                               user: User = Depends(api_current_user)):
    result = SCTService.update_resource_shards(run_id=run_id, resource_name=resource_name,
                                               new_shards=payload.shards)
    return APIResponse({
        "status": "ok",
        "response": result
    })


@router.post("/{run_id}/resource/{resource_name}/update",
             name="api.client_api.sct_api.sct_resource_update")
def sct_resource_update(run_id: str, resource_name: str, payload: ResourceUpdateRequest,
                        user: User = Depends(api_current_user)):
    result = SCTService.update_resource(run_id=run_id, resource_name=resource_name,
                                        update_data=payload.update_data)
    return APIResponse({
        "status": "ok",
        "response": result
    })


@router.post("/{run_id}/nemesis/submit", name="api.client_api.sct_api.sct_nemesis_submit")
def sct_nemesis_submit(run_id: str, payload: NemesisRequest, user: User = Depends(api_current_user)):
    result = SCTService.submit_nemesis(run_id=run_id, nemesis_details=payload.nemesis)
    return APIResponse({
        "status": "ok",
        "response": result
    })


@router.get("/{run_id}/nemesis/get", name="api.client_api.sct_api.sct_nemesis_get")
def sct_nemesis_get(run_id: str, user: User = Depends(api_current_user)):
    result = SCTService.get_nemesis(run_id=run_id)
    return APIResponse({
        "status": "ok",
        "response": result
    })


@router.post("/{run_id}/nemesis/finalize", name="api.client_api.sct_api.sct_nemesis_finalize")
def sct_nemesis_finalize(run_id: str, payload: NemesisRequest, user: User = Depends(api_current_user)):
    result = SCTService.finalize_nemesis(run_id=run_id, nemesis_details=payload.nemesis)
    return APIResponse({
        "status": "ok",
        "response": result
    })


@router.post("/{run_id}/events/submit", name="api.client_api.sct_api.sct_events_submit")
def sct_events_submit(run_id: str, payload: EventsSubmitRequest,
                      user: User = Depends(api_current_user)):
    """
        Legacy endpoint. Deprecated
        Submit a structure of EventsBySeverity that will be saved
        onto SCTTestRun
    """
    result = SCTService.submit_events(run_id=run_id, events=payload.events)
    return APIResponse({
        "status": "ok",
        "response": result
    })


@router.get("/{run_id}/events/get", name="api.client_api.sct_api.sct_events_get")
def sct_events_get(run_id: str, limit: int = Query(100), before: str | None = Query(None),
                   after: str | None = Query(None),
                   severities: list[str] = Query(default=[], alias="severity"),
                   user: User = Depends(api_current_user)):
    result = SCTService.get_events(run_id=run_id, limit=limit, before=before, after=after,
                                   severities=severities)
    return APIResponse({
        "status": "ok",
        "response": result
    })


@router.get("/{run_id}/events/{severity}/get", name="api.client_api.sct_api.sct_events_get_by_severity")
def sct_events_get_by_severity(run_id: str, severity: SCTEventSeverity, limit: int = Query(100),
                               before: str | None = Query(None), after: str | None = Query(None),
                               user: User = Depends(api_current_user)):
    result = SCTService.get_events(run_id=run_id, limit=limit, before=before, after=after,
                                   severities=[severity])
    return APIResponse({
        "status": "ok",
        "response": result
    })


@router.get("/{run_id}/events/{severity}/count",
            name="api.client_api.sct_api.sct_events_count_by_severity")
def sct_events_count_by_severity(run_id: str, severity: SCTEventSeverity,
                                 user: User = Depends(api_current_user)):
    result = SCTService.count_events_by_severity(run_id=run_id, severity=severity)
    return APIResponse({
        "status": "ok",
        "response": result
    })


@router.post("/{run_id}/event/submit", name="api.client_api.sct_api.sct_event_submit")
def sct_event_submit(run_id: str, payload: EventSubmitRequest,
                     user: User = Depends(api_current_user)):
    """
        Submit an event or a collection of events
    """
    event_data = payload.data
    if isinstance(event_data, list):
        result = all([SCTService.submit_event(run_id=run_id, raw_event=e) for e in event_data])
    else:
        result = SCTService.submit_event(run_id=run_id, raw_event=event_data)
    return APIResponse({
        "status": "ok",
        "response": result
    })


@router.post("/{run_id}/gemini/submit", name="api.client_api.sct_api.sct_gemini_results_submit")
def sct_gemini_results_submit(run_id: str, payload: GeminiResultsRequest,
                              user: User = Depends(api_current_user)):
    result = SCTService.submit_gemini_results(run_id=run_id, gemini_data=payload.gemini_data, user=user)
    return APIResponse({
        "status": "ok",
        "response": result
    })


@router.post("/{run_id}/performance/submit",
             name="api.client_api.sct_api.sct_performance_results_submit")
def sct_performance_results_submit(run_id: str, payload: PerformanceResultsRequest,
                                   user: User = Depends(api_current_user)):
    result = SCTService.submit_performance_results(run_id=run_id,
                                                   performance_results=payload.performance_results,
                                                   user=user)
    return APIResponse({
        "status": "ok",
        "response": result
    })


@router.get("/{run_id}/performance/history", name="api.client_api.sct_api.sct_get_performance_history")
def sct_get_performance_history(run_id: str, user: User = Depends(api_current_user)):
    result = SCTService.get_performance_history_for_test(run_id=run_id)
    return APIResponse({
        "status": "ok",
        "response": result
    })


@router.get("/release/{release_name:path}/kernels", name="api.client_api.sct_api.sct_get_kernel_report")
def sct_get_kernel_report(release_name: str, user: User = Depends(api_current_user)):
    result = SCTService.get_scylla_version_kernels_report(release_name=release_name)
    return APIResponse({
        "status": "ok",
        "response": result
    })


@router.post("/{run_id}/junit/submit", name="api.client_api.sct_api.sct_submit_junit_report")
def sct_submit_junit_report(run_id: str, payload: JunitSubmitRequest,
                            user: User = Depends(api_current_user)):
    result = SCTService.junit_submit(run_id, payload.file_name, payload.content)
    return APIResponse({
        "status": "ok",
        "response": result
    })


@router.post("/{run_id}/stress_cmd/submit", name="api.client_api.sct_api.sct_add_stress_cmd")
def sct_add_stress_cmd(run_id: str, payload: StressCommandRequest,
                       user: User = Depends(api_current_user)):
    result = SCTService.add_stress_command(run_id, cmd=payload.cmd, ts=payload.ts,
                                           loader_name=payload.loader_name, log_name=payload.log_name)
    return APIResponse({
        "status": "ok",
        "response": result
    })


@router.get("/{run_id}/stress_cmd/get", name="api.client_api.sct_api.sct_get_all_stress_cmds")
def sct_get_all_stress_cmds(run_id: str, user: User = Depends(api_current_user)):
    result = SCTService.get_stress_commands(run_id)
    return APIResponse({
        "status": "ok",
        "response": result
    })


@router.get("/{run_id}/similar_events", name="api.client_api.sct_api.sct_get_similar_events")
def sct_get_similar_events(run_id: str, user: User = Depends(api_current_user)):
    result = SCTService.get_similar_events(run_id=run_id)
    return APIResponse({
        "status": "ok",
        "response": result
    })


@router.post("/{run_id}/event/similar", name="api.client_api.sct_api.sct_get_similar_events_realtime")
def sct_get_similar_events_realtime(run_id: str, payload: SimilarEventRequest,
                                    user: User = Depends(api_current_user)):
    """Get similar events for a specific event using real-time vector search"""
    err_message = ""
    if not payload.severity and not payload.ts:
        err_message = "Missing required parameters: severity and ts"
    elif not payload.severity:
        err_message = "Missing required parameter: severity"
    elif not payload.ts:
        err_message = "Missing required parameter: ts"
    if err_message:
        raise SCTServiceException(err_message)

    result = SCTService.get_similar_events_realtime(
        run_id=run_id,
        severity=payload.severity,
        ts=payload.ts,
        limit=payload.limit
    )
    return APIResponse({
        "status": "ok",
        "response": result
    })


@router.post("/similar_runs_info", name="api.client_api.sct_api.sct_get_similar_runs_info")
def sct_get_similar_runs_info(payload: SimilarRunsInfoRequest,
                              user: User = Depends(api_current_user)):
    """Get build IDs and issues for a list of run IDs"""
    result = SCTService.get_similar_runs_info(run_ids=payload.run_ids)
    return APIResponse({
        "status": "ok",
        "response": result
    })
