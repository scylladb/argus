from fastapi import APIRouter, Depends, Query

from argus.backend.models.web import User
from argus.backend.plugins.driver_matrix_tests.raw_types import (
    DriverMatrixSubmitEnvRequest,
    DriverMatrixSubmitFailureRequest,
    DriverMatrixSubmitResultRequest,
)
from argus.backend.plugins.driver_matrix_tests.service import DriverMatrixService
from argus.backend.service.user import api_current_user
from argus.backend.util.encoders import ArgusJSONResponse

router = APIRouter(prefix="/driver_matrix")


@router.get("/test_report", name="api.client_api.driver_matrix_api.driver_matrix_test_report")
def driver_matrix_test_report(build_id: str = Query(..., alias="buildId"),
                              user: User = Depends(api_current_user)):
    result = DriverMatrixService().tested_versions_report(build_id=build_id)
    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.post("/result/submit", name="api.client_api.driver_matrix_api.submit_result")
def submit_result(payload: DriverMatrixSubmitResultRequest,
                  user: User = Depends(api_current_user)):
    result = DriverMatrixService().submit_driver_result(
        driver_name=payload.driver_name, driver_type=payload.driver_type,
        run_id=payload.run_id, raw_xml=payload.raw_xml)
    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.post("/result/fail", name="api.client_api.driver_matrix_api.submit_failure")
def submit_failure(payload: DriverMatrixSubmitFailureRequest,
                   user: User = Depends(api_current_user)):
    result = DriverMatrixService().submit_driver_failure(
        driver_name=payload.driver_name, driver_type=payload.driver_type,
        run_id=payload.run_id, failure_reason=payload.failure_reason)
    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.post("/env/submit", name="api.client_api.driver_matrix_api.submit_env")
def submit_env(payload: DriverMatrixSubmitEnvRequest, user: User = Depends(api_current_user)):
    result = DriverMatrixService().submit_env_info(run_id=payload.run_id, raw_env=payload.raw_env)
    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })
