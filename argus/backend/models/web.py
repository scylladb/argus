import logging
from typing import Annotated, Optional
from uuid import UUID, uuid1, uuid4
from datetime import datetime
from enum import Enum, IntEnum, auto
from cassandra.cqlengine.models import Model
from cassandra.cqlengine.usertype import UserType
from cassandra.cqlengine import columns
from cassandra.util import uuid_from_time, unix_time_from_uuid1
from pydantic import Field
from coodie import ClusteringKey, Indexed, PrimaryKey, SmallInt, TimeUUID
from coodie.exceptions import DocumentNotFound

from argus.backend.models.github_issue import GithubIssue, IssueAssignee, IssueLabel, IssueLink
from argus.backend.models.jira import JiraIssue
from argus.backend.models.plan import ArgusReleasePlan
from argus.backend.models.pytest import PytestResultTable, PytestResultTableOld, PytestUserField
from argus.backend.models.result import (
    ArgusGenericResultMetadata,
    ArgusGenericResultData,
    ArgusBestResultData,
    ArgusGraphView,
    ColumnMetadata,
    ValidationRules,
)
from argus.backend.models.run_config import RunConfigParam, RunConfiguration
from coodie.sync import Document

from argus.backend.models.runtime_store import RuntimeStore
from argus.backend.models.view_widgets import WidgetHighlights, WidgetComment
from argus.backend.models.argus_ai import ErrorEventEmbeddings, CriticalEventEmbeddings, SCTErrorEventEmbedding, \
    SCTCriticalEventEmbedding
from argus.backend.models.ssh_key import SSHTunnelKey, ProxyTunnelConfig


def uuid_now():
    return uuid_from_time(datetime.utcnow())


class ArgusTestException(Exception):
    pass


class UserRoles(str, Enum):
    User = "ROLE_USER"
    Manager = "ROLE_MANAGER"
    Admin = "ROLE_ADMIN"
    SSHTunnelServer = "ROLE_SSH_TUNNEL_SERVER"


class User(Document):
    id: Annotated[UUID, PrimaryKey()] = Field(default_factory=uuid4)
    username: Annotated[Optional[str], Indexed()] = None
    full_name: Optional[str] = None
    password: Optional[str] = None
    email: Annotated[Optional[str], Indexed()] = None
    registration_date: Optional[datetime] = None
    roles: list[str] = Field(default_factory=list)
    picture_id: Optional[UUID] = None
    api_token: Annotated[Optional[str], Indexed()] = None
    service_user: Optional[bool] = False

    class Settings:
        name = "user"

    def __hash__(self) -> int:
        return hash(self.id)

    def is_manager(self) -> bool:
        return UserRoles.Manager in self.roles

    def is_admin(self) -> bool:
        return UserRoles.Admin in self.roles

    def set_as_admin(self) -> None:
        if UserRoles.Admin not in self.roles:
            self.roles.append(UserRoles.Admin.value)

    def set_as_manager(self) -> None:
        if UserRoles.Manager not in self.roles:
            self.roles.append(UserRoles.Manager.value)

    def set_as_service_user(self) -> None:
        self.service_user = True
        self.save()

    def set_as_normal_user(self) -> None:
        self.service_user = False
        self.save()

    def is_service_user(self) -> bool:
        return bool(self.service_user)

    def get_id(self):
        return str(self.id)

    @classmethod
    def exists(cls, user_id: UUID):
        try:
            user = cls.get(id=user_id)
            if user:
                return user
        except DocumentNotFound:
            pass
        return None

    @classmethod
    def exists_by_name(cls, name: str) -> Optional['User']:
        try:
            user = cls.get(username=name)
            if user:
                return user
        except DocumentNotFound:
            pass
        return None

    @classmethod
    def exists_by_email(cls, email: str) -> Optional['User']:
        try:
            user = cls.get(email=email)
            if user:
                return user
        except DocumentNotFound:
            pass
        return None

    def __str__(self):
        return f"User('{self.id}','{self.username}')"

    def to_json(self):
        return {
            "id": str(self.id),
            "username": self.username,
            "full_name": self.full_name,
            "email": self.email,
            "picture_id": self.picture_id
        }


class Team(Document):
    id: Annotated[UUID, PrimaryKey()] = Field(default_factory=uuid4)
    name: Optional[str] = None
    leader: Annotated[Optional[UUID], Indexed()] = None
    members: list[UUID] = Field(default_factory=list)
    motd: Optional[str] = None

    class Settings:
        name = "team"


class UserOauthToken(Document):
    id: Annotated[UUID, PrimaryKey()] = Field(default_factory=uuid4)
    user_id: Annotated[Optional[UUID], Indexed()] = None
    kind: Annotated[Optional[str], Indexed()] = None
    token: Optional[str] = None

    class Settings:
        name = "user_oauth_token"


class ArgusRelease(Document):
    id: Annotated[UUID, PrimaryKey()] = Field(default_factory=uuid4)
    name: Annotated[Optional[str], Indexed()] = None
    pretty_name: Optional[str] = None
    description: Optional[str] = None
    github_repo_url: Optional[str] = None
    valid_version_regex: Optional[str] = None
    assignee: list[UUID] = Field(default_factory=list)
    picture_id: Optional[UUID] = None
    enabled: Optional[bool] = True
    perpetual: Optional[bool] = False
    dormant: Optional[bool] = False

    class Settings:
        name = "argus_release_v2"

    def __eq__(self, other):
        if isinstance(other, ArgusRelease):
            return self.name == other.name
        else:
            return super().__eq__(other)


class ArgusGroup(Document):
    id: Annotated[UUID, PrimaryKey()] = Field(default_factory=uuid4)
    release_id: Annotated[Optional[UUID], Indexed()] = None
    name: Annotated[Optional[str], Indexed()] = None
    pretty_name: Optional[str] = None
    description: Optional[str] = None
    assignee: list[UUID] = Field(default_factory=list)
    build_system_id: Optional[str] = None
    enabled: Optional[bool] = True

    class Settings:
        name = "argus_group_v2"

    def __hash__(self) -> int:
        return hash((self.id, self.release_id))

    def __eq__(self, other):
        if isinstance(other, ArgusGroup):
            return self.name == other.name and self.release_id == other.release_id
        else:
            return super().__eq__(other)


class ArgusUserView(Document):
    id: Annotated[UUID, PrimaryKey()] = Field(default_factory=uuid4)
    name: Annotated[Optional[str], Indexed()] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    user_id: Annotated[Optional[UUID], Indexed()] = None
    plan_id: Annotated[Optional[UUID], Indexed()] = None
    tests: list[UUID] = Field(default_factory=list)
    release_ids: list[UUID] = Field(default_factory=list)
    group_ids: list[UUID] = Field(default_factory=list)
    created: Optional[datetime] = Field(default_factory=datetime.utcnow)
    last_updated: Optional[datetime] = Field(default_factory=datetime.utcnow)
    widget_settings: Optional[str] = None

    class Settings:
        name = "argus_user_view"


class ArgusTest(Document):
    id: Annotated[UUID, PrimaryKey()] = Field(default_factory=uuid4)
    group_id: Annotated[Optional[UUID], Indexed()] = None
    release_id: Annotated[Optional[UUID], Indexed()] = None
    name: Annotated[Optional[str], Indexed()] = None
    pretty_name: Optional[str] = None
    description: Optional[str] = None
    assignee: list[UUID] = Field(default_factory=list)
    build_system_id: Annotated[Optional[str], Indexed()] = None
    enabled: Optional[bool] = True
    build_system_url: Optional[str] = None
    plugin_name: Optional[str] = None
    plugin_subtype: Optional[str] = None

    class Settings:
        name = "argus_test_v2"

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
        except DocumentNotFound:
            pass


class ArgusTestRunComment(Document):
    id: Annotated[UUID, PrimaryKey()] = Field(default_factory=uuid4)
    posted_at: Annotated[Optional[int], ClusteringKey(order="DESC")] = None
    test_run_id: Annotated[Optional[UUID], Indexed()] = None
    user_id: Annotated[Optional[UUID], Indexed()] = None
    release_id: Annotated[Optional[UUID], Indexed()] = None
    test_id: Annotated[Optional[UUID], Indexed()] = None
    message: Optional[str] = Field(default=None, min_length=1, max_length=65535)
    mentions: list[UUID] = Field(default_factory=list)
    reactions: dict[str, int] = Field(default_factory=dict)

    class Settings:
        name = "argus_test_run_comment"


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


class ArgusEvent(Document):
    id: Annotated[UUID, PrimaryKey()] = Field(default_factory=uuid4)
    release_id: Annotated[Optional[UUID], Indexed()] = None
    group_id: Annotated[Optional[UUID], Indexed()] = None
    test_id: Annotated[Optional[UUID], Indexed()] = None
    run_id: Annotated[Optional[UUID], Indexed()] = None
    user_id: Annotated[Optional[UUID], Indexed()] = None
    kind: Annotated[Optional[str], Indexed()] = None
    body: Optional[str] = None
    created_at: Optional[datetime] = None

    class Settings:
        name = "argus_event"


class ArgusNotificationTypes(str, Enum):
    Mention = "TYPE_MENTION"
    StatusChange = "TYPE_STATUS_CHANGE"
    AssigneeChange = "TYPE_ASSIGNEE_CHANGE"
    ScheduleChange = "TYPE_SCHEDULE_CHANGE"
    ViewActionItemAssignee = "TYPE_VIEW_ACTION_ITEM_ASSIGNEE"
    ViewHighlightMention = "TYPE_VIEW_HIGHLIGHT_MENTION"


class ArgusNotificationSourceTypes(str, Enum):
    TestRun = "TEST_RUN"
    Schedule = "SCHEDULE"
    Comment = "COMMENT"
    ViewActionItem = "VIEW_ACTION_ITEM"
    ViewHighlight = "VIEW_HIGHLIGHT"


class ArgusNotificationState(IntEnum):
    UNREAD = auto()
    READ = auto()


class ArgusNotification(Document):
    receiver: Annotated[Optional[UUID], PrimaryKey()] = None
    id: Annotated[UUID, TimeUUID(), ClusteringKey(order="DESC")] = Field(default_factory=uuid_now)
    type: Optional[str] = None
    state: Annotated[Optional[int], SmallInt()] = Field(default=ArgusNotificationState.UNREAD)
    sender: Optional[UUID] = None
    source_type: Optional[str] = None
    source_id: Optional[UUID] = None
    title: Optional[str] = Field(default=None, max_length=1024)
    content: Optional[str] = Field(default=None, max_length=65535)

    class Settings:
        name = "argus_notification"

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
    # FIXME: Deprecated. To be removed.
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


class ReleasePlannerComment(Document):
    release: Annotated[UUID, PrimaryKey()]
    group: Annotated[UUID, ClusteringKey(clustering_key_index=0)]
    test: Annotated[UUID, ClusteringKey(clustering_key_index=1)]
    comment: str = ""

    class Settings:
        name = "argus_planner_comment_v2"


class WebFileStorage(Document):
    id: Annotated[UUID, PrimaryKey()] = Field(default_factory=uuid4)
    filepath: Optional[str] = Field(default=None, min_length=1)
    filename: Optional[str] = Field(default=None, min_length=1)

    class Settings:
        name = "web_file_storage"


class ReleaseStatsSnapshot(Model):
    __table_name__ = "argus_release_stats_snapshot"
    release_id = columns.UUID(partition_key=True)
    filter_key = columns.Text(primary_key=True)
    payload = columns.Text()
    generated_at = columns.DateTime()


class ReleaseDistinctVersions(Model):
    """Denormalized index: distinct scylla_version values seen for a release.
    Replaces the expensive GSI scan in get_distinct_product_versions.
    Keyed by release_id (partition) + version (clustering) for O(1) reads.
    """
    release_id = columns.UUID(partition_key=True)
    version = columns.Text(primary_key=True)


class ReleaseDistinctImages(Model):
    """Denormalized index: distinct cloud image IDs seen for a release.
    Replaces the expensive GSI scan + UDT deserialization in get_distinct_cloud_images_for_release.
    Keyed by release_id (partition) + image_id (clustering) for O(1) reads.
    """
    release_id = columns.UUID(partition_key=True)
    image_id = columns.Text(primary_key=True)


_SNAPSHOT_LOGGER = logging.getLogger(__name__)


def invalidate_release_snapshots(release_id: UUID) -> None:
    """Full-partition delete of all ReleaseStatsSnapshot rows for a release.

    Use this for structural or metadata changes that affect all filter
    combinations (admin edits, group/test toggles, issue/comment/plan
    mutations). The next stats request will regenerate the snapshots.
    Version-scoped invalidation in PluginModelBase.invalidate_release_snapshot()
    is used only for run lifecycle events (submit/finish).
    """
    try:
        ReleaseStatsSnapshot.filter(release_id=release_id).delete()
    except Exception:  # pylint: disable=broad-except
        _SNAPSHOT_LOGGER.warning("Failed to invalidate release snapshots for %s", release_id, exc_info=True)


USED_MODELS: list[Model] = [
    ArgusSchedule,
    ArgusScheduleAssignee,
    ArgusScheduleGroup,
    ArgusScheduleTest,
    ReleaseDistinctVersions,
    ReleaseDistinctImages,
    ErrorEventEmbeddings,  # to be deprecated
    CriticalEventEmbeddings,  # to be deprecated
    SCTErrorEventEmbedding,
    SCTCriticalEventEmbedding,
    PytestResultTable,
    PytestUserField,
    PytestResultTableOld,
    RunConfiguration,
    RunConfigParam,
    SSHTunnelKey,
    ProxyTunnelConfig,
    ReleaseStatsSnapshot,
]

USED_TYPES: list[UserType] = [

]

# Models already ported from cqlengine to coodie; synced via Document.sync_table()
USED_COODIE_MODELS: list[type[Document]] = [
    RuntimeStore,
    User,
    UserOauthToken,
    WebFileStorage,
    ArgusRelease,
    ArgusGroup,
    ArgusTest,
    ArgusTestRunComment,
    ArgusEvent,
    ReleasePlannerComment,
    Team,
    ArgusNotification,
    ArgusGenericResultMetadata,
    ArgusGenericResultData,
    ArgusBestResultData,
    ArgusGraphView,
    ArgusUserView,
    WidgetHighlights,
    WidgetComment,
    ArgusReleasePlan,
    GithubIssue,
    IssueLink,
    JiraIssue,
]

# Coodie user-defined types; synced via UserType.sync_type() and registered
# with the driver cluster so result rows materialize them as model instances.
USED_COODIE_TYPES = [
    ColumnMetadata,
    ValidationRules,
    IssueLabel,
    IssueAssignee,
]
