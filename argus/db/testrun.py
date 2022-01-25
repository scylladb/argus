import logging
import time
import traceback
import sys
import threading
from dataclasses import asdict, is_dataclass, fields, Field, dataclass
from typing import Any
from uuid import uuid4, UUID

from argus.db.config import BaseConfig
from argus.db.utils import is_list_homogeneous
from argus.db.cloud_types import CloudResource, CloudInstanceDetails, BaseCloudSetupDetails
from argus.db.interface import ArgusDatabase
from argus.db.db_types import ColumnInfo, CollectionHint, NemesisRunInfo, TestStatus, EventsBySeverity, PackageVersion

LOGGER = logging.getLogger(__name__)


class TestInfoSerializationError(Exception):
    pass


class TestInfoSchemaError(Exception):
    pass


class TestInfoValueError(Exception):
    pass


class BaseTestInfo:
    EXPOSED_ATTRIBUTES = {}
    ATTRIBUTE_CONSTRAINTS = {}
    COLLECTION_HINTS = {}

    def __init__(self, *args, **kwargs):
        pass

    @classmethod
    def create_skeleton(cls):
        pass

    @classmethod
    def schema(cls):
        data = {}
        for attr, column_type in cls.EXPOSED_ATTRIBUTES.items():
            value = None
            if column_type is list or column_type is tuple:
                value = cls.schema_process_collection(attr)
                column_type = CollectionHint
            constraints = cls.ATTRIBUTE_CONSTRAINTS.get(attr, [])
            column_info = ColumnInfo(name=attr, type=column_type, value=value, constraints=constraints)
            data[attr] = column_info

        return data

    @classmethod
    def schema_process_collection(cls, attr_name: str):
        hint = cls.COLLECTION_HINTS.get(attr_name)
        if not hint:
            raise TestInfoSchemaError("Encountered a collection and no collection hint was found")

        return hint

    def serialize(self):
        data = {}
        for attr in self.EXPOSED_ATTRIBUTES:
            attribute_value = getattr(self, attr)
            if isinstance(attribute_value, list):
                attribute_value = self._process_list(attribute_value)
            elif is_dataclass(attribute_value):
                attribute_value = asdict(attribute_value)

            data[attr] = attribute_value

        return data

    @staticmethod
    def _process_list(list_to_check: list[Any]):
        if len(list_to_check) == 0:
            return list_to_check

        if not is_list_homogeneous(list_to_check):
            raise TestInfoSerializationError("Detected a non-homogenous list")

        contains_dataclass = is_dataclass(list_to_check[0])

        if contains_dataclass:
            return [asdict(dc) for dc in list_to_check]

        return list_to_check

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, value, field):  # pylint: disable=unused-argument
        return value


class TestDetails(BaseTestInfo):
    # pylint: disable=too-many-instance-attributes
    EXPOSED_ATTRIBUTES = {"name": str, "scm_revision_id": str, "started_by": str,
                          "build_job_name": str, "build_job_url": str, "start_time": int, "yaml_test_duration": int,
                          "config_files": list,
                          "packages": list, "end_time": int}
    COLLECTION_HINTS = {
        "packages": CollectionHint(list[PackageVersion]),
        "config_files": CollectionHint(list[str]),
    }

    def __init__(self, name: str, scm_revision_id: str,
                 started_by: str, build_job_name: str, build_job_url: str,
                 yaml_test_duration: int, start_time: int,
                 config_files: list[str], packages: list[PackageVersion], end_time: int = -1):
        # pylint: disable=too-many-arguments
        super().__init__()
        self.name = name
        self.scm_revision_id = scm_revision_id
        self.started_by = started_by
        self.build_job_name = build_job_name
        self.build_job_url = build_job_url
        self.start_time = start_time
        self.yaml_test_duration = yaml_test_duration
        if not (is_list_homogeneous(packages) or (
                len(packages) > 0 and isinstance(next(iter(packages)), PackageVersion))):
            raise TestInfoValueError("Package list contains incorrect values", packages)
        self.packages = packages
        self.config_files = config_files
        self.end_time = end_time

    @classmethod
    def from_db_row(cls, row):
        if row.packages:
            packages = [PackageVersion.from_db_udt(udt) for udt in row.packages]
        else:
            packages = []

        config_files = row.config_files if row.config_files else []

        return cls(name=row.name, scm_revision_id=row.scm_revision_id, started_by=row.started_by,
                   build_job_name=row.build_job_name, build_job_url=row.build_job_url,
                   start_time=row.start_time, end_time=row.end_time, yaml_test_duration=row.yaml_test_duration,
                   config_files=config_files,
                   packages=packages)

    def set_test_end_time(self):
        self.end_time = int(time.time())


class TestResourcesSetup(BaseTestInfo):
    EXPOSED_ATTRIBUTES = {
        "sct_runner_host": CloudInstanceDetails,
        "region_name": list,
        "cloud_setup": BaseCloudSetupDetails
    }
    COLLECTION_HINTS = {
        "region_name": CollectionHint(list[str]),
    }

    def __init__(self, sct_runner_host: CloudInstanceDetails,
                 region_name: list[str], cloud_setup: BaseCloudSetupDetails):
        super().__init__()
        self.sct_runner_host = sct_runner_host
        self.region_name = region_name
        self.cloud_setup = cloud_setup

    @classmethod
    def from_db_row(cls, row):
        runner = CloudInstanceDetails.from_db_udt(row.sct_runner_host)
        cloud_setup = BaseCloudSetupDetails.from_db_udt(row.cloud_setup)

        regions = row.region_name if row.region_name else []

        return cls(sct_runner_host=runner, region_name=regions,
                   cloud_setup=cloud_setup)


class TestLogs(BaseTestInfo):
    EXPOSED_ATTRIBUTES = {"logs": list}
    COLLECTION_HINTS = {
        "logs": CollectionHint(list[tuple[str, str]])
    }

    def __init__(self):
        super().__init__()
        self._log_collection = []

    def add_log(self, log_type: str, log_url: str | list[str]) -> None:
        if isinstance(log_url, str):
            self._log_collection.append((log_type, log_url))
        elif isinstance(log_url, list):
            for log in log_url:
                self._log_collection.append((log_type, log))
        else:
            LOGGER.warning("Unknown log type encountered: %s", log_url)

    @property
    def logs(self) -> list[tuple[str, str]]:
        return self._log_collection

    @classmethod
    def from_db_row(cls, row):
        logs = cls()
        if row.logs:
            for log_type, log_url in row.logs:
                logs.add_log(log_type, log_url)

        return logs


class TestResources(BaseTestInfo):
    EXPOSED_ATTRIBUTES = {"allocated_resources": list, "terminated_resources": list, "leftover_resources": list}
    COLLECTION_HINTS = {
        "allocated_resources": CollectionHint(list[CloudResource]),
        "terminated_resources": CollectionHint(list[CloudResource]),
        "leftover_resources": CollectionHint(list[CloudResource]),
    }

    def __init__(self):
        super().__init__()
        self._leftover_resources = []
        self._terminated_resources = []
        self._allocated_resources = []

    def attach_resource(self, resource: CloudResource):
        self._leftover_resources.append(resource)
        self._allocated_resources.append(resource)

    def detach_resource(self, resource: CloudResource):
        idx = self._leftover_resources.index(resource)
        detached_resource = self.leftover_resources.pop(idx)
        detached_resource.terminate()
        self._terminated_resources.append(detached_resource)

    @property
    def allocated_resources(self) -> list[CloudResource]:
        return self._allocated_resources

    @property
    def terminated_resources(self) -> list[CloudResource]:
        return self._terminated_resources

    @property
    def leftover_resources(self) -> list[CloudResource]:
        return self._leftover_resources

    @classmethod
    def from_db_row(cls, row):
        resources = cls()

        for resource_type in ["leftover", "allocated", "terminated"]:
            resource_column = getattr(row, f"{resource_type}_resources")
            if resource_column:
                for resources_of_type in resource_column:
                    cloud_resource = CloudResource.from_db_udt(resources_of_type)
                    list_ref: list[CloudResource] = getattr(resources, f"_{resource_type}_resources")
                    list_ref.append(cloud_resource)

        return resources


class TestResults(BaseTestInfo):
    EXPOSED_ATTRIBUTES = {"status": str, "events": list, "nemesis_data": list}
    COLLECTION_HINTS = {
        "events": CollectionHint(list[EventsBySeverity]),
        "nemesis_data": CollectionHint(list[NemesisRunInfo]),
    }

    def __init__(self, status: TestStatus, events: list[EventsBySeverity] = None,
                 nemesis_data: list[NemesisRunInfo] = None, max_stored_events=25):
        super().__init__()
        if isinstance(status, TestStatus):
            self._status = status.value
        else:
            self._status = TestStatus(status).value
        self.events = events if events else []
        self.nemesis_data = nemesis_data if nemesis_data else []
        self.max_stored_events = max_stored_events

    @classmethod
    def from_db_row(cls, row):
        if row.events:
            events = [EventsBySeverity.from_db_udt(event) for event in row.events]
        else:
            events = []

        if row.nemesis_data:
            nemesis_data = [NemesisRunInfo.from_db_udt(nemesis) for nemesis in row.nemesis_data]
        else:
            nemesis_data = []

        return cls(status=row.status, events=events, nemesis_data=nemesis_data)

    def _add_new_event_type(self, event: EventsBySeverity):
        if len([v for v in self.events if v.severity == event.severity]) > 0:
            raise TestInfoValueError(f"Severity event collection {event.severity} already exists in TestResults")

        self.events.append(event)

    def _collect_event_message(self, event: EventsBySeverity, message: str):
        if len(event.last_events) >= self.max_stored_events:
            event.last_events = event.last_events[1:]

        event.event_amount += 1
        event.last_events.append(message)

    def add_nemesis(self, nemesis: NemesisRunInfo):
        self.nemesis_data.append(nemesis)

    def add_event(self, event_severity: str, event_message: str):
        try:
            event = next(filter(lambda v: v.severity == event_severity, self.events))
        except StopIteration:
            event = EventsBySeverity(severity=event_severity, event_amount=0, last_events=[])
            self._add_new_event_type(event)

        self._collect_event_message(event, event_message)

    @property
    def status(self) -> TestStatus:
        return TestStatus(self._status)

    @status.setter
    def status(self, value: TestStatus):
        self._status = TestStatus(value).value


@dataclass
class TestRunInfo:
    details: TestDetails
    setup: TestResourcesSetup
    resources: TestResources
    logs: TestLogs
    results: TestResults


class TestRun:
    # pylint: disable=too-many-instance-attributes
    EXPOSED_ATTRIBUTES = {"id": UUID, "group": str, "release_name": str, "assignee": str, "heartbeat": int}
    ATTRIBUTE_CONSTRAINTS = {
    }
    PRIMARY_KEYS = {
        "id": (UUID, "partition"),
    }
    _USING_RUNINFO = TestRunInfo
    _TABLE_NAME = "test_runs_v3_shards_amount"
    _IS_TABLE_INITIALIZED = False
    _ARGUS_DB_INTERFACE = None

    def __init__(self, test_id: UUID, group: str, release_name: str, assignee: str,
                 run_info: TestRunInfo, config: BaseConfig = None, argus_interface: ArgusDatabase = None):
        # pylint: disable=too-many-arguments
        if not test_id:
            test_id = uuid4()
        self._save_lock = threading.Lock()
        self._id = test_id
        self._group = group
        self._release_name = release_name
        self._assignee = assignee
        self._run_info = run_info
        self._heartbeat = int(time.time())
        self._config = config
        for field in fields(run_info):
            setattr(self, field.name, getattr(run_info, field.name))

        if argus_interface:
            self.argus = argus_interface

    @classmethod
    def table_name(cls) -> str:
        return cls._TABLE_NAME

    @classmethod
    def from_db_row(cls, row, config: BaseConfig = None):
        if not cls._IS_TABLE_INITIALIZED:
            cls.init_own_table(config)
        nested_fields = {}
        for field in fields(cls._USING_RUNINFO):
            nested_fields[field.name] = field.type.from_db_row(row)

        run_info = cls._USING_RUNINFO(**nested_fields)
        run = cls(test_id=row.id, group=row.group, release_name=row.release_name,
                  assignee=row.assignee, run_info=run_info)
        run.heartbeat = row.heartbeat
        return run

    @classmethod
    def from_id(cls, test_id: UUID, config: BaseConfig = None):
        if not cls._IS_TABLE_INITIALIZED:
            cls.init_own_table(config)
        database = cls.get_argus()
        if row := database.fetch(cls._TABLE_NAME, test_id):
            return cls.from_db_row(row)

        return None

    @classmethod
    def get_argus(cls, config: BaseConfig = None) -> ArgusDatabase:
        if not cls._ARGUS_DB_INTERFACE:
            cls._ARGUS_DB_INTERFACE = ArgusDatabase(config=config)
        return cls._ARGUS_DB_INTERFACE

    @classmethod
    def set_argus(cls, argus_interface: ArgusDatabase):
        cls._ARGUS_DB_INTERFACE = argus_interface
        cls._IS_TABLE_INITIALIZED = False

    @property
    def argus(self) -> ArgusDatabase:
        if not self._ARGUS_DB_INTERFACE:
            self.get_argus(self._config)
        return self._ARGUS_DB_INTERFACE

    @argus.setter
    def argus(self, interface: ArgusDatabase | None):
        self._ARGUS_DB_INTERFACE = interface  # pylint: disable=invalid-name
        self._IS_TABLE_INITIALIZED = False  # pylint: disable=invalid-name

    @property
    def heartbeat(self) -> int:
        return self._heartbeat

    @heartbeat.setter
    def heartbeat(self, value: int | float):
        self._heartbeat = int(value)

    @property
    def id(self) -> UUID:  # pylint: disable=invalid-name
        return self._id

    @property
    def group(self) -> str:
        return self._group

    @property
    def release_name(self) -> str:
        return self._release_name

    @property
    def assignee(self) -> str:
        return self._assignee

    @assignee.setter
    def assignee(self, value):
        self._assignee = str(value)

    def serialize(self) -> dict[str, Any]:
        LOGGER.debug("Serializing test run...")
        nested_data = {}
        for field in fields(self._USING_RUNINFO):
            field: Field
            value: BaseTestInfo = getattr(self, field.name)
            nested_data = {
                **nested_data,
                **value.serialize()
            }

        data = {
            "id": str(self._id),
            "group": self._group,
            "release_name": self._release_name,
            "assignee": self._assignee,
            "heartbeat": self._heartbeat,
            **nested_data
        }
        LOGGER.debug("Serialized Data: %s", data)
        return data

    @classmethod
    def init_own_table(cls, config: BaseConfig = None):
        LOGGER.debug("Initializing TestRun table...")
        cls.get_argus(config).init_table(table_name=cls._TABLE_NAME, column_info=cls.schema())
        cls._IS_TABLE_INITIALIZED = True

    @classmethod
    def set_table_name(cls, new_table_name: str):
        cls._TABLE_NAME = new_table_name
        cls._IS_TABLE_INITIALIZED = False

    @classmethod
    def schema(cls) -> dict[str, ColumnInfo]:
        data = {}
        LOGGER.debug("Dumping full schema...")
        for attr, column_type in cls.EXPOSED_ATTRIBUTES.items():
            value = None
            constraints = cls.ATTRIBUTE_CONSTRAINTS.get(attr, [])
            column_info = ColumnInfo(name=attr, type=column_type, value=value, constraints=constraints)
            data[attr] = column_info

        schema_dump = {}
        for field in fields(cls._USING_RUNINFO):
            schema_dump = {
                **schema_dump,
                **field.type.schema(),
            }

        full_schema = dict(
            **{"$tablekeys$": cls.PRIMARY_KEYS},
            **data,
            **schema_dump
        )
        LOGGER.debug("Full Schema: %s", full_schema)
        return full_schema

    def save(self):
        with self._save_lock:
            if not self._IS_TABLE_INITIALIZED:
                self.init_own_table(self._config)
            if not self.exists():
                LOGGER.debug("Inserting data for test run: %s", self.id)
                self.argus.insert(table_name=self._TABLE_NAME, run_data=self.serialize())
            else:
                LOGGER.debug("Updating data for test run: %s", self.id)
                self.argus.update(table_name=self._TABLE_NAME, run_data=self.serialize())

    def exists(self) -> bool:
        if not self._IS_TABLE_INITIALIZED:
            self.init_own_table(self._config)

        if self.argus.fetch(table_name=self._TABLE_NAME, run_id=self.id):
            return True
        return False

    def shutdown(self):
        LOGGER.debug("Shutting down cluster connection...")
        self.argus.cluster.shutdown()

    @property
    def run_info(self) -> TestRunInfo:
        return self._run_info


class TestRunWithHeartbeat(TestRun):
    def __init__(self, test_id: UUID, group: str, release_name: str, assignee: str,
                 run_info: TestRunInfo, heartbeat_interval=30, config: BaseConfig = None,
                 argus_interface: ArgusDatabase = None):
        # pylint: disable=too-many-arguments
        self._heartbeat_interval = heartbeat_interval
        self._shutdown_event = threading.Event()
        super().__init__(test_id=test_id, group=group, release_name=release_name, assignee=assignee,
                         run_info=run_info, config=config, argus_interface=argus_interface)
        self._thread = threading.Thread(target=self._heartbeat_entry,
                                        name=f"{self.__class__.__name__}-{self.id}-heartbeat", daemon=True)
        self._thread.start()

    @property
    def heartbeat_interval(self) -> int:
        return self._heartbeat_interval

    @heartbeat_interval.setter
    def heartbeat_interval(self, value: float | int):
        self._heartbeat_interval = value

    @property
    def thread(self):
        return self._thread

    def _heartbeat_entry(self):
        while True:
            time.sleep(self.heartbeat_interval)
            if self._shutdown_event.is_set():
                break
            LOGGER.debug("Sending heartbeat...")
            self.heartbeat = time.time()
            self.save()
        LOGGER.debug("Heartbeat exit")

    def shutdown(self):
        self._shutdown_event.set()
        LOGGER.debug("Waiting for the heartbeat thread to exit...")
        self._thread.join(timeout=self.heartbeat_interval + 10)
        if self._thread.is_alive():
            LOGGER.warning("Heartbeat thread was not able to shut down correctly. Stack trace:")
            # pylint: disable=protected-access
            current_threads = sys._current_frames()
            stack_trace = traceback.extract_stack(current_threads[self._thread.ident])
            LOGGER.warning(
                "\n".join([f'#{lineno:3} : {line:50}: {fname}' for fname, lineno, _, line in stack_trace]))
        super().shutdown()
