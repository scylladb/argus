import base64
from dataclasses import dataclass
from functools import reduce
import logging
import math
import re
from time import time
from xml.etree import ElementTree
from flask import g
from argus.backend.models.web import ArgusEventTypes
from argus.backend.plugins.sct.testrun import SCTJunitReports, SCTTestRun, SubtestType
from argus.backend.plugins.sct.types import GeminiResultsRequest, PerformanceResultsRequest, ResourceUpdateRequest
from argus.backend.plugins.sct.udt import (
    CloudInstanceDetails,
    CloudResource,
    EventsBySeverity,
    NemesisRunInfo,
    NodeDescription,
    PackageVersion,
    PerformanceHDRHistogram,
)
from argus.backend.service.event_service import EventService
from argus.backend.util.common import get_build_number
from argus.backend.util.enums import NemesisStatus, ResourceState, TestStatus

LOGGER = logging.getLogger(__name__)


class SCTServiceException(Exception):
    pass


@dataclass(init=True, repr=True)
class NemesisSubmissionRequest:
    name: str
    class_name: str
    start_time: int
    node_name: str
    node_ip: str
    node_shards: int


@dataclass(init=True, repr=True)
class NemesisFinalizationRequest:
    name: str
    start_time: int
    status: str
    message: str


@dataclass(init=True, repr=True)
class EventSubmissionRequest:
    severity: str
    total_events: int
    messages: list[str]


class SCTService:

    @staticmethod
    def submit_packages(run_id: str, packages: list[dict]) -> str:
        try:
            run: SCTTestRun = SCTTestRun.get(id=run_id)
            for package_dict in packages:
                package = PackageVersion(**package_dict)
                if package not in run.packages:
                    run.packages.append(package)
            run.save()
        except SCTTestRun.DoesNotExist as exception:
            LOGGER.error("Run %s not found for SCTTestRun", run_id)
            raise SCTServiceException("Run not found", run_id) from exception

        return "added"


    @staticmethod
    def set_sct_runner(run_id: str, public_ip: str, private_ip: str, region: str, backend: str):
        try:
            run: SCTTestRun = SCTTestRun.get(id=run_id)
            run.sct_runner_host = CloudInstanceDetails(
                public_ip=public_ip,
                private_ip=private_ip,
                provider=backend,
                region=region,
            )
            run.save()
        except SCTTestRun.DoesNotExist as exception:
            LOGGER.error("Run %s not found for SCTTestRun", run_id)
            raise SCTServiceException("Run not found", run_id) from exception

        return "updated"

    @staticmethod
    def submit_screenshots(run_id: str, screenshot_links: list[str]) -> str:
        try:
            run: SCTTestRun = SCTTestRun.get(id=run_id)
            for link in screenshot_links:
                run.add_screenshot(link)
            run.save()
        except SCTTestRun.DoesNotExist as exception:
            LOGGER.error("Run %s not found for SCTTestRun", run_id)
            raise SCTServiceException("Run not found", run_id) from exception

        return "submitted"

    @staticmethod
    def submit_gemini_results(run_id: str, gemini_data: GeminiResultsRequest) -> str:
        try:
            run: SCTTestRun = SCTTestRun.get(id=run_id)
            run.subtest_name = SubtestType.GEMINI.value
            run.oracle_nodes_count = gemini_data.get("oracle_nodes_count")
            run.oracle_node_ami_id = gemini_data.get("oracle_node_ami_id")
            run.oracle_node_instance_type = gemini_data.get("oracle_node_instance_type")
            run.oracle_node_scylla_version = gemini_data.get("oracle_node_scylla_version")
            run.gemini_command = gemini_data.get("gemini_command")
            run.gemini_version = gemini_data.get("gemini_version")
            run.gemini_status = gemini_data.get("gemini_status")
            run.gemini_seed = str(gemini_data.get("gemini_seed"))
            run.gemini_write_ops = gemini_data.get("gemini_write_ops")
            run.gemini_write_errors = gemini_data.get("gemini_write_errors")
            run.gemini_read_ops = gemini_data.get("gemini_read_ops")
            run.gemini_read_errors = gemini_data.get("gemini_read_errors")
            run.save()

            if run.gemini_status != "PASSED":
                run.status = TestStatus.FAILED
                EventService.create_run_event(kind=ArgusEventTypes.TestRunStatusChanged, body={
                        "message": "[{username}] Setting run status to {status} due to Gemini reporting following status: {gemini_status}",
                        "username": g.user.username,
                        "status": TestStatus.FAILED.value,
                        "gemini_status": run.gemini_status,
                }, user_id=g.user.id, run_id=run_id, release_id=run.release_id, test_id=run.test_id)
                run.save()
        except SCTTestRun.DoesNotExist as exception:
            LOGGER.error("Run %s not found for SCTTestRun", run_id)
            raise SCTServiceException("Run not found", run_id) from exception

        return "submitted"

    @staticmethod
    def submit_performance_results(run_id: str, performance_results: PerformanceResultsRequest):
        # pylint: disable=too-many-statements
        try:
            run: SCTTestRun = SCTTestRun.get(id=run_id)
            run.subtest_name = SubtestType.PERFORMANCE.value
            run.perf_op_rate_average = performance_results.get("perf_op_rate_average")
            run.perf_op_rate_total = performance_results.get("perf_op_rate_total")
            run.perf_avg_latency_99th = performance_results.get("perf_avg_latency_99th")
            run.perf_avg_latency_mean = performance_results.get("perf_avg_latency_mean")
            run.perf_total_errors = performance_results.get("perf_total_errors")
            run.stress_cmd = performance_results.get("stress_cmd")
            run.test_name = performance_results.get("test_name")
            run.save()

            is_latency_test = "latency" in run.test_name
            threshold_negative = -10

            def cmp(lhs, rhs):
                delta = rhs - lhs
                change = int(math.fabs(delta) * 100 / rhs)
                return change if delta >= 0 else change * -1

            previous_runs = SCTTestRun.get_perf_results_for_test_name(run.build_id, run.start_time, run.test_name)
            metrics_to_check = ["perf_avg_latency_99th", "perf_avg_latency_mean"] if is_latency_test else ["perf_op_rate_total"]

            older_runs_by_version = {}
            for prev_run in previous_runs:
                if not older_runs_by_version.get(prev_run["scylla_version"]):
                    older_runs_by_version[prev_run["scylla_version"]] = []
                older_runs_by_version[prev_run["scylla_version"]].append(prev_run)

            regression_found = False
            regression_info = {
                "version": None,
                "delta": None,
                "id": None,
                "metric": None,
                "job_url": None,
            }

            if performance_results["histograms"]:
                for histogram in performance_results["histograms"]:
                    run.histograms = { k: PerformanceHDRHistogram(**v) for k, v in histogram.items() }

            for version, runs in older_runs_by_version.items():
                for metric in metrics_to_check:
                    # pylint: disable=cell-var-from-loop
                    best_run = sorted(runs, reverse=(not is_latency_test), key=lambda v: v[metric])[0]
                    last_run = runs[0]

                    metric_to_best = cmp(run[metric], best_run[metric])
                    metric_to_last = cmp(run[metric], last_run[metric])
                    if metric_to_last < threshold_negative:
                        regression_found = True
                        regression_info["metric"] = metric
                        regression_info["version"] = version
                        regression_info["job_url"] = last_run["build_job_url"]
                        regression_info["id"] = str(last_run["id"])
                        regression_info["delta"] = metric_to_last
                        break

                    if metric_to_best < threshold_negative:
                        regression_found = True
                        regression_info["metric"] = metric
                        regression_info["version"] = version
                        regression_info["job_url"] = best_run["build_job_url"]
                        regression_info["id"] = str(best_run["id"])
                        regression_info["delta"] = metric_to_best
                        break

                if regression_found:
                    break

            if regression_found:
                run.status = TestStatus.FAILED.value
                run.save()
                EventService.create_run_event(kind=ArgusEventTypes.TestRunStatusChanged, body={
                        "message": "[{username}] Setting run status to {status} due to performance metric '{metric}' falling "
                                   "below allowed threshold ({threshold_negative}): {delta}% compared to "
                                   "<a href='/test/{test_id}/runs?additionalRuns[]={base_run_id}&additionalRuns[]={previous_run_id}'>This {version} (#{build_number}) run</a>",
                        "username": g.user.username,
                        "status": TestStatus.FAILED.value,
                        "metric": regression_info["metric"],
                        "threshold_negative": threshold_negative,
                        "delta": regression_info["delta"],
                        "test_id": str(run.test_id),
                        "base_run_id": str(run.id),
                        "previous_run_id": regression_info["id"],
                        "version": regression_info["version"],
                        "build_number": get_build_number(regression_info["job_url"])
                }, user_id=g.user.id, run_id=run_id, release_id=run.release_id, test_id=run.test_id)
            else:
                # NOTE: This will override status set by SCT Events.
                run.status = TestStatus.PASSED.value
                run.save()

        except SCTTestRun.DoesNotExist as exception:
            LOGGER.error("Run %s not found for SCTTestRun", run_id)
            raise SCTServiceException("Run not found", run_id) from exception

        return "submitted"

    @staticmethod
    def get_performance_history_for_test(run_id: str):
        try:
            run: SCTTestRun = SCTTestRun.get(id=run_id)
            rows = run.get_perf_results_for_test_name(build_id=run.build_id, start_time=run.start_time, test_name=run.test_name)
            return rows
        except SCTTestRun.DoesNotExist as exception:
            LOGGER.error("Run %s not found for SCTTestRun", run_id)
            raise SCTServiceException("Run not found", run_id) from exception


    @staticmethod
    def create_resource(run_id: str, resource_details: dict) -> str:
        instance_details = CloudInstanceDetails(**resource_details.pop("instance_details"))
        resource = CloudResource(**resource_details, instance_info=instance_details)
        try:
            run: SCTTestRun = SCTTestRun.get(id=run_id)
            run.get_resources().append(resource)
            run.save()
        except SCTTestRun.DoesNotExist as exception:
            LOGGER.error("Run %s not found for SCTTestRun", run_id)
            raise SCTServiceException("Run not found", run_id) from exception

        return "created"

    @staticmethod
    def update_resource_shards(run_id: str, resource_name: str, new_shards: int) -> str:
        try:
            run: SCTTestRun = SCTTestRun.get(id=run_id)
            resource = next(res for res in run.get_resources() if res.name == resource_name)
            resource.get_instance_info().shards_amount = new_shards
            run.save()
        except StopIteration as exception:
            LOGGER.error("Resource %s not found in run %s", resource_name, run_id)
            raise SCTServiceException("Resource not found", resource_name) from exception
        except SCTTestRun.DoesNotExist as exception:
            LOGGER.error("Run %s not found for SCTTestRun", run_id)
            raise SCTServiceException("Run not found", run_id) from exception

        return "updated"

    @staticmethod
    def update_resource(run_id: str, resource_name: str, update_data: ResourceUpdateRequest) -> str:
        try:
            fields_updated = {}
            run: SCTTestRun = SCTTestRun.get(id=run_id)
            resource = next(res for res in run.get_resources() if res.name == resource_name)
            instance_info = update_data.pop("instance_info", None)
            resource.state = ResourceState(update_data.get("state", resource.state)).value
            if instance_info:
                resource_instance_info = resource.get_instance_info()
                for k, v in instance_info.items():
                    if k in resource_instance_info.keys():
                        resource_instance_info[k] = v
                        fields_updated[k] = v
            run.save()
        except StopIteration as exception:
            LOGGER.error("Resource %s not found in run %s", resource_name, run_id)
            raise SCTServiceException("Resource not found", resource_name) from exception
        except SCTTestRun.DoesNotExist as exception:
            LOGGER.error("Run %s not found for SCTTestRun", run_id)
            raise SCTServiceException("Run not found", run_id) from exception

        return {
            "state": "updated",
            "fields": fields_updated
        }

    @staticmethod
    def terminate_resource(run_id: str, resource_name: str, reason: str) -> str:
        try:
            run: SCTTestRun = SCTTestRun.get(id=run_id)
            resource = next(res for res in run.get_resources() if res.name == resource_name)
            resource.get_instance_info().termination_reason = reason
            resource.get_instance_info().termination_time = int(time())
            resource.state = ResourceState.TERMINATED.value
            run.save()
        except StopIteration as exception:
            LOGGER.error("Resource %s not found in run %s", resource_name, run_id)
            raise SCTServiceException("Resource not found", resource_name) from exception
        except SCTTestRun.DoesNotExist as exception:
            LOGGER.error("Run %s not found for SCTTestRun", run_id)
            raise SCTServiceException("Run not found", run_id) from exception

        return "terminated"

    @staticmethod
    def submit_nemesis(run_id: str, nemesis_details: dict) -> str:
        nem_req = NemesisSubmissionRequest(**nemesis_details)
        node_desc = NodeDescription(name=nem_req.node_name, ip=nem_req.node_ip, shards=nem_req.node_shards)
        nemesis_info = NemesisRunInfo(
            class_name=nem_req.class_name,
            name=nem_req.name,
            start_time=int(nem_req.start_time),
            end_time=0,
            duration=0,
            stack_trace="",
            status=NemesisStatus.RUNNING.value,
            target_node=node_desc,
        )
        try:
            run: SCTTestRun = SCTTestRun.get(id=run_id)
            run.add_nemesis(nemesis_info)
            run.save()
        except SCTTestRun.DoesNotExist as exception:
            LOGGER.error("Run %s not found for SCTTestRun", run_id)
            raise SCTServiceException("Run not found", run_id) from exception

        return "created"

    @staticmethod
    def finalize_nemesis(run_id: str, nemesis_details: dict) -> str:
        nem_req = NemesisFinalizationRequest(**nemesis_details)
        try:
            run: SCTTestRun = SCTTestRun.get(id=run_id)
            nemesis = next(nem for nem in run.get_nemeses() if nem.name ==
                           nem_req.name and nem.start_time == nem_req.start_time)
            nemesis.status = NemesisStatus(nem_req.status).value
            nemesis.stack_trace = nem_req.message
            nemesis.end_time = int(time())
            run.save()
        except StopIteration as exception:
            LOGGER.error("Nemesis %s (%s) not found for run %s", nem_req.name, nem_req.start_time, run_id)
            raise SCTServiceException("Nemesis not found", (nem_req.name, nem_req.start_time)) from exception
        except SCTTestRun.DoesNotExist as exception:
            LOGGER.error("Run %s not found for SCTTestRun", run_id)
            raise SCTServiceException("Run not found", run_id) from exception

        return "updated"

    @staticmethod
    def submit_events(run_id: str, events: list[dict]) -> str:
        wrapped_events = [EventSubmissionRequest(**ev) for ev in events]
        try:
            run: SCTTestRun = SCTTestRun.get(id=run_id)
            for event in wrapped_events:
                wrapper = EventsBySeverity(severity=event.severity,
                                           event_amount=event.total_events, last_events=event.messages)
                run.get_events().append(wrapper)
            coredumps = SCTService.locate_coredumps(run, run.get_events())
            run.submit_logs(coredumps)
            run.save()
        except SCTTestRun.DoesNotExist as exception:
            LOGGER.error("Run %s not found for SCTTestRun", run_id)
            raise SCTServiceException("Run not found", run_id) from exception

        return "added"

    @staticmethod
    def locate_coredumps(run: SCTTestRun, events: list[EventsBySeverity]) -> list[dict]:
        flat_messages: list[str] = []
        links = []
        for es in events:
            flat_messages.extend(es.last_events)
        coredump_events = filter(lambda v: "coredumpevent" in v.lower(), flat_messages)
        for idx, event in enumerate(coredump_events):
            core_pattern = r"corefile_url=(?P<url>.+)$"
            node_name_pattern = r"node=(?P<name>.+)$"
            core_url_match = re.search(core_pattern, event, re.MULTILINE)
            node_name_match = re.search(node_name_pattern, event, re.MULTILINE)
            if core_url_match:
                node_name = node_name_match.group("name") if node_name_match else f"unknown-node-{idx}"
                url = core_url_match.group("url")
                log_link = {
                    "log_name": f"COREDUMP-{node_name}",
                    "log_link": url
                }
                links.append(log_link)
        return links

    @staticmethod
    def get_scylla_version_kernels_report(release_name: str):
        all_release_runs = SCTTestRun.get_version_data_for_release(release_name=release_name)
        kernels_by_version = {}
        kernel_metadata = {}
        for run in all_release_runs:
            packages = run["packages"]
            if not packages:
                continue
            scylla_pkgs = {p["name"]: p for p in packages if "scylla-server" in p["name"]}
            scylla_pkg = scylla_pkgs["scylla-server-upgraded"] if scylla_pkgs.get(
                "scylla-server-upgraded") else scylla_pkgs.get("scylla-server")
            version = f"{scylla_pkg['version']}-{scylla_pkg['date']}.{scylla_pkg['revision_id']}" if scylla_pkgs else "unknown"
            kernel_packages = [p for p in packages if "kernel" in p["name"]]
            kernel_package = kernel_packages[0] if len(kernel_packages) > 0 else None
            if not kernel_package:
                continue
            version_list = set(kernels_by_version.get(version, []))
            version_list.add(kernel_package["version"])
            kernels_by_version[version] = list(version_list)
            metadata = kernel_metadata.get(
                kernel_package.version,
                {
                    "passed": 0,
                    "failed": 0,
                    "aborted": 0,
                }
            )
            if run["status"] in ["passed", "failed", "aborted", "test_error"]:
                metadata[run["status"]] += 1
            kernel_metadata[kernel_package["version"]] = metadata

        return {
            "versions": kernels_by_version,
            "metadata": kernel_metadata
        }
    
    @staticmethod
    def junit_submit(run_id: str, file_name: str, content: str) -> bool:
        try:
            report = SCTJunitReports.get(test_id=run_id, file_name=file_name)
            if report:
                raise SCTServiceException(f"Report {file_name} already exists.", file_name)
        except SCTJunitReports.DoesNotExist:
            pass
        report = SCTJunitReports()
        report.test_id = run_id
        report.file_name = file_name
        
        xml_content = str(base64.decodebytes(bytes(content, encoding="utf-8")), encoding="utf-8")
        try:
            _ = ElementTree.fromstring(xml_content)
        except Exception:
            raise SCTServiceException(f"Malformed JUnit report submitted")

        report.report = xml_content
        report.save()

        return True

    @staticmethod
    def junit_get_all(run_id: str) -> list[SCTJunitReports]:
        return list(SCTJunitReports.filter(test_id=run_id).all())
    
    @staticmethod
    def junit_get_single(run_id: str, file_name: str) -> SCTJunitReports:
        return SCTJunitReports.get(test_id=run_id, file_name=file_name)