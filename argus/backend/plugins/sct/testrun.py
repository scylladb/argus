import logging
from datetime import datetime
from dataclasses import dataclass
from time import time
from uuid import UUID

from cassandra.cqlengine import columns
from argus.backend.db import ScyllaCluster
from argus.backend.models.web import (
    ArgusRelease,
    ArgusGroup,
    ArgusTest,
    ArgusSchedule,
    ArgusScheduleGroup,
    ArgusScheduleTest,
    ArgusScheduleAssignee,
)
from argus.backend.plugins.core import PluginModelBase
from argus.backend.plugins.sct.resource_setup import ResourceSetup
from argus.backend.plugins.sct.udt import (
    CloudInstanceDetails,
    CloudResource,
    CloudSetupDetails,
    EventsBySeverity,
    NemesisRunInfo,
    PackageVersion,
)
from argus.backend.util.enums import TestInvestigationStatus, TestStatus

LOGGER = logging.getLogger(__name__)
SCT_REGION_PROPERTY_MAP = {
    "aws": "region_name",
    "aws-siren": "region_name",
    "k8s-eks": "region_name",
    "gce": "gce_datacenter",
    "gce-siren": "gce_datacenter",
    "k8s-gke": "gce_datacenter",
    "azure": "azure_region_name",
    "default": "region_name",
}


@dataclass(init=True, repr=True, frozen=True)
class SCTTestRunSubmissionRequest():
    schema_version: str
    run_id: str
    job_name: str
    job_url: str
    started_by: str
    commit_id: str
    runner_public_ip: str
    runner_private_ip: str
    sct_config: dict


class SCTTestRun(PluginModelBase):
    __table_name__ = "test_runs_v8"

    # Test Details
    scm_revision_id = columns.Text()
    started_by = columns.Text()
    build_job_url = columns.Text()
    config_files = columns.List(value_type=columns.Text())
    packages = columns.List(value_type=columns.UserDefinedType(user_type=PackageVersion))
    scylla_version = columns.Text()
    yaml_test_duration = columns.Integer()

    # Test Resources
    sct_runner_host = columns.UserDefinedType(user_type=CloudInstanceDetails)
    region_name = columns.List(value_type=columns.Text())
    cloud_setup = columns.UserDefinedType(user_type=CloudSetupDetails)

    # Test Resources
    allocated_resources = columns.List(value_type=columns.UserDefinedType(user_type=CloudResource))

    # Test Results
    events = columns.List(value_type=columns.UserDefinedType(user_type=EventsBySeverity))
    nemesis_data = columns.List(value_type=columns.UserDefinedType(user_type=NemesisRunInfo))
    screenshots = columns.List(value_type=columns.Text())

    @classmethod
    def table_name(cls) -> str:
        return cls.__table_name__

    @classmethod
    def load_test_run(cls, run_id: UUID) -> 'SCTTestRun':
        return cls.get(id=run_id)

    @classmethod
    def submit_run(cls, request_data: dict) -> 'SCTTestRun':
        req = SCTTestRunSubmissionRequest(**request_data)
        return cls.from_sct_config(req=req)

    @classmethod
    def get_distinct_product_versions(cls, cluster: ScyllaCluster, release_id: UUID) -> list[str]:
        statement = cluster.prepare(f"SELECT scylla_version FROM {cls.table_name()} WHERE release_id = ?")
        rows = cluster.session.execute(query=statement, parameters=(release_id,))
        unique_versions = {r["scylla_version"] for r in rows if r["scylla_version"]}

        return sorted(list(unique_versions), reverse=True)

    @classmethod
    def get_version_data_for_release(cls, release_name: str):
        cluster = ScyllaCluster.get()
        release = ArgusRelease.get(name=release_name)
        query = cluster.prepare(f"SELECT scylla_version, packages, status FROM {cls.table_name()} WHERE release_id = ?")
        rows = cluster.session.execute(query=query, parameters=(release.id,))

        return list(rows)

    @classmethod
    def from_sct_config(cls, req: SCTTestRunSubmissionRequest):
        run = cls()
        run.build_id = req.job_name
        run.assign_categories()
        run.assignee = run.get_scheduled_assignee()
        run.start_time = datetime.utcnow()
        run.id = UUID(req.run_id)  # pylint: disable=invalid-name
        run.scm_revision_id = req.commit_id
        run.started_by = req.started_by
        run.build_job_url = req.job_url

        backend = req.sct_config.get("cluster_backend")
        region_key = SCT_REGION_PROPERTY_MAP.get(backend, SCT_REGION_PROPERTY_MAP["default"])
        raw_regions = req.sct_config.get(region_key) or "undefined_region"
        regions = raw_regions.split() if isinstance(raw_regions, str) else raw_regions
        primary_region = regions[0]

        run.cloud_setup = ResourceSetup.get_resource_setup(backend=backend, sct_config=req.sct_config)

        run.sct_runner_host = CloudInstanceDetails(
            public_ip=req.runner_public_ip,
            private_ip=req.runner_private_ip,
            provider=backend,
            region=primary_region,
        )

        run.config_files = req.sct_config.get("config_files")
        run.region_name = regions
        run.save()
        return run

    def get_resources(self) -> list[CloudResource]:
        return self.allocated_resources

    def get_nemeses(self) -> list[NemesisRunInfo]:
        return self.nemesis_data

    def get_events(self) -> list[EventsBySeverity]:
        return self.events

    def update_heartbeat(self):
        self.heartbeat = int(time())

    def change_status(self, new_status: TestStatus):
        self.status = new_status.value

    def change_investigation_status(self, new_investigation_status: TestInvestigationStatus):
        self.investigation_status = new_investigation_status.value

    def submit_product_version(self, version: str):
        self.scylla_version = version

    def finish_run(self):
        self.end_time = datetime.utcnow()

    def submit_logs(self, logs: list[dict]):
        for log in logs:
            self.logs.append((log["name"], log["link"]))

    def assign_categories(self):
        key = self.build_id
        try:
            test: ArgusTest = ArgusTest.get(build_system_id=key)
            self.release_id = test.release_id
            self.group_id = test.group_id
            self.test_id = test.id
        except ArgusTest.DoesNotExist:
            LOGGER.warning("Test entity missing for key \"%s\", run won't be visible until this is corrected", key)

    def get_scheduled_assignee(self) -> UUID:
        """
            Iterate over all schedules (groups and tests) and return first available assignee
        """
        associated_test = ArgusTest.get(build_system_id=self.build_id)
        associated_group = ArgusGroup.get(id=associated_test.group_id)
        associated_release = ArgusRelease.get(id=associated_test.release_id)

        scheduled_groups = ArgusScheduleGroup.filter(
            release_id=associated_release.id,
            group_id=associated_group.id,
        ).all()

        scheduled_tests = ArgusScheduleTest.filter(
            release_id=associated_release.id,
            test_id=associated_test.id
        ).all()

        unique_schedule_ids = {scheduled_obj.schedule_id for scheduled_obj in [
            *scheduled_tests, *scheduled_groups]}

        schedules = ArgusSchedule.filter(
            release_id=associated_release.id,
            id__in=tuple(unique_schedule_ids),
        ).all()

        today = datetime.utcnow()

        valid_schedules = []
        for schedule in schedules:
            if schedule.period_start <= today <= schedule.period_end:
                valid_schedules.append(schedule)

        assignees_uuids = []
        for schedule in valid_schedules:
            assignees = ArgusScheduleAssignee.filter(
                schedule_id=schedule.id
            ).all()
            assignees_uuids.append(*[assignee.assignee for assignee in assignees])

        return assignees_uuids[0] if len(assignees_uuids) > 0 else None

    def add_screenshot(self, screenshot_link: str):
        self.screenshots.append(screenshot_link)

    def add_nemesis(self, nemesis: NemesisRunInfo):
        self.nemesis_data.append(nemesis)

    def _add_new_event_type(self, event: EventsBySeverity):
        self.events.append(event)

    def _collect_event_message(self, event: EventsBySeverity, message: str):
        if len(event.last_events) >= 100:
            event.last_events = event.last_events[1:]

        event.event_amount += 1
        event.last_events.append(message)

    def add_event(self, event_severity: str, event_message: str):
        try:
            event = next(filter(lambda v: v.severity ==
                         event_severity, self.events))
        except StopIteration:
            event = EventsBySeverity(
                severity=event_severity, event_amount=0, last_events=[])
            self._add_new_event_type(event)

        self._collect_event_message(event, event_message)
