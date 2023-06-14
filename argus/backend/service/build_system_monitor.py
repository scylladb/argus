import logging
from abc import ABC, abstractmethod
import jenkins
import click
from flask import current_app
from flask.cli import with_appcontext

from argus.backend.db import ScyllaCluster
from argus.backend.models.web import ArgusRelease, ArgusGroup, ArgusTest
from argus.backend.service.release_manager import ReleaseManagerService

LOGGER = logging.getLogger(__name__)


class ArgusTestsMonitor(ABC):
    def __init__(self) -> None:
        self._cluster = ScyllaCluster.get()
        self._existing_releases = list(ArgusRelease.all())
        self._existing_groups = list(ArgusGroup.all())
        self._existing_tests = list(ArgusTest.all())
        self._filtered_groups: list[str] = current_app.config["BUILD_SYSTEM_FILTERED_PREFIXES"]

    def create_release(self, release_name):
        # pylint: disable=no-self-use
        release = ArgusRelease()
        release.name = release_name
        release.save()

        return release

    def create_group(self, release: ArgusRelease, group_name: str, build_id: str, group_pretty_name: str | None = None):
        # pylint: disable=no-self-use
        group = ArgusGroup()
        group.release_id = release.id
        group.name = group_name
        group.build_system_id = build_id
        if group_pretty_name:
            group.pretty_name = group_pretty_name
        group.save()

        return group

    def create_test(self, release: ArgusRelease, group: ArgusGroup,
                    test_name: str, build_id: str, build_url: str) -> ArgusTest:
        # pylint: disable=no-self-use
        test = ArgusTest()
        test.name = test_name
        test.group_id = group.id
        test.release_id = release.id
        test.build_system_id = build_id
        test.build_system_url = build_url
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
    def __init__(self) -> None:
        super().__init__()
        self._jenkins = jenkins.Jenkins(url=current_app.config["JENKINS_URL"],
                                        username=current_app.config["JENKINS_USER"],
                                        password=current_app.config["JENKINS_API_TOKEN"])
        self._monitored_releases = current_app.config["JENKINS_MONITORED_RELEASES"]

    def collect(self):
        click.echo("Collecting new tests from jenkins")
        all_jobs = self._jenkins.get_all_jobs()
        all_monitored_folders = [job for job in all_jobs if job["fullname"] in self._monitored_releases]
        for release in all_monitored_folders:
            LOGGER.info("Processing release %s", release["name"])
            try:
                saved_release = ArgusRelease.get(name=release["name"])
                LOGGER.info("Release %s exists", release["name"])
            except ArgusRelease.DoesNotExist:
                LOGGER.warning("Release %s does not exist, creating...", release["name"])
                saved_release = self.create_release(release["name"])
                self._existing_releases.append(saved_release)

            try:
                groups = self.collect_groups_for_release(release["jobs"])
            except KeyError:
                LOGGER.error("Empty release!\n %s", release)
                continue
            folder_stack = [dict(parent_name="", parent_display_name="", group=g) for g in reversed(groups)]
            root_folder = {
                "parent_name": "",
                "parent_display_name": "",
                "group":  {
                    "name": f"{release['fullname']}-root",
                    "displayName": "-- root directory --",
                    "fullname": release["fullname"],
                    "jobs": self.collect_root_folder_jobs(release["jobs"]),
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
                    LOGGER.warning(
                        "Group %s for release %s doesn't exist, creating...", group_name, saved_release.name)
                    try:
                        display_name = group.get("displayName", self._jenkins.get_job_info(name=group["fullname"])["displayName"])
                        display_name = display_name if not group_dict[
                            "parent_display_name"] else f"{group_dict['parent_display_name']} - {display_name}"
                    except Exception:
                        display_name = None

                    saved_group = self.create_group(saved_release, group_name, group["fullname"], display_name)
                    self._existing_groups.append(saved_group)

                for job in group["jobs"]:
                    LOGGER.info("Processing job %s for release %s and group %s",
                                job["fullname"], saved_group.name, saved_release.name)
                    saved_test = None
                    if "Folder" in job["_class"]:
                        folder_stack.append(dict(parent_name=saved_group.name,
                                            parent_display_name=saved_group.pretty_name, group=job))
                    if "WorkflowJob" in job["_class"]:
                        try:
                            saved_test = filter(lambda t: t.build_system_id == job["fullname"], self._existing_tests)
                            saved_test = next(saved_test)
                            LOGGER.info("Test %s already exists. (id: %s)", saved_test.build_system_id, saved_test.id)
                        except StopIteration:
                            LOGGER.warning("Test %s for release %s (group %s) doesn't exist, creating...",
                                           job["name"], saved_release.name, saved_group.name)
                            saved_test = self.create_test(
                                saved_release, saved_group, job["name"], job["fullname"], job["url"])
                            self._existing_tests.append(saved_test)

    def collect_groups_for_release(self, jobs):
        # pylint: disable=no-self-use
        groups = [folder for folder in jobs if "Folder" in folder["_class"]]
        groups = [group for group in groups if self.check_filter(group["name"])]

        return groups

    def collect_root_folder_jobs(self, jobs):
        return [job for job in jobs if "WorkflowJob" in job["_class"]]
