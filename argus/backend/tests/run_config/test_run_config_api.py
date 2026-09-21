from uuid import uuid4

from argus.backend.models.run_config import NAME_BUCKET, RunConfigParamName, RunConfigParamValueIndex


def test_param_names_returns_the_envelope(api_client, argus_db):
    unique = uuid4().hex
    row = RunConfigParamName.model_construct()
    row.bucket = NAME_BUCKET
    row.name = f"sct_config.{unique}"
    row.save()

    response = api_client.get(f"/api/v1/run_configs/param_names?query={unique}")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ok"
    assert response.json()["response"] == [f"sct_config.{unique}"]


def test_param_values_returns_the_envelope(api_client, argus_db):
    name = f"sct_config.{uuid4().hex}"
    for value in ("aws", "gce"):
        row = RunConfigParamValueIndex.model_construct()
        row.name = name
        row.value = value
        row.save()

    response = api_client.get(f"/api/v1/run_configs/param_values?name={name}&query=a")

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
