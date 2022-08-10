from datetime import datetime
from uuid import UUID
from time import time

from cassandra.cqlengine import columns
from cassandra.cqlengine.models import Model
from flask import Blueprint
from argus.backend.db import ScyllaCluster
from argus.backend.util.enums import TestInvestigationStatus, TestStatus


class PluginModelBase(Model):
    # Metadata
    build_id = columns.Text(required=True, partition_key=True)
    start_time = columns.DateTime(required=True, primary_key=True, clustering_order="DESC", default=datetime.now)
    id = columns.UUID(index=True, required=True)
    release_id = columns.UUID(index=True)
    group_id = columns.UUID(index=True)
    test_id = columns.UUID(index=True)
    assignee = columns.UUID(index=True)
    status = columns.Text(default=lambda: TestStatus.CREATED.value)
    investigation_status = columns.Text(default=lambda: TestInvestigationStatus.NOT_INVESTIGATED.value)
    heartbeat = columns.Integer(default=lambda: int(time()))
    end_time = columns.DateTime(default=lambda: datetime.utcfromtimestamp(0))

    # Test Logs Collection
    logs = columns.List(value_type=columns.Tuple(columns.Text(), columns.Text()))

    @classmethod
    def load_test_run(cls, run_id: UUID) -> 'PluginModelBase':
        raise NotImplementedError()

    @classmethod
    def submit_run(cls, request_data: dict) -> 'PluginModelBase':
        raise NotImplementedError()

    @classmethod
    def get_distinct_product_versions(cls, cluster: ScyllaCluster, release_id: UUID) -> list[str]:
        raise NotImplementedError()

    def update_heartbeat(self):
        raise NotImplementedError()

    def change_status(self, new_status: TestStatus):
        raise NotImplementedError()

    def change_investigation_status(self, new_investigation_status: TestInvestigationStatus):
        raise NotImplementedError()

    def submit_product_version(self, version: str):
        raise NotImplementedError()

    def submit_logs(self, logs: list[dict]):
        raise NotImplementedError()

    def finish_run(self):
        raise NotImplementedError()


class PluginInfoBase:
    # pylint: disable=too-few-public-methods
    name: str
    controller: Blueprint
    model: PluginModelBase
