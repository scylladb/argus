import base64
import json
from dataclasses import asdict

from starlette.testclient import TestClient

from argus.backend.models.run_config import (
    NAME_BUCKET,
    RunConfigParamByRun,
    RunConfigParamName,
    RunConfigParamValueIndex,
)
from argus.backend.models.web import ArgusTest
from argus.backend.plugins.sct.testrun import SCTTestRun
from argus.backend.service.client_service import ClientService
from argus.backend.service.testrun import TestRunService
from argus.backend.tests.conftest import get_fake_test_run
from argus.backend.util.encoders import ArgusJSONEncoder

CONFIG = {
    "backend": "aws",
    "nested": {"inner": {"deep": 10}},
    "listed": ["first", "second"],
    "absent": None,
    "blank": "",
    "disabled": False,
}


def submit_config(api_client: TestClient, run_id, config: dict, name: str = "sct_config") -> None:
    response = api_client.post(
        f"/api/v1/client/{run_id}/config/submit",
        content=json.dumps({
            "name": name,
            "content": base64.encodebytes(json.dumps(config).encode(encoding="utf-8")).decode("utf-8"),
            "schema_version": "v8",
        }, cls=ArgusJSONEncoder),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ok"


def make_run(client_service: ClientService, testrun_service: TestRunService, fake_test: ArgusTest) -> SCTTestRun:
    run_type, run_req = get_fake_test_run(fake_test)
    client_service.submit_run(run_type, asdict(run_req))
    return testrun_service.get_run(run_type, run_req.run_id)


def test_submitted_config_lands_in_the_by_run_table(api_client, client_service, testrun_service, fake_test):
    run = make_run(client_service, testrun_service, fake_test)

    submit_config(api_client, run.id, CONFIG)

    stored = {row.name: row.value for row in RunConfigParamByRun.find(run_id=run.id).all()}

    assert stored["sct_config.backend"] == "aws"
    assert stored["sct_config.nested.inner.deep"] == "10"
    assert stored["sct_config.listed.0"] == "first"
    assert stored["sct_config.listed.1"] == "second"


def test_falsy_values_keep_the_legacy_encoding(api_client, client_service, testrun_service, fake_test):
    run = make_run(client_service, testrun_service, fake_test)

    submit_config(api_client, run.id, CONFIG)

    stored = {row.name: row.value for row in RunConfigParamByRun.find(run_id=run.id).all()}

    assert stored["sct_config.absent"] == "None"
    assert stored["sct_config.blank"] == "null"
    assert stored["sct_config.disabled"] == "False"


def test_a_non_canonical_run_id_still_writes_a_canonical_uuid(api_client, client_service, testrun_service, fake_test):
    run = make_run(client_service, testrun_service, fake_test)

    submit_config(api_client, str(run.id).upper(), CONFIG)

    assert RunConfigParamByRun.get(run_id=run.id, name="sct_config.backend").value == "aws"


def test_submitted_config_lands_in_the_value_index(api_client, client_service, testrun_service, fake_test):
    run = make_run(client_service, testrun_service, fake_test)

    submit_config(api_client, run.id, CONFIG)

    values = [row.value for row in RunConfigParamValueIndex.find(name="sct_config.backend").all()]

    assert "aws" in values


def test_submitted_config_lands_in_the_name_catalogue(api_client, client_service, testrun_service, fake_test):
    run = make_run(client_service, testrun_service, fake_test)
    unique = f"marker_{run.id.hex}"

    submit_config(api_client, run.id, {unique: "present"})

    names = [row.name for row in RunConfigParamName.find(bucket=NAME_BUCKET).all()]

    assert f"sct_config.{unique}" in names


def test_a_config_name_with_dots_is_flattened_into_the_prefix(api_client, client_service, testrun_service, fake_test):
    run = make_run(client_service, testrun_service, fake_test)

    submit_config(api_client, run.id, {"key": "value"}, name="my.config name")

    stored = {row.name for row in RunConfigParamByRun.find(run_id=run.id).all()}

    assert "my_config_name.key" in stored


def test_get_config_property_narrows_by_run_id(api_client, client_service, testrun_service, fake_test):
    wanted = make_run(client_service, testrun_service, fake_test)
    other = make_run(client_service, testrun_service, fake_test)
    submit_config(api_client, wanted.id, {"backend": "aws"})
    submit_config(api_client, other.id, {"backend": "aws"})

    found = client_service.get_config_property(name="sct_config.backend", value="aws", run_id=wanted.id)

    assert [row.run_id for row in found] == [str(wanted.id)]
