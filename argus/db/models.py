from uuid import uuid1, uuid4
from datetime import datetime
from enum import Enum
from cassandra.cqlengine.models import Model
from cassandra.cqlengine.usertype import UserType
from cassandra.cqlengine import columns
from cassandra.cqlengine.columns import UserDefinedType

# pylint: disable=invalid-name


class WebRunComment(UserType):
    user_id = columns.UUID(required=True)
    timestamp = columns.Integer(required=True)
    message = columns.Text(min_length=1)
    mentions = columns.List(value_type=columns.UUID, default=[])

    def to_json(self):
        return {
            'user_id': self.user_id,
            'timestamp': self.timestamp,
            'message': self.message,
            'mentions': self.mentions,
        }


class User(Model):
    id = columns.UUID(primary_key=True, default=uuid4)
    username = columns.Text(index=True)
    full_name = columns.Text()
    password = columns.Text()
    email = columns.Text(index=True)
    registration_date = columns.DateTime()
    roles = columns.List(value_type=columns.Text)
    picture_id = columns.UUID(default=None)

    def get_id(self):
        return str(self.id)

    def __str__(self):
        return f"User('{self.id}','{self.username}')"

    def to_json(self):
        return {
            "id": str(self.id),
            "username": self.username,
            "full_name": self.full_name,
            "picture_id": self.picture_id
        }


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
    assignee = columns.List(value_type=columns.UUID)
    picture_id = columns.UUID()
    enabled = columns.Boolean(default=lambda: True)
    perpetual = columns.Boolean(default=lambda: True)

    def __eq__(self, other):
        if isinstance(other, ArgusRelease):
            return self.name == other.name
        else:
            return super().__eq__(other)


class ArgusReleaseGroup(Model):
    __table_name__ = "argus_group_v2"
    id = columns.UUID(primary_key=True, default=uuid4)
    release_id = columns.UUID(required=True, index=True)
    name = columns.Text(required=True, index=True)
    pretty_name = columns.Text()
    description = columns.Text()
    assignee = columns.List(value_type=columns.UUID)
    enabled = columns.Boolean(default=lambda: True)

    def __eq__(self, other):
        if isinstance(other, ArgusReleaseGroup):
            return self.name == other.name and self.release_id == other.release_id
        else:
            return super().__eq__(other)


class ArgusReleaseGroupTest(Model):
    __table_name__ = "argus_test_v2"
    id = columns.UUID(primary_key=True, default=uuid4)
    group_id = columns.UUID(required=True, index=True)
    release_id = columns.UUID(required=True, index=True)
    name = columns.Text(required=True, index=True)
    pretty_name = columns.Text()
    description = columns.Text()
    assignee = columns.List(value_type=columns.UUID)
    enabled = columns.Boolean(default=lambda: True)

    def __eq__(self, other):
        if isinstance(other, ArgusReleaseGroupTest):
            return self.name == other.name and self.group_id == other.group_id and self.release_id == other.release_id
        else:
            return super().__eq__(other)


class ArgusPlannedTestsForRelease(Model):
    id = columns.UUID(primary_key=True, default=uuid4, partition_key=True)
    release_id = columns.UUID(required=True, index=True)
    group_id = columns.UUID(required=True, index=True)
    test_id = columns.UUID(required=True, index=True)


class ArgusTestRunComment(Model):
    id = columns.UUID(primary_key=True, default=uuid4, partition_key=True)
    test_run_id = columns.UUID(required=True, index=True)
    user_id = columns.UUID(required=True, index=True)
    release_id = columns.UUID(required=True, index=True)
    posted_at = columns.Integer(
        required=True, clustering_order="desc", primary_key=True)
    message = columns.Text(min_length=1)
    mentions = columns.List(value_type=columns.UUID, default=[])
    reactions = columns.Map(key_type=columns.Text, value_type=columns.Integer)


class ArgusEventTypes(str, Enum):
    AssigneeChanged = "ARGUS_ASSIGNEE_CHANGE"
    TestRunStatusChanged = "ARGUS_TEST_RUN_STATUS_CHANGE"
    TestRunInvestigationStatusChanged = "ARGUS_TEST_RUN_INVESTIGATION_STATUS_CHANGE"
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


class ArgusReleaseSchedule(Model):
    release = columns.Text(primary_key=True, required=True)
    schedule_id = columns.TimeUUID(
        primary_key=True, default=uuid1, clustering_order="DESC")
    period_start = columns.DateTime(required=True, default=datetime.utcnow)
    period_end = columns.DateTime(required=True)
    tag = columns.Text(default="")


class ArgusReleaseScheduleAssignee(Model):
    assignee = columns.UUID(primary_key=True)
    id = columns.TimeUUID(primary_key=True, default=uuid1,
                          clustering_order="DESC")
    schedule_id = columns.TimeUUID(required=True, index=True)
    release = columns.Text(required=True)


class ArgusReleaseScheduleTest(Model):
    name = columns.Text(partition_key=True)
    release = columns.Text(partition_key=True)
    id = columns.TimeUUID(primary_key=True, default=uuid1,
                          clustering_order="DESC")
    schedule_id = columns.TimeUUID(required=True, index=True)


class ArgusReleaseScheduleGroup(Model):
    name = columns.Text(partition_key=True)
    release = columns.Text(partition_key=True)
    id = columns.TimeUUID(primary_key=True, default=uuid1,
                          clustering_order="DESC")
    schedule_id = columns.TimeUUID(required=True, index=True)


class ReleasePlannerComment(Model):
    release = columns.Text(primary_key=True)
    group = columns.Text(primary_key=True)
    test = columns.Text(primary_key=True)
    comment = columns.Text(default=lambda: "")


class WebRunComments(Model):
    test_id = columns.UUID(primary_key=True, default=uuid4)
    comments = columns.List(
        value_type=UserDefinedType(WebRunComment), default=list)

    def get_comments_by_user(self, user: User):
        return [(idx, comment) for idx, comment in enumerate(self.comments) if comment.user_id == user.id]

    def to_json(self):
        return {
            'test': self.test_id,
            'comments': [comment.to_json() for comment in self.comments]  # pylint: disable=not-an-iterable
        }


class WebFileStorage(Model):
    id = columns.UUID(primary_key=True, default=uuid4)
    filepath = columns.Text(min_length=1)
    filename = columns.Text(min_length=1)


class WebRelease(Model):
    id = columns.UUID(primary_key=True, default=uuid4)
    name = columns.Text(min_length=1)
    pretty_name = columns.Text()
    description = columns.Text()
    picture_id = columns.UUID()


class WebCategoryGroup(Model):
    id = columns.UUID(primary_key=True, default=uuid4)
    name = columns.Text(min_length=1)
    pretty_name = columns.Text()
    description = columns.Text()


class WebNemesis(Model):
    id = columns.UUID(primary_key=True, default=uuid4)
    name = columns.Text(min_length=1)
    pretty_name = columns.Text()
    description = columns.Text()


USED_MODELS = [
    User, WebRunComments, WebRelease, WebCategoryGroup, WebNemesis,
    ArgusRelease, ArgusReleaseGroup, ArgusReleaseGroupTest, ArgusPlannedTestsForRelease,
    ArgusTestRunComment, ArgusEvent, UserOauthToken,
    WebFileStorage, ArgusGithubIssue, ReleasePlannerComment,
    ArgusReleaseSchedule, ArgusReleaseScheduleAssignee, ArgusReleaseScheduleGroup, ArgusReleaseScheduleTest
]
USED_TYPES = [WebRunComment]
