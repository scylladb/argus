import logging
from uuid import UUID
from flask import (
    Blueprint,
    jsonify,
    request,
)
from argus.backend.error_handlers import handle_api_exception
from argus.backend.models.web import User
from argus.backend.service.stats import ViewStatsCollector
from argus.backend.service.user import api_login_required
from argus.backend.service.views import UserViewService
from argus.backend.util.common import get_payload

bp = Blueprint('view_api', __name__, url_prefix='/views')
LOGGER = logging.getLogger(__name__)
bp.register_error_handler(Exception, handle_api_exception)


class ViewApiException(Exception):
    pass


@bp.route("/", methods=["GET"])
@api_login_required
def index():
    return {
        "status": "ok",
        "response": {
            "version": "v1",
        }
    }


@bp.route("/create", methods=["POST"])
@api_login_required
def create_view():
    payload = get_payload(request)
    service = UserViewService()
    view = service.create_view(
        name=payload["name"], 
        items=payload["items"],
        widget_settings=payload["settings"],
        description=payload.get("description"),
        display_name=payload.get("displayName")
    )
    return {
        "status": "ok",
        "response": view
    }


@bp.route("/get", methods=["GET"])
@api_login_required
def get_view():
    view_id = request.args.get("viewId")
    if not view_id:
        raise ViewApiException("No viewId provided.")
    service = UserViewService()
    view = service.get_view(UUID(view_id))
    return {
        "status": "ok",
        "response": view
    }


@bp.route("/all", methods=["GET"])
@api_login_required
def get_all_views():
    user_id = request.args.get("userId")
    if user_id:
        user = User.get(id=user_id)
    else:
        user = None
    service = UserViewService()
    views = service.get_all_views(user)
    return {
        "status": "ok",
        "response": views
    }


@bp.route("/update", methods=["POST"])
@api_login_required
def update_view():
    payload = get_payload(request)
    service = UserViewService()
    res = service.update_view(view_id=payload["viewId"], update_data=payload["updateData"])
    return {
        "status": "ok",
        "response": res
    }


@bp.route("/delete", methods=["POST"])
@api_login_required
def delete_view():
    payload = get_payload(request)
    service = UserViewService()
    res = service.delete_view(payload["viewId"])
    return {
        "status": "ok",
        "response": res
    }


@bp.route("/search", methods=["GET"])
@api_login_required
def search_tests():
    query = request.args.get("query")
    service = UserViewService()
    if query:
        res = service.test_lookup(query)
    else:
        res = []
    return {
        "status": "ok",
        "response": {
            "hits": res,
            "total": len(res)
        }
    }

@bp.route("/stats", methods=["GET"])
@api_login_required
def view_stats():
    view_id = request.args.get("viewId")
    if not view_id:
        raise ViewApiException("No view id provided.")
    limited = bool(int(request.args.get("limited", 0)))
    version = request.args.get("productVersion", None)
    include_no_version = bool(int(request.args.get("includeNoVersion", True)))
    force = bool(int(request.args.get("force",  0)))
    collector = ViewStatsCollector(view_id=view_id, filter=version)
    stats = collector.collect(limited=limited, force=force, include_no_version=include_no_version)

    res = jsonify({
        "status": "ok",
        "response": stats
    })
    res.cache_control.max_age = 300
    return res

@bp.route("/<string:view_id>/versions", methods=["GET"])
@api_login_required
def view_versions(view_id: str):
    service = UserViewService()
    res = service.get_versions_for_view(view_id)
    return {
        "status": "ok",
        "response": res
    }

@bp.route("/<string:view_id>/resolve", methods=["GET"])
@api_login_required
def view_resolve(view_id: str):
    service = UserViewService()
    res = service.resolve_view_for_edit(view_id)
    return {
        "status": "ok",
        "response": res
    }