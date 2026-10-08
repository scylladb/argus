import datetime
import json
import uuid
from dataclasses import asdict

import pytest
from argus.backend.tests.conftest import g, get_fake_test_run

from coodie.exceptions import DocumentNotFound

from argus.backend.models.plan import ArgusReleasePlan
from argus.backend.models.web import ArgusUserView, User, UserRoles
from argus.backend.service.client_service import ClientService
from argus.common.enums import TestInvestigationStatus
from argus.backend.service import test_lookup as lookup


@pytest.fixture
async def planner_user():
    user = User(
        id=uuid.uuid4(),
        username=f"planner_{uuid.uuid4().hex[:8]}",
        full_name="Planner User",
        email=f"planner_{uuid.uuid4().hex[:8]}@scylladb.com",
        password="pw",
        roles=[UserRoles.User.value], registration_date=datetime.datetime.now(datetime.UTC),
    )
    await user.save()
    return user


@pytest.fixture
async def cleanup_plans():
    yield
    for plan in list(await ArgusReleasePlan.find().all()):
        if plan.view_id:
            try:
                await (await ArgusUserView.get(id=plan.view_id)).delete()
            except DocumentNotFound:
                pass
        await plan.delete()


def _create_plan(api_client, release, fake_test, name=None, target_version="1.0",
                 owner=None, tests=None, groups=None):
    payload = {
        "name": name or f"plan_{uuid.uuid4().hex[:8]}",
        "description": "test plan",
        "owner": str(owner or g.user.id),
        "participants": [],
        "target_version": target_version,
        "release_id": str(release.id),
        "tests": [str(t) for t in (tests if tests is not None else [fake_test.id])],
        "groups": [str(gid) for gid in (groups or [])],
        "assignments": {},
    }
    return api_client.post("/api/v1/planning/plan/create", json=payload).json()


def test_version(api_client):
    res = api_client.get("/api/v1/planning/").json()
    assert res["status"] == "ok"
    assert res["response"] == "v1"


def test_create_plan_success(api_client, release, fake_test, cleanup_plans):
    res = _create_plan(api_client, release, fake_test)
    assert res["status"] == "ok"
    plan_id = res["response"]["id"]

    fetched = api_client.get(f"/api/v1/planning/plan/{plan_id}/get").json()
    assert fetched["status"] == "ok"
    body = fetched["response"]
    assert body["release_id"] == str(release.id)
    assert body["target_version"] == "1.0"
    assert str(fake_test.id) in [str(t) for t in body["tests"]]
    assert body["view_id"]  # Auto-created view


def test_create_plan_duplicate_name_version_errors(api_client, release, fake_test, cleanup_plans):
    name = f"plan_{uuid.uuid4().hex[:8]}"
    first = _create_plan(api_client, release, fake_test, name=name, target_version="2.0")
    assert first["status"] == "ok"
    dup = _create_plan(api_client, release, fake_test, name=name, target_version="2.0")
    assert dup["status"] == "error"
    assert "existing plan" in dup["response"]["arguments"][0]


def test_get_plan_unknown_id_errors(api_client):
    res = api_client.get(f"/api/v1/planning/plan/{uuid.uuid1()}/get").json()
    assert res["status"] == "error"
    assert res["response"]["exception"] == "DocumentNotFound"


def test_plans_for_release(api_client, release, fake_test, cleanup_plans):
    a = _create_plan(api_client, release, fake_test, target_version="3.1")["response"]["id"]
    b = _create_plan(api_client, release, fake_test, target_version="3.2")["response"]["id"]
    res = api_client.get(f"/api/v1/planning/release/{release.id}/all").json()
    assert res["status"] == "ok"
    ids = {p["id"] for p in res["response"]}
    assert {a, b}.issubset(ids)


def test_update_plan(api_client, release, fake_test, cleanup_plans):
    created = _create_plan(api_client, release, fake_test)["response"]
    plan_id = created["id"]

    # update_plan takes a diff-based payload (PlanDiffPayload): only changed
    # scalar fields and add/remove list diffs are sent.
    update_payload = {
        "id": plan_id,
        "description": "updated description",
        "target_version": "9.9",
    }
    res = api_client.post("/api/v1/planning/plan/update", json=update_payload).json()
    assert res["status"] == "ok"
    assert res["response"] is True

    fetched = api_client.get(f"/api/v1/planning/plan/{plan_id}/get").json()["response"]
    assert fetched["description"] == "updated description"
    assert fetched["target_version"] == "9.9"


def test_change_plan_owner(api_client, release, fake_test, planner_user, cleanup_plans):
    plan_id = _create_plan(api_client, release, fake_test)["response"]["id"]
    res = api_client.post(
        f"/api/v1/planning/plan/{plan_id}/owner/set",
        json={"newOwner": str(planner_user.id)},
    ).json()
    assert res["status"] == "ok"
    fetched = api_client.get(f"/api/v1/planning/plan/{plan_id}/get").json()["response"]
    assert fetched["owner"] == str(planner_user.id)


def test_resolve_plan_entities(api_client, release, fake_test, cleanup_plans):
    plan_id = _create_plan(api_client, release, fake_test)["response"]["id"]
    res = api_client.get(f"/api/v1/planning/plan/{plan_id}/resolve_entities").json()
    assert res["status"] == "ok"
    test_ids = {item.get("id") for item in res["response"]}
    assert str(fake_test.id) in test_ids


def test_delete_plan_removes_view(api_client, release, fake_test, cleanup_plans):
    created = _create_plan(api_client, release, fake_test)["response"]
    plan_id = created["id"]
    view_id = created["view_id"]
    res = api_client.delete(f"/api/v1/planning/plan/{plan_id}/delete?deleteView=1").json()
    assert res["status"] == "ok"
    assert res["response"] is True

    after = api_client.get(f"/api/v1/planning/plan/{plan_id}/get").json()
    assert after["status"] == "error"
    view_after = api_client.get(f"/api/v1/views/get?viewId={view_id}").json()
    assert view_after["status"] == "error"


def test_delete_plan_keeps_view(api_client, release, fake_test, cleanup_plans):
    created = _create_plan(api_client, release, fake_test)["response"]
    plan_id = created["id"]
    view_id = created["view_id"]
    res = api_client.delete(f"/api/v1/planning/plan/{plan_id}/delete?deleteView=0").json()
    assert res["status"] == "ok"
    view_after = api_client.get(f"/api/v1/views/get?viewId={view_id}").json()
    assert view_after["status"] == "ok"
    assert view_after["response"]["plan_id"] is None


def test_grid_view_for_release(api_client, release, group, fake_test):
    res = api_client.get(f"/api/v1/planning/release/{release.id}/gridview").json()
    assert res["status"] == "ok"
    body = res["response"]
    assert str(group.id) in body["groups"]
    assert str(fake_test.id) in body["tests"]
    assert body["tests"][str(fake_test.id)]["release"] == release.name


def test_search_no_query_returns_empty(api_client):
    res = api_client.get("/api/v1/planning/search").json()
    assert res["status"] == "ok"
    assert res["response"] == {"hits": [], "total": 0}


def test_search_finds_test_name(api_client, release, fake_test):
    res = api_client.get(
        f"/api/v1/planning/search?query={fake_test.name}&releaseId={release.id}"
    ).json()
    assert res["status"] == "ok"
    names = {h.get("name") for h in res["response"]["hits"]}
    assert fake_test.name in names


def _search(api_client, **params) -> dict:
    res = api_client.get("/api/v1/planning/search", params=params).json()
    assert res["status"] == "ok", res
    return res["response"]


def _search_token() -> str:
    return f"q{uuid.uuid4().hex[:12]}"


async def _release_tree(release_manager_service, test_names: list[str], priority: int = 0):
    release = await release_manager_service.create_release(f"search_rel_{uuid.uuid4().hex}", None, False)
    if priority:
        await release_manager_service.edit_release({
            "id": release.id, "pretty_name": None, "description": None, "valid_version_regex": None,
            "enabled": True, "perpetual": False, "dormant": False, "priority": priority,
        })
    group = await release_manager_service.create_group(
        f"search_grp_{uuid.uuid4().hex}", None, build_system_id=release.name, release_id=str(release.id))
    tests = [
        await release_manager_service.create_test(
            name, None, f"{release.name}/{name}", "", group_id=str(group.id), release_id=str(release.id),
            plugin_name="scylla-cluster-tests")
        for name in test_names
    ]
    return release, group, tests


async def _run_with_status(client_service, test, status: str) -> None:
    run_type, run_req = get_fake_test_run(test)
    await client_service.submit_run(run_type, asdict(run_req))
    await client_service.update_run_status(run_type, run_req.run_id, status)


async def test_search_status_facet_keeps_the_scoped_tests_in_that_status(
        api_client, release_manager_service, client_service):
    token = _search_token()
    release, _, (failed, passed, never_ran) = await _release_tree(
        release_manager_service, [f"{token}-a", f"{token}-b", f"{token}-c"])
    await _run_with_status(client_service, failed, "failed")
    await _run_with_status(client_service, passed, "passed")

    only_failed = _search(api_client, query=f"{token} status:failed", releaseId=str(release.id), limit=10)
    not_passed = _search(api_client, query=f"{token} -status:passed", releaseId=str(release.id), limit=10)

    assert [hit["id"] for hit in only_failed["hits"]] == [str(failed.id)]
    assert {hit["id"] for hit in not_passed["hits"]} == {str(failed.id), str(never_ran.id)}


async def test_search_istatus_and_assignee_facets_read_the_latest_run(
        api_client, release_manager_service, client_service, testrun_service, planner_user):
    token = _search_token()
    release, _, (mine, investigated) = await _release_tree(release_manager_service, [f"{token}-a", f"{token}-b"])
    run_type, mine_run = get_fake_test_run(mine)
    await client_service.submit_run(run_type, asdict(mine_run))
    await testrun_service.change_run_assignee(mine.id, uuid.UUID(mine_run.run_id), planner_user.id, planner_user)
    run_type, done_run = get_fake_test_run(investigated)
    await client_service.submit_run(run_type, asdict(done_run))
    await testrun_service.change_run_investigation_status(
        investigated.id, uuid.UUID(done_run.run_id), TestInvestigationStatus.INVESTIGATED, planner_user)

    by_assignee = _search(api_client, query=f"{token} assignee:{planner_user.username}",
                          releaseId=str(release.id), limit=10)
    by_full_name = _search(api_client, query=f'{token} assignee:"planner user"', releaseId=str(release.id), limit=10)
    pending = _search(api_client, query=f"{token} istatus:not", releaseId=str(release.id), limit=10)
    done = _search(api_client, query=f"{token} istatus:investigated", releaseId=str(release.id), limit=10)

    assert [hit["id"] for hit in by_assignee["hits"]] == [str(mine.id)]
    assert [hit["id"] for hit in by_full_name["hits"]] == [str(mine.id)]
    assert [hit["id"] for hit in pending["hits"]] == [str(mine.id)]
    assert [hit["id"] for hit in done["hits"]] == [str(investigated.id)]


async def _run_with_config(client_service, test, status: str, **params: str) -> str:
    run_type, run_req = get_fake_test_run(test)
    await client_service.submit_run(run_type, asdict(run_req))
    await client_service.update_run_status(run_type, run_req.run_id, status)
    await ClientService.parse_config_values("sct_config", json.dumps(params), run_req.run_id)
    return run_req.run_id


async def test_search_config_facet_narrows_the_recent_runs_of_the_scoped_release(
        api_client, release_manager_service, client_service):
    token = _search_token()
    release, _, (on_aws, on_gce) = await _release_tree(release_manager_service, [f"{token}-a", f"{token}-b"])
    aws_run = await _run_with_config(client_service, on_aws, "failed", backend=f"aws-{token}")
    await _run_with_config(client_service, on_gce, "failed", backend=f"gce-{token}")

    body = _search(api_client, query=f"config:sct_config.backend=aws-{token}", releaseId=str(release.id), limit=10)

    assert body["total"] == 1
    [hit] = body["hits"]
    assert hit["id"] == aws_run
    assert hit["type"] == "run"
    assert hit["test_id"] == str(on_aws.id)
    assert hit["status"] == "failed"


async def test_search_config_facet_without_a_release_reads_the_value_newest_first(
        api_client, release_manager_service, client_service):
    token = _search_token()
    _, _, (test,) = await _release_tree(release_manager_service, [f"{token}-a"])
    older = await _run_with_config(client_service, test, "passed", backend=f"aws-{token}")
    newer = await _run_with_config(client_service, test, "failed", backend=f"aws-{token}")

    body = _search(api_client, query=f"config:backend=aws-{token}", limit=10)

    assert [hit["id"] for hit in body["hits"]] == [newer, older]


async def test_search_facets_narrow_the_runs_of_a_config_facet(
        api_client, release_manager_service, client_service):
    token = _search_token()
    release, _, (first, second) = await _release_tree(release_manager_service, [f"{token}-a", f"{token}-b"])
    failed = await _run_with_config(client_service, first, "failed", backend=f"aws-{token}")
    await _run_with_config(client_service, second, "passed", backend=f"aws-{token}")

    by_status = _search(api_client, query=f"config:backend=aws-{token} status:fail", limit=10)
    by_word = _search(api_client, query=f"config:backend=aws-{token} {token}-a", limit=10)
    by_type = _search(api_client, query=f"config:backend=aws-{token} type:test", limit=10)

    assert [hit["id"] for hit in by_status["hits"]] == [failed]
    assert [hit["id"] for hit in by_word["hits"]] == [failed]
    assert by_type == {"hits": [], "total": 0}


async def test_search_config_facet_ors_the_values_of_one_name(
        api_client, release_manager_service, client_service):
    token = _search_token()
    _, _, (test,) = await _release_tree(release_manager_service, [f"{token}-a"])
    aws = await _run_with_config(client_service, test, "passed", backend=f"aws-{token}")
    gce = await _run_with_config(client_service, test, "passed", backend=f"gce-{token}")

    body = _search(api_client, query=f"config:backend=aws-{token} config:backend=gce-{token}", limit=10)

    assert {hit["id"] for hit in body["hits"]} == {aws, gce}


async def test_search_config_facet_with_only_a_name_matches_nothing_on_its_own(
        api_client, release_manager_service, client_service):
    token = _search_token()
    release, _, (test,) = await _release_tree(release_manager_service, [f"{token}-a"])
    await _run_with_config(client_service, test, "passed", backend=f"aws-{token}")

    body = _search(api_client, query="config:backend", releaseId=str(release.id), limit=10)

    assert body == {"hits": [], "total": 0}


def _search_error(api_client, **params) -> dict:
    body = api_client.get("/api/v1/planning/search", params=params).json()
    assert body["status"] == "error", body
    return body


@pytest.mark.parametrize("query", ["-longevity", "-type:group", "-issue:SCT-1", '"'])
def test_search_with_nothing_to_match_returns_nothing(api_client, query):
    assert _search(api_client, query=query, limit=10) == {"hits": [], "total": 0}


async def test_search_excludes_an_entity_by_its_uuid(api_client, release_manager_service):
    token = _search_token()
    _, _, (kept, dropped) = await _release_tree(release_manager_service, [f"{token}-a", f"{token}-b"])

    body = _search(api_client, query=f"{token} type:test -{dropped.id}", limit=10)

    assert [hit["id"] for hit in body["hits"]] == [str(kept.id)]


def test_search_refuses_a_query_with_too_many_words(api_client):
    _search_error(api_client, query=" ".join(f"group:g{index}" for index in range(lookup.MAX_QUERY_TOKENS + 1)))


def test_search_refuses_a_query_that_is_too_long(api_client):
    _search_error(api_client, query="x" * (lookup.MAX_QUERY_LENGTH + 1))


def test_search_refuses_too_many_config_values(api_client):
    _search_error(api_client, query=" ".join(f"config:backend=v{index}" for index in range(lookup.MAX_CONFIG_FILTERS + 1)))


async def test_search_config_facet_caps_the_runs_it_reads_across_values(
        api_client, release_manager_service, client_service, monkeypatch):
    monkeypatch.setattr(lookup, "CONFIG_RUN_LIMIT", 1)
    token = _search_token()
    _, _, (test,) = await _release_tree(release_manager_service, [f"{token}-a"])
    await _run_with_config(client_service, test, "passed", backend=f"aws-{token}")
    await _run_with_config(client_service, test, "passed", backend=f"gce-{token}")

    body = _search(api_client, query=f"config:backend=aws-{token} config:backend=gce-{token}", limit=10)

    assert body["total"] == 1


async def test_search_status_facet_takes_its_release_from_a_release_facet(
        api_client, release_manager_service, client_service):
    token = _search_token()
    release, _, (failed, _) = await _release_tree(release_manager_service, [f"{token}-a", f"{token}-b"])
    await _run_with_status(client_service, failed, "failed")

    body = _search(api_client, query=f"{token} release:{release.name} status:failed", limit=10)

    assert [hit["id"] for hit in body["hits"]] == [str(failed.id)]


async def test_search_status_facet_without_one_release_matches_nothing(
        api_client, release_manager_service, client_service):
    token = _search_token()
    _, _, (failed,) = await _release_tree(release_manager_service, [f"{token}-a"])
    await _run_with_status(client_service, failed, "failed")

    only_failed = _search(api_client, query=f"{token} status:failed", limit=10)
    not_passed = _search(api_client, query=f"{token} -status:passed", limit=10)

    assert only_failed == {"hits": [], "total": 0}
    assert not_passed == {"hits": [], "total": 0}


async def test_search_without_limit_leads_with_add_all_and_returns_the_cli_fields(
        api_client, release_manager_service):
    token = _search_token()
    release, group, (test,) = await _release_tree(release_manager_service, [f"{token}-longevity"])

    body = _search(api_client, query=token)

    assert body["total"] == 1
    assert body["hits"] == [
        {"id": str(lookup.TestLookup.ADD_ALL_ID), "name": "Add all...", "type": "special"},
        {
            "id": str(test.id), "type": "test", "name": test.name, "pretty_name": None,
            "build_system_id": test.build_system_id, "enabled": True, "test_metadata": {},
            "release_id": str(release.id), "group_id": str(group.id),
            "release": {"id": str(release.id), "name": release.name, "pretty_name": None, "enabled": True,
                        "priority": 0, "dormant": False},
            "group": {"id": str(group.id), "name": group.name, "pretty_name": None, "enabled": True},
        },
    ]


async def test_search_pages_are_disjoint_and_total_counts_every_match(api_client, release_manager_service):
    token = _search_token()
    await _release_tree(release_manager_service, [f"{token}-{number}" for number in range(5)])

    first = _search(api_client, query=token, limit=2, offset=0)
    second = _search(api_client, query=token, limit=2, offset=2)

    assert first["total"] == second["total"] == 5
    assert [hit["type"] for hit in first["hits"] + second["hits"]] == ["test"] * 4
    assert not {hit["id"] for hit in first["hits"]} & {hit["id"] for hit in second["hits"]}


async def test_search_ranks_exact_then_prefix_then_word_then_substring_matches(
        api_client, release_manager_service):
    token = _search_token()
    await _release_tree(release_manager_service, [f"x{token}", f"x-{token}", f"{token}-tail", token])

    body = _search(api_client, query=token, limit=10)

    assert [hit["name"] for hit in body["hits"]] == [token, f"{token}-tail", f"x-{token}", f"x{token}"]


async def test_search_ranks_a_prioritized_release_above_the_same_name_elsewhere(
        api_client, release_manager_service):
    token = _search_token()
    _, _, (plain,) = await _release_tree(release_manager_service, [token])
    _, _, (prioritized,) = await _release_tree(release_manager_service, [token], priority=10)

    body = _search(api_client, query=token, limit=10)

    assert [hit["id"] for hit in body["hits"]] == [str(prioritized.id), str(plain.id)]


async def test_search_with_release_id_returns_only_that_release(api_client, release_manager_service):
    token = _search_token()
    release, _, (inside,) = await _release_tree(release_manager_service, [token])
    await _release_tree(release_manager_service, [token])

    by_test = _search(api_client, query=token, releaseId=str(release.id), limit=10)
    by_release = _search(api_client, query=release.name, releaseId=str(release.id), limit=10)

    assert [hit["id"] for hit in by_test["hits"]] == [str(inside.id)]
    assert {hit["type"] for hit in by_release["hits"]} == {"group", "test"}


async def test_search_ors_a_repeated_facet_and_drops_excluded_terms(api_client, release_manager_service):
    token = _search_token()
    first, _, (in_first, _) = await _release_tree(release_manager_service, [f"{token}-aws", f"{token}-azure"])
    second, _, (in_second, _) = await _release_tree(release_manager_service, [f"{token}-aws", f"{token}-azure"])
    await _release_tree(release_manager_service, [f"{token}-aws"])

    body = _search(api_client, query=f"{token} release:{first.name} release:{second.name} -azure type:test",
                   limit=10)

    assert {hit["id"] for hit in body["hits"]} == {str(in_first.id), str(in_second.id)}


async def test_search_by_test_uuid_returns_that_test(api_client, release_manager_service):
    _, _, (test,) = await _release_tree(release_manager_service, [_search_token()])

    body = _search(api_client, query=str(test.id))

    assert [(hit["id"], hit["type"]) for hit in body["hits"]] == [(str(test.id), "test")]
    assert body["total"] == 1


async def test_search_by_uuid_pages_like_any_other_query(api_client, release_manager_service):
    _, _, (test,) = await _release_tree(release_manager_service, [_search_token()])

    first = _search(api_client, query=str(test.id), limit=30, offset=0)
    second = _search(api_client, query=str(test.id), limit=30, offset=30)

    assert [hit["id"] for hit in first["hits"]] == [str(test.id)]
    assert second == {"hits": [], "total": 1}


async def test_search_by_run_uuid_names_the_run_after_its_test(api_client, client_service, fake_test):
    run_type, run_request = get_fake_test_run(fake_test)
    await client_service.submit_run(run_type, asdict(run_request))

    (hit,) = _search(api_client, query=run_request.run_id)["hits"]

    assert hit["type"] == "run"
    assert hit["test"]["id"] == str(fake_test.id)
    assert hit["name"] == f"{fake_test.name}#{hit['build_number']}"


async def test_search_by_run_uuid_names_the_run_by_build_number_when_its_test_is_gone(
        api_client, client_service, release_manager_service, fake_test):
    run_type, run_request = get_fake_test_run(fake_test)
    await client_service.submit_run(run_type, asdict(run_request))
    await release_manager_service.delete_test(fake_test.id)

    (hit,) = _search(api_client, query=run_request.run_id)["hits"]

    assert hit["type"] == "run"
    assert hit["test"] is None
    assert hit["name"] == f"#{hit['build_number']}"


async def test_search_sees_a_new_group_after_the_index_is_cleared(api_client, release_manager_service):
    token = _search_token()
    release, _, _ = await _release_tree(release_manager_service, [])
    assert _search(api_client, query=token, limit=10)["total"] == 0

    await release_manager_service.create_group(token, None, build_system_id=token, release_id=str(release.id))
    assert _search(api_client, query=token, limit=10)["total"] == 0
    lookup.TestLookup.clear_index()

    hits = _search(api_client, query=token, limit=10)["hits"]
    assert [(hit["name"], hit["type"]) for hit in hits] == [(token, "group")]


def test_explode_group(api_client, group, fake_test):
    res = api_client.get(f"/api/v1/planning/group/{group.id}/explode").json()
    assert res["status"] == "ok"
    test_ids = {str(t["id"]) for t in res["response"]}
    assert str(fake_test.id) in test_ids


def test_check_plan_copy_eligibility_missing_release_id_errors(api_client, release, fake_test, cleanup_plans):
    plan_id = _create_plan(api_client, release, fake_test)["response"]["id"]
    res = api_client.get(f"/api/v1/planning/plan/{plan_id}/copy/check").json()
    assert res["status"] == "error"
    assert res["response"]["exception"] == "RequestValidationError"


async def test_check_plan_copy_eligibility_returns_failed_for_missing_tests(
    api_client, release_manager_service, release, fake_test, cleanup_plans
):
    plan_id = _create_plan(api_client, release, fake_test)["response"]["id"]
    # Create empty target release with no tests => copy will be missing
    target_release = await release_manager_service.create_release(
        f"target_rel_{uuid.uuid4().hex[:8]}", "Target", False
    )
    res = api_client.get(
        f"/api/v1/planning/plan/{plan_id}/copy/check?releaseId={target_release.id}"
    ).json()
    assert res["status"] == "ok"
    assert res["response"]["status"] == "failed"
    missing_test_ids = {t.get("id") for t in res["response"]["missing"]["tests"]}
    assert str(fake_test.id) in missing_test_ids


async def test_copy_plan_creates_plan_in_target_release(
    api_client, release_manager_service, release, fake_test, cleanup_plans
):
    """Copy a plan into a target release and verify via paired GET.

    Note: copy_plan resolves test/group mappings via build_system_id-based name
    replacement (release name substring) or by an explicit ``replacements``
    dict keyed by UUID. The session-scoped ``fake_test`` build_system_id does
    not contain the source release name, so we exercise the empty-tests path
    by creating a fresh source plan with no tests/groups; copy then produces
    a plan with the same metadata in the target release but empty tests.
    """
    # Source plan with no tests/groups
    source_payload = {
        "name": f"src_{uuid.uuid4().hex[:8]}",
        "description": "source plan",
        "owner": str(g.user.id),
        "participants": [],
        "target_version": "1.0",
        "release_id": str(release.id),
        "tests": [],
        "groups": [],
        "assignments": {},
    }
    plan_id = api_client.post(
        "/api/v1/planning/plan/create", json=source_payload
    ).json()["response"]["id"]
    # copy_plan resolves the source plan by its real key/id; the service mints a
    # fresh key for the copy, so the payload key is echoed back from the source.
    source_key = (await ArgusReleasePlan.get(id=uuid.UUID(str(plan_id)))).key

    target_release = await release_manager_service.create_release(
        f"copy_target_{uuid.uuid4().hex[:8]}", "Copy Target", False
    )

    participant_id = str(uuid.uuid4())
    payload = {
        "plan": {
            "id": plan_id,
            "name": f"copied_{uuid.uuid4().hex[:8]}",
            "completed": False,
            "description": "copied plan",
            "owner": str(g.user.id),
            "key": source_key,
            "participants": [participant_id],
            "target_version": "2.0",
            "assignee_mapping": {},
            "release_id": str(target_release.id),
            "tests": [],
            "groups": [],
            "creation_time": "",
            "last_updated": "",
            "ends_at": "",
            "created_from": plan_id,
            "options": {},
        },
        "keepParticipants": True,
        "replacements": {},
        "targetReleaseId": str(target_release.id),
        "targetReleaseName": target_release.name,
    }
    res = api_client.post("/api/v1/planning/plan/copy", json=payload).json()
    assert res["status"] == "ok", res
    new_plan_id = res["response"]["id"]
    assert new_plan_id != plan_id

    fetched = api_client.get(f"/api/v1/planning/plan/{new_plan_id}/get").json()
    assert fetched["status"] == "ok"
    body = fetched["response"]
    assert body["release_id"] == str(target_release.id)
    assert body["target_version"] == "2.0"
    assert body["description"] == "copied plan"
    # keepParticipants=True copies participants from the payload
    assert body["participants"] == [participant_id]


async def test_create_plan_generates_sequential_keys_per_release(
    api_client, release_manager_service, fake_test, cleanup_plans
):
    """create_plan auto-assigns human-readable keys (``<release.name>#N``) that
    increment per release. A fresh release is used so the counter starts at 1
    regardless of plans created by other tests in the shared session release.
    """
    rel = await release_manager_service.create_release(
        f"keyrel_{uuid.uuid4().hex[:8]}", "Key Release", False
    )

    first_id = _create_plan(api_client, rel, fake_test, tests=[])["response"]["id"]
    second_id = _create_plan(api_client, rel, fake_test, tests=[])["response"]["id"]

    assert (await ArgusReleasePlan.get(id=uuid.UUID(str(first_id)))).key == f"{rel.name}#1"
    assert (await ArgusReleasePlan.get(id=uuid.UUID(str(second_id)))).key == f"{rel.name}#2"


async def test_copy_plan_generates_fresh_key_for_target_release(
    api_client, release_manager_service, release, fake_test, cleanup_plans
):
    """copy_plan mints a new key scoped to the target release rather than
    carrying over the source plan's key (the payload key is ignored)."""
    source_payload = {
        "name": f"src_{uuid.uuid4().hex[:8]}",
        "description": "source plan",
        "owner": str(g.user.id),
        "participants": [],
        "target_version": "1.0",
        "release_id": str(release.id),
        "tests": [],
        "groups": [],
        "assignments": {},
    }
    src_id = api_client.post(
        "/api/v1/planning/plan/create", json=source_payload
    ).json()["response"]["id"]
    src_key = (await ArgusReleasePlan.get(id=uuid.UUID(str(src_id)))).key

    target_release = await release_manager_service.create_release(
        f"copykey_{uuid.uuid4().hex[:8]}", "Copy Key Target", False
    )
    payload = {
        "plan": {
            "id": src_id,
            "name": f"copied_{uuid.uuid4().hex[:8]}",
            "completed": False,
            "description": "copied plan",
            "owner": str(g.user.id),
            "key": src_key,
            "participants": [],
            "target_version": "3.0",
            "assignee_mapping": {},
            "release_id": str(target_release.id),
            "tests": [],
            "groups": [],
            "creation_time": "",
            "last_updated": "",
            "ends_at": "",
            "created_from": src_id,
            "options": {},
        },
        "keepParticipants": False,
        "replacements": {},
        "targetReleaseId": str(target_release.id),
        "targetReleaseName": target_release.name,
    }
    res = api_client.post("/api/v1/planning/plan/copy", json=payload).json()
    assert res["status"] == "ok", res

    new_key = (await ArgusReleasePlan.get(id=uuid.UUID(str(res["response"]["id"])))).key
    assert new_key == f"{target_release.name}#1"
    assert new_key != src_key


async def test_update_plan_resolves_source_by_key(
    api_client, release_manager_service, fake_test, cleanup_plans
):
    """A plan's key is an alternate identifier: update_plan resolves the target
    by key when the diff payload's ``id`` carries the key string instead of the
    UUID."""
    rel = await release_manager_service.create_release(
        f"reskey_{uuid.uuid4().hex[:8]}", "Resolve Key Release", False
    )
    plan_id = _create_plan(api_client, rel, fake_test, tests=[])["response"]["id"]
    plan_key = (await ArgusReleasePlan.get(id=uuid.UUID(str(plan_id)))).key

    res = api_client.post(
        "/api/v1/planning/plan/update",
        json={"id": plan_key, "description": "updated via key"},
    ).json()
    assert res["status"] == "ok"
    assert res["response"] is True

    assert (await ArgusReleasePlan.get(id=uuid.UUID(str(plan_id)))).description == "updated via key"


async def test_update_plan_leaves_omitted_scalars_unchanged(
    api_client, release, fake_test, cleanup_plans
):
    """PlanDiffPayload scalars are Optional[...] = None: only fields present in
    the payload are applied, the rest are left untouched (last-edit-wins)."""
    created = _create_plan(api_client, release, fake_test, target_version="7.7")["response"]
    plan_id = created["id"]
    original = await ArgusReleasePlan.get(id=uuid.UUID(str(plan_id)))
    orig_name, orig_owner = original.name, original.owner

    res = api_client.post(
        "/api/v1/planning/plan/update",
        json={"id": plan_id, "description": "only desc changed"},
    ).json()
    assert res["status"] == "ok"

    updated = await ArgusReleasePlan.get(id=uuid.UUID(str(plan_id)))
    assert updated.description == "only desc changed"
    assert updated.name == orig_name
    assert updated.owner == orig_owner
    assert updated.target_version == "7.7"


async def test_update_plan_toggles_completed(api_client, release, fake_test, cleanup_plans):
    """The ``completed`` scalar diff flips the plan's boolean flag."""
    plan_id = _create_plan(api_client, release, fake_test)["response"]["id"]
    assert (await ArgusReleasePlan.get(id=uuid.UUID(str(plan_id)))).completed is False

    api_client.post(
        "/api/v1/planning/plan/update",
        json={"id": plan_id, "completed": True},
    )
    assert (await ArgusReleasePlan.get(id=uuid.UUID(str(plan_id)))).completed is True


async def test_update_plan_adds_and_removes_tests(
    api_client, release_manager_service, group, release, fake_test, cleanup_plans
):
    """tests_add / tests_remove diffs mutate the plan's test list (remove wins)."""
    second_test = await release_manager_service.create_test(
        f"t2_{uuid.uuid4().hex[:8]}", "Second Test",
        f"bsid_{uuid.uuid4().hex[:8]}", "url",
        group_id=str(group.id), release_id=str(release.id),
        plugin_name="scylla-cluster-tests",
    )
    plan_id = _create_plan(api_client, release, fake_test)["response"]["id"]

    api_client.post(
        "/api/v1/planning/plan/update",
        json={"id": plan_id, "tests_add": [str(second_test.id)]},
    )
    assert set((await ArgusReleasePlan.get(id=uuid.UUID(str(plan_id)))).tests) == {fake_test.id, second_test.id}

    api_client.post(
        "/api/v1/planning/plan/update",
        json={"id": plan_id, "tests_remove": [str(fake_test.id)]},
    )
    assert set((await ArgusReleasePlan.get(id=uuid.UUID(str(plan_id)))).tests) == {second_test.id}


async def test_update_plan_add_tests_is_idempotent(
    api_client, release, fake_test, cleanup_plans
):
    """Re-adding a test already in the plan is a no-op (no duplicate entry)."""
    plan_id = _create_plan(api_client, release, fake_test)["response"]["id"]

    api_client.post(
        "/api/v1/planning/plan/update",
        json={"id": plan_id, "tests_add": [str(fake_test.id)]},
    )
    assert (await ArgusReleasePlan.get(id=uuid.UUID(str(plan_id)))).tests == [fake_test.id]


async def test_update_plan_adds_and_removes_groups(
    api_client, release_manager_service, release, fake_test, cleanup_plans
):
    """groups_add / groups_remove diffs mutate the plan's group list."""
    new_group = await release_manager_service.create_group(
        f"g2_{uuid.uuid4().hex[:8]}", "Second Group",
        build_system_id=f"gbsid_{uuid.uuid4().hex[:8]}", release_id=str(release.id),
    )
    plan_id = _create_plan(api_client, release, fake_test, groups=[])["response"]["id"]

    api_client.post(
        "/api/v1/planning/plan/update",
        json={"id": plan_id, "groups_add": [str(new_group.id)]},
    )
    assert set((await ArgusReleasePlan.get(id=uuid.UUID(str(plan_id)))).groups) == {new_group.id}

    api_client.post(
        "/api/v1/planning/plan/update",
        json={"id": plan_id, "groups_remove": [str(new_group.id)]},
    )
    assert (await ArgusReleasePlan.get(id=uuid.UUID(str(plan_id)))).groups == []


async def test_update_plan_adds_and_removes_participants(
    api_client, release, fake_test, cleanup_plans
):
    """participants_add / participants_remove diffs mutate the participant list."""
    plan_id = _create_plan(api_client, release, fake_test)["response"]["id"]
    p1, p2 = str(uuid.uuid4()), str(uuid.uuid4())

    api_client.post(
        "/api/v1/planning/plan/update",
        json={"id": plan_id, "participants_add": [p1, p2]},
    )
    assert set((await ArgusReleasePlan.get(id=uuid.UUID(str(plan_id)))).participants) == {uuid.UUID(p1), uuid.UUID(p2)}

    api_client.post(
        "/api/v1/planning/plan/update",
        json={"id": plan_id, "participants_remove": [p1]},
    )
    assert set((await ArgusReleasePlan.get(id=uuid.UUID(str(plan_id)))).participants) == {uuid.UUID(p2)}


async def test_update_plan_sets_and_removes_assignee_mapping(
    api_client, planner_user, release, fake_test, cleanup_plans
):
    """assignee_mapping_set / assignee_mapping_remove diffs mutate the per-entity
    assignee map (entity must be a member of the plan)."""
    plan_id = _create_plan(api_client, release, fake_test)["response"]["id"]

    api_client.post(
        "/api/v1/planning/plan/update",
        json={"id": plan_id, "assignee_mapping_set": {str(fake_test.id): str(planner_user.id)}},
    )
    assert (await ArgusReleasePlan.get(id=uuid.UUID(str(plan_id)))).assignee_mapping == {fake_test.id: planner_user.id}

    api_client.post(
        "/api/v1/planning/plan/update",
        json={"id": plan_id, "assignee_mapping_remove": [str(fake_test.id)]},
    )
    assert (await ArgusReleasePlan.get(id=uuid.UUID(str(plan_id)))).assignee_mapping == {}


async def test_update_plan_prunes_assignee_mapping_for_removed_test(
    api_client, planner_user, release, fake_test, cleanup_plans
):
    """Removing a test from the plan also drops its assignee_mapping entry."""
    plan_id = _create_plan(api_client, release, fake_test)["response"]["id"]
    api_client.post(
        "/api/v1/planning/plan/update",
        json={"id": plan_id, "assignee_mapping_set": {str(fake_test.id): str(planner_user.id)}},
    )
    assert (await ArgusReleasePlan.get(id=uuid.UUID(str(plan_id)))).assignee_mapping == {fake_test.id: planner_user.id}

    api_client.post(
        "/api/v1/planning/plan/update",
        json={"id": plan_id, "tests_remove": [str(fake_test.id)]},
    )
    assert (await ArgusReleasePlan.get(id=uuid.UUID(str(plan_id)))).assignee_mapping == {}


def test_trigger_jobs_no_plans_returns_falsy(api_client, mock_jenkins_service):
    """No matching plans => service returns (False, 'No plans to trigger')."""
    from cassandra.util import uuid_from_time
    res = api_client.post(
        "/api/v1/planning/plan/trigger",
        json={
            "plan_id": str(uuid_from_time(datetime.datetime.now(tz=datetime.UTC))),
            "common_params": {},
            "params": [],
        },
    ).json()
    assert res["status"] == "ok"
    # Service returns a tuple (False, "No plans to trigger") which Flask
    # serializes as a 2-element list.
    assert res["response"] == [False, "No plans to trigger"]


def test_trigger_jobs_missing_filters_errors(api_client, mock_jenkins_service):
    """Without release/plan_id/version the service raises PlannerServiceException."""
    res = api_client.post(
        "/api/v1/planning/plan/trigger",
        json={"common_params": {}, "params": []},
    ).json()
    assert res["status"] == "error"


def test_trigger_jobs_for_plan_with_no_tests(
    api_client, release, fake_test, cleanup_plans, mock_jenkins_service
):
    """Triggering a plan whose tests list is empty returns empty jobs/failures."""
    # Create a plan with NO tests/groups so the trigger loop has nothing to do
    payload = {
        "name": f"plan_{uuid.uuid4().hex[:8]}",
        "description": "empty plan",
        "owner": str(g.user.id),
        "participants": [],
        "target_version": "1.0",
        "release_id": str(release.id),
        "tests": [],
        "groups": [],
        "assignments": {},
    }
    plan_id = api_client.post(
        "/api/v1/planning/plan/create", json=payload
    ).json()["response"]["id"]

    res = api_client.post(
        "/api/v1/planning/plan/trigger",
        json={"plan_id": plan_id, "common_params": {}, "params": []},
    ).json()
    assert res["status"] == "ok"
    body = res["response"]
    assert body["jobs"] == []
    assert body["failed_to_execute"] == []
    # Jenkins must NOT be invoked since there are no tests
    mock_jenkins_service.return_value.build_job.assert_not_called()
