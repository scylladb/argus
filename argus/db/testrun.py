from dataclasses import asdict, is_dataclass
from pydantic.fields import ModelField
from uuid import uuid4, UUID
import logging

from argus.db.utils import is_list_homogeneous
from argus.db.cloud_types import *
from argus.db.interface import ArgusDatabase
from argus.db.db_types import *

T = TypeVar("T")


class TestInfoSerializationError(Exception):
    pass


class TestInfoSchemaError(Exception):
    pass


class TestInfoValueError(Exception):
    pass


class BaseTestInfo:
    EXPOSED_ATTRIBUTES = tuple()
    ATTRIBUTE_CONSTRAINTS = dict()
    COLLECTION_HINTS = dict()

    def __init__(self, *args, **kwargs):
        pass

    @classmethod
    def create_skeleton(cls):
        pass

    def schema(self):
        data = {}
        for attr in self.EXPOSED_ATTRIBUTES:
            value = getattr(self, attr)
            column_type = type(value)
            if column_type is list or column_type is tuple:
                value = self.schema_process_collection(attr)
                column_type = CollectionHint
            constraints = self.ATTRIBUTE_CONSTRAINTS.get(attr, [])
            column_info = ColumnInfo(name=attr, type=column_type, value=value, constraints=constraints)
            data[attr] = column_info

        return data

    def schema_process_collection(self, attr_name: str):
        hint = self.COLLECTION_HINTS.get(attr_name)
        if not hint:
            raise TestInfoSchemaError("Encountered a collection and no collection hint was found")

        return hint

    def serialize(self):
        data = {}
        for attr in self.EXPOSED_ATTRIBUTES:
            attribute_value = getattr(self, attr)
            if type(attribute_value) is list:
                attribute_value = self._process_list(attribute_value)
            elif is_dataclass(attribute_value):
                attribute_value = asdict(attribute_value)

            data[attr] = attribute_value

        return data

    @staticmethod
    def _process_list(list_to_check: list[T]):
        if not len(list_to_check):
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
    def validate(cls, v, field: ModelField):
        return v


class TestDetails(BaseTestInfo):
    EXPOSED_ATTRIBUTES = ("name", "scm_revision_id", "started_by",
                          "build_job_name", "build_job_url", "start_time", "yaml_test_duration", "config_files",
                          "packages")
    COLLECTION_HINTS = {
        "packages": CollectionHint(list[PackageVersion]),
        "config_files": CollectionHint(list[str]),
    }

    def __init__(self, name: str, scm_revision_id: str,
                 started_by: str, build_job_name: str, build_job_url: str,
                 yaml_test_duration: int, start_time: int,
                 config_files: list[str], packages: list[PackageVersion]):
        super().__init__()
        self.name = name
        self.scm_revision_id = scm_revision_id
        self.started_by = started_by
        self.build_job_name = build_job_name
        self.build_job_url = build_job_url
        self.start_time = start_time
        self.yaml_test_duration = yaml_test_duration
        self.packages = packages
        self.config_files = config_files

    @classmethod
    def from_db_row(cls, row):
        packages = [PackageVersion.from_db_udt(udt) for udt in row.packages]
        return cls(name=row.name, scm_revision_id=row.scm_revision_id, started_by=row.started_by,
                   build_job_name=row.build_job_name, build_job_url=row.build_job_url,
                   start_time=row.start_time, yaml_test_duration=row.yaml_test_duration, config_files=row.config_files,
                   packages=packages)


class TestResourcesSetup(BaseTestInfo):
    EXPOSED_ATTRIBUTES = ("sct_runner_host", "region_name", "cloud_setup")
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
        if row.cloud_setup.backend == "aws":
            cloud_setup = AWSSetupDetails.from_db_udt(row.cloud_setup)
        elif row.cloud_setup.backend == "gce":
            cloud_setup = GCESetupDetails.from_db_udt(row.cloud_setup)
        else:
            raise NotImplementedError()

        return cls(sct_runner_host=runner, region_name=row.region_name,
                   cloud_setup=cloud_setup)


class TestLogs(BaseTestInfo):
    EXPOSED_ATTRIBUTES = ("logs",)
    COLLECTION_HINTS = {
        "logs": CollectionHint(list[tuple[str, str]])
    }

    def __init__(self):
        super().__init__()
        self._log_collection = list()

    def add_log(self, log_type: str, log_url: str) -> None:
        self._log_collection.append((log_type, log_url))

    @property
    def logs(self) -> list[tuple[str, str]]:
        return self._log_collection

    @classmethod
    def from_db_row(cls, row):
        logs = cls()
        for log_type, log_url in row.logs:
            logs.add_log(log_type, log_url)

        return logs


class TestResources(BaseTestInfo):
    EXPOSED_ATTRIBUTES = ("allocated_resources", "terminated_resources", "leftover_resources")
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
        resource = self._leftover_resources.pop(idx)
        self._terminated_resources.append(resource)

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
            for resources_of_type in getattr(row, f"{resource_type}_resources"):
                cloud_resource = CloudResource.from_db_udt(resources_of_type)
                list_ref: list[CloudResource] = getattr(resources, f"_{resource_type}_resources")
                list_ref.append(cloud_resource)

        return resources


class TestResults(BaseTestInfo):
    EXPOSED_ATTRIBUTES = ("status", "events", "nemesis_data")
    COLLECTION_HINTS = {
        "events": CollectionHint(list[EventsBySeverity]),
        "nemesis_data": CollectionHint(list[NemesisRunInfo]),
    }

    def __init__(self, status: str, events: list[EventsBySeverity] = None,
                 nemesis_data: list[NemesisRunInfo] = None, max_stored_events=25):
        super().__init__()
        self.status = status
        self.events = events if events else list()
        self.nemesis_data = nemesis_data if nemesis_data else list()
        self.max_stored_events = max_stored_events

    @classmethod
    def from_db_row(cls, row):
        events = [EventsBySeverity.from_db_udt(event) for event in row.events]
        nemesis_data = [NemesisRunInfo.from_db_udt(nemesis) for nemesis in row.nemesis_data]

        return cls(status=row.status, events=events, nemesis_data=nemesis_data)

    def _add_new_event_type(self, event: EventsBySeverity):
        if len([v for v in self.events if v.severity == event.severity]):
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


@dataclass(init=True, repr=True)
class TestRunInfo:
    details: TestDetails
    logs: TestLogs
    setup: TestResourcesSetup
    resources: TestResources
    results: TestResults


class TestRun:
    EXPOSED_ATTRIBUTES = ("id", "group", "release_name", "assignee")
    ATTRIBUTE_CONSTRAINTS = {
    }
    PRIMARY_KEYS = {  # TODO: Implement
        "id": (UUID, "partition"),
        "release_name": (str, "clustering"),  # release version, e.g. 4.5rc5
        "name": (str, "clustering"),  # test case name, e.g longevity-test-500gb-4h
    }
    _TABLE_NAME = "test_runs"

    def __init__(self, test_id: UUID, group: str, release_name: str, assignee: str,
                 run_info: TestRunInfo, argus_interface: ArgusDatabase = None):
        if not test_id:
            test_id = uuid4()
        self._id = test_id
        self._group = group
        self._release_name = release_name
        self._assignee = assignee
        self._details = run_info.details
        self._setup = run_info.setup
        self._resources = run_info.resources
        self._logs = run_info.logs
        self._results = run_info.results
        self._log = logging.getLogger(self.__class__.__name__)

        if not argus_interface:
            argus_interface = ArgusDatabase.get()
        self._argus = argus_interface
        self._is_table_initialized = False

    @classmethod
    def from_db_row(cls, row):
        # TODO: Use UDT Object mapping from scylla-driver
        details = TestDetails.from_db_row(row)
        setup = TestResourcesSetup.from_db_row(row)
        logs = TestLogs.from_db_row(row)
        results = TestResults.from_db_row(row)
        resources = TestResources.from_db_row(row)

        run_info = TestRunInfo(details=details, setup=setup, logs=logs, results=results, resources=resources)

        return cls(test_id=row.id, group=row.group, release_name=row.release_name,
                   assignee=row.assignee, run_info=run_info)

    @classmethod
    def from_id(cls, test_id: UUID):
        db = ArgusDatabase.get()
        if row := db.fetch(cls._TABLE_NAME, test_id):
            return cls.from_db_row(row)

        return None

    @classmethod
    def create_skeleton_run(cls):
        pass

    @property
    def id(self) -> UUID:
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

    def serialize(self) -> dict[str, Any]:
        self._log.info("Serializing test run...")
        data = {
            "id": str(self._id),
            "group": self._group,
            "release_name": self._release_name,
            "assignee": self._assignee,
            **self._details.serialize(),
            **self._setup.serialize(),
            **self._resources.serialize(),
            **self._logs.serialize(),
            **self._results.serialize(),
        }
        logging.debug("Serialized Data: %s", data)
        return data

    def init_own_table(self):
        self._log.info("Initializing TestRun table...")
        self._argus.init_table(table_name=self._TABLE_NAME, column_info=self.schema())
        self._is_table_initialized = True

    def schema(self) -> dict[str, ColumnInfo]:
        data = {}
        self._log.info("Dumping full schema...")
        for attr in self.EXPOSED_ATTRIBUTES:
            value = getattr(self, attr)
            column_type = type(value)
            constraints = self.ATTRIBUTE_CONSTRAINTS.get(attr, [])
            column_info = ColumnInfo(name=attr, type=column_type, value=value, constraints=constraints)
            data[attr] = column_info

        full_schema = dict(
            **{"$tablekeys$": self.PRIMARY_KEYS},
            **data,
            **self._details.schema(),
            **self._setup.schema(),
            **self._resources.schema(),
            **self._logs.schema(),
            **self._results.schema()
        )
        self._log.debug("Full Schema: %s", full_schema)
        return full_schema

    def save(self):
        if not self._is_table_initialized:
            self.init_own_table()
        if not self.exists():
            self._log.info("Inserting data for test run: %s", self.id)
            self._argus.insert(table_name=self._TABLE_NAME, run_data=self.serialize())
        else:
            self._log.info("Updating data for test run: %s", self.id)
            self._argus.update(table_name=self._TABLE_NAME, run_data=self.serialize())

    def exists(self):
        if not self._is_table_initialized:
            self.init_own_table()

        if self._argus.fetch(table_name=self._TABLE_NAME, run_id=self.id):
            return True
        return False

    @property
    def details(self):
        return self._details

    @property
    def setup(self):
        return self._setup

    @property
    def resources(self):
        return self._resources

    @property
    def logs(self):
        return self._logs

    @property
    def results(self):
        return self._results
