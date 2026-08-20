import importlib
import logging
import pkgutil
from types import ModuleType
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from flask import Blueprint
from pydantic import BaseModel

from argus.backend.controller import views_widgets
from argus.backend.error_handlers import APIException, handle_api_exception
from argus.backend.models.web import User
from argus.backend.service.stats import ViewStatsCollector
from argus.backend.service.user import api_current_user
from argus.backend.service.views import UserViewService
from argus.backend.util.common import NoneIfEmpty
from argus.backend.util.encoders import ArgusJSONResponse

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/views")


class ViewApiException(APIException):
    pass


class CreateViewRequest(BaseModel):
    name: str
    items: list[str]
    settings: str
    description: str | None = None
    displayName: str | None = None


class UpdateViewRequest(BaseModel):
    viewId: str
    updateData: dict


class DeleteViewRequest(BaseModel):
    viewId: str


@router.get("/", name="api.view_api.index")
def index(user: User = Depends(api_current_user)):
    return ArgusJSONResponse({
        "status": "ok",
        "response": {
            "version": "v1",
        }
    })


@router.post("/create", name="api.view_api.create_view")
def create_view(payload: CreateViewRequest, user: User = Depends(api_current_user)):
    service = UserViewService()
    view = service.create_view(
        name=payload.name,
        items=payload.items,
        widget_settings=payload.settings,
        user=user,
        description=payload.description,
        display_name=payload.displayName
    )
    return ArgusJSONResponse({
        "status": "ok",
        "response": view
    })


@router.get("/get", name="api.view_api.get_view")
def get_view(view_id: UUID = Query(..., alias="viewId"), user: User = Depends(api_current_user)):
    service = UserViewService()
    view = service.get_view(view_id)
    return ArgusJSONResponse({
        "status": "ok",
        "response": view
    })


@router.get("/all", name="api.view_api.get_all_views")
def get_all_views(user_id: Annotated[UUID | None, NoneIfEmpty, Query(alias="userId")] = None,
                  user: User = Depends(api_current_user)):
    view_user = User.get(id=user_id) if user_id else None
    service = UserViewService()
    views = service.get_all_views(view_user)
    return ArgusJSONResponse({
        "status": "ok",
        "response": views
    })


@router.post("/update", name="api.view_api.update_view")
def update_view(payload: UpdateViewRequest, user: User = Depends(api_current_user)):
    service = UserViewService()
    res = service.update_view(view_id=payload.viewId, update_data=payload.updateData, user=user)
    return ArgusJSONResponse({
        "status": "ok",
        "response": res
    })


@router.post("/delete", name="api.view_api.delete_view")
def delete_view(payload: DeleteViewRequest, user: User = Depends(api_current_user)):
    service = UserViewService()
    res = service.delete_view(payload.viewId, user=user)
    return ArgusJSONResponse({
        "status": "ok",
        "response": res
    })


@router.get("/search", name="api.view_api.search_tests")
def search_tests(query: str | None = Query(None), user: User = Depends(api_current_user)):
    service = UserViewService()
    if query:
        res = service.test_lookup(query)
    else:
        res = []
    return ArgusJSONResponse({
        "status": "ok",
        "response": {
            "hits": res,
            "total": len(res)
        }
    })


@router.get("/stats", name="api.view_api.view_stats")
def view_stats(view_id: str = Query(..., alias="viewId"), limited: bool = Query(False),
               version: str | None = Query(None, alias="productVersion"),
               include_no_version: bool = Query(True, alias="includeNoVersion"),
               image_id: str | None = Query(None, alias="imageId"),
               force: bool = Query(False),
               widget_id: Annotated[int | None, NoneIfEmpty, Query(alias="widgetId")] = None,
               user: User = Depends(api_current_user)):
    collector = ViewStatsCollector(view_id=view_id, filter=version)
    stats = collector.collect(limited=limited, force=force, include_no_version=include_no_version,
                              widget_id=widget_id, image_id=image_id)

    return ArgusJSONResponse({
        "status": "ok",
        "response": stats
    })


@router.get("/{view_id}/versions", name="api.view_api.view_versions")
def view_versions(view_id: str, user: User = Depends(api_current_user)):
    service = UserViewService()
    res = service.get_versions_for_view(view_id)
    return ArgusJSONResponse({
        "status": "ok",
        "response": res
    })


@router.get("/{view_id}/images", name="api.view_api.view_images")
def view_images(view_id: str, user: User = Depends(api_current_user)):
    service = UserViewService()
    res = service.get_images_for_view(view_id)
    return ArgusJSONResponse({
        "status": "ok",
        "response": res
    })


@router.get("/{view_id}/resolve", name="api.view_api.view_resolve")
def view_resolve(view_id: str, user: User = Depends(api_current_user)):
    service = UserViewService()
    res = service.resolve_view_for_edit(view_id)
    return ArgusJSONResponse({
        "status": "ok",
        "response": res
    })


@router.get("/{view_id}/resolve/tests", name="api.view_api.view_resolve_tests")
def view_resolve_tests(view_id: str, user: User = Depends(api_current_user)):
    service = UserViewService()
    res = service.resolve_view_tests(view_id)
    return ArgusJSONResponse({
        "status": "ok",
        "response": res
    })


@router.get("/{view_id}/pytest/results", name="api.view_api.view_get_pytest_results")
def view_get_pytest_results(view_id: str, user: User = Depends(api_current_user)):
    service = UserViewService()
    res = service.get_pytest_view_results(view_id)
    return ArgusJSONResponse({
        "status": "ok",
        "response": res
    })


# The routes above are served by FastAPI; these view-less rules keep the
# endpoints buildable through Flask's url_for until the Flask app is retired.
bp = Blueprint('view_api', __name__, url_prefix='/views')
bp.register_error_handler(Exception, handle_api_exception)

for _rule, _endpoint in (
    ("/", "index"),
    ("/create", "create_view"),
    ("/get", "get_view"),
    ("/all", "get_all_views"),
    ("/update", "update_view"),
    ("/delete", "delete_view"),
    ("/search", "search_tests"),
    ("/stats", "view_stats"),
    ("/<string:view_id>/versions", "view_versions"),
    ("/<string:view_id>/images", "view_images"),
    ("/<string:view_id>/resolve", "view_resolve"),
    ("/<string:view_id>/resolve/tests", "view_resolve_tests"),
    ("/<string:view_id>/pytest/results", "view_get_pytest_results"),
):
    bp.add_url_rule(_rule, _endpoint, None)


def _widget_modules() -> list[ModuleType]:
    """Discover the view widget controllers: every module in views_widgets
    that exports a FastAPI ``router``."""
    modules = []
    for module_info in pkgutil.iter_modules(views_widgets.__path__):
        module = importlib.import_module(f"{views_widgets.__package__}.{module_info.name}")
        if getattr(module, "router", None) is not None:
            modules.append(module)
    return modules


for _module in _widget_modules():
    router.include_router(_module.router)
    if (widget_bp := getattr(_module, "bp", None)) is not None:
        bp.register_blueprint(widget_bp)
