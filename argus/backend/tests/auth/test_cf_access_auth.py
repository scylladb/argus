import uuid
from types import SimpleNamespace

import pytest
from flask import current_app

from argus.backend.models.web import User
from argus.backend.service import user as user_service


def _set_cf_config():
    current_app.config["CLOUDFLARE_ACCESS_TEAM_DOMAIN"] = "scylladb.cloudflareaccess.com"
    current_app.config["CLOUDFLARE_ACCESS_AUD"] = "test-aud"
    current_app.config["LOGIN_METHODS"] = ["cf"]


def test_cf_access_payload_valid(monkeypatch, argus_app):
    with argus_app.app_context():
        _set_cf_config()
        fake_client = SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key="key"))
        current_app.config["CLOUDFLARE_ACCESS_JWK_CLIENT"] = fake_client

        def fake_decode(token, key, algorithms, audience, issuer):
            assert audience == current_app.config["CLOUDFLARE_ACCESS_AUD"]
            assert issuer == "https://scylladb.cloudflareaccess.com"
            return {"email": "user@scylladb.com"}

        monkeypatch.setattr(user_service.jwt, "decode", fake_decode)

        payload = user_service._get_cf_access_payload("token")
        assert payload["email"] == "user@scylladb.com"


def test_cf_access_payload_invalid(monkeypatch, argus_app):
    with argus_app.app_context():
        _set_cf_config()
        fake_client = SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key="key"))
        current_app.config["CLOUDFLARE_ACCESS_JWK_CLIENT"] = fake_client

        def fake_decode(*_args, **_kwargs):
            raise user_service.jwt.PyJWTError("bad token")

        monkeypatch.setattr(user_service.jwt, "decode", fake_decode)

        with pytest.raises(user_service.UserServiceException):
            user_service._get_cf_access_payload("token")


def test_cf_access_payload_missing_config(argus_app):
    with argus_app.app_context():
        current_app.config.pop("CLOUDFLARE_ACCESS_TEAM_DOMAIN", None)
        current_app.config.pop("CLOUDFLARE_ACCESS_AUD", None)
        current_app.config["LOGIN_METHODS"] = ["cf"]
        with pytest.raises(user_service.UserServiceException):
            user_service._get_cf_access_payload("token")


def test_user_creation_rejects_non_scylladb_domain(monkeypatch, argus_app, argus_db):
    with argus_app.app_context():
        _set_cf_config()
        monkeypatch.setattr(user_service, "_get_cf_access_payload", lambda _token: {"email": "user@example.com"})
        with pytest.raises(user_service.UserServiceException):
            user_service._get_user_from_cf_access("token")


def test_user_creation_rejects_missing_email(monkeypatch, argus_app, argus_db):
    with argus_app.app_context():
        _set_cf_config()
        monkeypatch.setattr(user_service, "_get_cf_access_payload", lambda _token: {})
        with pytest.raises(user_service.UserServiceException):
            user_service._get_user_from_cf_access("token")


def test_user_cf_access_returns_existing_user_by_email(monkeypatch, argus_app, argus_db):
    with argus_app.app_context():
        _set_cf_config()
        existing = User()
        existing.username = f"user-{uuid.uuid4()}"
        existing.email = f"{existing.username}@scylladb.com"
        existing.roles = ["ROLE_USER"]
        existing.save()
        monkeypatch.setattr(user_service, "_get_cf_access_payload", lambda _token: {"email": existing.email})

        res = user_service._get_user_from_cf_access("token")
        assert res["user"] is not None
        assert res["user"].id == existing.id
        assert res["exists"]


def test_user_cf_access_returns_none_when_user_missing(monkeypatch, argus_app, argus_db):
    with argus_app.app_context():
        _set_cf_config()
        email = f"user-{uuid.uuid4()}@scylladb.com"
        monkeypatch.setattr(user_service, "_get_cf_access_payload", lambda _token: {"email": email})
        res = user_service._get_user_from_cf_access("token")
        assert res["user"] is None
        assert not res["exists"]
