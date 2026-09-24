import base64
from dataclasses import asdict, dataclass
import json

import pytest
from starlette.testclient import TestClient

from argus.backend.models.web import ArgusTest
from argus.backend.service.client_service import ClientService
from argus.backend.plugins.sct.service import SCTService
from argus.backend.service.testrun import TestRunService
from argus.backend.plugins.sct.testrun import SCTTestRun
from argus.backend.tests.conftest import get_fake_test_run
from argus.backend.util.encoders import ArgusJSONEncoder



def test_submit_simple_config(api_client: TestClient, client_service: ClientService, sct_service: SCTService, testrun_service: TestRunService, fake_test: ArgusTest):
    run_type, run_req = get_fake_test_run(fake_test)
    client_service.submit_run(run_type, asdict(run_req))
    run: SCTTestRun = testrun_service.get_run(run_type, run_req.run_id)

    config = {
        "prop": {
            "inner": {
                "deep": 10
            }
        },
        "another": "text",
        "some_more": 1.052,
    }

    response = api_client.post(
        f"/api/v1/client/{run.id}/config/submit",
        content=json.dumps({
            "name": "my_config",
            "content": base64.encodebytes(json.dumps(config).encode(encoding="utf-8")).decode("utf-8"),
            "schema_version": "v8",
        }, cls=ArgusJSONEncoder),
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["status"] == "ok"
    assert response.json()["response"]


def test_get_config_properties(api_client: TestClient, client_service: ClientService, sct_service: SCTService, testrun_service: TestRunService, fake_test: ArgusTest):
    run_type, run_req = get_fake_test_run(fake_test)
    client_service.submit_run(run_type, asdict(run_req))
    run: SCTTestRun = testrun_service.get_run(run_type, run_req.run_id)

    config = {
        "prop": {
            "inner": {
                "deep": 10
            }
        },
        "another": "text",
        "some_more": 1.052,
    }

    response = api_client.post(
        f"/api/v1/client/{run.id}/config/submit",
        content=json.dumps({
            "name": "my_config",
            "content": base64.encodebytes(json.dumps(config).encode(encoding="utf-8")).decode("utf-8"),
            "schema_version": "v8",
        }, cls=ArgusJSONEncoder),
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["status"] == "ok"
    assert response.json()["response"]

    props = client_service.get_config_property(name="my_config.prop.inner.deep", value=10, run_id=run.id)
    assert len(props) > 0
    assert props[0].value == "10"


def test_get_configs_for_runs(api_client: TestClient, client_service: ClientService, sct_service: SCTService, testrun_service: TestRunService, fake_test: ArgusTest):
    run_type, run_req = get_fake_test_run(fake_test)
    client_service.submit_run(run_type, asdict(run_req))
    run: SCTTestRun = testrun_service.get_run(run_type, run_req.run_id)

    config = {
        "prop": {
            "inner": {
                "deep": 10
            }
        },
        "another": "text",
        "some_more": 1.052,
    }
    serialized_config = base64.encodebytes(json.dumps(config).encode(encoding="utf-8"))

    for name in ["my_config", "another_config"]:
        response = api_client.post(
            f"/api/v1/client/{run.id}/config/submit",
            json={
                "name": name,
                "content": serialized_config.decode("utf-8"),
                "schema_version": "v8",
            },
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")
        assert response.json()["status"] == "ok"
        assert response.json()["response"]

    configs = client_service.get_all_configs(run.id)
    assert len(configs) == 2
    assert [cfg.name for cfg in configs] == ["another_config", "my_config"]


def test_get_config_property_returns_only_the_run_asked_for(api_client: TestClient, client_service: ClientService, testrun_service: TestRunService, fake_test: ArgusTest):
    runs = []
    for _ in range(2):
        run_type, run_req = get_fake_test_run(fake_test)
        client_service.submit_run(run_type, asdict(run_req))
        runs.append(testrun_service.get_run(run_type, run_req.run_id))
    content = base64.encodebytes(json.dumps({"prop": {"inner": {"deep": 10}}}).encode("utf-8")).decode("utf-8")
    for run in runs:
        response = api_client.post(
            f"/api/v1/client/{run.id}/config/submit",
            content=json.dumps({"name": "my_config", "content": content, "schema_version": "v8"}, cls=ArgusJSONEncoder),
            headers={"content-type": "application/json"},
        )
        assert response.json()["status"] == "ok"

    props = client_service.get_config_property(name="my_config.prop.inner.deep", value=10, run_id=runs[0].id)

    assert [prop.run_id for prop in props] == [str(runs[0].id)]
