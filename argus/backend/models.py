from uuid import uuid4
from cassandra.cqlengine.models import Model
from cassandra.cqlengine.usertype import UserType
from cassandra.cqlengine import columns
from cassandra.cqlengine.columns import UserDefinedType


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
            "picture_id": self.picture_id
        }


class ArgusRelease(Model):
    id = columns.UUID(primary_key=True, default=uuid4)
    name = columns.Text(index=True, required=True)
    pretty_name = columns.Text()
    description = columns.Text()
    assignee = columns.List(value_type=columns.UUID)
    picture_id = columns.UUID()

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
    posted_at = columns.Integer(required=True)
    message = columns.Text(min_length=1)
    mentions = columns.List(value_type=columns.UUID, default=[])

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


USED_MODELS = [User, WebRunComments, WebRelease, WebCategoryGroup, WebNemesis, ArgusRelease, ArgusReleaseGroup, ArgusReleaseGroupTest, ArgusPlannedTestsForRelease, ArgusTestRunComment]
USED_TYPES = [WebRunComment]
