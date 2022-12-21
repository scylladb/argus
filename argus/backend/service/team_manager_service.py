import logging
from uuid import UUID

from flask.globals import g
from argus.backend.db import ScyllaCluster
from argus.backend.models.web import Team, User

LOGGER = logging.getLogger(__name__)


class TeamManagerException(Exception):
    pass


class TeamManagerService:
    # pylint: disable=no-self-use
    def __init__(self, database: ScyllaCluster | None = None) -> None:
        if not database:
            database = ScyllaCluster.get()

        self.session = database.get_session()
        self.database = database

    def create_team(self, name: str, leader: UUID, members: list[UUID]):
        team = Team()
        team.name = name
        team.leader = leader
        team.members = [leader, *members]

        team.save()
        return team

    def get_teams_for_user(self, user_id: UUID) -> list[Team]:
        return list(Team.filter(leader=user_id).all())

    def get_team_by_id(self, team_id: UUID) -> Team:
        try:
            return Team.get(id=team_id)
        except Team.DoesNotExist as exc:
            raise TeamManagerException(f"Team {team_id} does not exist", team_id) from exc

    def edit_team(self, team_id: UUID, name: str, members: list[UUID]):
        user: User = g.user
        try:
            team: Team = Team.get(id=team_id)
            if team.leader != user.id:
                raise TeamManagerException(f"Cannot edit team \"{team.name}\" as it doesn't belong to the user.")
            team.name = name
            team.members = [team.leader, *members] if team.leader not in members else members

            team.save()

            return team
        except Team.DoesNotExist as exc:
            raise TeamManagerException(f"Team {team_id} doesn't exist!", team_id) from exc

    def edit_team_motd(self, team_id: UUID, message: str):
        user: User = g.user
        try:
            team: Team = Team.get(id=team_id)
            if team.leader != user.id:
                raise TeamManagerException(f"Cannot edit team \"{team.name}\"'s MOTD as it doesn't belong to the user.")
            team.motd = message

            team.save()
        except Team.DoesNotExist as exc:
            raise TeamManagerException(f"Team {team_id} doesn't exist!", team_id) from exc

    def delete_team(self, team_id: UUID):
        user: User = g.user
        try:
            team: Team = Team.get(id=team_id)
            if team.leader != user.id:
                raise TeamManagerException(f"Cannot delete team \"{team.name}\" as it doesn't belong to the user.")
            team.delete()
        except Team.DoesNotExist as exc:
            raise TeamManagerException(f"Team {team_id} doesn't exist!", team_id) from exc

    def get_users_teams(self, user_id: UUID) -> list[Team]:
        teams_containing_user = list(Team.all())
        users_teams = self.get_teams_for_user(user_id)
        created_teams_ids = [team.id for team in users_teams]
        return [*users_teams, *[team for team in teams_containing_user if team.id not in created_teams_ids]]
