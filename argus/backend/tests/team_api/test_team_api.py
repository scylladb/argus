import uuid

import pytest
from flask import g

from argus.backend.models.web import Team, User, UserRoles


def _make_user() -> User:
    user = User(
        id=uuid.uuid4(),
        username=f"team_user_{uuid.uuid4().hex[:8]}",
        full_name="Team User",
        email=f"team_{uuid.uuid4().hex[:8]}@scylladb.com",
        password="pw",
        roles=[UserRoles.User.value],
    )
    user.save()
    return user


@pytest.fixture
def team_member():
    return _make_user()


@pytest.fixture
def team_member_2():
    return _make_user()


@pytest.fixture(autouse=True)
def cleanup_teams():
    yield
    for team in list(Team.all()):
        team.delete()


def _create_team(flask_client, name=None, leader_id=None, members=None):
    payload = {
        "name": name or f"team_{uuid.uuid4().hex[:8]}",
        "leader": str(leader_id or g.user.id),
        "members": [str(m) for m in (members or [])],
    }
    return flask_client.post("/api/v1/team/create", json=payload).json


def test_team_create_includes_leader_in_members(flask_client, team_member):
    res = _create_team(flask_client, members=[team_member.id])
    assert res["status"] == "ok"
    team_id = res["response"]["id"]
    fetched = flask_client.get(f"/api/v1/team/{team_id}/get").json
    assert fetched["status"] == "ok"
    member_ids = {str(m) for m in fetched["response"]["members"]}
    assert str(g.user.id) in member_ids
    assert str(team_member.id) in member_ids
    assert fetched["response"]["leader"] == str(g.user.id)


def test_team_get_unknown_id_errors(flask_client):
    res = flask_client.get(f"/api/v1/team/{uuid.uuid4()}/get").json
    assert res["status"] == "error"
    assert "does not exist" in res["response"]["arguments"][0]


def test_team_edit_updates_name_and_members(flask_client, team_member, team_member_2):
    created = _create_team(flask_client, members=[team_member.id])["response"]
    team_id = created["id"]

    res = flask_client.post(
        f"/api/v1/team/{team_id}/edit",
        json={
            "id": team_id,
            "name": "renamed-team",
            "members": [str(team_member_2.id)],
        },
    ).json
    assert res["status"] == "ok"
    assert res["response"]["status"] == "updated"

    fetched = flask_client.get(f"/api/v1/team/{team_id}/get").json["response"]
    assert fetched["name"] == "renamed-team"
    member_ids = {str(m) for m in fetched["members"]}
    assert str(g.user.id) in member_ids  # leader auto-included
    assert str(team_member_2.id) in member_ids
    assert str(team_member.id) not in member_ids


def test_team_edit_by_non_leader_errors(flask_client, team_member):
    other_leader = _make_user()
    created = _create_team(flask_client, leader_id=other_leader.id)["response"]
    team_id = created["id"]

    res = flask_client.post(
        f"/api/v1/team/{team_id}/edit",
        json={"id": team_id, "name": "hijack", "members": []},
    ).json
    assert res["status"] == "error"
    assert "doesn't belong to the user" in res["response"]["arguments"][0]


def test_team_edit_motd_success(flask_client):
    created = _create_team(flask_client)["response"]
    team_id = created["id"]

    res = flask_client.post(
        f"/api/v1/team/{team_id}/motd/edit",
        json={"id": team_id, "motd": "hello-team"},
    ).json
    assert res["status"] == "ok"

    fetched = flask_client.get(f"/api/v1/team/{team_id}/get").json["response"]
    assert fetched["motd"] == "hello-team"


def test_team_edit_motd_by_non_leader_errors(flask_client):
    other_leader = _make_user()
    team_id = _create_team(flask_client, leader_id=other_leader.id)["response"]["id"]
    res = flask_client.post(
        f"/api/v1/team/{team_id}/motd/edit",
        json={"id": team_id, "motd": "nope"},
    ).json
    assert res["status"] == "error"
    assert "doesn't belong to the user" in res["response"]["arguments"][0]


def test_team_delete_success(flask_client):
    team_id = _create_team(flask_client)["response"]["id"]
    res = flask_client.delete(f"/api/v1/team/{team_id}/delete").json
    assert res["status"] == "ok"
    assert res["response"]["status"] == "deleted"

    after = flask_client.get(f"/api/v1/team/{team_id}/get").json
    assert after["status"] == "error"


def test_team_delete_by_non_leader_errors(flask_client):
    other_leader = _make_user()
    team_id = _create_team(flask_client, leader_id=other_leader.id)["response"]["id"]
    res = flask_client.delete(f"/api/v1/team/{team_id}/delete").json
    assert res["status"] == "error"
    assert "doesn't belong to the user" in res["response"]["arguments"][0]


def test_team_delete_unknown_id_errors(flask_client):
    res = flask_client.delete(f"/api/v1/team/{uuid.uuid4()}/delete").json
    assert res["status"] == "error"
    assert "doesn't exist" in res["response"]["arguments"][0]


def test_leader_teams_lists_owned_teams(flask_client):
    a = _create_team(flask_client)["response"]["id"]
    b = _create_team(flask_client)["response"]["id"]
    res = flask_client.get(f"/api/v1/team/leader/{g.user.id}/teams").json
    assert res["status"] == "ok"
    ids = {t["id"] for t in res["response"]}
    assert {a, b}.issubset(ids)


def test_leader_teams_other_user_empty(flask_client):
    _create_team(flask_client)
    other = _make_user()
    res = flask_client.get(f"/api/v1/team/leader/{other.id}/teams").json
    assert res["status"] == "ok"
    assert res["response"] == []


def test_user_teams_includes_owned_and_member(flask_client, team_member):
    owned = _create_team(flask_client)["response"]["id"]
    other_leader = _make_user()
    member_team = _create_team(flask_client, leader_id=other_leader.id, members=[g.user.id])["response"]["id"]

    res = flask_client.get(f"/api/v1/team/user/{g.user.id}/teams").json
    assert res["status"] == "ok"
    ids = {t["id"] for t in res["response"]}
    assert owned in ids
    assert member_team in ids


def test_user_jobs_returns_empty_for_unassigned_user(flask_client):
    user = _make_user()
    res = flask_client.get(f"/api/v1/team/user/{user.id}/jobs").json
    assert res["status"] == "ok"
    assert res["response"] == []
