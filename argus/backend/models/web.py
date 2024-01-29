from uuid import UUID, uuid1, uuid4
from datetime import datetime
from enum import Enum, IntEnum, auto
from cassandra.cqlengine.models import Model
from cassandra.cqlengine.usertype import UserType
from cassandra.cqlengine import columns
from cassandra.util import uuid_from_time, unix_time_from_uuid1  # pylint: disable=no-name-in-module


def uuid_now():
    return uuid_from_time(datetime.utcnow())

# pylint: disable=invalid-name


class ArgusTestException(Exception):
    pass


class UserRoles(str, Enum):
    User = "ROLE_USER"
    Manager = "ROLE_MANAGER"
    Admin = "ROLE_ADMIN"


class User(Model):
    id = columns.UUID(primary_key=True, default=uuid4)
    username = columns.Text(index=True)
    full_name = columns.Text()
    password = columns.Text()
    email = columns.Text(index=True)
    registration_date = columns.DateTime()
    roles = columns.List(value_type=columns.Text)
    picture_id = columns.UUID(default=None)
    api_token = columns.Text(index=True)

    def __hash__(self) -> int:
        return hash(self.id)

    def is_manager(self) -> bool:
        # pylint: disable=unsupported-membership-test
        return UserRoles.Manager in self.roles

    def is_admin(self) -> bool:
        # pylint: disable=unsupported-membership-test
        return UserRoles.Admin in self.roles

    def set_as_admin(self) -> None:
        # pylint: disable=unsupported-membership-test
        if UserRoles.Admin not in self.roles:
            self.roles.append(UserRoles.Admin.value)

    def set_as_manager(self) -> None:
        # pylint: disable=unsupported-membership-test
        if UserRoles.Manager not in self.roles:
            self.roles.append(UserRoles.Manager.value)

    def get_id(self):
        return str(self.id)

    @classmethod
    def exists(cls, user_id: UUID):
        try:
            user = cls.get(id=user_id)
            if user:
                return user
        except cls.DoesNotExist:
            pass
        return None

    @classmethod
    def exists_by_name(cls, name: str):
        try:
            user = cls.get(username=name)
            if user:
                return user
        except cls.DoesNotExist:
            pass
        return None

    def __str__(self):
        return f"User('{self.id}','{self.username}')"

    def to_json(self):
        return {
            "id": str(self.id),
            "username": self.username,
            "full_name": self.full_name,
            "picture_id": self.picture_id
        }


class Team(Model):
    id = columns.UUID(primary_key=True, default=uuid4)
    name = columns.Text(required=True)
    leader = columns.UUID(index=True, required=True)
    members = columns.List(value_type=columns.UUID)
    motd = columns.Text()

class UserOauthToken(Model):
    id = columns.UUID(primary_key=True, default=uuid4)
    user_id = columns.UUID(index=True, required=True)
    kind = columns.Text(required=True, index=True)
    token = columns.Text(required=True)


class ArgusRelease(Model):
    __table_name__ = "argus_release_v2"
    id = columns.UUID(primary_key=True, default=uuid4)
    name = columns.Text(index=True, required=True)
    pretty_name = columns.Text()
    description = columns.Text()
    github_repo_url = columns.Text()
    valid_version_regex = columns.Text()
    assignee = columns.List(value_type=columns.UUID)
    picture_id = columns.UUID()
    enabled = columns.Boolean(default=lambda: True)
    perpetual = columns.Boolean(default=lambda: False)
    dormant = columns.Boolean(default=lambda: False)

    def __eq__(self, other):
        if isinstance(other, ArgusRelease):
            return self.name == other.name
        else:
            return super().__eq__(other)


class ArgusGroup(Model):
    __table_name__ = "argus_group_v2"
    id = columns.UUID(primary_key=True, default=uuid4)
    release_id = columns.UUID(required=True, index=True)
    name = columns.Text(required=True, index=True)
    pretty_name = columns.Text()
    description = columns.Text()
    assignee = columns.List(value_type=columns.UUID)
    build_system_id = columns.Text()
    enabled = columns.Boolean(default=lambda: True)

    def __hash__(self) -> int:
        return hash((self.id, self.release_id))

    def __eq__(self, other):
        if isinstance(other, ArgusGroup):
            return self.name == other.name and self.release_id == other.release_id
        else:
            return super().__eq__(other)


class ArgusTest(Model):
    __table_name__ = "argus_test_v2"
    id = columns.UUID(primary_key=True, default=uuid4)
    group_id = columns.UUID(required=True, index=True)
    release_id = columns.UUID(required=True, index=True)
    name = columns.Text(required=True, index=True)
    pretty_name = columns.Text()
    description = columns.Text()
    assignee = columns.List(value_type=columns.UUID)
    build_system_id = columns.Text(index=True)
    enabled = columns.Boolean(default=lambda: True)
    build_system_url = columns.Text()
    plugin_name = columns.Text()

    def __eq__(self, other):
        if isinstance(other, ArgusTest):
            return self.name == other.name and self.group_id == other.group_id and self.release_id == other.release_id
        else:
            return super().__eq__(other)

    def validate_build_system_id(self):
        try:
            t = ArgusTest.get(build_system_id=self.build_system_id)
            if t.id != self.id:
                raise ArgusTestException("Build Id is already used by another test", t.id, self.id)
        except ArgusTest.DoesNotExist:
            pass


class ArgusTestRunComment(Model):
    id = columns.UUID(primary_key=True, default=uuid4, partition_key=True)
    test_run_id = columns.UUID(required=True, index=True)
    user_id = columns.UUID(required=True, index=True)
    release_id = columns.UUID(required=True, index=True)
    posted_at = columns.Integer(
        required=True, clustering_order="desc", primary_key=True)
    message = columns.Text(min_length=1, max_length=65535)
    mentions = columns.List(value_type=columns.UUID, default=[])
    reactions = columns.Map(key_type=columns.Text, value_type=columns.Integer)


class ArgusEventTypes(str, Enum):
    AssigneeChanged = "ARGUS_ASSIGNEE_CHANGE"
    TestRunStatusChanged = "ARGUS_TEST_RUN_STATUS_CHANGE"
    TestRunInvestigationStatusChanged = "ARGUS_TEST_RUN_INVESTIGATION_STATUS_CHANGE"
    TestRunBatchInvestigationStatusChange = "ARGUS_TEST_RUN_INVESTIGATION_BATCH_STATUS_CHANGE"
    TestRunCommentPosted = "ARGUS_TEST_RUN_COMMENT_POSTED"
    TestRunCommentUpdated = "ARGUS_TEST_RUN_COMMENT_UPDATED"
    TestRunCommentDeleted = "ARGUS_TEST_RUN_COMMENT_DELETED"
    TestRunIssueAdded = "ARGUS_TEST_RUN_ISSUE_ADDED"
    TestRunIssueRemoved = "ARGUS_TEST_RUN_ISSUE_REMOVED"


class ArgusEvent(Model):
    id = columns.UUID(primary_key=True, default=uuid4, partition_key=True)
    release_id = columns.UUID(index=True)
    group_id = columns.UUID(index=True)
    test_id = columns.UUID(index=True)
    run_id = columns.UUID(index=True)
    user_id = columns.UUID(index=True)
    kind = columns.Text(required=True, index=True)
    body = columns.Text(required=True)
    created_at = columns.DateTime(required=True)


class ArgusNotificationTypes(str, Enum):
    Mention = "TYPE_MENTION"
    StatusChange = "TYPE_STATUS_CHANGE"
    AssigneeChange = "TYPE_ASSIGNEE_CHANGE"
    ScheduleChange = "TYPE_SCHEDULE_CHANGE"


class ArgusNotificationSourceTypes(str, Enum):
    TestRun = "TEST_RUN"
    Schedule = "SCHEDULE"
    Comment = "COMMENT"


class ArgusNotificationState(IntEnum):
    UNREAD = auto()
    READ = auto()


class ArgusNotification(Model):
    receiver = columns.UUID(primary_key=True, partition_key=True)
    id = columns.TimeUUID(primary_key=True, clustering_order="DESC", default=uuid_now)
    type = columns.Text(required=True)
    state = columns.SmallInt(required=True, default=lambda: ArgusNotificationState.UNREAD)
    sender = columns.UUID(required=True)
    source_type = columns.Text(required=True)
    source_id = columns.UUID(required=True)
    title = columns.Text(required=True, max_length=1024)
    content = columns.Text(required=True, max_length=65535)

    def to_dict_short_summary(self) -> dict:
        return {
            "receiver": self.receiver,
            "sender": self.sender,
            "id": self.id,
            "created": unix_time_from_uuid1(self.id) * 1000,
            "title": self.title,
            "state": self.state,
        }

    def to_dict(self) -> dict:
        return {
            "receiver": self.receiver,
            "sender": self.sender,
            "id": self.id,
            "created": unix_time_from_uuid1(self.id) * 1000,
            "title": self.title,
            "type": self.type,
            "content": self.content,
            "source": self.source_type,
            "source_id": self.source_id,
            "state": self.state,
        }


class ArgusGithubIssue(Model):
    # pylint: disable=too-many-instance-attributes
    id = columns.UUID(primary_key=True, default=uuid4, partition_key=True)
    added_on = columns.DateTime(default=datetime.utcnow)
    release_id = columns.UUID(index=True)
    group_id = columns.UUID(index=True)
    test_id = columns.UUID(index=True)
    run_id = columns.UUID(index=True)
    user_id = columns.UUID(index=True)
    type = columns.Text()
    owner = columns.Text()
    repo = columns.Text()
    issue_number = columns.Integer()
    last_status = columns.Text()
    title = columns.Text()
    url = columns.Text()

    def __hash__(self) -> int:
        return hash((self.owner, self.repo, self.issue_number))

    def __eq__(self, other):
        if isinstance(other, ArgusGithubIssue):
            return self.owner == other.owner and self.repo == other.repo and self.issue_number == other.issue_number
        return super().__eq__(other)

    def __ne__(self, other):
        return not self == other


class ArgusSchedule(Model):
    __table_name__ = "argus_schedule_v4"
    release_id = columns.UUID(primary_key=True, required=True)
    id = columns.TimeUUID(primary_key=True, default=uuid1, clustering_order="DESC")
    period_start = columns.DateTime(required=True, default=datetime.utcnow)
    period_end = columns.DateTime(required=True, primary_key=True, clustering_order="DESC")
    tag = columns.Text(default="")


class ArgusScheduleAssignee(Model):
    __table_name__ = "argus_schedule_user_v3"
    assignee = columns.UUID(primary_key=True)
    id = columns.TimeUUID(primary_key=True, default=uuid1,
                          clustering_order="DESC")
    schedule_id = columns.TimeUUID(required=True, index=True)
    release_id = columns.UUID(required=True)


class ArgusScheduleTest(Model):
    __table_name__ = "argus_schedule_test_v5"
    test_id = columns.UUID(primary_key=True, required=True)
    id = columns.TimeUUID(primary_key=True, default=uuid1,
                          clustering_order="DESC")
    schedule_id = columns.TimeUUID(required=True, index=True)
    release_id = columns.UUID(partition_key=True)


class ArgusScheduleGroup(Model):
    __table_name__ = "argus_schedule_group_v3"
    group_id = columns.UUID(partition_key=True, required=True)
    id = columns.TimeUUID(primary_key=True, default=uuid1,
                          clustering_order="DESC")
    schedule_id = columns.TimeUUID(required=True, index=True)
    release_id = columns.UUID(partition_key=True)


class ReleasePlannerComment(Model):
    __table_name__ = "argus_planner_comment_v2"
    release = columns.UUID(primary_key=True)
    group = columns.UUID(primary_key=True)
    test = columns.UUID(primary_key=True)
    comment = columns.Text(default=lambda: "")


class WebFileStorage(Model):
    id = columns.UUID(primary_key=True, default=uuid4)
    filepath = columns.Text(min_length=1)
    filename = columns.Text(min_length=1)


USED_MODELS: list[Model] = [
    User,
    UserOauthToken,
    Team,
    WebFileStorage,
    ArgusRelease,
    ArgusGroup,
    ArgusTest,
    ArgusTestRunComment,
    ArgusEvent,
    ArgusGithubIssue,
    ReleasePlannerComment,
    ArgusNotification,
    ArgusSchedule,
    ArgusScheduleAssignee,
    ArgusScheduleGroup,
    ArgusScheduleTest,
]

USED_TYPES: list[UserType] = [

]
