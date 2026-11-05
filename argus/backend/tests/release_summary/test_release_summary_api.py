import uuid

import pytest
from starlette.testclient import TestClient

from argus.backend.tests.release_summary.helpers import seed_release, submit_run

pytestmark = pytest.mark.docker_required

WIDGET = "/api/v1/views/widgets/release_summary"


def create_view(client: TestClient, items: list[str]) -> str:
    body = client.post("/api/v1/views/create", json={"name": f"summary_{uuid.uuid4().hex[:8]}", "items": items,
                                                     "settings": "{}"}).json()
    assert body["status"] == "ok", body
    return body["response"]["id"]


async def test_the_release_route_lists_families_newest_first(api_client: TestClient, release_manager_service,
                                                             client_service):
    seeded = await seed_release(release_manager_service, test_count=1)
    test = seeded.tests[0]
    for version in ("2033.1.0~rc0", "2033.1.0", "2033.1.1"):
        await submit_run(client_service, test, version, "passed")

    body = api_client.get(f"/api/v1/release/{seeded.release.id}/version_summary").json()

    assert body["status"] == "ok"
    response = body["response"]
    assert response["release_name"] == seeded.release.name
    assert response["stale"] is False
    assert [entry["family"] for entry in response["families"]] == ["2033.1.1", "2033.1.0"]
    assert [version["version"] for version in response["families"][1]["versions"]] == ["2033.1.0~rc0", "2033.1.0"]
    assert response["families"][1]["rollup"]["version"] is None
    assert response["families"][1]["rollup"]["counts"]["passed"] == 1


def test_an_unknown_release_is_an_error(api_client: TestClient):
    assert api_client.get(f"/api/v1/release/{uuid.uuid4()}/version_summary").json()["status"] == "error"


async def test_the_widget_counts_only_the_tests_of_the_view(api_client: TestClient, release_manager_service,
                                                            client_service):
    seeded = await seed_release(release_manager_service, test_count=2)
    in_view, outside = seeded.tests
    await submit_run(client_service, in_view, "2033.2.0", "passed")
    await submit_run(client_service, outside, "2033.2.0", "failed")
    view_id = create_view(api_client, [f"test:{in_view.id}"])

    body = api_client.get(WIDGET, params={"view_id": view_id}).json()

    assert body["status"] == "ok"
    [release] = body["response"]["releases"]
    rollup = release["families"][0]["rollup"]
    assert [entry["test_id"] for entry in rollup["tests"]] == [str(in_view.id)]
    assert rollup["counts"]["failed"] == 0


async def test_the_widget_gives_one_summary_per_release_of_the_view(api_client: TestClient, release_manager_service,
                                                                    client_service):
    first = await seed_release(release_manager_service, test_count=1)
    second = await seed_release(release_manager_service, test_count=1)
    await submit_run(client_service, first.tests[0], "2033.3.0", "passed")
    await submit_run(client_service, second.tests[0], "2033.3.0", "passed")
    view_id = create_view(api_client, [f"release:{first.release.id}", f"release:{second.release.id}"])

    body = api_client.get(WIDGET, params={"view_id": view_id}).json()

    assert sorted(release["release_id"] for release in body["response"]["releases"]) == sorted(
        [str(first.release.id), str(second.release.id)])


def test_an_unknown_view_is_an_error(api_client: TestClient):
    assert api_client.get(WIDGET, params={"view_id": str(uuid.uuid4())}).json()["status"] == "error"
