import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
import jenkins
import click
import re

from argus.backend.db import ScyllaCluster
from argus.backend.util.common import first
from argus.backend.util.config import Config
from argus.backend.models.web import ArgusRelease, ArgusGroup, ArgusTest, ArgusTestException
from argus.backend.service.release_manager import ReleaseManagerService
from argus.backend.service.test_metadata import apply_test_metadata, parse_test_metadata

LOGGER = logging.getLogger(__name__)


class ArgusTestsMonitor(ABC):
    BUILD_SYSTEM_FILTERED_PREFIXES = [

    ]

    PROGRESS_INTERVAL = 0.1

    def __init__(self) -> None:
        self._cluster = ScyllaCluster.get()
        self._existing_releases = list(ArgusRelease.find())
        self._existing_groups = list(ArgusGroup.find())
        self._existing_tests = list(ArgusTest.find())
        self._filtered_groups: list[str] = self.BUILD_SYSTEM_FILTERED_PREFIXES
        self.init_progress()

    def init_progress(self) -> None:
        self._last_progress = 0.0
        self.stats = {
            "release": "",
            "releases": 0,
            "releases_total": 0,
            "jobs": 0,
            "groups_created": 0,
            "tests_created": 0,
            "tests_updated": 0,
        }
        self.on_progress: Callable[[dict], None] = lambda stats: None

    def report_progress(self, force: bool = False) -> None:
        now = time.monotonic()
        if force or now - self._last_progress >= self.PROGRESS_INTERVAL:
            self._last_progress = now
            self.on_progress(self.stats)

    def create_release(self, release_name: str):
        release = ArgusRelease.model_construct()
        release.name = release_name
        release.save()

        return release

    def create_group(self, release: ArgusRelease, group_name: str, build_id: str, group_pretty_name: str | None = None):
        group = ArgusGroup.model_construct()
        group.release_id = release.id
        group.name = group_name
        group.build_system_id = build_id
        if group_pretty_name:
            group.pretty_name = group_pretty_name
        group.save()

        return group

    def create_test(self, release: ArgusRelease, group: ArgusGroup,
                    test_name: str, build_id: str, build_url: str,
                    test_metadata: dict[str, str] | None = None) -> ArgusTest:
        test = ArgusTest.model_construct()
        test.name = test_name
        test.group_id = group.id
        test.release_id = release.id
        test.build_system_id = build_id
        test.build_system_url = build_url
        test.test_metadata = test_metadata or {}
        test.validate_build_system_id()
        test.save()
        ReleaseManagerService().move_test_runs(test)

        return test

    @abstractmethod
    def collect(self):
        raise NotImplementedError()

    def check_filter(self, group_name: str) -> bool:
        for prefix in self._filtered_groups:
            if prefix.lower() in group_name.lower():
                return False

        return True


class JenkinsMonitor(ArgusTestsMonitor):

    BUILD_SYSTEM_FILTERED_PREFIXES = [
        "releng",
    ]

    JENKINS_MONITORED_RELEASES = [
        r"^scylla-master$",
        r"^drivers$",
        r"^scylla-\d+\.\d+/releng-testing$",
        r"^enterprise-20\d{2}\.\d+/releng-testing$",
        r"^scylla-staging$",
        r"^scylla-\d+\.\d+$",
        r"^manager-3.\d+$",
        r"^scylla-operator/operator-master$",
        r"^scylla-operator/operator-\d+.\d+$",
        r"^scylla-enterprise$",
        r"^enterprise-20\d{2}\.\d+$",
        r"^siren-tests$",
        r"^releng-testing$",
        r"^sct-github-PRs-scan$",
    ]

    JOB_TREE_FIELDS = "fullName,displayName,description,url,name"
    JOB_TREE_DEPTH = 9
    JENKINS_TIMEOUT = 60
    DISCOVERY_FOLDER_DEPTH = 1
    DISCOVERY_FOLDER_DEPTH_PER_REQUEST = 2

    def __init__(self) -> None:
        super().__init__()
        config = Config.load_yaml_config()
        self._jenkins = jenkins.Jenkins(url=config["JENKINS_URL"],
                                        username=config["JENKINS_USER"],
                                        password=config["JENKINS_API_TOKEN"],
                                        timeout=self.JENKINS_TIMEOUT)
        self._monitored_releases = self.JENKINS_MONITORED_RELEASES

    def _check_release_name(self, release_name: str):
        return any(re.match(pattern, release_name, re.IGNORECASE) for pattern in self._monitored_releases)

    def _jobs_query(self) -> str:
        tree = "jobs"
        for _ in range(self.JOB_TREE_DEPTH):
            tree = f"jobs[{self.JOB_TREE_FIELDS},{tree}]"

        return f"?tree={tree}"

    def _fetch_release_info(self, release_name: str) -> dict:
        item = "/".join(f"job/{segment}" for segment in release_name.split("/"))

        return self._jenkins.get_info(item=item, query=self._jobs_query())

    def _normalize_jobs(self, jobs: list[dict], path: list[str], refetched: set[str] | None = None) -> list[dict]:
        refetched = set() if refetched is None else refetched
        normalized = []
        for job in jobs:
            if "url" not in job:
                folder = "/".join(path)
                if folder in refetched:
                    LOGGER.error("Job below %s still carries no url after a refetch, dropping it: %s", folder, job)
                    continue
                refetched.add(folder)
                LOGGER.warning("Job tree below %s is deeper than %s levels, fetching it again",
                               folder, self.JOB_TREE_DEPTH)
                return self._normalize_jobs(self._fetch_release_info(folder)["jobs"], path, refetched)
            job["fullname"] = job.get("fullName") or "/".join([*path, job["name"]])
            if isinstance(job.get("jobs"), list):
                job["jobs"] = self._normalize_jobs(job["jobs"], [*path, job["name"]], refetched)
            normalized.append(job)

        return normalized

    def _refresh_test_metadata(self, test: ArgusTest, job: dict) -> None:
        try:
            if apply_test_metadata(test, job.get("description")):
                test.update(test_metadata=test.test_metadata)
                self.stats["tests_updated"] += 1
                LOGGER.info("Refreshed the metadata of test %s", test.build_system_id)
        except Exception:
            LOGGER.error("Unable to refresh the metadata of test %s", job["fullname"], exc_info=True)

    def collect(self):
        click.echo("Collecting new tests from jenkins")
        all_jobs = self._jenkins.get_all_jobs(folder_depth=self.DISCOVERY_FOLDER_DEPTH,
                                              folder_depth_per_request=self.DISCOVERY_FOLDER_DEPTH_PER_REQUEST)
        all_monitored_folders = [job for job in all_jobs if self._check_release_name(job["fullname"])]
        LOGGER.info("Will collect %s", [f["fullname"] for f in all_monitored_folders])
        self.stats["releases_total"] = len(all_monitored_folders)

        for release in all_monitored_folders:
            LOGGER.info("Processing release %s", release["fullname"])
            self.stats["release"] = release["fullname"]
            self.stats["releases"] += 1
            self.report_progress(force=True)
            saved_release = first(self._existing_releases, release["fullname"], key=lambda r: r.name)
            if saved_release:
                LOGGER.info("Release %s exists", release["fullname"])
            else:
                LOGGER.info("Release %s does not exist, creating...", release["fullname"])
                saved_release = self.create_release(release["fullname"])
                self._existing_releases.append(saved_release)

            if saved_release.dormant:
                LOGGER.info("Release %s is dormant, skipping", saved_release.name)
                continue

            started_at = time.monotonic()
            try:
                release_info = self._fetch_release_info(release["fullname"])
            except Exception:
                LOGGER.error("Unable to fetch the job tree of release %s, skipping",
                             release["fullname"], exc_info=True)
                continue
            LOGGER.info("Fetched the job tree of release %s in %.2fs",
                        release["fullname"], time.monotonic() - started_at)

            try:
                jobs = self._normalize_jobs(release_info["jobs"], release["fullname"].split("/"))
                groups = self.collect_groups_for_release(jobs)
            except KeyError:
                LOGGER.error("Empty release!\n %s", release)
                continue
            except Exception:
                LOGGER.error("Unable to read the job tree of release %s, skipping",
                             release["fullname"], exc_info=True)
                continue
            folder_stack = [dict(parent_name="", parent_display_name="", group=g) for g in reversed(groups)]
            root_folder = {
                "parent_name": "",
                "parent_display_name": "",
                "group":  {
                    "name": f"{release['fullname']}-root",
                    "displayName": "-- root directory --",
                    "fullname": release["fullname"],
                    "jobs": self.collect_root_folder_jobs(jobs),
                }
            }
            folder_stack.append(root_folder)
            while len(folder_stack) != 0:
                group_dict = folder_stack.pop()
                group = group_dict["group"]
                LOGGER.info("Processing group %s for release %s", group["name"], saved_release.name)
                try:
                    group_name = group["name"] if not group_dict["parent_name"] else f"{group_dict['parent_name']}-{group['name']}"
                    saved_group = filter(lambda g: g.build_system_id == group["fullname"], self._existing_groups)
                    saved_group = next(saved_group)
                    LOGGER.info("Group %s already exists. (id: %s)", saved_group.build_system_id, saved_group.id)
                except StopIteration:
                    LOGGER.info(
                        "Group %s for release %s doesn't exist, creating...", group_name, saved_release.name)
                    try:
                        display_name = group.get("displayName") or self._jenkins.get_job_info(
                            name=group["fullname"])["displayName"]
                        display_name = display_name if not group_dict[
                            "parent_display_name"] else f"{group_dict['parent_display_name']} - {display_name}"
                    except Exception:
                        display_name = None

                    saved_group = self.create_group(saved_release, group_name, group["fullname"], display_name)
                    self._existing_groups.append(saved_group)
                    self.stats["groups_created"] += 1

                for job in group["jobs"]:
                    LOGGER.info("Processing job %s for release %s and group %s",
                                job["fullname"], saved_group.name, saved_release.name)
                    saved_test = None
                    self.stats["jobs"] += 1
                    self.report_progress()
                    if "Folder" in job["_class"]:
                        folder_stack.append(dict(parent_name=saved_group.name,
                                            parent_display_name=saved_group.pretty_name, group=job))
                    if "WorkflowJob" in job["_class"]:
                        saved_test = first(self._existing_tests, job["fullname"], key=lambda t: t.build_system_id)
                        if saved_test:
                            LOGGER.info("Test %s already exists. (id: %s)", saved_test.build_system_id, saved_test.id)
                            self._refresh_test_metadata(saved_test, job)
                        else:
                            LOGGER.info("Test %s for release %s (group %s) doesn't exist, creating...",
                                        job["name"], saved_release.name, saved_group.name)
                            try:
                                saved_test = self.create_test(
                                    saved_release, saved_group, job["name"], job["fullname"], job["url"],
                                    test_metadata=parse_test_metadata(job.get("description")))
                                self._existing_tests.append(saved_test)
                                self.stats["tests_created"] += 1
                            except ArgusTestException:
                                LOGGER.error("Unable to create test for build_id %s", job["fullname"], exc_info=True)

    def collect_groups_for_release(self, jobs):
        groups = [folder for folder in jobs if "Folder" in folder["_class"] or "WorkflowMultiBranchProject" in folder["_class"]]
        groups = [group for group in groups if self.check_filter(group["name"])]

        return groups

    def collect_root_folder_jobs(self, jobs):
        return [job for job in jobs if "WorkflowJob" in job["_class"]]
