from datetime import UTC, datetime
import uuid
from types import SimpleNamespace

import pytest

from argus.backend.models.web import User
from argus.backend.service import user as user_service


def _cf_config(**overrides) -> dict:
    config = {
        "CLOUDFLARE_ACCESS_TEAM_DOMAIN": "scylladb.cloudflareaccess.com",
        "CLOUDFLARE_ACCESS_AUD": "test-aud",
        "LOGIN_METHODS": ["cf"],
    }
    config.update(overrides)
    return config


def test_cf_access_payload_valid(monkeypatch):
    fake_client = SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key="key"))
    config = _cf_config(CLOUDFLARE_ACCESS_JWK_CLIENT=fake_client)

    def fake_decode(token, key, algorithms, audience, issuer):
        assert audience == config["CLOUDFLARE_ACCESS_AUD"]
        assert issuer == "https://scylladb.cloudflareaccess.com"
        return {"email": "user@scylladb.com"}

    monkeypatch.setattr(user_service.jwt, "decode", fake_decode)

    payload = user_service._get_cf_access_payload("token", config)
    assert payload == {"email": "user@scylladb.com"}


def test_cf_access_payload_invalid(monkeypatch):
    fake_client = SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key="key"))
    config = _cf_config(CLOUDFLARE_ACCESS_JWK_CLIENT=fake_client)

    def fake_decode(*args, **kwargs):
        raise user_service.jwt.PyJWTError("bad token")

    monkeypatch.setattr(user_service.jwt, "decode", fake_decode)

    with pytest.raises(user_service.UserServiceException):
        user_service._get_cf_access_payload("token", config)


def test_cf_access_payload_missing_config():
    with pytest.raises(user_service.UserServiceException):
        user_service._get_cf_access_payload("token", {"LOGIN_METHODS": ["cf"]})


def test_user_creation_rejects_non_scylladb_domain(monkeypatch, argus_db):
    monkeypatch.setattr(user_service, "_get_cf_access_payload",
                        lambda _token, _config: {"email": "user@example.com"})
    with pytest.raises(user_service.UserServiceException):
        user_service._get_user_from_cf_access("token", _cf_config())


def test_user_creation_rejects_missing_email(monkeypatch, argus_db):
    monkeypatch.setattr(user_service, "_get_cf_access_payload", lambda _token, _config: {})
    with pytest.raises(user_service.UserServiceException):
        user_service._get_user_from_cf_access("token", _cf_config())


def test_user_cf_access_returns_existing_user_by_email(monkeypatch, argus_db):
    existing = User(id=uuid.uuid4(), username=f"cf-access-{uuid.uuid4().hex[:8]}", roles=["ROLE_USER"], password="", registration_date=datetime.now(UTC))
    existing.email = f"{existing.username}@scylladb.com"
    existing.save()

    monkeypatch.setattr(user_service, "_get_cf_access_payload",
                        lambda _token, _config: {"email": existing.email})

    res = user_service._get_user_from_cf_access("token", _cf_config())
    assert res["exists"]
    assert res["user"].id == existing.id


def test_user_cf_access_returns_none_when_user_missing(monkeypatch, argus_db):
    email = f"missing-{uuid.uuid4().hex[:8]}@scylladb.com"
    monkeypatch.setattr(user_service, "_get_cf_access_payload", lambda _token, _config: {"email": email})
    res = user_service._get_user_from_cf_access("token", _cf_config())
    assert res["user"] is None
    assert not res["exists"]
