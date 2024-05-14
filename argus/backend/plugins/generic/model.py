from datetime import datetime
from uuid import UUID
from cassandra.cqlengine import columns
from cassandra.cqlengine.models import Model
from argus.backend.db import ScyllaCluster
from argus.backend.models.web import ArgusRelease
from argus.backend.plugins.core import PluginModelBase
from argus.backend.plugins.generic.types import GenericRunFinishRequest, GenericRunSubmitRequest
from argus.backend.util.enums import TestStatus


class GenericPluginException(Exception):
    pass


class GenericRun(PluginModelBase):
    _plugin_name = "generic"
    __table_name__ = "generic_run"
    logs = columns.Map(key_type=columns.Text(), value_type=columns.Text())
    started_by = columns.Text()
    # TODO: Legacy field name, should be renamed to product_version and abstracted
    scylla_version = columns.Text()

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
        self.set_product_version(version)

    @classmethod
    def load_test_run(cls, run_id: UUID) -> 'GenericRun':
        return cls.get(id=run_id)

    @classmethod
    def submit_run(cls, request_data: GenericRunSubmitRequest) -> 'GenericRun':
        try:
            run = cls.get(id=request_data["run_id"])
            raise GenericPluginException(f"Run with UUID {request_data['run_id']} already exists.", request_data["run_id"])
        except cls.DoesNotExist:
            pass
        run = cls()
        run.start_time = datetime.utcnow()
        run.build_id = request_data["build_id"]
        run.started_by = request_data["started_by"]
        run.id = request_data["run_id"]
        run.build_job_url = request_data["build_url"]
        run.assign_categories()
        try:
            run.assignee = run.get_scheduled_assignee()
        except Model.DoesNotExist:
            run.assignee = None
        if version := request_data.get("scylla_version"):
            run.submit_product_version(version)
        run.status = TestStatus.RUNNING.value
        run.save()

        return run

    def finish_run(self, payload: GenericRunFinishRequest = None):
        self.end_time = datetime.utcnow()
        self.status = TestStatus(payload["status"]).value
        if version := payload.get("scylla_version"):
            self.submit_product_version(version)
