import base64
import json
import uuid
from dataclasses import asdict

import pytest

from argus.backend.tests.conftest import get_fake_test_run
from argus.backend.util.encoders import ArgusJSONEncoder

PARAM = "sct_config.unified_package"


def make_test(release_manager_service, group, release):
    name = f"test_{uuid.uuid4().hex[:12]}"
    return release_manager_service.create_test(
        name, name, name, name,
        group_id=str(group.id), release_id=str(release.id), plugin_name="scylla-cluster-tests",
    )


def make_run_with_config(api_client, client_service, argus_test, config: dict):
    run_type, run_req = get_fake_test_run(argus_test)
    client_service.submit_run(run_type, asdict(run_req))
    response = api_client.post(
        f"/api/v1/client/{run_req.run_id}/config/submit",
        content=json.dumps({
            "name": "sct_config",
            "content": base64.encodebytes(json.dumps(config).encode("utf-8")).decode("utf-8"),
            "schema_version": "v8",
        }, cls=ArgusJSONEncoder),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 200, response.text
    return run_req.run_id


def make_view(api_client, tests, config_param_filters):
    settings = [{
        "position": 1,
        "type": "testDashboard",
        "filter": [],
        "settings": {"configParamFilters": config_param_filters} if config_param_filters is not None else {},
    }]
    name = f"view_{uuid.uuid4().hex[:12]}"
    created = api_client.post("/api/v1/views/create", json={
        "name": name,
        "items": [f"test:{t.id}" for t in tests],
        "settings": json.dumps(settings),
    }).json()
    assert created["status"] == "ok", created
    return created["response"]["id"]


def fetch_stats(api_client, view_id, **params):
    response = api_client.get("/api/v1/views/stats", params={"viewId": view_id, "widgetId": 1, **params})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok", body
    return body["response"]


def collected_test_ids(stats) -> set[str]:
    return {test_id for group in stats["groups"].values() for test_id in group["tests"]}


@pytest.fixture
def two_tests_one_matching(api_client, client_service, release_manager_service, group, release):
    matching = make_test(release_manager_service, group, release)
    other = make_test(release_manager_service, group, release)
    make_run_with_config(api_client, client_service, matching, {"unified_package": "http://pkg.invalid/p.tar.gz"})
    make_run_with_config(api_client, client_service, other, {"unified_package": ""})
    return matching, other


def test_an_any_value_row_keeps_only_the_matching_test(api_client, two_tests_one_matching):
    matching, other = two_tests_one_matching
    view_id = make_view(api_client, [matching, other], [{"name": PARAM, "value": None}])

    found = collected_test_ids(fetch_stats(api_client, view_id))

    assert str(matching.id) in found
    assert str(other.id) not in found


def test_a_concrete_value_row_keeps_only_the_matching_test(api_client, two_tests_one_matching):
    matching, other = two_tests_one_matching
    view_id = make_view(
        api_client, [matching, other],
        [{"name": PARAM, "value": "http://pkg.invalid/p.tar.gz"}],
    )

    found = collected_test_ids(fetch_stats(api_client, view_id))

    assert found == {str(matching.id)}


def test_a_concrete_value_nobody_carries_empties_the_widget(api_client, two_tests_one_matching):
    matching, other = two_tests_one_matching
    view_id = make_view(api_client, [matching, other], [{"name": PARAM, "value": "nope"}])

    assert collected_test_ids(fetch_stats(api_client, view_id)) == set()


def test_no_filter_setting_keeps_every_test(api_client, two_tests_one_matching):
    matching, other = two_tests_one_matching
    view_id = make_view(api_client, [matching, other], None)

    found = collected_test_ids(fetch_stats(api_client, view_id))

    assert {str(matching.id), str(other.id)} <= found


def test_switching_the_row_off_widens_the_widget(api_client, two_tests_one_matching):
    matching, other = two_tests_one_matching
    view_id = make_view(api_client, [matching, other], [{"name": PARAM, "value": None}])

    found = collected_test_ids(fetch_stats(api_client, view_id, paramFilterOff=PARAM))

    assert {str(matching.id), str(other.id)} <= found


def test_switching_off_a_name_the_widget_does_not_configure_adds_no_filter(api_client, two_tests_one_matching):
    matching, other = two_tests_one_matching
    view_id = make_view(api_client, [matching, other], [{"name": PARAM, "value": None}])

    found = collected_test_ids(fetch_stats(api_client, view_id, paramFilterOff="sct_config.something_else"))

    assert str(matching.id) in found
    assert str(other.id) not in found


def test_a_blank_row_name_is_ignored(api_client, two_tests_one_matching):
    matching, other = two_tests_one_matching
    view_id = make_view(api_client, [matching, other], [{"name": "  ", "value": "aws"}])

    found = collected_test_ids(fetch_stats(api_client, view_id))

    assert {str(matching.id), str(other.id)} <= found


def test_the_pruned_test_is_absent_from_the_group_total(api_client, two_tests_one_matching):
    matching, other = two_tests_one_matching
    unfiltered = fetch_stats(api_client, make_view(api_client, [matching, other], None))
    filtered = fetch_stats(
        api_client,
        make_view(api_client, [matching, other], [{"name": PARAM, "value": None}]),
    )

    assert filtered["total"] == unfiltered["total"] - 1
