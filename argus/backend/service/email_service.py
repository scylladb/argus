import base64
from dataclasses import asdict, dataclass
from io import BytesIO
import logging
import re
from typing import Any

from flask import render_template
import humanize
from argus.backend.plugins.sct.testrun import SCTEventSeverity, SCTTestRun
from argus.backend.service.results_service import ResultsService
from argus.backend.util.common import get_build_number
from argus.backend.util.send_email import Attachment, Email
from argus.common.email import RawAttachment, RawReportSendRequest, ReportSection, ReportSectionShortHand


LOGGER = logging.getLogger(__name__)

class GmailSender(Email):
    pass


@dataclass(init=True, repr=True)
class ReportSendRequest():
    schema_version: str | None
    run_id: str
    title: str
    recipients: list[str]
    sections: list[ReportSection | ReportSectionShortHand]
    attachments: list[RawAttachment]


class Partial():
    TEMPLATE_PATH = "#PATH"

    def __init__(self, section_type: str, test_run: SCTTestRun):
        self.test_run = test_run
        self.section_type = section_type
        self._service_fields = {
            "template_path": self.TEMPLATE_PATH,
            "type": self.section_type,
            "has_data": True,
        }

    def create_context(self, options: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError()

    def default_options(self) ->  dict[str, Any]:
        raise NotImplementedError()


class Header(Partial):
    TEMPLATE_PATH = "email/partials/header.html.j2"
    def create_context(self, options: dict[str, Any]):
        return {
            **self.default_options(),
        }

    def default_options(self):
        return {
            **self._service_fields,
            "id": self.test_run.id,
            "build_id": self.test_run.build_id,
            "build_number": get_build_number(self.test_run.build_job_url),
            "status": self.test_run.status,
        }


class Main(Partial):
    TEMPLATE_PATH = "email/partials/main.html.j2"

    def create_context(self, options: dict[str, Any]) -> dict[str, Any]:
        return {
            **self.default_options(),
        }

    def default_options(self) -> dict[str, Any]:
        return {
            **self._service_fields,
            "started_by": self.test_run.started_by,
            "end_time": self.test_run.end_time,
            "start_time": self.test_run.start_time,
            "duration": humanize.naturaldelta(self.test_run.end_time - self.test_run.start_time),
            "build_job_url": self.test_run.build_job_url,
            "run_id": self.test_run.id,
            "packages": self.test_run.packages,
            "status": self.test_run.status,
            "commit": self.test_run.scm_revision_id,
            "branch": self.test_run.branch_name,
            "repo": self.test_run.origin_url,
            "cloud_setup": self.test_run.cloud_setup,
        }


class Packages(Partial):
    TEMPLATE_PATH = "email/partials/packages.html.j2"
    def create_context(self, options: dict[str, Any]):
        return {
            **self.default_options(),
            "has_data": len(self.test_run.packages) > 0,
        }

    def default_options(self):
        return {
            **self._service_fields,
            "run_id": self.test_run.id,
            "packages": [dict(p) for p in self.test_run.packages],
        }



class Logs(Partial):
    TEMPLATE_PATH = "email/partials/logs.html.j2"
    def create_context(self, options: dict[str, Any]):
        return {
            **self.default_options(),
            "has_data": len(self.test_run.logs) > 0,
        }

    def default_options(self):
        create_link = lambda log: f"/api/v1/tests/scylla-cluster-tests/{self.test_run.id}/log/{log[0]}/download"
        proxy_links = { log[0]: create_link(log) for log in self.test_run.logs }
        return {
            **self._service_fields,
            "run_id": self.test_run.id,
            "logs": self.test_run.logs,
            "proxied_links": proxy_links,
        }


class Screenshots(Partial):
    TEMPLATE_PATH = "email/partials/screenshots.html.j2"
    def create_context(self, options: dict[str, Any]):
        return {
            **self.default_options(),
            "has_data": len(self.test_run.screenshots) > 0,
        }

    def default_options(self):
        return {
            **self._service_fields,
            "run_id": self.test_run.id,
            "links": self.test_run.screenshots,
        }


class Cloud(Partial):
    TEMPLATE_PATH = "email/partials/cloud.html.j2"
    def create_context(self, options: dict[str, Any]):
        resources = list(filter(lambda res: res.resource_type != "sct-runner", self.test_run.get_resources()))
        return {
            **self.default_options(),
            "has_data": len(list(filter(lambda r: r.state == "running", resources))) > 0,
            "resources": resources,
        }

    def default_options(self):
        return {
            **self._service_fields,
            "run_id": self.test_run.id,
            "cloud_setup": self.test_run.cloud_setup,
        }


class Nemesis(Partial):
    TEMPLATE_PATH = "email/partials/nemesis.html.j2"
    def create_context(self, options: dict[str, Any]):
        status_filter = options.get("status_filter") or ["failed", "succeeded"]
        nemesis = list(filter(lambda nem: nem.status in status_filter, self.test_run.nemesis_data))
        return {
            **self.default_options(),
            "run_id": self.test_run.id,
            "sort_order": options.get("sort_order") or ["start_time", "desc"],
            "status_filter": status_filter,
            "has_data": len(nemesis) > 0,
            "nemesis": nemesis,
        }

    def default_options(self):
        return {
            **self._service_fields,
        }


class Events(Partial):
    TEMPLATE_PATH = "email/partials/events.html.j2"
    def create_context(self, options: dict[str, Any]):
        severities = [SCTEventSeverity(s) for s in options.get("severity_filter", ["CRITICAL",  "ERROR"])]
        limit = options.get("amount_per_severity", 25)
        events = self.test_run.get_events_limited(self.test_run.id, severities=severities, per_partition_limit=limit)
        return {
            **self.default_options(),
            "events": events,
        }

    def default_options(self):
        return {
            **self._service_fields,
            "run_id": self.test_run.id,
        }


class GenericResults(Partial):
    TEMPLATE_PATH = "email/partials/generic_results.html.j2"
    def create_context(self, options: dict[str, Any]):
        results = ResultsService().get_run_results(run_id=self.test_run.id, test_id=self.test_run.test_id)
        table_filter: list[str] = options.get("table_filter", [])
        final_tables = set()
        tables = [next(iter(t.keys())) for t in results]
        if table_filter:
            filters: list[re.Pattern] = []
            for filter in table_filter:
                try:
                    filters.append(re.compile(filter))
                except re.error:
                    LOGGER.warning("Received invalid regexp filter: %s", filter)
                    continue
            for f in filters:
                [final_tables.add(table) for table in tables if f.search(table)]
        else:
            final_tables = tables
        return {
            "section_name": options.get("section_name", "Results"),
            "results": [result for result in results if next(iter(result.keys())) in final_tables],
            **self.default_options(),
        }

    def default_options(self):
        return {
            **self._service_fields,
            "run_id": self.test_run.id,
        }


class Unsupported(Partial):
    TEMPLATE_PATH = "email/partials/unsupported.html.j2"
    def create_context(self, options: dict[str, Any]):
        return {
            **self.default_options(),
            **options
        }

    def default_options(self):
        return {
            **self._service_fields,
        }


class CustomHtml(Partial):
    TEMPLATE_PATH = "email/partials/custom_html.html.j2"
    def create_context(self, options: dict[str, Any]):
        return {
            **self.default_options(),
            **options,
        }

    def default_options(self):
        return {
            **self._service_fields,
            "run_id": self.test_run.id,
        }


class CustomTable(Partial):
    TEMPLATE_PATH = "email/partials/custom_table.html.j2"
    def create_context(self, options: dict[str, Any]):
        return {
            **self.default_options(),
            **options,
        }

    def default_options(self):
        return {
            **self._service_fields,
            "run_id": self.test_run.id,
        }


PARTIALS: dict[str, Partial] = {
    "main": Main,
    "header": Header,
    "packages": Packages,
    "logs": Logs,
    "cloud": Cloud,
    "nemesis": Nemesis,
    "events": Events,
    "screenshots": Screenshots,
    "generic_results": GenericResults,
    "custom_table": CustomTable,
    "custom_html": CustomHtml,
    "unsupported": Unsupported,
}


DEFAULT_SECTIONS = [
    "header",
    "main",
    "packages",
    "screenshots",
    "cloud",
    {
        "type": "events",
        "options": {
            "amount_per_severity": 25,
            "severity_filter": [
                "CRITICAL",
                "ERROR"
            ]
        }
    },
    {
        "type": "nemesis",
        "options": {
            "sort_order": [
                "start_time",
                "desc"
            ],
            "status_filter": [
                "failed",
                "succeeded",
                "started",
                "running"
            ]
        }
    },
    "logs",
]


class EmailServiceException(Exception):
    pass


class EmailService:
    SENDER = None

    @classmethod
    def set_sender(cls, sender: Email):
        cls.SENDER = sender

    def __init__(self, sender: Email = None):
        if not self.SENDER:
            self.sender = sender if sender else GmailSender()
        else:
            self.sender = self.SENDER

    def send_report(self, request_data: RawReportSendRequest) -> bool:
        req = ReportSendRequest(**request_data)
        try:
            report = self.create_report(req)
        except Exception as exc:
            raise EmailServiceException("Error during template render", exc.args)
        attachments = []
        for raw_attach in req.attachments:
            data_io = BytesIO(base64.decodebytes(raw_attach["data"].encode()))
            attachment: Attachment = {
                "filename": raw_attach["filename"],
                "data": data_io,
            }
            attachments.append(attachment)
        try:
            self.sender.send(req.title, report, recipients=req.recipients, html=True, attachments=attachments)
        except Exception as exc:
            raise EmailServiceException("Error sending email report", exc.args)
        return True

    def display_report(self, request_data: RawReportSendRequest) -> str:
        req = ReportSendRequest(**request_data)
        return self.create_report(req)

    def create_report(self, request: ReportSendRequest) -> str:
        run: SCTTestRun = SCTTestRun.get(id=request.run_id)
        partials = []
        for section in request.sections if len(request.sections) > 0 else DEFAULT_SECTIONS:
            if isinstance(section, dict):
                partial = PARTIALS.get(section["type"], PARTIALS["unsupported"])(section_type=section["type"], test_run=run)
                partials.append(partial.create_context(section["options"]))
            elif isinstance(section, str):
                partial = PARTIALS.get(section, PARTIALS["unsupported"])(section_type=section, test_run=run)
                partials.append(partial.create_context({}))
        if request.title == "#auto":
            request.title = f"[{run.status.upper()}] {run.build_id}#{get_build_number(run.build_job_url)}: {run.start_time.strftime("%d/%m/%Y %H:%M:%S")}"
        request.sections = partials
        return render_template("email/base.html.j2", **asdict(request), run=run)
