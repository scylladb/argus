import ipaddress
from typing import Any

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9300


TOKEN_SCHEME = "token"


def configured_address(config: dict[str, Any]) -> tuple[str, int]:
    return config.get("HEALTH_HOST") or DEFAULT_HOST, int(config.get("HEALTH_PORT") or DEFAULT_PORT)


def configured_token(config: dict[str, Any]) -> str | None:
    return config.get("HEALTH_TOKEN") or None


def is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"
