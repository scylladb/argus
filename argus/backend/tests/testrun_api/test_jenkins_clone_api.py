import time
from unittest.mock import MagicMock, patch

import pytest

from argus.backend.models.web import ArgusGroup, ArgusRelease, ArgusTest


API_PREFIX = "/api/v1"

JOB_CONFIG = """<?xml version='1.1' encoding='UTF-8'?>
<flow-definition plugin="workflow-job">
  <displayName>source</displayName>
</flow-definition>
"""


@pytest.fixture
def fake_jenkins():
    client = MagicMock(name="JenkinsClient")
    client.get_job_config.return_value = JOB_CONFIG
    client.get_job_info.return_value = {"url": "http://jenkins.test/job/cloned/"}
    with patch("argus.backend.service.jenkins_service.jenkins.Jenkins", return_value=client):
        yield client


def test_clone_groups_returns_groups_of_target_release(api_client, release: ArgusRelease, group: ArgusGroup):
    resp = api_client.get(f"{API_PREFIX}/jenkins/clone/groups", params={"targetId": str(release.id)})

    body = resp.json()
    assert body["status"] == "ok", body
    assert str(group.id) in [g["id"] for g in body["response"]["groups"]]


def test_clone_job_creates_test_in_target_group(api_client, fake_jenkins, fake_test: ArgusTest,
                                                release: ArgusRelease, group: ArgusGroup):
    new_name = f"clone_{time.time_ns()}"

    resp = api_client.post(f"{API_PREFIX}/jenkins/clone/create", json={
        "currentTestId": str(fake_test.id),
        "newName": new_name,
        "target": str(release.id),
        "group": str(group.id),
        "advancedSettings": {},
    })

    body = resp.json()
    assert body["status"] == "ok", body
    new_build_id = f"{group.build_system_id}/{new_name}"
    fake_jenkins.create_job.assert_called_once()
    assert fake_jenkins.create_job.call_args.kwargs["name"] == new_build_id
    new_test = ArgusTest.get(build_system_id=new_build_id)
    assert new_test.group_id == group.id
    assert new_test.release_id == release.id
    assert new_test.plugin_name == fake_test.plugin_name
