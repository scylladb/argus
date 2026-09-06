from typing import Any

import httpx

from qatools_health.checks.primitives import HttpHealthCheck
from qatools_health.result import HealthCheckResult

GITHUB_API_URL = "https://api.github.com"
ANTHROPIC_API_URL = "https://api.anthropic.com"
ANTHROPIC_VERSION = "2023-06-01"


def join(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


class JenkinsApiHealthCheck(HttpHealthCheck):
    name = "jenkins_api"
    critical = True
    interval = 120.0

    def __init__(
        self,
        base_url: str,
        user: str | None = None,
        token: str | None = None,
        *,
        client: httpx.AsyncClient | None = None,
        **kwargs: Any,
    ) -> None:
        auth = httpx.BasicAuth(user, token) if user and token else None
        super().__init__(join(base_url, "api/json?tree=mode"), auth=auth, client=client, **kwargs)


class JiraApiHealthCheck(HttpHealthCheck):
    name = "jira_api"
    interval = 300.0

    def __init__(
        self,
        base_url: str,
        email: str | None = None,
        token: str | None = None,
        *,
        client: httpx.AsyncClient | None = None,
        **kwargs: Any,
    ) -> None:
        auth = httpx.BasicAuth(email, token) if email and token else None
        super().__init__(join(base_url, "rest/api/3/myself"), auth=auth, client=client, **kwargs)


class GitHubApiHealthCheck(HttpHealthCheck):
    name = "github_api"
    interval = 300.0

    def __init__(
        self,
        token: str,
        expected_login: str | None = None,
        *,
        base_url: str = GITHUB_API_URL,
        client: httpx.AsyncClient | None = None,
        **kwargs: Any,
    ) -> None:
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }
        self.base_url = base_url
        self.expected_login = expected_login
        super().__init__(join(base_url, "rate_limit"), headers=headers, client=client, **kwargs)

    async def perform_check(self) -> Any:
        response = await self.request(self.url)
        if response.status_code not in self.expect:
            return HealthCheckResult(self.failure_status, f"rate_limit answered {response.status_code}")
        core = response.json().get("resources", {}).get("core", {})
        budget = f"{core.get('remaining', '?')}/{core.get('limit', '?')} core requests left"

        if self.expected_login is None:
            return HealthCheckResult.healthy(budget)

        identity = await self.request(join(self.base_url, "user"))
        if identity.status_code not in self.expect:
            return HealthCheckResult(self.failure_status, f"user answered {identity.status_code}")
        login = identity.json().get("login")
        if login != self.expected_login:
            return HealthCheckResult(
                self.failure_status,
                f"the token belongs to {login!r}, expected {self.expected_login!r}",
            )
        return HealthCheckResult.healthy(f"{login}, {budget}")


class ArgusApiHealthCheck(HttpHealthCheck):
    name = "argus_api"
    interval = 300.0

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        cf_id: str | None = None,
        cf_secret: str | None = None,
        *,
        client: httpx.AsyncClient | None = None,
        **kwargs: Any,
    ) -> None:
        headers = {}
        if token:
            headers["Authorization"] = f"token {token}"
        if cf_id and cf_secret:
            headers["CF-Access-Client-Id"] = cf_id
            headers["CF-Access-Client-Secret"] = cf_secret
        url = join(base_url, "api/v1/notifications/get_unread")
        super().__init__(url, headers=headers, client=client, **kwargs)


class AnthropicApiHealthCheck(HttpHealthCheck):
    name = "llm_api"
    critical = True
    interval = 300.0

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = ANTHROPIC_API_URL,
        client: httpx.AsyncClient | None = None,
        **kwargs: Any,
    ) -> None:
        headers = {"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION}
        super().__init__(join(base_url, "v1/models"), headers=headers, client=client, **kwargs)


class HeadroomProxyHealthCheck(HttpHealthCheck):
    name = "headroom_proxy"
    interval = 120.0

    def __init__(self, url: str, *, client: httpx.AsyncClient | None = None, **kwargs: Any) -> None:
        super().__init__(url, client=client, **kwargs)


class MaiaApiHealthCheck(HttpHealthCheck):
    name = "maia_api"
    interval = 300.0

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        *,
        path: str = "",
        client: httpx.AsyncClient | None = None,
        **kwargs: Any,
    ) -> None:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        super().__init__(join(base_url, path), headers=headers, client=client, **kwargs)
