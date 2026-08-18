import logging
from datetime import datetime, timezone
from uuid import UUID

import requests
from fastapi import APIRouter, Body, Depends, Query, Request
from flask import Blueprint
from pydantic import BaseModel
from starlette.responses import RedirectResponse, Response

from argus.backend.controller.client_api import bp as client_bp
from argus.backend.controller.notification_api import bp as notifications_bp
from argus.backend.controller.planner_api import bp as planner_bp
from argus.backend.controller.team import bp as team_bp
from argus.backend.controller.testrun_api import bp as testrun_bp
from argus.backend.controller.view_api import bp as view_bp
from argus.backend.error_handlers import APIException, handle_api_exception
from argus.backend.models.web import ArgusGroup, ArgusRelease, ArgusTest, User
from argus.backend.rendering import url_for
from argus.backend.service.argus_service import ArgusService, ScheduleUpdateRequest
from argus.backend.service.results_service import ResultsService
from argus.backend.service.stats import ReleaseStatsCollector
from argus.backend.service.testrun import TestRunService
from argus.backend.service.user import UserService, api_current_user
from argus.backend.util.encoders import ArgusJSONResponse

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")

CACHEABLE = {"Cache-Control": "max-age=60"}


class SetTestPluginRequest(BaseModel):
    plugin_name: str


class CreateGraphViewRequest(BaseModel):
    testId: UUID
    name: str
    description: str


class UpdateGraphViewRequest(BaseModel):
    testId: UUID
    id: UUID
    name: str
    description: str
    graphs: dict[str, str]


@router.get("/version", name="api.app_version")
def app_version():
    service = ArgusService()
    argus_version = service.get_version()
    return ArgusJSONResponse({
        "status": "ok",
        "response": {
            "commit_id": argus_version
        }
    })


@router.get("/test/{build_id:path}/{build_number:int}", name="api.get_run_by_build")
def get_run_by_build(asgi_request: Request, build_id: str, build_number: int,
                     user: User = Depends(api_current_user)):
    # JSON sibling of main.get_run_by_build: resolve a run from its
    # build_system_id + Jenkins build number and return its id and Argus URL.
    run = TestRunService().get_run_by_build_number(build_id, build_number)
    if not run:
        raise Exception(f"Run not found for {build_id} #{build_number}")
    run_path = url_for(asgi_request, "main.get_run_by_plugin",
                       plugin_name=run._plugin_name, run_id=run.id)
    return ArgusJSONResponse({
        "status": "ok",
        "response": {
            "run_id": str(run.id),
            "plugin_name": run._plugin_name,
            "url": str(asgi_request.base_url).rstrip("/") + run_path,
        }
    })


@router.get("/releases", name="api.releases")
def releases(force_all: bool = Query(False, alias="all"),
             user: User = Depends(api_current_user)):
    service = ArgusService()
    all_releases = service.get_releases()
    return ArgusJSONResponse({
        "status": "ok",
        "response": [d.model_dump() for d in all_releases if d.enabled or force_all]
    }, headers=CACHEABLE)


@router.get("/release/activity", name="api.release_activity")
def release_activity(release_name: str = Query(..., alias="releaseName"),
                     user: User = Depends(api_current_user)):
    service = ArgusService()
    activity_data = service.fetch_release_activity(release_name)

    return ArgusJSONResponse({
        "status": "ok",
        "response": activity_data
    })


@router.get("/release/planner/data", name="api.release_planner_data")
def release_planner_data(release_id: UUID = Query(..., alias="releaseId"),
                         user: User = Depends(api_current_user)):
    service = ArgusService()
    planner_data = service.get_planner_data(release_id)
    return ArgusJSONResponse({
        "status": "ok",
        "response": planner_data
    })


@router.get("/release/{release_id}/versions", name="api.release_versions")
def release_versions(release_id: UUID, user: User = Depends(api_current_user)):
    service = ArgusService()
    distinct_versions = service.get_distinct_release_versions(release_id=release_id)

    return ArgusJSONResponse({
        "status": "ok",
        "response": distinct_versions
    })


@router.get("/release/{release_id}/pytest/results", name="api.release_pytest_results")
def release_pytest_results(release_id: UUID, user: User = Depends(api_current_user)):
    service = TestRunService()
    res = service.get_pytest_release_results(release_id=release_id)

    return ArgusJSONResponse({
        "status": "ok",
        "response": res
    })


@router.get("/release/{release_id}/images", name="api.release_images")
def release_images(release_id: UUID, user: User = Depends(api_current_user)):
    service = ArgusService()
    distinct_images = service.get_distinct_release_images(release_id=release_id)

    return ArgusJSONResponse({
        "status": "ok",
        "response": distinct_images
    })


@router.get("/release/planner/comment/get/test", name="api.get_planner_comment_by_test")
def get_planner_comment_by_test(test_id: UUID = Query(..., alias="id")):
    service = ArgusService()
    planner_comments_by_test = service.get_planner_comment_by_test(test_id)

    return ArgusJSONResponse({
        "status": "ok",
        "response": planner_comments_by_test
    }, headers=CACHEABLE)


@router.post("/release/schedules/comment/update", name="api.release_schedules_comment_update")
def release_schedules_comment_update(payload: dict = Body(...),
                                     user: User = Depends(api_current_user)):
    service = ArgusService()
    comment_update_result = service.update_schedule_comment(payload)

    return ArgusJSONResponse({
        "status": "ok",
        "response": comment_update_result
    })


@router.get("/release/schedules", name="api.release_schedules")
def release_schedules(release: UUID = Query(..., alias="releaseId"),
                      user: User = Depends(api_current_user)):
    service = ArgusService()
    release_schedules_data = service.get_schedules_for_release(release)

    return ArgusJSONResponse({
        "status": "ok",
        "response": release_schedules_data
    })


@router.post("/release/schedules/assignee/update", name="api.release_schedules_assignee_update")
def release_schedules_assignee_update(payload: dict = Body(...),
                                      user: User = Depends(api_current_user)):
    service = ArgusService()
    assignee_update_status = service.update_schedule_assignees(payload)

    return ArgusJSONResponse({
        "status": "ok",
        "response": assignee_update_status
    })


@router.get("/release/assignees/groups", name="api.group_assignees")
def group_assignees(release_id: UUID = Query(..., alias="releaseId"),
                    version: str | None = Query(None), plan_id: UUID | None = Query(None, alias="planId"),
                    user: User = Depends(api_current_user)):
    service = ArgusService()
    group_assignees_list = service.get_groups_assignees(release_id, version, plan_id)

    return ArgusJSONResponse({
        "status": "ok",
        "response": group_assignees_list
    })


@router.get("/release/assignees/tests", name="api.tests_assignees")
def tests_assignees(group_id: UUID = Query(..., alias="groupId"),
                    version: str | None = Query(None), plan_id: UUID | None = Query(None, alias="planId"),
                    user: User = Depends(api_current_user)):
    service = ArgusService()
    tests_assignees_list = service.get_tests_assignees(group_id, version, plan_id)

    return ArgusJSONResponse({
        "status": "ok",
        "response": tests_assignees_list
    })


@router.post("/release/schedules/submit", name="api.release_schedules_submit")
def release_schedules_submit(payload: dict = Body(...),
                             user: User = Depends(api_current_user)):
    service = ArgusService()
    schedule_submit_result = service.submit_new_schedule(
        release=payload["releaseId"],
        start_time=payload["start"],
        end_time=payload["end"],
        tests=payload["tests"],
        groups=payload["groups"],
        assignees=payload["assignees"],
        tag=payload["tag"],
        comments=payload.get("comments"),
        group_ids=payload.get("groupIds"),
    )

    return ArgusJSONResponse({
        "status": "ok",
        "response": schedule_submit_result
    })


@router.post("/release/schedules/delete", name="api.release_schedules_delete")
def release_schedules_delete(payload: dict = Body(...),
                             user: User = Depends(api_current_user)):
    service = ArgusService()
    schedule_delete_result = service.delete_schedule(payload)

    return ArgusJSONResponse({
        "status": "ok",
        "response": schedule_delete_result
    })


@router.post("/release/schedules/update", name="api.release_schedule_update")
def release_schedule_update(payload: dict = Body(...),
                            user: User = Depends(api_current_user)):
    req = ScheduleUpdateRequest(**payload)
    service = ArgusService()
    update_result = service.update_schedule(
        release_id=req.release_id,
        schedule_id=req.schedule_id,
        old_tests=req.old_tests,
        new_tests=req.new_tests,
        comments=req.comments,
        assignee=req.assignee
    )

    return ArgusJSONResponse({
        "status": "ok",
        "response": update_result
    })


@router.get("/groups", name="api.argus_groups")
def argus_groups(release_id: UUID = Query(..., alias="releaseId"),
                 force_all: bool = Query(False, alias="all"),
                 user: User = Depends(api_current_user)):
    service = ArgusService()
    groups = service.get_groups(release_id)
    result_groups = [group.model_dump() for group in groups if group.enabled or force_all]

    return ArgusJSONResponse({
        "status": "ok",
        "response": result_groups
    }, headers=CACHEABLE)


@router.get("/tests", name="api.argus_tests")
def argus_tests(group_id: UUID = Query(..., alias="groupId"),
                force_all: bool = Query(False, alias="all"),
                user: User = Depends(api_current_user)):
    service = ArgusService()
    tests = service.get_tests(group_id=group_id)
    result_tests = [t.model_dump() for t in tests if t.enabled or force_all]

    return ArgusJSONResponse({
        "status": "ok",
        "response": result_tests
    }, headers=CACHEABLE)


@router.get("/release/{release_id}/details", name="api.get_release_details")
def get_release_details(release_id: UUID, user: User = Depends(api_current_user)):
    release = ArgusRelease.get(id=release_id)
    return ArgusJSONResponse({
        "status": "ok",
        "response": release,
    }, headers=CACHEABLE)


@router.get("/group/{group_id}/details", name="api.get_group_details")
def get_group_details(group_id: UUID, user: User = Depends(api_current_user)):
    group = ArgusGroup.get(id=group_id)
    return ArgusJSONResponse({
        "status": "ok",
        "response": group,
    }, headers=CACHEABLE)


@router.get("/test/{test_id}/details", name="api.get_test_details")
def get_test_details(test_id: UUID, user: User = Depends(api_current_user)):
    test = ArgusTest.get(id=test_id)
    return ArgusJSONResponse({
        "status": "ok",
        "response": test
    }, headers=CACHEABLE)


@router.post("/test/{test_id}/set_plugin", name="api.set_test_plugin")
def set_test_plugin(test_id: UUID, payload: SetTestPluginRequest,
                    user: User = Depends(api_current_user)):
    test: ArgusTest = ArgusTest.get(id=test_id)
    test.plugin_name = payload.plugin_name
    test.save()

    return ArgusJSONResponse({
        "status": "ok",
        "response": test
    })


@router.get("/test-info", name="api.test_info")
def test_info(test_id: UUID = Query(..., alias="testId"),
              user: User = Depends(api_current_user)):
    service = ArgusService()
    info = service.get_test_info(test_id=test_id)

    return ArgusJSONResponse({
        "status": "ok",
        "response": info
    })


@router.get("/test-results", name="api.test_results")
@router.head("/test-results", name="api.test_results")
def test_results(asgi_request: Request, test_id: UUID = Query(..., alias="testId"),
                 start_date: datetime | None = Query(None, alias="startDate"),
                 end_date: datetime | None = Query(None, alias="endDate"),
                 table_names: list[str] = Query(default=[], alias="tableNames[]"),
                 user: User = Depends(api_current_user)):
    start_date = start_date.astimezone(timezone.utc) if start_date else None
    end_date = end_date.astimezone(timezone.utc) if end_date else None

    service = ResultsService()
    if asgi_request.method == "HEAD":
        exists = service.is_results_exist(test_id=test_id)
        return Response(status_code=200 if exists else 404)

    graphs, ticks, releases_filters = service.get_test_graphs(
        test_id=test_id, start_date=start_date, end_date=end_date, table_names=table_names)
    graph_views = service.get_argus_graph_views(test_id=test_id)

    return ArgusJSONResponse({
        "status": "ok",
        "response": {"graphs": graphs, "ticks": ticks, "releases_filters": releases_filters,
                     "graph_views": graph_views}
    })


@router.post("/create-graph-view", name="api.create_graph_view")
def create_graph_view(payload: CreateGraphViewRequest, user: User = Depends(api_current_user)):
    service = ResultsService()
    graph_view = service.create_argus_graph_view(
        test_id=payload.testId, name=payload.name, description=payload.description)
    return ArgusJSONResponse({
        "status": "ok",
        "response": graph_view
    })


@router.post("/update-graph-view", name="api.update_graph_view")
def update_graph_view(payload: UpdateGraphViewRequest, user: User = Depends(api_current_user)):
    service = ResultsService()
    graph_view = service.update_argus_graph_view(
        test_id=payload.testId, view_id=payload.id, name=payload.name,
        description=payload.description, graphs=payload.graphs)
    return ArgusJSONResponse({
        "status": "ok",
        "response": graph_view
    })


@router.get("/test_run/comment/get", name="api.get_test_run_comment")  # TODO: remove
def get_test_run_comment(comment_id: UUID = Query(..., alias="commentId"),
                         user: User = Depends(api_current_user)):
    service = ArgusService()
    comment = service.get_comment(comment_id=comment_id)
    return ArgusJSONResponse({
        "status": "ok",
        "response": comment if comment else False
    })


@router.get("/users", name="api.user_info")
def user_info(user: User = Depends(api_current_user)):
    result = UserService().get_users()

    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.get("/release/stats/v2", name="api.release_stats_v2")
def release_stats_v2(release: str = Query(...), limited: bool = Query(...),
                     version: str | None = Query(None, alias="productVersion"),
                     image_id: str | None = Query(None, alias="imageId"),
                     include_no_version: bool = Query(True, alias="includeNoVersion"),
                     force: bool = Query(...),
                     user: User = Depends(api_current_user)):
    stats = ReleaseStatsCollector(
        release_name=release, release_version=version).collect(
            limited=limited,
            force=force,
            include_no_version=include_no_version,
            image_id=image_id
    )

    return ArgusJSONResponse({
        "status": "ok",
        "response": stats
    })


@router.get("/test_runs/poll", name="api.test_runs_poll")
def test_runs_poll(user: User = Depends(api_current_user)):
    raise APIException("This endpoint has been removed")


@router.get("/test_run/poll", name="api.test_run_poll_single")
def test_run_poll_single(user: User = Depends(api_current_user)):
    raise APIException("This endpoint has been removed")


@router.post("/release/create", name="api.release_create")
def release_create(payload: dict = Body(...), user: User = Depends(api_current_user)):
    service = ArgusService()
    result = service.create_release(payload)

    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.get("/artifact/resolveSize", name="api.resolve_artifact_size")
def resolve_artifact_size(link: str = Query(..., alias="l"),
                          user: User = Depends(api_current_user)):
    length = TestRunService().resolve_artifact_size(link)

    return ArgusJSONResponse({
        "status": "ok",
        "response": {
            "artifactSize": length,
        }
    })


@router.get("/s3/{bucket_name}/{bucket_path:path}", name="api.s3_generic_proxy")
def s3_generic_proxy(bucket_name: str, bucket_path: str,
                     user: User = Depends(api_current_user)):
    service = TestRunService()
    result = service.proxy_s3_file(
        bucket_name=bucket_name,
        bucket_path=bucket_path
    )

    return RedirectResponse(result, status_code=302)


@router.get("/user/token", name="api.user_token")
def user_token(user: User = Depends(api_current_user)):
    token = UserService().get_or_generate_token(user=user)

    return ArgusJSONResponse({
        "status": "ok",
        "response": {
            "token": token
        }
    })


@router.get("/user/jobs", name="api.user_jobs")
def user_jobs(user: User = Depends(api_current_user)):
    service = ArgusService()
    result = list(service.get_jobs_for_user(user=user))

    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.get("/user/planned_jobs", name="api.user_planned_jobs")
def user_planned_jobs(user: User = Depends(api_current_user)):
    service = ArgusService()
    result = list(service.get_planned_jobs_for_user(user=user))

    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.api_route("/zeus/{endpoint:path}", methods=["GET", "POST", "HEAD", "PUT", "DELETE"],
                  name="api.zeus_proxy")
def zeus_proxy(asgi_request: Request, endpoint: str, body: bytes = Body(b""),
               user: User = Depends(api_current_user)):
    config = asgi_request.app.state.flask_app.config
    zeus_host = config.get("ZEUS_HOST")
    zeus_schema = config.get("ZEUS_SCHEMA", "http")
    zeus_token = config.get("ZEUS_TOKEN")
    if not zeus_host:
        raise Exception("ZEUS_HOST is not configured, proxying is impossible.")
    if not zeus_token:
        raise Exception("Missing authorization token for Zeus [ZEUS_TOKEN]")

    query_str = asgi_request.url.query
    method = asgi_request.method.lower()
    headers = dict(asgi_request.headers)
    headers["X-Forwarded-For"] = asgi_request.client.host if asgi_request.client else ""
    headers["X-Argus-Proxy"] = "1"
    headers["Authorization"] = f"Bearer {zeus_token}"

    session = requests.Session()
    proxy_request = requests.Request(
        method=method, url=f"{zeus_schema}://{zeus_host}/{endpoint}?{query_str}",
        headers=headers, data=body)
    prepared = proxy_request.prepare()

    response = session.send(prepared)

    return Response(response.content, status_code=response.status_code,
                    headers=dict(response.headers))


# The routes above are served by FastAPI; the blueprint keeps the nested
# (not yet migrated) sub-blueprints on Flask plus view-less rules that keep
# the api.* endpoints buildable through Flask's url_for.
bp = Blueprint('api', __name__, url_prefix='/api/v1')
bp.register_blueprint(notifications_bp)
bp.register_blueprint(client_bp)
bp.register_blueprint(testrun_bp)
bp.register_blueprint(team_bp)
bp.register_blueprint(view_bp)
bp.register_blueprint(planner_bp)
bp.register_error_handler(Exception, handle_api_exception)

for _rule, _endpoint in (
    ("/version", "app_version"),
    ("/test/<path:build_id>/<int:build_number>", "get_run_by_build"),
    ("/releases", "releases"),
    ("/release/activity", "release_activity"),
    ("/release/planner/data", "release_planner_data"),
    ("/release/<string:release_id>/versions", "release_versions"),
    ("/release/<string:release_id>/pytest/results", "release_pytest_results"),
    ("/release/<string:release_id>/images", "release_images"),
    ("/release/planner/comment/get/test", "get_planner_comment_by_test"),
    ("/release/schedules/comment/update", "release_schedules_comment_update"),
    ("/release/schedules", "release_schedules"),
    ("/release/schedules/assignee/update", "release_schedules_assignee_update"),
    ("/release/assignees/groups", "group_assignees"),
    ("/release/assignees/tests", "tests_assignees"),
    ("/release/schedules/submit", "release_schedules_submit"),
    ("/release/schedules/delete", "release_schedules_delete"),
    ("/release/schedules/update", "release_schedule_update"),
    ("/groups", "argus_groups"),
    ("/tests", "argus_tests"),
    ("/release/<string:release_id>/details", "get_release_details"),
    ("/group/<string:group_id>/details", "get_group_details"),
    ("/test/<string:test_id>/details", "get_test_details"),
    ("/test/<string:test_id>/set_plugin", "set_test_plugin"),
    ("/test-info", "test_info"),
    ("/test-results", "test_results"),
    ("/create-graph-view", "create_graph_view"),
    ("/update-graph-view", "update_graph_view"),
    ("/test_run/comment/get", "get_test_run_comment"),
    ("/users", "user_info"),
    ("/release/stats/v2", "release_stats_v2"),
    ("/test_runs/poll", "test_runs_poll"),
    ("/test_run/poll", "test_run_poll_single"),
    ("/release/create", "release_create"),
    ("/artifact/resolveSize", "resolve_artifact_size"),
    ("/s3/<string:bucket_name>/<path:bucket_path>", "s3_generic_proxy"),
    ("/user/token", "user_token"),
    ("/user/jobs", "user_jobs"),
    ("/user/planned_jobs", "user_planned_jobs"),
    ("/zeus/<path:endpoint>", "zeus_proxy"),
):
    bp.add_url_rule(_rule, _endpoint, None)
