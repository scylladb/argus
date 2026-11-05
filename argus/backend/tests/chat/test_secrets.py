import pytest

from argus.backend.util.secrets import SecretUnreadableError, decrypt, encrypt


def test_a_secret_round_trips_and_is_not_stored_in_clear():
    token = encrypt("sk-live-123", secret="one")

    assert "sk-live-123" not in token
    assert decrypt(token, secret="one") == "sk-live-123"


def test_another_secret_key_cannot_read_it():
    token = encrypt("sk-live-123", secret="one")

    with pytest.raises(SecretUnreadableError):
        decrypt(token, secret="two")
