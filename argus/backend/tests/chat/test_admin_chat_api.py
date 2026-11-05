import pytest
from starlette.testclient import TestClient

from argus.backend.service.chat.llm import ProbedModel

pytestmark = [pytest.mark.docker_required, pytest.mark.usefixtures("clean_chat_config")]

API = "/admin/api/v1/chat"


def ok(response) -> dict | list:
    body = response.json()
    assert body["status"] == "ok", body
    return body["response"]


def test_a_saved_connection_never_returns_its_token(api_client: TestClient):
    saved = ok(api_client.post(f"{API}/connection", json={"name": "db-webui", "endpoint": "https://db.test/api",
                                                            "token": "sk-secret"}))
    listed = ok(api_client.get(f"{API}/connections"))

    assert saved["token_set"] is True
    assert "sk-secret" not in str(saved) and "sk-secret" not in str(listed)
    assert [connection["name"] for connection in listed["connections"]] == ["db-webui"]
    assert listed["default"] is None


def test_a_connection_name_is_checked(api_client: TestClient):
    body = api_client.post(f"{API}/connection", json={"name": "bad name", "endpoint": "https://db.test"}).json()

    assert body["status"] == "error"


def test_the_default_is_set_from_a_probed_model(api_client: TestClient, scripted_client):
    ok(api_client.post(f"{API}/connection", json={"name": "db-webui", "endpoint": "https://db.test/api",
                                                   "token": "sk-secret"}))
    scripted_client.models = [ProbedModel("Gemma-4", "Gemma-4", 65536, True, True)]

    models = ok(api_client.get(f"{API}/connection/db-webui/models"))
    default = ok(api_client.post(f"{API}/default", json={"connection": "db-webui", "model": models[0]["id"],
                                                          "context_window": models[0]["context_window"],
                                                          "tools": True, "vision": True}))

    assert models == [{"id": "Gemma-4", "name": "Gemma-4", "context_window": 65536, "tools": True, "vision": True}]
    assert (default["connection"], default["model"]) == ("db-webui", "Gemma-4")
    assert ok(api_client.get(f"{API}/connections"))["default"]["model"] == "Gemma-4"


def test_deleting_a_connection(api_client: TestClient):
    ok(api_client.post(f"{API}/connection", json={"name": "db-webui", "endpoint": "https://db.test/api"}))

    assert ok(api_client.delete(f"{API}/connection/db-webui")) == {"deleted": "db-webui"}
    assert ok(api_client.get(f"{API}/connections"))["connections"] == []


@pytest.mark.usefixtures("normal_user_identity")
def test_a_non_admin_is_refused(api_client: TestClient):
    response = api_client.get(f"{API}/connections")

    assert response.status_code == 403
