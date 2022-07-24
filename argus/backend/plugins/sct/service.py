from dataclasses import dataclass
import logging
from time import time
from argus.backend.plugins.sct.testrun import SCTTestRun
from argus.backend.plugins.sct.udt import (
    CloudInstanceDetails,
    CloudResource,
    EventsBySeverity,
    NemesisRunInfo,
    NodeDescription,
    PackageVersion,
)
from argus.backend.util.enums import NemesisStatus

LOGGER = logging.getLogger(__name__)


class SCTServiceException(Exception):
    pass


@dataclass(init=True, repr=True)
class NemesisSubmissionRequest:
    name: str
    class_name: str
    method_name: str
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
                run.packages.append(package)
            run.save()
        except SCTTestRun.DoesNotExist as exception:
            LOGGER.error("Run %s not found for SCTTestRun", run_id)
            raise SCTServiceException("Run not found", run_id) from exception

        return "added"

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
    def terminate_resource(run_id: str, resource_name: str, reason: str) -> str:
        try:
            run: SCTTestRun = SCTTestRun.get(id=run_id)
            resource = next(res for res in run.get_resources() if res.name == resource_name)
            resource.get_instance_info().termination_reason = reason
            resource.get_instance_info().termination_time = int(time())
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
            method_name=nem_req.method_name,
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
            run.save()
        except SCTTestRun.DoesNotExist as exception:
            LOGGER.error("Run %s not found for SCTTestRun", run_id)
            raise SCTServiceException("Run not found", run_id) from exception

        return "added"
