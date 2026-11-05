import json
import time
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from argus.backend.service.jenkins_service import JenkinsService
from argus.backend.tests.chat.helpers import seed_entity_release, text_turn, tool_turn

pytestmark = pytest.mark.docker_required

JOB = [{"name": "backend", "value": "aws"}, {"name": "scylla_version", "value": "2025.1.0"}]


@pytest.fixture
def jenkins():
    instance = MagicMock(spec=JenkinsService, name="JenkinsService")
    instance.retrieve_job_parameters.side_effect = lambda build_id, build_number, **_: [dict(param) for param in JOB]
    instance.build_job.return_value = 777
    instance.next_build_number.return_value = 42
    with patch("argus.backend.service.chat.actions.JenkinsService", return_value=instance):
        yield instance


@pytest.fixture
async def seeded(release_manager_service):
    return await seed_entity_release(release_manager_service)


def ok(response):
    body = response.json()
    assert body["status"] == "ok", body
    return body["response"]


def ask(client: TestClient, base: str, content: str, auto: bool) -> dict:
    ok(client.post(f"{base}/messages", json={"content": content, "auto": auto}))
    deadline = time.monotonic() + 10
    while (conversation := ok(client.get(base)))["busy"] is not None and time.monotonic() < deadline:
        time.sleep(0.05)
    return conversation


async def test_auto_mode_runs_the_card_inside_the_answer(chat_client: TestClient, chat_model, jenkins, seeded,
                                                         logged_in_user):
    base = f"/api/v1/chat/release/{seeded.release.id}"
    chat_model.turns = [tool_turn(("execute_tests", {"tests": [seeded.tests[0].name]})), text_turn("Started")]

    conversation = ask(chat_client, base, "start it", auto=True)

    card = next(node for node in conversation["nodes"] if node["role"] == "action")
    tool_result = json.loads(chat_model.requests[1].messages[-1].content)
    second = chat_client.post(f"{base}/actions/{card['node']}/confirm").json()
    assert card["action"]["state"] == "done" and card["action"]["auto"] is True
    assert card["action"]["confirmed_by"] == str(logged_in_user.id)
    assert jenkins.build_job.call_count == 1
    assert tool_result["status"].startswith("confirmed automatically") and "build 42" in tool_result["outcome"]
    assert "Auto mode is on" in chat_model.requests[0].messages[0].content
    assert second["status"] == "error"


async def test_without_auto_mode_the_card_waits(chat_client: TestClient, chat_model, jenkins, seeded):
    base = f"/api/v1/chat/release/{seeded.release.id}"
    chat_model.turns = [tool_turn(("execute_tests", {"tests": [seeded.tests[0].name]})), text_turn("Confirm it")]

    conversation = ask(chat_client, base, "start it", auto=False)

    card = next(node for node in conversation["nodes"] if node["role"] == "action")
    assert card["action"]["state"] == "pending"
    assert "Auto mode is on" not in chat_model.requests[0].messages[0].content
    jenkins.build_job.assert_not_called()
