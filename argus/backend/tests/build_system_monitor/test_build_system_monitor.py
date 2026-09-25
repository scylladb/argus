from unittest.mock import patch
from uuid import uuid4

import pytest
from requests.exceptions import ConnectionError as RequestsConnectionError

from argus.backend.models.web import ArgusGroup, ArgusRelease, ArgusTest
from argus.backend.service.build_system_monitor import JenkinsMonitor

FOLDER_CLASS = "com.cloudbees.hudson.plugins.folder.Folder"
JOB_CLASS = "org.jenkinsci.plugins.workflow.job.WorkflowJob"

DESCRIPTION = """pipelines/longevity/longevity-10gb-3h.jenkinsfile

Basic longevity test running cassandra-stress.

### TestMetadata
tier: tier1
supported_backends: ['aws', 'gce']
"""

EXPECTED_METADATA = {
    "description": "Basic longevity test running cassandra-stress.",
    "tier": "tier1",
    "supported_backends": '["aws", "gce"]',
}


def item_to_release_name(item):
    return item[len("job/"):].replace("/job/", "/")


class FakeJenkins:
    def __init__(self, info=None, errors=None, releases=None):
        self.info = info or {}
        self.errors = errors or {}
        self.releases = list(releases) if releases is not None else [
            item_to_release_name(item) for item in self.info]
        self.info_calls = []
        self.job_info_calls = []

    def get_all_jobs(self, folder_depth=None, folder_depth_per_request=10):
        return [
            {"fullname": name, "name": name.split("/")[-1], "_class": FOLDER_CLASS, "url": f"http://j/{name}"}
            for name in self.releases
        ]

    def get_info(self, item="", query=None):
        self.info_calls.append((item, query))
        if item in self.errors:
            raise self.errors[item]
        return self.info[item]

    def get_job_info(self, name, depth=0, fetch_all_builds=False):
        self.job_info_calls.append(name)
        return {"displayName": name.split("/")[-1]}


def workflow_job(fullname, description=None):
    job = {
        "_class": JOB_CLASS,
        "name": fullname.split("/")[-1],
        "fullName": fullname,
        "url": f"http://j/{fullname}",
    }
    if description is not None:
        job["description"] = description
    return job


def folder(fullname, jobs):
    return {
        "_class": FOLDER_CLASS,
        "name": fullname.split("/")[-1],
        "fullName": fullname,
        "displayName": fullname.split("/")[-1],
        "url": f"http://j/{fullname}",
        "jobs": jobs,
    }


def release_tree(release_name, jobs):
    return {"job/" + "/job/".join(release_name.split("/")): {"_class": FOLDER_CLASS, "jobs": jobs}}


def make_monitor(fake, releases=(), groups=(), tests=()):
    monitor = object.__new__(JenkinsMonitor)
    monitor._jenkins = fake
    monitor._existing_releases = list(releases)
    monitor._existing_groups = list(groups)
    monitor._existing_tests = list(tests)
    monitor._filtered_groups = JenkinsMonitor.BUILD_SYSTEM_FILTERED_PREFIXES
    monitor._monitored_releases = JenkinsMonitor.JENKINS_MONITORED_RELEASES
    monitor.init_progress()

    async def load_existing():
        pass

    monitor._load_existing = load_existing
    monitor.created_releases = []
    monitor.created_groups = []
    monitor.created_tests = []

    async def create_release(release_name):
        created = ArgusRelease.model_construct(id=uuid4(), name=release_name, dormant=False)
        monitor.created_releases.append(created)
        return created

    async def create_group(release, group_name, build_id, group_pretty_name=None):
        created = ArgusGroup.model_construct(
            id=uuid4(), release_id=release.id, name=group_name,
            build_system_id=build_id, pretty_name=group_pretty_name)
        monitor.created_groups.append(created)
        return created

    async def create_test(release, group, test_name, build_id, build_url, test_metadata=None):
        created = ArgusTest.model_construct(
            id=uuid4(), release_id=release.id, group_id=group.id, name=test_name,
            build_system_id=build_id, build_system_url=build_url, test_metadata=test_metadata or {})
        monitor.created_tests.append(created)
        return created

    monitor.create_release = create_release
    monitor.create_group = create_group
    monitor.create_test = create_test
    return monitor


def stored_release(name, dormant=False):
    return ArgusRelease.model_construct(id=uuid4(), name=name, dormant=dormant)


def stored_test(build_system_id, metadata):
    return ArgusTest.model_construct(
        id=uuid4(), name=build_system_id.split("/")[-1],
        build_system_id=build_system_id, test_metadata=metadata)


async def test_requests_the_job_tree_of_each_monitored_release():
    fake = FakeJenkins(release_tree("scylla-master", []))
    await make_monitor(fake, releases=[stored_release("scylla-master")]).collect()

    assert [item for item, _ in fake.info_calls] == ["job/scylla-master"]


async def test_requests_the_nested_folder_of_a_release_as_a_job_path():
    fake = FakeJenkins(release_tree("scylla-6.0/releng-testing", []))
    await make_monitor(fake, releases=[stored_release("scylla-6.0/releng-testing")]).collect()

    assert fake.info_calls[0][0] == "job/scylla-6.0/job/releng-testing"


async def test_asks_for_the_description_and_not_for_the_class():
    fake = FakeJenkins(release_tree("scylla-master", []))
    await make_monitor(fake, releases=[stored_release("scylla-master")]).collect()

    query = fake.info_calls[0][1]
    assert "description" in query
    assert "_class" not in query
    assert query.count("jobs[") == 9


async def test_creates_a_test_with_the_metadata_from_the_job_description():
    tree = release_tree("scylla-master", [
        folder("scylla-master/longevity", [
            workflow_job("scylla-master/longevity/longevity-10gb-3h-test", DESCRIPTION)]),
    ])
    monitor = make_monitor(FakeJenkins(tree), releases=[stored_release("scylla-master")])

    await monitor.collect()

    assert [t.build_system_id for t in monitor.created_tests] == [
        "scylla-master/longevity/longevity-10gb-3h-test"]
    assert monitor.created_tests[0].test_metadata == EXPECTED_METADATA


async def test_creates_a_test_with_an_empty_map_when_the_description_has_no_block():
    tree = release_tree("scylla-master", [
        folder("scylla-master/longevity", [
            workflow_job("scylla-master/longevity/plain-test", "Nothing to parse here.")]),
    ])
    monitor = make_monitor(FakeJenkins(tree), releases=[stored_release("scylla-master")])

    await monitor.collect()

    assert monitor.created_tests[0].test_metadata == {}


async def test_does_not_recreate_a_group_or_a_test_that_already_exists():
    tree = release_tree("scylla-master", [
        folder("scylla-master/longevity", [
            workflow_job("scylla-master/longevity/longevity-10gb-3h-test", DESCRIPTION)]),
    ])
    release = stored_release("scylla-master")
    group = ArgusGroup.model_construct(
        id=uuid4(), release_id=release.id, name="longevity",
        build_system_id="scylla-master/longevity", pretty_name="Longevity")
    root_group = ArgusGroup.model_construct(
        id=uuid4(), release_id=release.id, name="scylla-master-root",
        build_system_id="scylla-master", pretty_name="-- root directory --")
    test = stored_test("scylla-master/longevity/longevity-10gb-3h-test", dict(EXPECTED_METADATA))
    monitor = make_monitor(
        FakeJenkins(tree), releases=[release], groups=[group, root_group], tests=[test])

    with patch.object(ArgusTest, "update") as update:
        await monitor.collect()

    assert monitor.created_groups == []
    assert monitor.created_tests == []
    update.assert_not_called()


async def test_writes_the_one_column_when_the_description_changed():
    tree = release_tree("scylla-master", [
        folder("scylla-master/longevity", [
            workflow_job("scylla-master/longevity/longevity-10gb-3h-test", DESCRIPTION)]),
    ])
    release = stored_release("scylla-master")
    group = ArgusGroup.model_construct(
        id=uuid4(), release_id=release.id, name="longevity",
        build_system_id="scylla-master/longevity", pretty_name="Longevity")
    test = stored_test("scylla-master/longevity/longevity-10gb-3h-test", {"tier": "tier9"})
    monitor = make_monitor(FakeJenkins(tree), releases=[release], groups=[group], tests=[test])

    with patch.object(ArgusTest, "update") as update:
        await monitor.collect()

    update.assert_called_once_with(test_metadata=EXPECTED_METADATA)


async def test_keeps_the_stored_map_when_the_description_has_no_block():
    tree = release_tree("scylla-master", [
        folder("scylla-master/longevity", [
            workflow_job("scylla-master/longevity/longevity-10gb-3h-test", "No block at all.")]),
    ])
    release = stored_release("scylla-master")
    group = ArgusGroup.model_construct(
        id=uuid4(), release_id=release.id, name="longevity",
        build_system_id="scylla-master/longevity", pretty_name="Longevity")
    test = stored_test("scylla-master/longevity/longevity-10gb-3h-test", {"tier": "tier1"})
    monitor = make_monitor(FakeJenkins(tree), releases=[release], groups=[group], tests=[test])

    with patch.object(ArgusTest, "update") as update:
        await monitor.collect()

    update.assert_not_called()
    assert test.test_metadata == {"tier": "tier1"}


async def test_skips_a_dormant_release_before_it_asks_jenkins():
    fake = FakeJenkins(release_tree("scylla-master", []))
    monitor = make_monitor(fake, releases=[stored_release("scylla-master", dormant=True)])

    await monitor.collect()

    assert fake.info_calls == []


async def test_a_release_that_fails_does_not_stop_the_next_one():
    tree = release_tree("scylla-master", [])
    tree.update(release_tree("scylla-enterprise", [
        folder("scylla-enterprise/longevity", [
            workflow_job("scylla-enterprise/longevity/a-test", DESCRIPTION)]),
    ]))
    fake = FakeJenkins(tree, errors={"job/scylla-master": RequestsConnectionError("boom")})
    monitor = make_monitor(fake, releases=[
        stored_release("scylla-master"), stored_release("scylla-enterprise")])

    await monitor.collect()

    assert [t.build_system_id for t in monitor.created_tests] == ["scylla-enterprise/longevity/a-test"]


async def test_creates_a_release_that_is_not_in_argus_yet_and_scans_it():
    tree = release_tree("scylla-master", [
        folder("scylla-master/longevity", [workflow_job("scylla-master/longevity/a-test", DESCRIPTION)]),
    ])
    monitor = make_monitor(FakeJenkins(tree))

    await monitor.collect()

    assert [r.name for r in monitor.created_releases] == ["scylla-master"]
    assert [t.build_system_id for t in monitor.created_tests] == ["scylla-master/longevity/a-test"]


async def test_a_release_whose_tree_holds_no_jobs_key_does_not_raise():
    fake = FakeJenkins({"job/scylla-master": {"_class": JOB_CLASS}})
    monitor = make_monitor(fake, releases=[stored_release("scylla-master")])

    await monitor.collect()

    assert monitor.created_tests == []


async def test_fetches_a_folder_again_when_the_tree_is_deeper_than_the_query():
    placeholder = {"_class": FOLDER_CLASS}
    tree = release_tree("scylla-master", [folder("scylla-master/longevity", [placeholder])])
    tree["job/scylla-master/job/longevity"] = {
        "_class": FOLDER_CLASS,
        "jobs": [workflow_job("scylla-master/longevity/deep-test", DESCRIPTION)],
    }
    fake = FakeJenkins(tree, releases=["scylla-master"])
    monitor = make_monitor(fake, releases=[stored_release("scylla-master")])

    await monitor.collect()

    assert "job/scylla-master/job/longevity" in [item for item, _ in fake.info_calls]
    assert [t.build_system_id for t in monitor.created_tests] == ["scylla-master/longevity/deep-test"]


async def test_does_not_ask_jenkins_again_for_a_display_name_it_already_has():
    tree = release_tree("scylla-master", [
        folder("scylla-master/longevity", [workflow_job("scylla-master/longevity/a-test", DESCRIPTION)]),
    ])
    fake = FakeJenkins(tree)
    monitor = make_monitor(fake, releases=[stored_release("scylla-master")])

    await monitor.collect()

    assert fake.job_info_calls == []


@pytest.mark.docker_required
async def test_update_writes_the_column_and_leaves_the_other_fields_alone(argus_db, fake_test):
    fake_test.assignee = []
    fake_test.enabled = False
    await fake_test.save()

    await fake_test.update(test_metadata={"tier": "tier1"})
    reloaded = await ArgusTest.get(id=fake_test.id)

    assert reloaded.test_metadata == {"tier": "tier1"}
    assert reloaded.enabled is False
    assert reloaded.name == fake_test.name


async def test_a_refetch_that_fails_does_not_stop_the_next_release():
    tree = release_tree("scylla-master", [folder("scylla-master/longevity", [{"_class": FOLDER_CLASS}])])
    tree.update(release_tree("scylla-enterprise", [
        folder("scylla-enterprise/longevity", [workflow_job("scylla-enterprise/longevity/a-test", DESCRIPTION)]),
    ]))
    fake = FakeJenkins(tree,
                       errors={"job/scylla-master/job/longevity": RequestsConnectionError("boom")},
                       releases=["scylla-master", "scylla-enterprise"])
    monitor = make_monitor(fake, releases=[
        stored_release("scylla-master"), stored_release("scylla-enterprise")])

    await monitor.collect()

    assert [t.build_system_id for t in monitor.created_tests] == ["scylla-enterprise/longevity/a-test"]


async def test_drops_a_job_that_never_exposes_a_url_instead_of_looping():
    tree = release_tree("scylla-master", [
        folder("scylla-master/longevity", [{"_class": FOLDER_CLASS}]),
    ])
    tree["job/scylla-master/job/longevity"] = {
        "_class": FOLDER_CLASS,
        "jobs": [{"_class": FOLDER_CLASS}, workflow_job("scylla-master/longevity/a-test", DESCRIPTION)],
    }
    fake = FakeJenkins(tree, releases=["scylla-master"])
    monitor = make_monitor(fake, releases=[stored_release("scylla-master")])

    await monitor.collect()

    assert len([item for item, _ in fake.info_calls if item == "job/scylla-master/job/longevity"]) == 1
    assert [t.build_system_id for t in monitor.created_tests] == ["scylla-master/longevity/a-test"]


async def test_a_group_write_failure_does_not_stop_the_next_release():
    tree = {}
    for name in ("scylla-master", "scylla-enterprise"):
        tree.update(release_tree(name, [
            folder(f"{name}/longevity", [workflow_job(f"{name}/longevity/a-test", DESCRIPTION)]),
        ]))
    monitor = make_monitor(FakeJenkins(tree, releases=["scylla-master", "scylla-enterprise"]),
                           releases=[stored_release("scylla-master"), stored_release("scylla-enterprise")])
    healthy_create_group = monitor.create_group
    failed = []

    async def create_group(release, *args, **kwargs):
        if release.name == "scylla-master":
            failed.append(release.name)
            raise RuntimeError("scylla write timeout")
        return await healthy_create_group(release, *args, **kwargs)

    monitor.create_group = create_group

    await monitor.collect()

    assert failed == ["scylla-master"]
    assert [t.build_system_id for t in monitor.created_tests] == ["scylla-enterprise/longevity/a-test"]
