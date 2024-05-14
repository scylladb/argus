from datetime import datetime
from uuid import UUID, uuid4
from cassandra.cqlengine import columns
from cassandra.cqlengine.usertype import UserType
from cassandra.cqlengine.models import Model
from argus.backend.db import ScyllaCluster
from argus.backend.models.web import ArgusRelease
from argus.backend.plugins.core import PluginModelBase
from argus.backend.plugins.sirenada.types import RawSirenadaRequest, SirenadaPluginException
from argus.backend.util.enums import TestStatus


class SirenadaTest(UserType):
    test_name = columns.Text()
    class_name = columns.Text()
    file_name = columns.Text()
    browser_type = columns.Text()
    cluster_type = columns.Text()
    status = columns.Text()
    duration = columns.Float()
    message = columns.Text()
    start_time = columns.DateTime()
    stack_trace = columns.Text()
    screenshot_file = columns.Text()
    s3_folder_id = columns.Text()
    requests_file = columns.Text()
    sirenada_test_id = columns.Text()
    sirenada_user = columns.Text()
    sirenada_password = columns.Text()



class SirenadaRun(PluginModelBase):
    _plugin_name = "sirenada"
    __table_name__ = "sirenada_run"
    logs = columns.Map(key_type=columns.Text(), value_type=columns.Text())
    # TODO: Legacy field name, should be renamed to product_version and abstracted
    scylla_version = columns.Text()
    region = columns.Text()
    sirenada_test_ids = columns.List(value_type=columns.Text())
    s3_folder_ids = columns.List(value_type=columns.Tuple(columns.Text(), columns.Text()))
    browsers = columns.List(value_type=columns.Text())
    clusters = columns.List(value_type=columns.Text())
    sct_test_id = columns.UUID()
    results = columns.List(value_type=columns.UserDefinedType(user_type=SirenadaTest))

    @classmethod
    def _stats_query(cls) -> str:
        return ("SELECT id, test_id, group_id, release_id, status, start_time, build_job_url, build_id, "
                f"assignee, end_time, investigation_status, heartbeat, scylla_version FROM {cls.table_name()} WHERE build_id IN ? PER PARTITION LIMIT 15")

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
        except cls.DoesNotExist:
            run = cls()
            run.id = request_data["run_id"] # FIXME: Validate pls
            run.build_id = request_data["build_id"]
            run.start_time = datetime.utcnow()
            run.assign_categories()
            run.build_job_url = request_data["build_job_url"]
            run.region = request_data["region"]
            run.status = TestStatus.PASSED.value
            try:
                run.assignee = run.get_scheduled_assignee()
            except Model.DoesNotExist:
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
