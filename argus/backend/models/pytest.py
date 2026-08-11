from typing import Annotated, Any, Optional, TypedDict
from datetime import UTC, datetime
from uuid import UUID

from pydantic import Field
from cassandra.util import uuid_from_time
from cassandra.cluster import Session
from coodie import ClusteringKey, Double, Indexed, PrimaryKey, TimeUUID
from coodie.sync import Document

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


class PytestResultTableOld(Document):
    name: Annotated[Optional[str], PrimaryKey()] = None
    id: Annotated[UUID, TimeUUID(), ClusteringKey(order="DESC")] = Field(
        default_factory=lambda: uuid_from_time(datetime.now(tz=UTC)))
    test_type: Optional[str] = None
    run_id: Annotated[Optional[UUID], Indexed()] = None
    release_id: Annotated[Optional[UUID], Indexed()] = None
    test_id: Annotated[Optional[UUID], Indexed()] = None
    duration: Annotated[Optional[float], Double()] = None
    message: Optional[str] = None
    status: Optional[str] = Field(default=PytestStatus.PASSED.value)
    test_timestamp: Optional[datetime] = None  # timestamp for the submitted test
    session_timestamp: Optional[datetime] = None  # timestamp of the test session
    markers: list[str] = Field(default_factory=list)

    # User fields map remaining user-specified fields into a simple string:string mapping
    # Example: SCYLLA_MODE = release
    user_fields: dict[str, str] = Field(default_factory=dict)

    class Settings:
        name = "pytest_result_table"

    @classmethod
    def _sync_additional_rules(cls, session: Session):
        session.execute(
            "CREATE INDEX IF NOT EXISTS pytest_result_table_user_key_idx ON pytest_result_table (KEYS(user_fields))")
        session.execute(
            "CREATE INDEX IF NOT EXISTS pytest_result_table_user_entries_idx ON pytest_result_table (ENTRIES(user_fields))")
        session.execute(
            "CREATE INDEX IF NOT EXISTS pytest_result_table_user_value_idx ON pytest_result_table (VALUES(user_fields))")


class PytestResultTable(Document):
    name: Annotated[Optional[str], PrimaryKey()] = None
    status: Annotated[Optional[str], ClusteringKey(clustering_key_index=0)] = Field(
        default=PytestStatus.PASSED.value)
    id: Annotated[Optional[datetime], ClusteringKey(clustering_key_index=1)] = Field(
        default_factory=lambda: datetime.now(tz=UTC))
    test_type: Optional[str] = None
    run_id: Annotated[Optional[UUID], Indexed()] = None
    test_id: Annotated[Optional[UUID], Indexed()] = None
    release_id: Annotated[Optional[UUID], Indexed()] = None
    duration: Annotated[Optional[float], Double()] = None
    message: Optional[str] = None
    test_timestamp: Optional[datetime] = None  # timestamp for the submitted test
    session_timestamp: Optional[datetime] = None  # timestamp of the test session
    markers: list[str] = Field(default_factory=list)

    class Settings:
        name = "pytest_v2"


class PytestUserField(Document):
    name: Annotated[Optional[str], PrimaryKey()] = None
    id: Annotated[Optional[datetime], ClusteringKey(clustering_key_index=0)] = None
    field_name: Annotated[Optional[str], ClusteringKey(clustering_key_index=1)] = None
    field_value: Optional[str] = None

    class Settings:
        name = "pytest_user_field"
