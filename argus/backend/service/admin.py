
from flask import g, current_app, session

from argus.backend.db import ScyllaCluster
from argus.backend.models.web import (
    ArgusGithubIssue,
    ArgusRelease,
    ArgusGroup,
    ArgusTest,
    ArgusSchedule,
    ArgusScheduleAssignee,
    ArgusScheduleGroup,
    ArgusScheduleTest,
    ArgusTestRunComment,
    ArgusEvent,
    ArgusEventTypes,
    ReleasePlannerComment,
    User,
    UserOauthToken,
    WebFileStorage,
)


class AdminService:
    def __init__(self, database_session=None):
        self.session = database_session if database_session else ScyllaCluster.get_session()
        self.database = ScyllaCluster.get()
