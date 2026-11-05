import json
from dataclasses import asdict, dataclass
from uuid import UUID, uuid1, uuid4

import pytest

from argus.backend.models.web import ArgusGroup, ArgusRelease, ArgusTest
from argus.backend.plugins.sct.testrun import SCTTestRun
from argus.backend.service.chat.entity import resolve_entity
from argus.backend.service.chat.llm import ToolCall
from argus.backend.service.chat.resolve import (
    TestReferenceError,
    load_scope,
    resolve_group,
    resolve_release,
    resolve_run_reference,
    resolve_test_reference,
    resolve_tests,
    run_url,
)
from argus.backend.service.chat.tools import ToolContext, run_tool
from argus.backend.service.release_manager import ReleaseManagerService
from argus.backend.tests.conftest import get_fake_test_run
from argus.backend.tests.release_summary.helpers import SCT, unique

pytestmark = pytest.mark.docker_required

JENKINS = "https://jenkins.example.com"


@dataclass
class World:
    release: ArgusRelease
    upgrades: ArgusGroup
    longevity: ArgusGroup
    rolling: ArgusTest
    twin: ArgusTest
    cdc: ArgusTest


@pytest.fixture
async def world(release_manager_service: ReleaseManagerService) -> World:
    name = unique("refs")
    release = await release_manager_service.create_release(name, f"Pretty {name}", False)
    upgrades = await release_manager_service.create_group("upgrades", "Rolling Upgrades",
                                                          build_system_id=f"{name}/upgrades", release_id=release.id)
    longevity = await release_manager_service.create_group("longevity", "Longevity Tests",
                                                           build_system_id=f"{name}/longevity", release_id=release.id)

    async def test(group: ArgusGroup, test_name: str, pretty: str) -> ArgusTest:
        build_id = f"{group.build_system_id}/{test_name}"
        return await release_manager_service.create_test(test_name, pretty, build_id, f"{JENKINS}/job/{build_id}",
                                                         group_id=group.id, release_id=release.id, plugin_name=SCT)

    return World(release=release, upgrades=upgrades, longevity=longevity,
                 rolling=await test(upgrades, "rolling-upgrade-centos9-test", "Rolling upgrade on CentOS 9"),
                 twin=await test(longevity, "rolling-upgrade-centos9-test", "Longevity twin"),
                 cdc=await test(longevity, "longevity-cdc-100gb-4h-test", "CDC 100GB 4h"))


@pytest.fixture
async def scope(world):
    return await load_scope(await resolve_entity("release", world.release.id))


def job_url(test: ArgusTest) -> str:
    return JENKINS + "".join(f"/job/{part}" for part in test.build_system_id.split("/")) + "/"


@pytest.mark.parametrize("reference", [
    "id", "build_system_id", "job_url", "longevity-cdc-100gb-4h-test", "CDC 100GB 4h", "cdc 100gb 4h",
    "longevity/longevity-cdc-100gb-4h-test", "Longevity Tests/CDC 100GB 4h",
    "release/longevity/longevity-cdc-100gb-4h-test",
])
async def test_a_test_is_found_every_way(world, scope, reference):
    reference = {"id": str(world.cdc.id), "build_system_id": world.cdc.build_system_id, "job_url": job_url(world.cdc),
                 "release/longevity/longevity-cdc-100gb-4h-test":
                     f"{world.release.name}/longevity/longevity-cdc-100gb-4h-test"}.get(reference, reference)

    assert resolve_test_reference(scope, reference).id == world.cdc.id


async def test_a_shared_name_needs_its_group(world, scope):
    with pytest.raises(TestReferenceError, match="upgrades/rolling-upgrade-centos9-test"):
        resolve_test_reference(scope, "rolling-upgrade-centos9-test")

    assert resolve_test_reference(scope, "Rolling Upgrades/rolling-upgrade-centos9-test").id == world.rolling.id


async def test_groups_and_releases_are_found_every_way(world, scope):
    for reference in (str(world.longevity.id), "longevity", "Longevity Tests", world.longevity.build_system_id,
                      f"{world.release.name}/longevity"):
        assert resolve_group(scope, reference).id == world.longevity.id
    for reference in (str(world.release.id), world.release.name, f"pretty {world.release.name}"):
        assert resolve_release(scope, reference).id == world.release.id


async def test_a_group_or_a_release_stands_for_its_tests(world, scope):
    assert {test.id for test in resolve_tests(scope, ["longevity"])} == {world.twin.id, world.cdc.id}
    assert len(resolve_tests(scope, [world.release.name])) == 3
    assert [test.id for test in resolve_tests(scope, ["CDC 100GB 4h", "longevity"])] == [world.cdc.id, world.twin.id]


async def submit_build(client_service, test: ArgusTest, number: int):
    run_type, request = get_fake_test_run(test, job_url=f"{job_url(test)}{number}/")
    await client_service.submit_run(run_type, asdict(request))
    await client_service.submit_product_version(run_type, UUID(request.run_id), "2039.1.0")
    return UUID(request.run_id)


async def test_a_run_is_found_every_way(world, scope, client_service):
    run_id = await submit_build(client_service, world.cdc, 7)
    entity = await resolve_entity("release", world.release.id)

    for reference in (str(run_id), f"{world.cdc.build_system_id}#7", "longevity/longevity-cdc-100gb-4h-test#7",
                      "CDC 100GB 4h #7", f"{job_url(world.cdc)}7/", f"{job_url(world.cdc)}7/consoleFull"):
        assert (await resolve_run_reference(entity, scope, reference)).id == run_id, reference


async def test_a_test_without_a_build_number_lists_its_builds(world, scope, client_service):
    await submit_build(client_service, world.cdc, 7)
    entity = await resolve_entity("release", world.release.id)

    with pytest.raises(TestReferenceError, match="#7"):
        await resolve_run_reference(entity, scope, "CDC 100GB 4h")
    with pytest.raises(TestReferenceError):
        await resolve_run_reference(entity, scope, str(uuid4()))
    with pytest.raises(TestReferenceError):
        await resolve_run_reference(entity, scope, "CDC 100GB 4h#99")


async def test_tools_take_the_wide_references(world, client_service, logged_in_user):
    await submit_build(client_service, world.cdc, 7)
    ctx = ToolContext(entity=await resolve_entity("release", world.release.id), user=logged_in_user, node=uuid1())

    run = await run_tool(ctx, ToolCall("c1", "read_run", json.dumps({"run": "CDC 100GB 4h#7"})))
    runs = await run_tool(ctx, ToolCall("c2", "get_runs", json.dumps({"test": job_url(world.cdc)})))
    release = await run_tool(ctx, ToolCall("c3", "read_release",
                                           json.dumps({"release": f"Pretty {world.release.name}"})))
    shown = await run_tool(ctx, ToolCall("c4", "show_run", json.dumps({"run": f"{job_url(world.cdc)}7/"})))

    assert not run.error and json.loads(run.content)["build_number"] == 7
    assert not runs.error and len(json.loads(runs.content)["runs"]) == 1
    assert not release.error and json.loads(release.content)["name"] == world.release.name
    assert shown.card_state == "done"
    assert shown.action["proposal"]["url"] == f"/test/{world.cdc.build_system_id}/7"
    assert shown.action["proposal"]["test"] == "longevity/longevity-cdc-100gb-4h-test"


def test_a_run_without_a_build_number_links_by_its_plugin():
    run_id = uuid4()

    with_build = SCTTestRun.model_construct(id=run_id, build_id="scylla-2025.1/upgrades/x", build_number=12)
    without = SCTTestRun.model_construct(id=run_id, build_id="scylla-2025.1/upgrades/x", build_number=None)

    assert run_url(with_build) == "/test/scylla-2025.1/upgrades/x/12"
    assert run_url(without) == f"/tests/scylla-cluster-tests/{run_id}"
