import base64

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from argus.backend.db import ScyllaCluster

KEY_INFO = b"argus-chat-token"


class SecretUnreadableError(Exception):
    pass


def _fernet(secret: str | None) -> Fernet:
    secret = secret if secret is not None else str(ScyllaCluster.get().config["SECRET_KEY"])
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=KEY_INFO).derive(secret.encode("utf-8"))
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(text: str, secret: str | None = None) -> str:
    return _fernet(secret).encrypt(text.encode("utf-8")).decode("ascii")


def decrypt(token: str, secret: str | None = None) -> str:
    try:
        return _fernet(secret).decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as exception:
        raise SecretUnreadableError("The stored secret cannot be decrypted with the current SECRET_KEY") from exception
