from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from argus.backend.error_handlers import handle_api_exception
from argus.backend.service.results_service import ResultsService
from argus.backend.service.user import api_login_required

bp = Blueprint("results_api", __name__, url_prefix="/api/results")
bp.register_error_handler(Exception, handle_api_exception)


@bp.route("/catalog", methods=["GET"])
@api_login_required
def results_catalog():
    """Cross-test catalog of every generic result table name, with per-name
    test count and column metadata."""
    service = ResultsService()
    catalog = service.get_generic_result_catalog()

    return jsonify({
        "status": "ok",
        "response": catalog,
    })


@bp.route("/search", methods=["GET"])
@api_login_required
def results_search():
    """Cross-test flattened cell dump over generic result tables, filtered by
    table name substring, status, and a sut_timestamp range."""
    name = request.args.get("name")
    statuses = request.args.getlist("status[]")
    before = request.args.get("before")
    after = request.args.get("after")
    limit = int(request.args.get("limit", 500))

    before_dt = datetime.fromtimestamp(int(before), tz=timezone.utc) if before else None
    after_dt = datetime.fromtimestamp(int(after), tz=timezone.utc) if after else None

    service = ResultsService()
    result = service.search_generic_results(
        name=name,
        statuses=statuses or None,
        before=before_dt,
        after=after_dt,
        limit=limit,
    )

    return jsonify({
        "status": "ok",
        "response": result,
    })
