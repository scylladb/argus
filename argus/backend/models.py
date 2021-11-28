from uuid import uuid4
from cassandra.cqlengine.models import Model
from cassandra.cqlengine.usertype import UserType
from cassandra.cqlengine import columns
from cassandra.cqlengine.columns import UserDefinedType
from enum import Enum


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

    def is_active(self):
        return True

    def is_anonymous(self):
        return False

    def is_authenticated(self):
        return True

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
    id = columns.UUID(primary_key=True, default=uuid4)
    name = columns.Text(index=True, required=True)
    pretty_name = columns.Text()
    description = columns.Text()
    github_repo_url = columns.Text()
    assignee = columns.List(value_type=columns.UUID)
    picture_id = columns.UUID()
    enabled = columns.Boolean(default=lambda: True)


class ArgusReleaseGroup(Model):
    id = columns.UUID(primary_key=True, default=uuid4)
    release_id = columns.UUID(required=True, index=True)
    name = columns.Text(required=True, index=True)
    pretty_name = columns.Text()
    description = columns.Text()
    assignee = columns.List(value_type=columns.UUID)


class ArgusReleaseGroupTest(Model):
    id = columns.UUID(primary_key=True, default=uuid4)
    group_id = columns.UUID(required=True, index=True)
    release_id = columns.UUID(required=True, index=True)
    name = columns.Text(required=True, index=True)
    pretty_name = columns.Text()
    description = columns.Text()
    assignee = columns.List(value_type=columns.UUID)


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
    posted_at = columns.Integer(required=True, clustering_order="desc", primary_key=True)
    message = columns.Text(min_length=1)
    mentions = columns.List(value_type=columns.UUID, default=[])


class ArgusEventTypes(str, Enum):
    AssigneeChanged = "ARGUS_ASSIGNEE_CHANGE"
    TestRunStatusChanged = "ARGUS_TEST_RUN_STATUS_CHANGE"
    TestRunCommentPosted = "ARGUS_TEST_RUN_COMMENT_POSTED"
    TestRunIssueAdded = "ARGUS_TEST_RUN_ISSUE_ADDED"


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
    id = columns.UUID(primary_key=True, default=uuid4, partition_key=True)
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


class WebRunComments(Model):
    test_id = columns.UUID(primary_key=True, default=uuid4)
    comments = columns.List(value_type=UserDefinedType(WebRunComment), default=list)

    def get_comments_by_user(self, user: User):
        return [(idx, comment) for idx, comment in enumerate(self.comments) if comment.user_id == user.id]

    def to_json(self):
        return {
            'test': self.test_id,
            'comments': [comment.to_json() for comment in self.comments]
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


USED_MODELS = [User, WebRunComments, WebRelease, WebCategoryGroup, WebNemesis,
               ArgusRelease, ArgusReleaseGroup, ArgusReleaseGroupTest, ArgusPlannedTestsForRelease, ArgusTestRunComment, ArgusEvent, UserOauthToken, WebFileStorage, ArgusGithubIssue]
USED_TYPES = [WebRunComment]
