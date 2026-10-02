"""Read the health process answer for the navigation bar."""

import ipaddress
import logging
from functools import cache
from typing import Any

import httpx2
from qatools_health import Severity

from argus.backend.service.health.app import PENDING
from argus.backend.service.health.config import DEFAULT_HOST, TOKEN_SCHEME, configured_address, configured_token

LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 2
WILDCARD_HOSTS = {"0.0.0.0", "::", ""}


@cache
def health_client() -> httpx2.AsyncClient:
    return httpx2.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, trust_env=False)


def settled_status(checks: list[dict[str, Any]]) -> str:
    if any(check["status"] == "unhealthy" and check["severity"] == Severity.CRITICAL for check in checks):
        return "unhealthy"
    if any(check["status"] != "healthy" and check["severity"] != Severity.OPTIONAL for check in checks):
        return "degraded"
    return "healthy"


def url_host(host: str) -> str:
    try:
        is_ipv6 = ipaddress.ip_address(host).version == 6
    except ValueError:
        is_ipv6 = False
    return f"[{host}]" if is_ipv6 else host


class HealthSummaryService:
    """Ask the health process for /health and keep what a user needs to see.

    The summary holds the aggregate status and the checks that are not
    healthy. A pending check has not finished its first run, so the summary
    leaves it out until it has a result. A health process that does not answer
    reads as unknown, because the workers keep serving while it is down.
    """

    def __init__(self, config: dict[str, Any], client: httpx2.AsyncClient | None = None) -> None:
        self.config = config
        self.client = client or health_client()

    def health_url(self) -> str:
        """Return the /health URL of the health process as a worker reaches it."""
        host, port = configured_address(self.config)
        if host in WILDCARD_HOSTS:
            host = DEFAULT_HOST
        return f"http://{url_host(host)}:{port}/health"

    def headers(self) -> dict[str, str]:
        token = configured_token(self.config)
        return {"Authorization": f"{TOKEN_SCHEME} {token}"} if token else {}

    async def get_summary(self) -> dict[str, Any]:
        """Return enabled, the aggregate status, and the failing checks."""
        if not self.config.get("HEALTH_ENABLED"):
            return {"enabled": False, "status": "unknown", "failing": []}
        try:
            response = await self.client.get(self.health_url(), headers=self.headers())
            if response.status_code != 200:
                raise ValueError(f"/health answered {response.status_code}")
            settled = [
                {"name": check["name"], "severity": check["severity"], "status": check["status"]}
                for check in response.json().get("checks", [])
                if check["status"] != PENDING
            ]
        except (httpx2.HTTPError, httpx2.InvalidURL, ValueError, KeyError, TypeError, AttributeError) as exc:
            LOGGER.warning("The health process did not answer: %r", exc)
            return {"enabled": True, "status": "unknown", "failing": []}
        failing = [check for check in settled if check["status"] != "healthy"]
        return {"enabled": True, "status": settled_status(settled), "failing": failing}
