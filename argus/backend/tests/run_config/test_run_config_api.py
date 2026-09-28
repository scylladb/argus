import json
from uuid import uuid4

from argus.backend.service.client_service import ClientService


def index_config(params: dict, config_name: str = "sct_config") -> None:
    ClientService.parse_config_values(config_name, json.dumps(params), str(uuid4()))


def test_param_names_returns_the_envelope(api_client, argus_db):
    unique = uuid4().hex
    index_config({unique: "present"})

    response = api_client.get(f"/api/v1/run_configs/param_names?query={unique}")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ok"
    assert response.json()["response"] == [f"sct_config.{unique}"]


def test_param_values_returns_the_envelope(api_client, argus_db):
    key = uuid4().hex
    for value in ("aws", "gce"):
        index_config({key: value})

    response = api_client.get(f"/api/v1/run_configs/param_values?name=sct_config.{key}&query=a")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ok"
    assert response.json()["response"] == ["aws"]


def test_param_values_without_a_name_answers_the_error_envelope(api_client, argus_db):
    response = api_client.get("/api/v1/run_configs/param_values")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "error"


def test_param_names_requires_a_user(anon_client, argus_db):
    response = anon_client.get("/api/v1/run_configs/param_names")

    assert response.status_code == 403
    assert response.json() == {"status": "error", "message": "Authorization required"}


def test_param_values_requires_a_user(anon_client, argus_db):
    response = anon_client.get("/api/v1/run_configs/param_values?name=sct_config.backend")

    assert response.status_code == 403
    assert response.json() == {"status": "error", "message": "Authorization required"}
