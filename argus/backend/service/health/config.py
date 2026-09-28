from typing import Any

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9300


def configured_address(config: dict[str, Any]) -> tuple[str, int]:
    return config.get("HEALTH_HOST") or DEFAULT_HOST, int(config.get("HEALTH_PORT") or DEFAULT_PORT)
