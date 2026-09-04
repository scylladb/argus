from datetime import UTC, datetime
from uuid import UUID
from typing import Annotated, ClassVar, Optional

from pydantic import Field
from coodie import PrimaryKey
from coodie.exceptions import DocumentNotFound
from coodie.sync import Document
from coodie.usertype import UserType

from argus.backend.db import ScyllaCluster
from argus.backend.models.web import ArgusRelease
from argus.backend.plugins.core import PluginModelBase
from argus.backend.util.common import get_build_number
from argus.common.sirenada_types import RawSirenadaRequest, SirenadaPluginException
from argus.common.enums import TestStatus


class SirenadaTest(UserType):
    test_name: Optional[str] = None
    class_name: Optional[str] = None
    file_name: Optional[str] = None
    browser_type: Optional[str] = None
    cluster_type: Optional[str] = None
    status: Optional[str] = None
    duration: Optional[float] = None
    message: Optional[str] = None
    start_time: Optional[datetime] = None
    stack_trace: Optional[str] = None
    screenshot_file: Optional[str] = None
    s3_folder_id: Optional[str] = None
    requests_file: Optional[str] = None
    sirenada_test_id: Optional[str] = None
    sirenada_user: Optional[str] = None
    sirenada_password: Optional[str] = None

    class Settings:
        __type_name__ = "sirenada_test"


class SirenadaRun(PluginModelBase):
    _plugin_name: ClassVar[str] = "sirenada"

    class Settings:
        name = "sirenada_run"

    logs: dict[str, str] = Field(default_factory=dict)
    # TODO: Legacy field name, should be renamed to product_version and abstracted
    scylla_version: Optional[str] = None
    region: str
    sirenada_test_ids: list[str] = Field(default_factory=list)
    s3_folder_ids: list[tuple[str, str]] = Field(default_factory=list)
    browsers: list[str] = Field(default_factory=list)
    clusters: list[str] = Field(default_factory=list)
    sct_test_id: Optional[UUID] = None
    results: list[SirenadaTest] = Field(default_factory=list)

    @classmethod
    def _stats_query(cls) -> str:
        return ("SELECT id, test_id, group_id, release_id, status, start_time, build_job_url, build_id, "
                f"assignee, end_time, investigation_status, heartbeat, build_number, scylla_version FROM {cls.table_name()} WHERE build_id IN ? PER PARTITION LIMIT 15")

    @classmethod
    def get_distinct_product_versions(cls, release: ArgusRelease, cluster: ScyllaCluster = None) -> list[str]:
        if not cluster:
            cluster = ScyllaCluster.get()
        statement = cluster.prepare(f"SELECT scylla_version FROM {cls.table_name()} WHERE release_id = ?")
        rows = cluster.session.execute(query=statement, parameters=(release.id,))
        unique_versions = {r["scylla_version"] for r in rows if r["scylla_version"]}

        return sorted(list(unique_versions), reverse=True)

    def submit_product_version(self, version: str):
        self.scylla_version = version
        try:
            new_assignee = self.get_assignment(version)
        except DocumentNotFound:
            new_assignee = None
        if new_assignee:
            self.assignee = new_assignee

    def submit_logs(self, logs: dict[str, str]):
        raise SirenadaPluginException("Log submission is not supported for Sirenada")

    def finish_run(self, payload: dict = None):
        raise SirenadaPluginException("Sirenada runs do not need finalization")

    @classmethod
    def load_test_run(cls, run_id: UUID) -> 'SirenadaRun':
        return cls.get(id=run_id)

    @classmethod
    def submit_run(cls, request_data: RawSirenadaRequest) -> 'SirenadaRun':
        try:
            run = cls.get(id=UUID(request_data["run_id"]))
        except DocumentNotFound:
            run = cls.model_construct()
            run.id = UUID(request_data["run_id"])
            run.build_id = request_data["build_id"]
            run.start_time = datetime.now(UTC)
            run.assign_categories()
            run.build_job_url = request_data["build_job_url"]
            run.build_number = get_build_number(request_data["build_job_url"])
            run.region = request_data["region"]
            run.status = TestStatus.PASSED.value
            try:
                run.assignee = run.get_scheduled_assignee()
            except DocumentNotFound:
                run.assignee = None

        for raw_case in request_data["results"]:
            case = SirenadaTest(**raw_case)
            if case.status in ["failed", "error"] and run.status not in [TestStatus.FAILED.value, TestStatus.ABORTED.value]:
                run.status = TestStatus.FAILED.value
            run.results.append(case)

            if case.sirenada_test_id not in run.sirenada_test_ids:
                run.sirenada_test_ids.append(case.sirenada_test_id)

            if case.browser_type not in run.browsers:
                run.browsers.append(case.browser_type)

            if case.cluster_type not in run.clusters:
                run.clusters.append(case.cluster_type)

            if (case.s3_folder_id, case.sirenada_test_id) not in run.s3_folder_ids and case.s3_folder_id:
                run.s3_folder_ids.append((case.s3_folder_id, case.sirenada_test_id))

        run.save()

        return run
