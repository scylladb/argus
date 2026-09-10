"""The checks over the HTTP APIs the QA services depend on."""

import time
from typing import Any

import httpx

from qatools_health.checks.primitives import HttpHealthCheck
from qatools_health.result import HealthCheckResult
from qatools_health.status import HealthCheckStatus, Severity

GITHUB_API_URL = "https://api.github.com"
GITHUB_LOW_BUDGET_FRACTION = 0.1
ANTHROPIC_API_URL = "https://api.anthropic.com"
ANTHROPIC_VERSION = "2023-06-01"
ANTHROPIC_STATUS_URL = "https://status.anthropic.com/api/v2/summary.json"
ANTHROPIC_STATUS_COMPONENT = "Claude API (api.anthropic.com)"
ANTHROPIC_PROBE_MODEL = "claude-haiku-4-5"

COMPONENT_STATUS: dict[str, HealthCheckStatus] = {
    "operational": HealthCheckStatus.HEALTHY,
    "degraded_performance": HealthCheckStatus.DEGRADED,
    "under_maintenance": HealthCheckStatus.DEGRADED,
    "partial_outage": HealthCheckStatus.DEGRADED,
    "major_outage": HealthCheckStatus.UNHEALTHY,
}

ANTHROPIC_FAILURE_STATUS: dict[int, HealthCheckStatus] = {
    429: HealthCheckStatus.DEGRADED,
    529: HealthCheckStatus.DEGRADED,
}


def join(base_url: str, path: str) -> str:
    """Join a base URL and a path with exactly one slash between them."""
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def base_of(base_url: str | None, client: httpx.AsyncClient | None, dependency: str) -> str:
    """Return the base URL of a dependency, from the argument or from the client."""
    if base_url:
        return base_url
    carried = str(client.base_url) if client is not None else ""
    if carried:
        return carried
    raise ValueError(f"{dependency} needs a base URL, either its own or one the client carries")


def api_error_message(response: httpx.Response) -> str:
    """Pull the human-readable error out of a JSON error body."""
    try:
        payload = response.json()
    except ValueError:
        return response.reason_phrase
    detail = payload.get("error", {}) if isinstance(payload, dict) else {}
    return detail.get("message", "") or response.reason_phrase


def reset_hint(reset: object, now: float | None = None) -> str:
    """Render a rate-limit reset time as the minutes left before it."""
    if not isinstance(reset, int | float) or isinstance(reset, bool):
        return ""
    seconds = max(0.0, float(reset) - (time.time() if now is None else now))
    return f", resets in {seconds / 60:.0f}m"


class JenkinsApiHealthCheck(HttpHealthCheck):
    """Jenkins answers an authenticated read of its mode."""

    name = "jenkins_api"
    interval = 120.0

    def __init__(
        self,
        base_url: str | None = None,
        user: str | None = None,
        token: str | None = None,
        *,
        client: httpx.AsyncClient | None = None,
        **kwargs: Any,
    ) -> None:
        auth = httpx.BasicAuth(user, token) if user and token else None
        base = base_of(base_url, client, "jenkins_api")
        super().__init__(join(base, "api/json?tree=mode"), auth=auth, credential=(user, token), client=client, **kwargs)


class JiraApiHealthCheck(HttpHealthCheck):
    """Jira answers with the account the credentials belong to."""

    name = "jira_api"
    interval = 300.0

    def __init__(
        self,
        base_url: str | None = None,
        email: str | None = None,
        token: str | None = None,
        *,
        client: httpx.AsyncClient | None = None,
        **kwargs: Any,
    ) -> None:
        auth = httpx.BasicAuth(email, token) if email and token else None
        base = base_of(base_url, client, "jira_api")
        super().__init__(join(base, "rest/api/3/myself"), auth=auth, credential=(email, token), client=client, **kwargs)


class GitHubApiHealthCheck(HttpHealthCheck):
    """The GitHub token works, and it has requests left to spend.

    A spent core budget is UNHEALTHY, and a budget under low_budget_fraction of
    the limit is DEGRADED. A token that answers but has nothing left cannot do
    the work, so the budget is part of the verdict. Pass an expected login to
    also confirm which account the token belongs to.
    """

    name = "github_api"
    interval = 300.0

    def __init__(
        self,
        token: str,
        expected_login: str | None = None,
        *,
        base_url: str = GITHUB_API_URL,
        low_budget_fraction: float = GITHUB_LOW_BUDGET_FRACTION,
        client: httpx.AsyncClient | None = None,
        **kwargs: Any,
    ) -> None:
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }
        self.base_url = base_url
        self.expected_login = expected_login
        self.low_budget_fraction = low_budget_fraction
        super().__init__(join(base_url, "rate_limit"), headers=headers, client=client, **kwargs)

    async def perform_check(self) -> Any:
        """Read the rate limit, then compare the login when one is expected."""
        response = await self.request(self.url)
        if response.status_code not in self.expect:
            return HealthCheckResult.unhealthy(
                f"rate_limit answered {response.status_code}{self._header_hint(response)}"
            )

        core = response.json().get("resources", {}).get("core", {})
        budget = f"{core.get('remaining', '?')}/{core.get('limit', '?')} core requests left"
        spent = self._budget_verdict(core, budget)
        if spent is not None:
            return spent
        if self.expected_login is None:
            return HealthCheckResult.healthy(budget)
        return await self._compare_the_login(budget)

    def _budget_verdict(self, core: dict[str, Any], budget: str) -> HealthCheckResult | None:
        remaining = core.get("remaining")
        window = reset_hint(core.get("reset"))
        if remaining == 0:
            return HealthCheckResult.unhealthy(f"the GitHub rate limit is spent, {budget}{window}")
        if self._is_low(remaining, core.get("limit")):
            return HealthCheckResult.degraded(f"the GitHub rate limit is nearly spent, {budget}{window}")
        return None

    async def _compare_the_login(self, budget: str) -> HealthCheckResult:
        identity = await self.request(join(self.base_url, "user"))
        if identity.status_code not in self.expect:
            return HealthCheckResult.unhealthy(f"user answered {identity.status_code}{self._header_hint(identity)}")
        login = identity.json().get("login")
        if login != self.expected_login:
            return HealthCheckResult.unhealthy(f"the token belongs to {login!r}, expected {self.expected_login!r}")
        return HealthCheckResult.healthy(f"{login}, {budget}")

    def _is_low(self, remaining: object, limit: object) -> bool:
        if not isinstance(remaining, int) or not isinstance(limit, int) or limit <= 0:
            return False
        return remaining <= limit * self.low_budget_fraction

    def _header_hint(self, response: httpx.Response) -> str:
        if response.headers.get("x-ratelimit-remaining") != "0":
            return ""
        return f", the rate limit is spent{reset_hint(self._header_reset(response))}"

    def _header_reset(self, response: httpx.Response) -> object:
        raw = response.headers.get("x-ratelimit-reset", "")
        return int(raw) if raw.isdigit() else None


class ArgusApiHealthCheck(HttpHealthCheck):
    """Argus answers an authenticated read, through Cloudflare Access when needed."""

    name = "argus_api"
    interval = 300.0

    def __init__(
        self,
        base_url: str | None = None,
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
        base = base_of(base_url, client, "argus_api")
        super().__init__(join(base, "api/v1/notifications/get_unread"), headers=headers, client=client, **kwargs)


class AnthropicApiHealthCheck(HttpHealthCheck):
    """The Claude API is up, and the key can spend on it.

    The check reads the Claude API component on the public status page first,
    and returns at once on an outage. It then sends one completion of one token.
    Only a completion proves that the key is authorized, has credit, and is
    inside its rate limit. A 429 or a 529 is DEGRADED, because both clear on
    their own. The API pins every model identifier, so model names a real model
    and moves when that model retires.
    """

    name = "llm_api"
    severity = Severity.CRITICAL
    interval = 300.0
    method = "POST"

    def __init__(
        self,
        api_key: str,
        *,
        model: str = ANTHROPIC_PROBE_MODEL,
        base_url: str = ANTHROPIC_API_URL,
        status_url: str = ANTHROPIC_STATUS_URL,
        component: str = ANTHROPIC_STATUS_COMPONENT,
        client: httpx.AsyncClient | None = None,
        **kwargs: Any,
    ) -> None:
        headers = {
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        self.model = model
        self.status_url = status_url
        self.component = component
        super().__init__(join(base_url, "v1/messages"), headers=headers, client=client, **kwargs)

    async def perform_check(self) -> Any:
        """Grade the platform status, then spend one token on the key."""
        platform = await self.read_platform_status()
        if platform is not None and platform[0] is not HealthCheckStatus.HEALTHY:
            status, detail = platform
            return HealthCheckResult(status, detail)
        return await self.probe_the_key()

    async def read_platform_status(self) -> tuple[HealthCheckStatus, str] | None:
        """Grade the Claude API component on the status page.

        Return None when the page is unreachable, refuses, or lists no such
        component. An unreachable status page is not a verdict on the API.
        """
        try:
            response = await self.client().get(self.status_url)
        except httpx.HTTPError:
            return None
        if response.status_code not in self.expect:
            return None
        for component in response.json().get("components", []):
            if component.get("name") != self.component:
                continue
            indicator = component.get("status", "")
            status = COMPONENT_STATUS.get(indicator, HealthCheckStatus.DEGRADED)
            return status, f"{self.component} is {indicator.replace('_', ' ')}"
        return None

    async def probe_the_key(self) -> HealthCheckResult:
        """Spend one token to prove the key is authorized and funded."""
        payload = {
            "model": self.model,
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "ping"}],
        }
        response = await self.request(self.url, json=payload)
        if response.status_code in self.expect:
            return HealthCheckResult.healthy(f"{self.model} answered")
        status = ANTHROPIC_FAILURE_STATUS.get(response.status_code, HealthCheckStatus.UNHEALTHY)
        return HealthCheckResult(status, f"v1/messages answered {response.status_code}: {api_error_message(response)}")
