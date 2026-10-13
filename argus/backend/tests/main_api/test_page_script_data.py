import time
import uuid

import pytest

from argus.backend.tests.util import client_post, script_value

ADMIN_PREFIX = "/admin/api/v1"
DESCRIPTION = 'say "hi"\nthen </script>'
VERSION_REGEX = r"^\d+\.\d+$"
INJECTED = 'x";alert(1);"'


@pytest.fixture
def quoted_release(api_client) -> str:
    name = f"script_data_{time.time_ns()}"
    resp = client_post(api_client, f"{ADMIN_PREFIX}/release/create",
                       {"release_name": name, "pretty_name": name, "perpetual": False})
    assert resp.status_code == 200, resp.content
    release = resp.json()["response"]["new_release"]
    resp = client_post(api_client, f"{ADMIN_PREFIX}/release/edit", {
        "id": release["id"],
        "pretty_name": name,
        "description": DESCRIPTION,
        "valid_version_regex": VERSION_REGEX,
        "enabled": True,
        "perpetual": False,
        "dormant": False,
    })
    assert resp.status_code == 200, resp.content
    return name


@pytest.mark.parametrize("path", ["/dashboard/{name}", "/release/{name}/scheduler", "/release/{name}/duty"])
def test_release_page_embeds_release_data_intact(api_client, quoted_release, path):
    res = api_client.get(path.format(name=quoted_release))

    assert res.status_code == 200, res.text
    release = script_value(res.text, "releaseData")["release"]
    assert release["description"] == DESCRIPTION
    assert release["valid_version_regex"] == VERSION_REGEX


def test_runs_page_embeds_additional_runs_intact(api_client):
    run = 'a"b\\c'

    res = api_client.get(f"/test/{uuid.uuid4()}/runs", params={"additionalRuns[]": run})

    assert res.status_code == 200, res.text
    assert script_value(res.text, "additionalRuns") == [run]


def test_admin_page_keeps_route_inside_its_string(api_client):
    res = api_client.get("/admin/x%22%3Balert(1)%3B%22")

    assert res.status_code == 200, res.text
    assert script_value(res.text, "gCurrentRoute") == INJECTED
