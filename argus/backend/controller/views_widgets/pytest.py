from uuid import UUID

from flask import Blueprint

from argus.backend.service.user import api_login_required
from argus.backend.service.views_widgets.pytest import PytestViewService

bp = Blueprint("pytest", __name__, url_prefix="/widgets")


@bp.route("/pytest/view", methods=["GET"])
@api_login_required
def get_versioned_runs():
    service = PytestViewService()
    return {
        "status": "ok",
        "response": 0,
    }


@bp.route("/pytest/release/<string:release_id>/results")
@api_login_required
def get_release_pytest_results(release_id: str):
    release_id = UUID(release_id)
    service = PytestViewService()
    res = service.release_results(release_id)

    return {
        "status": "ok",
        "response": res
    }


@bp.route("/pytest/view/<string:view_id>/results", methods=["GET"])
@api_login_required
def get_view_pytest_results(view_id: str):
    service = PytestViewService()
    res = service.view_results(view_id)
    return {
        "status": "ok",
        "response": res
    }

@bp.route("/pytest/<string:test_name>/<string:id>/fields", methods=["GET"])
@api_login_required
def get_user_fields_for_test(test_name: str, id: str):
    service = PytestViewService()
    res = service.get_user_fields_for_result(test_name, id)
    return {
        "status": "ok",
        "response": res
    }
