import logging
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, Request
from flask import Blueprint
from pydantic import BaseModel

from coodie.exceptions import DocumentNotFound
from starlette.responses import RedirectResponse

from argus.backend.error_handlers import handle_api_exception
from argus.backend.models.web import ArgusTest, User
from argus.backend.service.issue_service import IssueService
from argus.backend.service.jenkins_service import JenkinsService
from argus.backend.service.results_service import ResultsService
from argus.backend.service.testrun import TestRunService
from argus.backend.service.user import api_current_user
from argus.backend.util.encoders import ArgusJSONResponse
from argus.common.enums import TestInvestigationStatus, TestStatus

LOGGER = logging.getLogger(__name__)

router = APIRouter()


class SetStatusRequest(BaseModel):
    status: TestStatus


class SetInvestigationStatusRequest(BaseModel):
    investigation_status: TestInvestigationStatus


class SetAssigneeRequest(BaseModel):
    assignee: str


class IssueSubmitRequest(BaseModel):
    issue_url: str


class IssueDeleteRequest(BaseModel):
    issue_id: UUID
    run_id: UUID


class CommentRequest(BaseModel):
    message: str
    reactions: dict
    mentions: list[str]


class IgnoreJobsRequest(BaseModel):
    testId: UUID
    reason: str


class JenkinsParamsRequest(BaseModel):
    buildId: str
    buildNumber: int | None = None
    fromDefaults: bool = False


class JenkinsBuildRequest(BaseModel):
    buildId: str
    parameters: dict
    includeBuildNumber: bool = False


class JenkinsCloneRequest(BaseModel):
    currentTestId: UUID
    newName: str
    target: str
    group: str
    advancedSettings: dict


class JenkinsSettingsChangeRequest(BaseModel):
    buildId: str
    settings: dict


class JenkinsSettingsValidateRequest(BaseModel):
    buildId: str
    newSettings: dict


@router.get("/test/{test_id}/runs", name="api.testrun_api.get_runs_for_test")
def get_runs_for_test(test_id: UUID, limit: int = Query(10), before: float | None = Query(None),
                      after: float | None = Query(None), full: bool = Query(False),
                      additional_runs: list[UUID] = Query(default=[], alias="additionalRuns[]"),
                      user: User = Depends(api_current_user)):
    service = TestRunService()
    runs = service.get_runs_by_test_id(test_id=test_id, additional_runs=additional_runs,
                                       limit=limit, full=full, before=before, after=after)

    return ArgusJSONResponse({
        "status": "ok",
        "response": runs
    })


@router.get("/run/{run_id}/type", name="api.testrun_api.get_type_for_run")
def get_type_for_run(run_id: str, user: User = Depends(api_current_user)):
    service = TestRunService()
    run_type = service.get_test_type_for_run(run_id)

    return ArgusJSONResponse({
        "status": "ok",
        "response": {
            "run_type": run_type,
        }
    })


@router.get("/run/{run_id}/activity", name="api.testrun_api.test_run_activity")
def test_run_activity(run_id: UUID, user: User = Depends(api_current_user)):
    service = TestRunService()
    activity = service.get_run_events(run_id=run_id)

    return ArgusJSONResponse({
        "status": "ok",
        "response": activity
    })


@router.get("/run/{test_id}/{run_id}/fetch_results", name="api.testrun_api.fetch_results")
def fetch_results(test_id: UUID, run_id: UUID, user: User = Depends(api_current_user)):
    tables = ResultsService().get_run_results(test_id=test_id, run_id=run_id)
    return ArgusJSONResponse({
        "status": "ok",
        "tables": tables
    })


@router.post("/test/{test_id}/run/{run_id}/status/set", name="api.testrun_api.set_testrun_status")
def set_testrun_status(test_id: UUID, run_id: UUID, payload: SetStatusRequest,
                       user: User = Depends(api_current_user)):
    service = TestRunService()
    result = service.change_run_status(
        test_id=test_id,
        run_id=run_id,
        new_status=payload.status,
        user=user,
    )

    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.get("/tests/{plugin_name}/{run_id}/log/{log_name}/download", name="api.testrun_api.download_log")
def download_log(plugin_name: str, run_id: UUID, log_name: str,
                 user: User = Depends(api_current_user)):
    service = TestRunService()
    result = service.get_log(
        plugin_name=plugin_name,
        run_id=run_id,
        log_name=log_name,
    )

    return RedirectResponse(result, status_code=302)


@router.get("/tests/{plugin_name}/{run_id}/screenshot/{image_name}", name="api.testrun_api.proxy_screenshot")
def proxy_screenshot(plugin_name: str, run_id: UUID, image_name: str,
                     user: User = Depends(api_current_user)):
    service = TestRunService()
    result = service.proxy_stored_s3_image(
        plugin_name=plugin_name,
        run_id=run_id,
        image_name=image_name,
    )

    return RedirectResponse(result, status_code=302)


@router.post("/test/{test_id}/run/{run_id}/investigation_status/set",
             name="api.testrun_api.set_testrun_investigation_status")
def set_testrun_investigation_status(test_id: UUID, run_id: UUID,
                                     payload: SetInvestigationStatusRequest,
                                     user: User = Depends(api_current_user)):
    service = TestRunService()
    result = service.change_run_investigation_status(
        test_id=test_id,
        run_id=run_id,
        new_status=payload.investigation_status,
        user=user,
    )

    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.post("/test/{test_id}/run/{run_id}/assignee/set", name="api.testrun_api.set_testrun_assignee")
def set_testrun_assignee(test_id: UUID, run_id: UUID, payload: SetAssigneeRequest,
                         user: User = Depends(api_current_user)):
    service = TestRunService()
    result = service.change_run_assignee(
        test_id=test_id,
        run_id=run_id,
        new_assignee=UUID(payload.assignee) if payload.assignee != TestRunService.ASSIGNEE_PLACEHOLDER else None,
        user=user,
    )

    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.post("/test/{test_id}/run/{run_id}/issues/submit", name="api.testrun_api.issues_submit")
def issues_submit(test_id: UUID, run_id: UUID, payload: IssueSubmitRequest,
                  user: User = Depends(api_current_user)):
    service = IssueService()
    submit_result = service.submit(
        issue_url=payload.issue_url,
        test_id=test_id,
        run_id=run_id,
        user=user,
    )

    return ArgusJSONResponse({
        "status": "ok",
        "response": submit_result
    })


@router.post("/test/{test_id}/run/{run_id}/issues/event/{event_id}/submit",
             name="api.testrun_api.issues_submit_for_event")
def issues_submit_for_event(test_id: UUID, run_id: UUID, event_id: UUID,
                            payload: IssueSubmitRequest,
                            user: User = Depends(api_current_user)):
    service = IssueService()
    submit_result = service.submit_for_sct_event(
        issue_url=payload.issue_url,
        test_id=test_id,
        event_id=event_id,
        run_id=run_id,
        user=user,
    )

    return ArgusJSONResponse({
        "status": "ok",
        "response": submit_result
    })


@router.get("/issues/get", name="api.testrun_api.issues_get")
def issues_get(filter_key: str = Query(..., alias="filterKey"),
               key_value: UUID = Query(..., alias="id"),
               aggregate_by_issue: bool = Query(False, alias="aggregateByIssue"),
               product_version: str | None = Query(None, alias="productVersion"),
               include_no_version: bool = Query(False, alias="includeNoVersion"),
               user: User = Depends(api_current_user)):
    service = IssueService()
    issues = service.get(
        filter_key=filter_key,
        filter_id=key_value,
        aggregate_by_issue=aggregate_by_issue,
        product_version=product_version or None,
        include_no_version=include_no_version,
    )

    return ArgusJSONResponse({
        "status": "ok",
        "response": issues
    })


@router.post("/issues/delete", name="api.testrun_api.issues_delete")
def issues_delete(payload: IssueDeleteRequest, user: User = Depends(api_current_user)):
    service = IssueService()
    result = service.delete(issue_id=payload.issue_id, run_id=payload.run_id, user=user)

    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.get("/run/{run_id}/comments", name="api.testrun_api.get_testrun_comments")
def get_testrun_comments(run_id: UUID, user: User = Depends(api_current_user)):
    service = TestRunService()
    comments = service.get_run_comments(run_id=run_id)

    return ArgusJSONResponse({
        "status": "ok",
        "response": comments
    })


@router.get("/run/{run_id}/pytest/results", name="api.testrun_api.get_testrun_pytest_results")
def get_testrun_pytest_results(run_id: UUID, user: User = Depends(api_current_user)):
    service = TestRunService()
    res = service.get_pytest_run_results(run_id=run_id)

    return ArgusJSONResponse({
        "status": "ok",
        "response": res
    })


# NOTE: declared after the specific /run/{run_id}/<suffix> routes — Starlette
# matches in declaration order and this generic pattern would shadow them.
@router.get("/run/{run_type}/{run_id}", name="api.testrun_api.get_testrun")
def get_testrun(run_type: str, run_id: UUID, user: User = Depends(api_current_user)):
    service = TestRunService()
    test_run = service.get_run_response(run_type=run_type, run_id=run_id)
    return ArgusJSONResponse({
        "status": "ok",
        "response": test_run
    })


@router.get("/comment/{comment_id}/get", name="api.testrun_api.get_single_comment")
def get_single_comment(comment_id: UUID, user: User = Depends(api_current_user)):
    service = TestRunService()
    comment = service.get_run_comment(comment_id=comment_id)

    return ArgusJSONResponse({
        "status": "ok",
        "response": comment
    })


@router.post("/test/{test_id}/run/{run_id}/comments/submit", name="api.testrun_api.submit_testrun_comment")
def submit_testrun_comment(test_id: UUID, run_id: UUID, payload: CommentRequest,
                           user: User = Depends(api_current_user)):
    service = TestRunService()
    result = service.post_run_comment(
        test_id=test_id,
        run_id=run_id,
        message=payload.message,
        reactions=payload.reactions,
        mentions=payload.mentions,
        user=user,
    )

    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.post("/test/{test_id}/run/{run_id}/comment/{comment_id}/update",
             name="api.testrun_api.test_run_update_comment")
def test_run_update_comment(test_id: UUID, run_id: UUID, comment_id: UUID,
                            payload: CommentRequest,
                            user: User = Depends(api_current_user)):
    service = TestRunService()
    result = service.update_run_comment(
        test_id=test_id,
        run_id=run_id,
        comment_id=comment_id,
        message=payload.message,
        reactions=payload.reactions,
        mentions=payload.mentions,
        user=user,
    )

    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.post("/test/{test_id}/run/{run_id}/comment/{comment_id}/delete",
             name="api.testrun_api.test_run_delete_comment")
def test_run_delete_comment(test_id: UUID, run_id: UUID, comment_id: UUID,
                            user: User = Depends(api_current_user)):
    service = TestRunService()
    result = service.delete_run_comment(
        test_id=test_id,
        run_id=run_id,
        comment_id=comment_id,
        user=user,
    )

    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.post("/terminate_stuck_runs", name="api.testrun_api.sct_terminate_stuck_runs")
def sct_terminate_stuck_runs(user: User = Depends(api_current_user)):
    result = TestRunService().terminate_stuck_runs(user=user)
    return ArgusJSONResponse({
        "status": "ok",
        "response": {
            "total": result
        }
    })


@router.post("/ignore_jobs", name="api.testrun_api.ignore_jobs")
def ignore_jobs(payload: IgnoreJobsRequest, user: User = Depends(api_current_user)):
    service = TestRunService()

    result = service.ignore_jobs(test_id=payload.testId, reason=payload.reason, user=user)

    return ArgusJSONResponse({
        "status": "ok",
        "response": {
            "affectedJobs": result
        }
    })


@router.post("/get_runs_by_test_id_run_id", name="api.testrun_api.get_runs_by_test_id_run_id")
def get_runs_by_test_id_run_id(payload: list[tuple[UUID, UUID]] = Body(...),
                               user: User = Depends(api_current_user)):
    service = TestRunService()

    result = service.resolve_run_build_id_and_number_multiple(payload)

    return ArgusJSONResponse({
        "status": "ok",
        "response": {
            "runs": result
        }
    })


@router.post("/jenkins/params", name="api.testrun_api.get_jenkins_job_params")
def get_jenkins_job_params(payload: JenkinsParamsRequest, user: User = Depends(api_current_user)):
    service = JenkinsService()

    result = service.retrieve_job_parameters(
        build_id=payload.buildId,
        build_number=payload.buildNumber,
        from_defaults=payload.fromDefaults,
    )

    return ArgusJSONResponse({
        "status": "ok",
        "response": {
            "parameters": result
        }
    })


@router.post("/jenkins/build", name="api.testrun_api.build_jenkins_job")
def build_jenkins_job(payload: JenkinsBuildRequest, user: User = Depends(api_current_user)):
    service = JenkinsService()

    # scylla-cluster-tests jobs require exactly one Scylla version source to be
    # set, otherwise the build fails to start. Validate before triggering so the
    # caller (CLI/UI/API) gets a clear error instead of a broken run. Skipped
    # when the test/plugin can't be resolved (e.g. a brand-new job).
    try:
        test = ArgusTest.get(build_system_id=payload.buildId)
    except DocumentNotFound:
        test = None
    if test and test.plugin_name == "scylla-cluster-tests":
        JenkinsService.validate_sct_version_source(payload.parameters)

    result = service.build_job(build_id=payload.buildId, params=payload.parameters,
                               requested_by=user)

    response = {
        "queueItem": result
    }
    # The CLI opts in via includeBuildNumber to receive the guessed next build
    # number, so it can print a stable Argus run link without waiting for the
    # build to leave the queue. Omitted (not fatal) when it can't be resolved.
    if payload.includeBuildNumber:
        next_build_number = service.next_build_number(build_id=payload.buildId)
        if next_build_number > 0:
            response["nextBuildNumber"] = next_build_number

    return ArgusJSONResponse({
        "status": "ok",
        "response": response
    })


@router.get("/jenkins/queue_info", name="api.testrun_api.get_queue_info")
def get_queue_info(queue_item: int = Query(..., alias="queueItem"),
                   user: User = Depends(api_current_user)):
    service = JenkinsService()
    result = service.get_queue_info(queue_item)

    return ArgusJSONResponse({
        "status": "ok",
        "response": {
            "queueItem": result
        }
    })


@router.get("/jenkins/clone/targets", name="api.testrun_api.get_clone_targets")
def get_clone_targets(test_id: str = Query(..., alias="testId"),
                      user: User = Depends(api_current_user)):
    service = JenkinsService()
    result = service.get_releases_for_clone(test_id)

    return ArgusJSONResponse({
        "status": "ok",
        "response": {
            "targets": result
        }
    })


@router.get("/jenkins/clone/groups", name="api.testrun_api.get_groups_for_target")
def get_groups_for_target(target_id: str = Query(..., alias="targetId"),
                          user: User = Depends(api_current_user)):
    service = JenkinsService()
    result = service.get_groups_for_release(target_id)

    return ArgusJSONResponse({
        "status": "ok",
        "response": {
            "groups": result
        }
    })


@router.post("/jenkins/clone/create", name="api.testrun_api.clone_jenkins_job")
def clone_jenkins_job(payload: JenkinsCloneRequest, user: User = Depends(api_current_user)):
    service = JenkinsService()

    result = service.clone_job(
        current_test_id=payload.currentTestId,
        new_name=payload.newName,
        target=payload.target,
        group=payload.group,
        advanced_settings=payload.advancedSettings,
    )

    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.post("/jenkins/clone/build", name="api.testrun_api.clone_build_jenkins_job")
def clone_build_jenkins_job(payload: JenkinsBuildRequest, user: User = Depends(api_current_user)):
    service = JenkinsService()

    result = service.clone_build_job(build_id=payload.buildId, params=payload.parameters,
                                     requested_by=user)

    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.get("/jenkins/clone/settings", name="api.testrun_api.get_clone_job_advanced_settings")
def get_clone_job_advanced_settings(build_id: str = Query(..., alias="buildId"),
                                    user: User = Depends(api_current_user)):
    service = JenkinsService()
    result = service.get_advanced_settings(build_id)

    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.post("/jenkins/clone/settings/change", name="api.testrun_api.set_job_settings")
def set_job_settings(payload: JenkinsSettingsChangeRequest, user: User = Depends(api_current_user)):
    service = JenkinsService()
    test = ArgusTest.get(build_system_id=payload.buildId)
    result = service.adjust_job_settings(build_id=test.build_system_id,
                                         plugin_name=test.plugin_name, settings=payload.settings)

    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.post("/jenkins/clone/settings/validate", name="api.testrun_api.clone_validate_new_settings")
def clone_validate_new_settings(payload: JenkinsSettingsValidateRequest,
                                user: User = Depends(api_current_user)):
    service = JenkinsService()

    result = service.verify_job_settings(build_id=payload.buildId, new_settings=payload.newSettings)

    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.get("/pytest/{test_name}/stats/{field_name}/{aggr_function}",
            name="api.testrun_api.get_pytest_test_field_stats")
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


@router.get("/pytest/{test_name}/results", name="api.testrun_api.get_pytest_test_results")
def get_pytest_test_results(test_name: str, before: float | None = Query(None),
                            after: float | None = Query(None),
                            user: User = Depends(api_current_user)):
    result = TestRunService().get_pytest_test_results(test_name=test_name, before=before, after=after)

    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


# The routes above are served by FastAPI; these view-less rules keep the
# endpoints buildable through Flask's url_for until the Flask app is retired.
bp = Blueprint('testrun_api', __name__, 'testrun')
bp.register_error_handler(Exception, handle_api_exception)

for _rule, _endpoint in (
    ("/test/<string:test_id>/runs", "get_runs_for_test"),
    ("/run/<string:run_id>/type", "get_type_for_run"),
    ("/run/<string:run_type>/<string:run_id>", "get_testrun"),
    ("/run/<string:run_id>/activity", "test_run_activity"),
    ("/run/<string:test_id>/<string:run_id>/fetch_results", "fetch_results"),
    ("/test/<string:test_id>/run/<string:run_id>/status/set", "set_testrun_status"),
    ("/tests/<string:plugin_name>/<string:run_id>/log/<string:log_name>/download", "download_log"),
    ("/tests/<string:plugin_name>/<string:run_id>/screenshot/<string:image_name>", "proxy_screenshot"),
    ("/test/<string:test_id>/run/<string:run_id>/investigation_status/set", "set_testrun_investigation_status"),
    ("/test/<string:test_id>/run/<string:run_id>/assignee/set", "set_testrun_assignee"),
    ("/test/<string:test_id>/run/<string:run_id>/issues/submit", "issues_submit"),
    ("/test/<string:test_id>/run/<string:run_id>/issues/event/<string:event_id>/submit", "issues_submit_for_event"),
    ("/issues/get", "issues_get"),
    ("/issues/delete", "issues_delete"),
    ("/run/<string:run_id>/comments", "get_testrun_comments"),
    ("/run/<string:run_id>/pytest/results", "get_testrun_pytest_results"),
    ("/comment/<string:comment_id>/get", "get_single_comment"),
    ("/test/<string:test_id>/run/<string:run_id>/comments/submit", "submit_testrun_comment"),
    ("/test/<string:test_id>/run/<string:run_id>/comment/<string:comment_id>/update", "test_run_update_comment"),
    ("/test/<string:test_id>/run/<string:run_id>/comment/<string:comment_id>/delete", "test_run_delete_comment"),
    ("/terminate_stuck_runs", "sct_terminate_stuck_runs"),
    ("/ignore_jobs", "ignore_jobs"),
    ("/get_runs_by_test_id_run_id", "get_runs_by_test_id_run_id"),
    ("/jenkins/params", "get_jenkins_job_params"),
    ("/jenkins/build", "build_jenkins_job"),
    ("/jenkins/queue_info", "get_queue_info"),
    ("/jenkins/clone/targets", "get_clone_targets"),
    ("/jenkins/clone/groups", "get_groups_for_target"),
    ("/jenkins/clone/create", "clone_jenkins_job"),
    ("/jenkins/clone/build", "clone_build_jenkins_job"),
    ("/jenkins/clone/settings", "get_clone_job_advanced_settings"),
    ("/jenkins/clone/settings/change", "set_job_settings"),
    ("/jenkins/clone/settings/validate", "clone_validate_new_settings"),
    ("/pytest/<string:test_name>/results", "get_pytest_test_results"),
    ("/pytest/<string:test_name>/stats/<string:field_name>/<string:aggr_function>", "get_pytest_test_field_stats"),
):
    bp.add_url_rule(_rule, _endpoint, None)
