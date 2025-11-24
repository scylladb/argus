import base64
from dataclasses import asdict
from datetime import datetime, UTC
from io import BytesIO
import json
import logging
from typing import IO

from flask.testing import FlaskClient

from argus.backend.models.web import ArgusRelease, ArgusGroup, ArgusTest
from argus.backend.plugins.sct.testrun import SCTTestRun
from argus.backend.service.client_service import ClientService
from argus.backend.plugins.sct.service import SCTService
from argus.backend.service.testrun import TestRunService
from argus.backend.tests.conftest import get_fake_test_run
from argus.backend.util.encoders import ArgusJSONEncoder
from argus.backend.tests.email_service.conftest import EmailListener

LOGGER = logging.getLogger(__name__)



def test_send_default_email(flask_client: FlaskClient, fake_test: ArgusTest, client_service: ClientService, testrun_service: TestRunService, email_listener: EmailListener):
    run_type, run_req = get_fake_test_run(fake_test)
    client_service.submit_run(run_type, asdict(run_req))
    run: SCTTestRun = testrun_service.get_run(run_type, run_req.run_id)

    response = flask_client.post(
        f"/api/v1/client/testrun/report/email",
        data=json.dumps({
            "run_id": run.id,
            "title": "#auto",
            "recipients": ["john.smith@scylladb.com"],
            "sections": [],
            "attachments": [],
            "schema_version": "v8",
        }, cls=ArgusJSONEncoder),
        content_type="application/json",
    )

    assert response.json["status"] == "ok"
    assert response.json["response"]

    assert "default_user" in email_listener.content
    assert "default_commit" in email_listener.content
    assert ["john.smith@scylladb.com"] == email_listener.recipients


def test_send_default_email_empty_sections_not_rendered(flask_client: FlaskClient, fake_test: ArgusTest, client_service: ClientService, testrun_service: TestRunService, email_listener: EmailListener):
    run_type, run_req = get_fake_test_run(fake_test)
    client_service.submit_run(run_type, asdict(run_req))
    run: SCTTestRun = testrun_service.get_run(run_type, run_req.run_id)

    response = flask_client.post(
        f"/api/v1/client/testrun/report/email",
        data=json.dumps({
            "run_id": run.id,
            "title": "#auto",
            "recipients": ["john.smith@scylladb.com"],
            "sections": [],
            "attachments": [],
            "schema_version": "v8",
        }, cls=ArgusJSONEncoder),
        content_type="application/json",
    )

    assert response.json["status"] == "ok"
    assert response.json["response"]

    assert "Logs" not in email_listener.content
    assert "Nemesis" not in email_listener.content
    assert "Resources" not in email_listener.content



def test_send_email_custom_html(flask_client: FlaskClient, fake_test: ArgusTest, client_service: ClientService, testrun_service: TestRunService, email_listener: EmailListener):
    run_type, run_req = get_fake_test_run(fake_test)
    client_service.submit_run(run_type, asdict(run_req))
    run: SCTTestRun = testrun_service.get_run(run_type, run_req.run_id)

    response = flask_client.post(
        f"/api/v1/client/testrun/report/email",
        data=json.dumps({
            "run_id": run.id,
            "title": "#auto",
            "recipients": ["john.smith@scylladb.com"],
            "sections": [
                {
                    "type": "custom_html",
                    "options": {
                        "section_name": "Hello world",
                        "html": "<p title='my section'>This is a custom section</p>",
                    }
                }
            ],
            "attachments": [],
            "schema_version": "v8",
        }, cls=ArgusJSONEncoder),
        content_type="application/json",
    )

    assert response.json["status"] == "ok"
    assert response.json["response"]

    assert "Hello world" in email_listener.content
    assert "<p title='my section'>This is a custom section</p>" in email_listener.content


def test_send_email_unsupported_section(flask_client: FlaskClient, fake_test: ArgusTest, client_service: ClientService, testrun_service: TestRunService, email_listener: EmailListener):
    run_type, run_req = get_fake_test_run(fake_test)
    client_service.submit_run(run_type, asdict(run_req))
    run: SCTTestRun = testrun_service.get_run(run_type, run_req.run_id)

    response = flask_client.post(
        f"/api/v1/client/testrun/report/email",
        data=json.dumps({
            "run_id": run.id,
            "title": "#auto",
            "recipients": ["john.smith@scylladb.com"],
            "sections": [
                {
                    "type": "something_magical",
                    "options": {
                        "key": 42,
                    }
                }
            ],
            "attachments": [],
            "schema_version": "v8",
        }, cls=ArgusJSONEncoder),
        content_type="application/json",
    )

    assert response.json["status"] == "ok"
    assert response.json["response"]

    assert "Received an unknown template request" in email_listener.content
    assert "something_magical" in email_listener.content
    assert "42" in email_listener.content


def test_send_email_attachments(flask_client: FlaskClient, fake_test: ArgusTest, client_service: ClientService, testrun_service: TestRunService, email_listener: EmailListener):
    run_type, run_req = get_fake_test_run(fake_test)
    client_service.submit_run(run_type, asdict(run_req))
    run: SCTTestRun = testrun_service.get_run(run_type, run_req.run_id)

    data = base64.encodebytes(b"Hello World!")
    filename = "my_file.txt"

    response = flask_client.post(
        f"/api/v1/client/testrun/report/email",
        data=json.dumps({
            "run_id": run.id,
            "title": "#auto",
            "recipients": ["john.smith@scylladb.com"],
            "sections": [],
            "attachments": [
                {
                    "filename": filename,
                    "data": data.decode(encoding="utf-8"),
                }
            ],
            "schema_version": "v8",
        }, cls=ArgusJSONEncoder),
        content_type="application/json",
    )

    assert response.json["status"] == "ok"
    assert response.json["response"]

    assert len(email_listener.attachments) > 0
    attachment = email_listener.attachments[0]
    assert attachment["filename"] == filename
    assert isinstance(attachment["data"], BytesIO)
    decoded = attachment["data"].read()
    assert decoded == base64.decodebytes(data)
