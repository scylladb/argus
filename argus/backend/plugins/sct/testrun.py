from enum import Enum
import logging
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID

from cassandra.cqlengine import columns
from cassandra.cqlengine.models import _DoesNotExist, Model
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
    PerformanceHDRHistogram
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


class SubtestType(str, Enum):
    GEMINI = "gemini"
    PERFORMANCE = "performance"


@dataclass(init=True, repr=True, frozen=True)
class SCTTestRunSubmissionRequest():
    schema_version: str
    run_id: str
    job_name: str
    job_url: str
    started_by: str
    commit_id: str
    sct_config: dict | None
    origin_url: Optional[str] = field(default=None)
    branch_name: Optional[str] = field(default=None)
    runner_public_ip: Optional[str] = field(default=None)
    runner_private_ip: Optional[str] = field(default=None)


class SCTTestRun(PluginModelBase):
    __table_name__ = "sct_test_run"
    _plugin_name = "scylla-cluster-tests"

    # Test Details
    test_name = columns.Text()
    stress_duration = columns.Float()
    scm_revision_id = columns.Text()
    branch_name = columns.Text()
    origin_url = columns.Text()
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

    # Subtest
    subtest_name = columns.Text()

    # Gemini-related fields
    oracle_nodes_count = columns.Integer()
    oracle_node_ami_id = columns.Text()
    oracle_node_instance_type = columns.Text()
    oracle_node_scylla_version = columns.Text()
    gemini_command = columns.Text()
    gemini_version = columns.Text()
    gemini_status = columns.Text()
    gemini_seed = columns.Text()
    gemini_write_ops = columns.Integer()
    gemini_write_errors = columns.Integer()
    gemini_read_ops = columns.Integer()
    gemini_read_errors = columns.Integer()

    # Performance fields
    perf_op_rate_average = columns.Double()
    perf_op_rate_total = columns.Double()
    perf_avg_latency_99th = columns.Double()
    perf_avg_latency_mean = columns.Double()
    perf_total_errors = columns.Double()
    stress_cmd = columns.Text()

    histograms = columns.List(value_type=columns.Map(key_type=columns.Text(), value_type=columns.UserDefinedType(user_type=PerformanceHDRHistogram)))

    @classmethod
    def _stats_query(cls) -> str:
        return ("SELECT id, test_id, group_id, release_id, status, start_time, build_job_url, build_id, "
                f"assignee, end_time, investigation_status, heartbeat, scylla_version FROM {cls.table_name()} WHERE build_id IN ? PER PARTITION LIMIT 15")

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
    def get_perf_results_for_test_name(cls, build_id: str, start_time: float, test_name: str):
        cluster = ScyllaCluster.get()
        query = cluster.prepare(f"SELECT build_id, packages, scylla_version, test_name, perf_op_rate_average, perf_op_rate_total, "
                                "perf_avg_latency_99th, perf_avg_latency_mean, perf_total_errors, id, start_time, build_job_url"
                                f" FROM {cls.table_name()} WHERE build_id = ? AND start_time < ? AND test_name = ? ALLOW FILTERING")
        rows = cluster.session.execute(query=query, parameters=(build_id, start_time, test_name))

        return list(rows)

    @classmethod
    def init_sct_run(cls, req: SCTTestRunSubmissionRequest):
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
        if req.origin_url:
            run.origin_url = req.origin_url
            run.branch_name = req.branch_name
        run.started_by = req.started_by
        run.build_job_url = req.job_url

        return run

    @classmethod
    def from_sct_config(cls, req: SCTTestRunSubmissionRequest):
        try:
            run = cls.get(id=req.run_id)
        except cls.DoesNotExist:
            run = cls.init_sct_run(req)
            run.save()

        if req.sct_config:
            backend = req.sct_config.get("cluster_backend")
            if duration_override := req.sct_config.get("stress_duration"):
                run.stress_duration = float(duration_override)
            region_key = SCT_REGION_PROPERTY_MAP.get(backend, SCT_REGION_PROPERTY_MAP["default"])
            raw_regions = req.sct_config.get(region_key) or "undefined_region"
            regions = raw_regions.split() if isinstance(raw_regions, str) else raw_regions
            primary_region = regions[0]
            if req.runner_public_ip:  # NOTE: Legacy support, not needed otherwise
                run.sct_runner_host = CloudInstanceDetails(
                    public_ip=req.runner_public_ip,
                    private_ip=req.runner_private_ip,
                    provider=backend,
                    region=primary_region,
                )
            run.cloud_setup = ResourceSetup.get_resource_setup(backend=backend, sct_config=req.sct_config)

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

    def finish_run(self, payload: dict = None):
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


class SCTJunitReports(Model):
    test_id = columns.UUID(primary_key=True, partition_key=True, required=True)
    file_name = columns.Text(primary_key=True, required=True)
    report = columns.Text(required=True)
