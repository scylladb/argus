import base64
import json

from uuid import uuid4

import pytest
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


async def make_run(client_service: ClientService, testrun_service: TestRunService, fake_test: ArgusTest) -> SCTTestRun:
    run_type, run_req = get_fake_test_run(fake_test)
    await client_service.submit_run(run_type, asdict(run_req))
    return await testrun_service.get_run(run_type, run_req.run_id)


async def test_submitted_config_lands_in_the_by_run_table(api_client, client_service, testrun_service, fake_test):
    run = await make_run(client_service, testrun_service, fake_test)

    submit_config(api_client, run.id, CONFIG)

    stored = {row.name: row.value for row in await RunConfigParamByRun.find(run_id=run.id).all()}

    assert stored["sct_config.backend"] == "aws"
    assert stored["sct_config.nested.inner.deep"] == "10"
    assert stored["sct_config.listed.0"] == "first"
    assert stored["sct_config.listed.1"] == "second"


async def test_falsy_values_keep_the_legacy_encoding(api_client, client_service, testrun_service, fake_test):
    run = await make_run(client_service, testrun_service, fake_test)

    submit_config(api_client, run.id, CONFIG)

    stored = {row.name: row.value for row in await RunConfigParamByRun.find(run_id=run.id).all()}

    assert stored["sct_config.absent"] == "None"
    assert stored["sct_config.blank"] == "null"
    assert stored["sct_config.disabled"] == "False"


async def test_a_non_canonical_run_id_still_writes_a_canonical_uuid(api_client, client_service, testrun_service, fake_test):
    run = await make_run(client_service, testrun_service, fake_test)

    submit_config(api_client, str(run.id).upper(), CONFIG)

    assert (await RunConfigParamByRun.get(run_id=run.id, name="sct_config.backend")).value == "aws"


async def test_submitted_config_lands_in_the_value_index(api_client, client_service, testrun_service, fake_test):
    run = await make_run(client_service, testrun_service, fake_test)

    submit_config(api_client, run.id, CONFIG)

    values = [row.value for row in await RunConfigParamValueIndex.find(name="sct_config.backend").all()]

    assert "aws" in values


async def test_submitted_config_lands_in_the_name_catalogue(api_client, client_service, testrun_service, fake_test):
    run = await make_run(client_service, testrun_service, fake_test)
    unique = f"marker_{run.id.hex}"

    submit_config(api_client, run.id, {unique: "present"})

    names = [row.name for row in await RunConfigParamName.find(bucket=NAME_BUCKET).all()]

    assert f"sct_config.{unique}" in names


async def test_a_config_name_with_dots_is_flattened_into_the_prefix(api_client, client_service, testrun_service, fake_test):
    run = await make_run(client_service, testrun_service, fake_test)

    submit_config(api_client, run.id, {"key": "value"}, name="my.config name")

    stored = {row.name for row in await RunConfigParamByRun.find(run_id=run.id).all()}

    assert "my_config_name.key" in stored


async def test_get_config_property_narrows_by_run_id(api_client, client_service, testrun_service, fake_test):
    wanted = await make_run(client_service, testrun_service, fake_test)
    other = await make_run(client_service, testrun_service, fake_test)
    submit_config(api_client, wanted.id, {"backend": "aws"})
    submit_config(api_client, other.id, {"backend": "aws"})

    found = await client_service.get_config_property(name="sct_config.backend", value="aws", run_id=wanted.id)

    assert [row.run_id for row in found] == [str(wanted.id)]


async def test_a_failed_catalogue_write_does_not_mark_the_name_as_indexed(argus_db, monkeypatch):
    """The name must stay unknown to this worker, or it is never written again."""
    import argus.backend.service.client_service as module

    unique = f"marker_{uuid4().hex}"
    real = module.save_in_batches

    async def failing(items, to_documents, *args, **kwargs):
        if to_documents is module.ClientService._catalogue_row:
            raise RuntimeError("flush failed")
        return await real(items, to_documents, *args, **kwargs)

    monkeypatch.setattr(module, "save_in_batches", failing)

    with pytest.raises(RuntimeError):
        await module.ClientService.parse_config_values("sct_config", json.dumps({unique: "present"}), str(uuid4()))

    assert f"sct_config.{unique}" not in module._INDEXED_NAMES


async def test_a_successful_write_marks_the_name_as_indexed(argus_db):
    import argus.backend.service.client_service as module

    unique = f"marker_{uuid4().hex}"
    await module.ClientService.parse_config_values("sct_config", json.dumps({unique: "present"}), str(uuid4()))

    assert f"sct_config.{unique}" in module._INDEXED_NAMES
