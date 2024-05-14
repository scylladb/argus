import logging
from uuid import UUID
from flask import (
    Blueprint,
    request
)

from argus.backend.error_handlers import handle_api_exception
from argus.backend.models.web import ArgusTest
from argus.backend.service.jenkins_service import JenkinsService
from argus.backend.service.testrun import TestRunService
from argus.backend.service.user import api_login_required
from argus.backend.util.common import get_payload
from argus.backend.util.enums import TestInvestigationStatus, TestStatus

bp = Blueprint('testrun_api', __name__, 'testrun')
bp.register_error_handler(Exception, handle_api_exception)
LOGGER = logging.getLogger(__name__)


@bp.route("/test/<string:test_id>/runs")
@api_login_required
def get_runs_for_test(test_id: str):
    limit = request.args.get("limit")
    if not limit:
        limit = 10
    else:
        limit = int(limit)
    additional_runs = [UUID(run) for run in request.args.getlist('additionalRuns[]')]
    service = TestRunService()

    runs = service.get_runs_by_test_id(test_id=UUID(test_id), additional_runs=additional_runs, limit=limit)

    return {
        "status": "ok",
        "response": runs
    }


@bp.route("/run/<string:run_type>/<string:run_id>")
@api_login_required
def get_testrun(run_type: str, run_id: str):
    run_id = UUID(run_id)
    service = TestRunService()
    test_run = service.get_run(run_type=run_type, run_id=run_id)

    return {
        "status": "ok",
        "response": test_run
    }


@bp.route("/run/<string:run_id>/activity")
@api_login_required
def test_run_activity(run_id: str):
    run_id = UUID(run_id)
    service = TestRunService()
    activity = service.get_run_events(run_id=run_id)

    return {
        "status": "ok",
        "response": activity
    }


@bp.route("/test/<string:test_id>/run/<string:run_id>/status/set", methods=["POST"])
@api_login_required
def set_testrun_status(test_id: str, run_id: str):
    payload = get_payload(client_request=request)
    new_status = payload.get("status")
    if not new_status:
        raise Exception("Status not specified in the request")
    service = TestRunService()
    result = service.change_run_status(
        test_id=UUID(test_id),
        run_id=UUID(run_id),
        new_status=TestStatus(new_status)
    )

    return {
        "status": "ok",
        "response": result
    }


@bp.route("/test/<string:test_id>/run/<string:run_id>/investigation_status/set", methods=["POST"])
@api_login_required
def set_testrun_investigation_status(test_id: str, run_id: str):
    payload = get_payload(client_request=request)
    new_status = payload.get("investigation_status")
    if not new_status:
        raise Exception("Status not specified in the request")
    service = TestRunService()
    result = service.change_run_investigation_status(
        test_id=UUID(test_id),
        run_id=UUID(run_id),
        new_status=TestInvestigationStatus(new_status),
    )

    return {
        "status": "ok",
        "response": result
    }


@bp.route("/test/<string:test_id>/run/<string:run_id>/assignee/set", methods=["POST"])
@api_login_required
def set_testrun_assignee(test_id: str, run_id: str):
    payload = get_payload(client_request=request)
    assignee = payload.get("assignee")
    if not assignee:
        raise Exception("Assignee not specified in the request")
    service = TestRunService()
    result = service.change_run_assignee(
        test_id=UUID(test_id),
        run_id=UUID(run_id),
        new_assignee=UUID(assignee) if assignee != TestRunService.ASSIGNEE_PLACEHOLDER else None,
    )

    return {
        "status": "ok",
        "response": result
    }


@bp.route("/test/<string:test_id>/run/<string:run_id>/issues/submit", methods=["POST"])
@api_login_required
def issues_submit(test_id: str, run_id: str):
    payload = get_payload(client_request=request)
    service = TestRunService()
    submit_result = service.submit_github_issue(
        issue_url=payload["issue_url"],
        test_id=UUID(test_id),
        run_id=UUID(run_id)
    )

    return {
        "status": "ok",
        "response": submit_result
    }


@bp.route("/issues/get", methods=["GET"])
@api_login_required
def issues_get():
    filter_key = request.args.get("filterKey")
    if not filter_key:
        raise Exception("Filter key not provided in the request")
    key_value = request.args.get("id")
    if not key_value:
        raise Exception("Id wasn't provided in the request")
    key_value = UUID(key_value)
    aggregate_by_issue = request.args.get("aggregateByIssue")
    aggregate_by_issue = bool(int(aggregate_by_issue)) if aggregate_by_issue else False
    service = TestRunService()
    issues = service.get_github_issues(
        filter_key=filter_key,
        filter_id=key_value,
        aggregate_by_issue=aggregate_by_issue
    )

    return {
        "status": "ok",
        "response": issues
    }


@bp.route("/issues/delete", methods=["POST"])
@api_login_required
def issues_delete():
    payload = get_payload(client_request=request)
    service = TestRunService()
    result = service.delete_github_issue(issue_id=payload["issue_id"])

    return {
        "status": "ok",
        "response": result
    }


@bp.route("/run/<string:run_id>/comments", methods=["GET"])
@api_login_required
def get_testrun_comments(run_id: str):
    service = TestRunService()
    comments = service.get_run_comments(
        run_id=UUID(run_id)
    )

    return {
        "status": "ok",
        "response": comments
    }


@bp.route("/comment/<string:comment_id>/get", methods=["GET"])
@api_login_required
def get_single_comment(comment_id: str):
    service = TestRunService()
    comment = service.get_run_comment(
        comment_id=UUID(comment_id)
    )

    return {
        "status": "ok",
        "response": comment
    }


@bp.route("/test/<string:test_id>/run/<string:run_id>/comments/submit", methods=["POST"])
@api_login_required
def submit_testrun_comment(test_id: str, run_id: str):
    payload = get_payload(request)
    service = TestRunService()
    result = service.post_run_comment(
        test_id=UUID(test_id),
        run_id=UUID(run_id),
        message=payload["message"],
        reactions=payload["reactions"],
        mentions=payload["mentions"],
    )

    return {
        "status": "ok",
        "response": result
    }


@bp.route("/test/<string:test_id>/run/<string:run_id>/comment/<string:comment_id>/update", methods=["POST"])
@api_login_required
def test_run_update_comment(test_id: str, run_id: str, comment_id: str):
    payload = get_payload(request)
    service = TestRunService()
    result = service.update_run_comment(
        test_id=UUID(test_id),
        run_id=UUID(run_id),
        comment_id=UUID(comment_id),
        message=payload["message"],
        reactions=payload["reactions"],
        mentions=payload["mentions"],
    )

    return {
        "status": "ok",
        "response": result
    }


@bp.route("/test/<string:test_id>/run/<string:run_id>/comment/<string:comment_id>/delete", methods=["POST"])
@api_login_required
def test_run_delete_comment(test_id: str, run_id: str, comment_id: str):
    service = TestRunService()
    result = service.delete_run_comment(
        test_id=UUID(test_id),
        run_id=UUID(run_id),
        comment_id=UUID(comment_id),
    )

    return {
        "status": "ok",
        "response": result
    }


@bp.route("/terminate_stuck_runs", methods=["POST"])
@api_login_required
def sct_terminate_stuck_runs():
    result = TestRunService().terminate_stuck_runs()
    return {
        "status": "ok",
        "response": {
            "total": result
        }
    }


@bp.route("/ignore_jobs", methods=["POST"])
@api_login_required
def ignore_jobs():
    payload = get_payload(request)
    service = TestRunService()

    result = service.ignore_jobs(test_id=payload["testId"], reason=payload["reason"])

    return {
        "status": "ok",
        "response": {
            "affectedJobs": result
        }
    }


@bp.route("/jenkins/params", methods=["POST"])
@api_login_required
def get_jenkins_job_params():

    payload = get_payload(request)
    service = JenkinsService()

    result = service.retrieve_job_parameters(build_id=payload["buildId"], build_number=payload["buildNumber"])

    return {
        "status": "ok",
        "response": {
            "parameters": result
        }
    }


@bp.route("/jenkins/build", methods=["POST"])
@api_login_required
def build_jenkins_job():

    payload = get_payload(request)
    service = JenkinsService()

    result = service.build_job(build_id=payload["buildId"], params=payload["parameters"])

    return {
        "status": "ok",
        "response": {
            "queueItem": result
        }
    }


@bp.route("/jenkins/queue_info")
@api_login_required
def get_queue_info():
    queue_item = request.args.get("queueItem")
    if not queue_item:
        raise Exception("No queueItem provided")
    service = JenkinsService()
    result = service.get_queue_info(int(queue_item))

    return {
        "status": "ok",
        "response": {
            "queueItem": result
        }
    }


@bp.route("/jenkins/clone/targets")
@api_login_required
def get_clone_targets():
    test_id = request.args.get("testId")
    if not test_id:
        raise Exception("No testId provided")
    service = JenkinsService()
    result = service.get_releases_for_clone(test_id)

    return {
        "status": "ok",
        "response": {
            "targets": result
        }
    }


@bp.route("/jenkins/clone/groups")
@api_login_required
def get_groups_for_target():
    target_id = request.args.get("targetId")
    if not target_id:
        raise Exception("No targetId provided")
    service = JenkinsService()
    result = service.get_groups_for_release(target_id)

    return {
        "status": "ok",
        "response": {
            "groups": result
        }
    }


@bp.route("/jenkins/clone/create", methods=["POST"])
@api_login_required
def clone_jenkins_job():

    payload = get_payload(request)
    service = JenkinsService()

    result = service.clone_job(
        current_test_id=payload["currentTestId"],
        new_name=payload["newName"],
        target=payload["target"],
        group=payload["group"],
        advanced_settings=payload["advancedSettings"],
    )

    return {
        "status": "ok",
        "response": result
    }


@bp.route("/jenkins/clone/build", methods=["POST"])
@api_login_required
def clone_build_jenkins_job():

    payload = get_payload(request)
    service = JenkinsService()

    result = service.clone_build_job(build_id=payload["buildId"], params=payload["parameters"])

    return {
        "status": "ok",
        "response": result
    }


@bp.route("/jenkins/clone/settings")
@api_login_required
def get_clone_job_advanced_settings():
    build_id = request.args.get("buildId")
    if not build_id:
        raise Exception("No testId provided")
    service = JenkinsService()
    result = service.get_advanced_settings(build_id)

    return {
        "status": "ok",
        "response": result
    }


@bp.route("/jenkins/clone/settings/change", methods=["POST"])
@api_login_required
def set_job_settings():
    payload = get_payload(request)
    service = JenkinsService()
    test = ArgusTest.get(build_system_id=payload["buildId"])
    result = service.adjust_job_settings(build_id=test.build_system_id, plugin_name=test.plugin_name, settings=payload["settings"])

    return {
        "status": "ok",
        "response": result
    }


@bp.route("/jenkins/clone/settings/validate", methods=["POST"])
@api_login_required
def clone_validate_new_settings():

    payload = get_payload(request)
    service = JenkinsService()

    result = service.verify_job_settings(build_id=payload["buildId"], new_settings=payload["newSettings"])

    return {
        "status": "ok",
        "response": result
    }
