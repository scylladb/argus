from fastapi import APIRouter, Body, Depends, Request
from pydantic import BaseModel
from starlette.responses import HTMLResponse

from argus.backend.controller import replay_api, ssh_api
from argus.backend.models.web import User
from argus.backend.plugins.loader import AVAILABLE_PLUGINS
from argus.backend.service.client_service import ClientService
from argus.backend.service.email_service import EmailService
from argus.backend.service.testrun import TestRunService
from argus.backend.service.user import api_current_user
from argus.backend.util.encoders import ArgusJSONResponse

router = APIRouter(prefix="/client")
router.include_router(ssh_api.router)
router.include_router(replay_api.router)
for plugin in AVAILABLE_PLUGINS.values():
    if plugin.controller is not None:
        router.include_router(plugin.controller)


class SetStatusRequest(BaseModel):
    new_status: str


class ProductVersionRequest(BaseModel):
    product_version: str


class LogsSubmitRequest(BaseModel):
    logs: list[dict]


class ConfigSubmitRequest(BaseModel):
    name: str
    content: str


@router.get("/testrun/{run_id}/info", name="api.client_api.get_run_info")
def get_run_info(run_id: str, user: User = Depends(api_current_user)):
    result = ClientService().get_run_info(run_id=run_id)
    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.post("/testrun/{run_type}/submit", name="api.client_api.submit_run")
def submit_run(run_type: str, payload: dict = Body(...), user: User = Depends(api_current_user)):
    result = ClientService().submit_run(run_type=run_type, request_data=payload)
    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.get("/testrun/{run_type}/{run_id}/get", name="api.client_api.get_run")
def get_run(run_type: str, run_id: str, user: User = Depends(api_current_user)):
    result = ClientService().get_run(run_type=run_type, run_id=run_id)
    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.post("/testrun/{run_type}/{run_id}/heartbeat", name="api.client_api.run_heartbeat")
def run_heartbeat(run_type: str, run_id: str, user: User = Depends(api_current_user)):
    result = ClientService().heartbeat(run_type=run_type, run_id=run_id)
    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.get("/testrun/{run_type}/{run_id}/get_status", name="api.client_api.run_get_status")
def run_get_status(run_type: str, run_id: str, user: User = Depends(api_current_user)):
    result = ClientService().get_run_status(run_type=run_type, run_id=run_id)
    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.post("/testrun/{run_type}/{run_id}/set_status", name="api.client_api.run_set_status")
def run_set_status(run_type: str, run_id: str, payload: SetStatusRequest,
                   user: User = Depends(api_current_user)):
    result = ClientService().update_run_status(run_type=run_type, run_id=run_id,
                                               new_status=payload.new_status)
    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.post("/testrun/{run_type}/{run_id}/update_product_version",
             name="api.client_api.run_update_product_version")
def run_update_product_version(run_type: str, run_id: str, payload: ProductVersionRequest,
                               user: User = Depends(api_current_user)):
    result = ClientService().submit_product_version(
        run_type=run_type, run_id=run_id, version=payload.product_version)
    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.post("/testrun/{run_type}/{run_id}/logs/submit", name="api.client_api.run_submit_logs")
def run_submit_logs(run_type: str, run_id: str, payload: LogsSubmitRequest,
                    user: User = Depends(api_current_user)):
    result = ClientService().submit_logs(run_type=run_type, run_id=run_id, logs=payload.logs)
    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.post("/{run_id}/config/submit", name="api.client_api.submit_run_config")
def submit_run_config(run_id: str, payload: ConfigSubmitRequest,
                      user: User = Depends(api_current_user)):
    result = ClientService().submit_config(run_id, config_name=payload.name,
                                           config_content=payload.content)
    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.get("/{run_id}/config/all", name="api.client_api.get_all_run_configs")
def get_all_run_configs(run_id: str, user: User = Depends(api_current_user)):
    result = ClientService().get_all_configs(run_id)
    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.post("/testrun/{run_type}/{run_id}/finalize", name="api.client_api.run_finalize")
def run_finalize(run_type: str, run_id: str, payload: dict | None = Body(None),
                 user: User = Depends(api_current_user)):
    result = ClientService().finish_run(run_type=run_type, run_id=run_id, payload=payload)
    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.post("/testrun/{run_type}/{run_id}/submit_results", name="api.client_api.submit_results")
def submit_results(run_type: str, run_id: str, payload: dict = Body(...),
                   user: User = Depends(api_current_user)):
    return ArgusJSONResponse(
        ClientService().submit_results(run_type=run_type, run_id=run_id, results=payload))


@router.post("/testrun/pytest/result/submit", name="api.client_api.submit_pytest_result")
def submit_pytest_result(payload: dict = Body(...), user: User = Depends(api_current_user)):
    result = ClientService().submit_pytest_result(request_data=payload)
    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.get("/testrun/pytest/{test_name}/stats/{field_name}/{aggr_function}",
            name="api.client_api.get_pytest_test_field_stats")
def get_pytest_test_field_stats(asgi_request: Request, test_name: str, field_name: str,
                                aggr_function: str, user: User = Depends(api_current_user)):
    """
        Method: GET
        Params:
            test_name: name of a pytest unit, for example "sample.py::TestSample::test_sampe"
            field_name: a field inside PytestResultTable that supports aggregation, e.g. duration
            aggr_function: Supported: avg, count, min, max - which function to use for the aggregate
    """
    result = TestRunService().get_pytest_test_field_stats(
        test_name=test_name, field_name=field_name,
        aggr_function=aggr_function, query=dict(asgi_request.query_params))

    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.post("/testrun/report/email", name="api.client_api.send_email_report")
def send_email_report(payload: dict = Body(...), user: User = Depends(api_current_user)):
    result = EmailService().send_report(request_data=payload)
    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.post("/testrun/report", name="api.client_api.render_email_report")
def render_email_report(payload: dict = Body(...), user: User = Depends(api_current_user)):
    result = EmailService().display_report(request_data=payload)
    # the rendered report is returned as raw HTML, not the JSON envelope
    return HTMLResponse(result)
