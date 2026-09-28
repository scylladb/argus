import time
import xml.etree.ElementTree as ET
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


async def test_clone_job_creates_test_in_target_group(api_client, fake_jenkins, fake_test: ArgusTest,
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
    new_test = await ArgusTest.get(build_system_id=new_build_id)
    try:
        fake_jenkins.create_job.assert_called_once()
        create_args = fake_jenkins.create_job.call_args.kwargs
        assert create_args["name"] == new_build_id
        assert ET.fromstring(create_args["config_xml"]).find("displayName").text == new_name
        assert new_test.group_id == group.id
        assert new_test.release_id == release.id
        assert new_test.plugin_name == fake_test.plugin_name
    finally:
        await new_test.delete()


async def test_clone_job_rejects_source_group_and_name(api_client, fake_jenkins, fake_test: ArgusTest,
                                                      release: ArgusRelease, group: ArgusGroup):
    resp = api_client.post(f"{API_PREFIX}/jenkins/clone/create", json={
        "currentTestId": str(fake_test.id),
        "newName": fake_test.name,
        "target": str(release.id),
        "group": str(group.id),
        "advancedSettings": {},
    })

    body = resp.json()
    assert body["status"] == "error"
    assert body["response"]["arguments"][0] == "Unable to clone: source and destination are the same"
    fake_jenkins.create_job.assert_not_called()


async def test_clone_job_rejects_used_build_system_id(api_client, fake_jenkins, release_manager_service,
                                                     fake_test: ArgusTest, release: ArgusRelease, group: ArgusGroup):
    used_name = f"used_{time.time_ns()}"
    used_test = await release_manager_service.create_test(
        used_name, used_name, f"{group.build_system_id}/{used_name}", used_name,
        group_id=str(group.id), release_id=str(release.id), plugin_name="scylla-cluster-tests")
    try:
        resp = api_client.post(f"{API_PREFIX}/jenkins/clone/create", json={
            "currentTestId": str(fake_test.id),
            "newName": used_name,
            "target": str(release.id),
            "group": str(group.id),
            "advancedSettings": {},
        })

        body = resp.json()
        assert body["status"] == "error"
        assert body["response"]["arguments"][0] == "Build Id is already used by another test"
        fake_jenkins.create_job.assert_not_called()
    finally:
        await used_test.delete()
