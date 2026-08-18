from uuid import UUID

from fastapi import APIRouter, Depends, Request
from flask import Blueprint

from argus.backend.models.web import User
from argus.backend.service.user import api_current_user
from argus.backend.service.views_widgets.pytest import PytestViewService
from argus.backend.util.encoders import ArgusJSONResponse

router = APIRouter(prefix="/widgets")


@router.get("/pytest/view", name="api.view_api.pytest.get_versioned_runs")
def get_versioned_runs(user: User = Depends(api_current_user)):
    return ArgusJSONResponse({
        "status": "ok",
        "response": 0,
    })


@router.get("/pytest/release/{release_id}/results", name="api.view_api.pytest.get_release_pytest_results")
def get_release_pytest_results(asgi_request: Request, release_id: UUID,
                               user: User = Depends(api_current_user)):
    service = PytestViewService()
    res = service.release_results(release_id, asgi_request.query_params)

    return ArgusJSONResponse({
        "status": "ok",
        "response": res
    })


@router.get("/pytest/view/{view_id}/results", name="api.view_api.pytest.get_view_pytest_results")
def get_view_pytest_results(asgi_request: Request, view_id: str,
                            user: User = Depends(api_current_user)):
    service = PytestViewService()
    res = service.view_results(view_id, asgi_request.query_params)
    return ArgusJSONResponse({
        "status": "ok",
        "response": res
    })


@router.get("/pytest/results", name="api.view_api.pytest.get_pytest_results")
def get_pytest_results(asgi_request: Request, user: User = Depends(api_current_user)):
    service = PytestViewService()
    res = service.result_filter(asgi_request.query_params)
    return ArgusJSONResponse({
        "status": "ok",
        "response": res
    })


@router.get("/pytest/{test_name:path}/{id}/fields", name="api.view_api.pytest.get_user_fields_for_test")
def get_user_fields_for_test(test_name: str, id: str, user: User = Depends(api_current_user)):
    service = PytestViewService()
    res = service.get_user_fields_for_result(test_name, id)
    return ArgusJSONResponse({
        "status": "ok",
        "response": res
    })


# The routes above are served by FastAPI; these view-less rules keep the
# endpoints buildable through Flask's url_for until the Flask app is retired.
bp = Blueprint("pytest", __name__, url_prefix="/widgets")
for _rule, _endpoint in (
    ("/pytest/view", "get_versioned_runs"),
    ("/pytest/release/<string:release_id>/results", "get_release_pytest_results"),
    ("/pytest/view/<string:view_id>/results", "get_view_pytest_results"),
    ("/pytest/results", "get_pytest_results"),
    ("/pytest/<path:test_name>/<string:id>/fields", "get_user_fields_for_test"),
):
    bp.add_url_rule(_rule, _endpoint, None)
