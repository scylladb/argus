from typing import Any, TypedDict
from datetime import UTC, datetime
from cassandra.cqlengine.models import Model
from cassandra.cqlengine import columns
from cassandra.util import uuid_from_time
from cassandra.cluster import Session

from argus.common.enums import PytestStatus


class PytestSubmitData(TypedDict):
    name: str
    timestamp: float
    session_timestamp: float
    test_type: str
    run_id: str
    status: PytestStatus
    duration: float
    markers: list[str]
    user_fields: dict[str, Any]


class PytestResultTable(Model):
    name = columns.Text(primary_key=True, partition_key=True)
    id = columns.TimeUUID(primary_key=True, clustering_order="DESC",
                          default=lambda: uuid_from_time(datetime.now(tz=UTC)))
    test_type = columns.Text(required=True)
    run_id = columns.UUID(index=True, required=True)
    release_id = columns.UUID(index=True)
    test_id = columns.UUID(index=True)
    duration = columns.Double()
    message = columns.Text()
    status = columns.Text(default=lambda: PytestStatus.PASSED.value)
    test_timestamp = columns.DateTime()
    session_timestamp = columns.DateTime()
    markers = columns.List(value_type=columns.Text())
    user_fields = columns.Map(key_type=columns.Text(), value_type=columns.Text())

    @classmethod
    def _sync_additional_rules(cls, session: Session):
        session.execute(
            "CREATE INDEX IF NOT EXISTS pytest_result_table_user_key_idx ON pytest_result_table (KEYS(user_fields))")
        session.execute(
            "CREATE INDEX IF NOT EXISTS pytest_result_table_user_entries_idx ON pytest_result_table (ENTRIES(user_fields))")
        session.execute(
            "CREATE INDEX IF NOT EXISTS pytest_result_table_user_value_idx ON pytest_result_table (VALUES(user_fields))")
