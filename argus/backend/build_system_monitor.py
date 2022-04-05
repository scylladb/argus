import logging
from abc import ABC, abstractmethod
import jenkins
import click
from flask import current_app
from flask.cli import with_appcontext

from argus.backend.db import ScyllaCluster
from argus.db.models import ArgusRelease, ArgusReleaseGroup, ArgusReleaseGroupTest
from argus.backend.service.release_manager import ReleaseManagerService

LOGGER = logging.getLogger(__name__)


class ArgusTestsMonitor(ABC):
    def __init__(self) -> None:
        self._cluster = ScyllaCluster.get()
        self._existing_releases = list(ArgusRelease.all())
        self._existing_groups = list(ArgusReleaseGroup.all())
        self._existing_tests = list(ArgusReleaseGroupTest.all())
        self._filtered_groups: list[str] = current_app.config["BUILD_SYSTEM_FILTERED_PREFIXES"]

    def create_release(self, release_name):
        # pylint: disable=no-self-use
        release = ArgusRelease()
        release.name = release_name
        release.save()

        return release

    def create_group(self, release: ArgusRelease, group_name: str, group_pretty_name: str | None = None):
        # pylint: disable=no-self-use
        group = ArgusReleaseGroup()
        group.release_id = release.id
        group.name = group_name.rstrip("-")
        if group_pretty_name:
            group.pretty_name = group_pretty_name
        group.save()

        return group

    def create_test(self, release: ArgusRelease, group: ArgusReleaseGroup,
                    test_name: str, build_id: str, build_url: str) -> ArgusReleaseGroupTest:
        # pylint: disable=no-self-use
        test = ArgusReleaseGroupTest()
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
        all_jobs = self._jenkins.get_all_jobs(folder_depth=4)
        all_monitored_folders = [
            job for job in all_jobs if job["name"] in self._monitored_releases]
        for release in all_monitored_folders:
            LOGGER.info("Processing release %s", release["name"])
            try:
                saved_release = ArgusRelease.get(name=release["name"])
            except ArgusRelease.DoesNotExist:
                LOGGER.warning(
                    "Release %s does not exist, creating...", release["name"])
                saved_release = self.create_release(release["name"])
                self._existing_releases.append(saved_release)

            groups = self.collect_groups_for_release(release["jobs"])
            for group in groups:
                LOGGER.info("Processing group %s for release %s",
                            group["name"], saved_release.name)
                try:
                    group_name = group["name"].rstrip("-")
                    saved_groups = [g for g in self._existing_groups if g.release_id ==
                                    saved_release.id and g.name == group_name]
                    saved_group = saved_groups[0]
                except IndexError:
                    LOGGER.warning(
                        "Group %s for release %s doesn't exist, creating...", group_name, saved_release.name)
                    try:
                        display_name = self._jenkins.get_job_info(name=group["fullname"])["displayName"]
                    except Exception:
                        display_name = None
                    saved_group = self.create_group(saved_release, group_name, display_name)
                    self._existing_groups.append(saved_group)
                tests = self.collect_tests_from_group(group)
                for test in tests:
                    LOGGER.info("Processing test %s for release %s and group %s",
                                test["name"], saved_group.name, saved_release.name)
                    saved_test = None
                    for t in self._existing_tests:  # pylint: disable=invalid-name
                        if t.build_system_id == test["fullname"]:
                            saved_test = t
                            break
                    if not saved_test:
                        LOGGER.warning("Test %s for release %s (group %s) doesn't exist, creating...",
                                       test["name"], saved_release.name, saved_group.name)
                        saved_test = self.create_test(
                            saved_release, saved_group, test["name"], test["fullname"], test["url"])
                        self._existing_tests.append(saved_test)

    def collect_groups_for_release(self, jobs):
        # pylint: disable=no-self-use
        groups = [folder for folder in jobs if "Folder" in folder["_class"]]
        groups = [group for group in groups if self.check_filter(group["name"])]

        return groups

    def collect_tests_from_group(self, group):
        # pylint: disable=no-self-use
        tests = [test for test in group["jobs"]
                 if "WorkflowJob" in test["_class"]]
        return tests


@click.command('scan-jenkins')
@with_appcontext
def scan_jenkins_command():
    monitor = JenkinsMonitor()
    monitor.collect()
    click.echo("Done.")
