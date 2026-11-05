import uuid

import pytest
from starlette.testclient import TestClient

from argus.backend.tests.chat.helpers import seed_entity_release
from argus.backend.tests.release_summary.helpers import submit_run

pytestmark = pytest.mark.docker_required


def ok(response):
    body = response.json()
    assert body["status"] == "ok", body
    return body["response"]


async def test_memories_are_managed_through_the_routes(api_client: TestClient, release_manager_service):
    seeded = await seed_entity_release(release_manager_service)
    base = f"/api/v1/chat/release/{seeded.release.id}/memories"

    created = ok(api_client.post(base, json={"content": "We run on GCE", "kind": "note"}))
    edited = ok(api_client.put(f"{base}/{created['id']}", json={"content": "We run on AWS"}))
    listed = ok(api_client.get(base))
    deleted = ok(api_client.delete(f"{base}/{created['id']}"))
    history = ok(api_client.get(f"{base}/history"))
    restored = ok(api_client.post(f"{base}/history/{history[0]['revision']}/revert"))

    assert edited["content"] == "We run on AWS"
    assert [memory["content"] for memory in listed] == ["We run on AWS"]
    assert deleted["id"] == created["id"]
    assert [entry["action"] for entry in history] == ["delete", "update", "create"]
    assert restored["content"] == "We run on AWS"


def test_an_unknown_entity_is_an_error(api_client: TestClient):
    body = api_client.get(f"/api/v1/chat/release/{uuid.uuid4()}/memories").json()

    assert body["status"] == "error"
    assert body["response"]["exception"] == "ChatEntityError"


async def test_findings_show_in_the_summary_and_survive_a_recompute(api_client: TestClient,
                                                                    release_manager_service, client_service):
    seeded = await seed_entity_release(release_manager_service)
    await submit_run(client_service, seeded.tests[0], "2034.1.0", "passed")
    ok(api_client.post(f"/api/v1/chat/release/{seeded.release.id}/memories",
                       json={"content": "rc failures were infra", "kind": "finding"}))
    ok(api_client.post(f"/api/v1/chat/release/{seeded.release.id}/memories",
                       json={"content": "just a note", "kind": "note"}))

    first = ok(api_client.get(f"/api/v1/release/{seeded.release.id}/version_summary"))
    await submit_run(client_service, seeded.tests[1], "2034.1.0", "failed")
    second = ok(api_client.get(f"/api/v1/release/{seeded.release.id}/version_summary"))

    assert [finding["content"] for finding in first["findings"]] == ["rc failures were infra"]
    assert second["families"][0]["rollup"]["counts"]["failed"] == 1
    assert [finding["content"] for finding in second["findings"]] == ["rc failures were infra"]


async def test_the_view_summary_carries_view_and_release_findings(api_client: TestClient,
                                                                  release_manager_service, client_service):
    seeded = await seed_entity_release(release_manager_service)
    await submit_run(client_service, seeded.tests[0], "2034.2.0", "passed")
    view = ok(api_client.post("/api/v1/views/create", json={
        "name": f"chat_{uuid.uuid4().hex[:8]}", "items": [f"test:{seeded.tests[0].id}"], "settings": "[]"}))
    ok(api_client.post(f"/api/v1/chat/release/{seeded.release.id}/memories",
                       json={"content": "release finding", "kind": "finding"}))
    ok(api_client.post(f"/api/v1/chat/view/{view['id']}/memories",
                       json={"content": "view finding", "kind": "finding"}))

    summary = ok(api_client.get("/api/v1/views/widgets/release_summary", params={"view_id": view["id"]}))

    assert [finding["content"] for finding in summary["findings"]] == ["view finding"]
    assert [finding["content"] for finding in summary["releases"][0]["findings"]] == ["release finding"]
