import logging
from datetime import datetime
from dataclasses import dataclass
from uuid import UUID

from cassandra.cqlengine import columns
from cassandra.cqlengine.models import _DoesNotExist
from argus.backend.db import ScyllaCluster
from argus.backend.models.web import ArgusRelease
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
    __table_name__ = "sct_test_run"
    _plugin_name = "scylla-cluster-tests"

    # Test Details
    scm_revision_id = columns.Text()
    started_by = columns.Text()
    config_files = columns.List(value_type=columns.Text())
    packages = columns.List(value_type=columns.UserDefinedType(user_type=PackageVersion))
    scylla_version = columns.Text()
    yaml_test_duration = columns.Integer()

    # Test Preset Resources
    sct_runner_host = columns.UserDefinedType(user_type=CloudInstanceDetails)
    region_name = columns.List(value_type=columns.Text())
    cloud_setup = columns.UserDefinedType(user_type=CloudSetupDetails)

    # Test Runtime Resources
    allocated_resources = columns.List(value_type=columns.UserDefinedType(user_type=CloudResource))

    # Test Results
    events = columns.List(value_type=columns.UserDefinedType(user_type=EventsBySeverity))
    nemesis_data = columns.List(value_type=columns.UserDefinedType(user_type=NemesisRunInfo))
    screenshots = columns.List(value_type=columns.Text())

    @classmethod
    def _stats_query(cls) -> str:
        return ("SELECT id, test_id, group_id, release_id, status, start_time, build_job_url, build_id, "
                f"assignee, end_time, investigation_status, heartbeat, scylla_version FROM {cls.table_name()} WHERE release_id = ?")

    @classmethod
    def load_test_run(cls, run_id: UUID) -> 'SCTTestRun':
        return cls.get(id=run_id)

    @classmethod
    def submit_run(cls, request_data: dict) -> 'SCTTestRun':
        req = SCTTestRunSubmissionRequest(**request_data)
        return cls.from_sct_config(req=req)

    @classmethod
    def get_distinct_product_versions(cls, release: ArgusRelease) -> list[str]:
        cluster = ScyllaCluster.get()
        statement = cluster.prepare(f"SELECT scylla_version FROM {cls.table_name()} WHERE release_id = ?")
        rows = cluster.session.execute(query=statement, parameters=(release.id,))
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
        try:
            run.assignee = run.get_scheduled_assignee()
        except _DoesNotExist:
            run.assignee = None
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

    def submit_product_version(self, version: str):
        self.scylla_version = version

    def finish_run(self):
        self.end_time = datetime.utcnow()

    def submit_logs(self, logs: list[dict]):
        for log in logs:
            self.logs.append((log["log_name"], log["log_link"]))

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
