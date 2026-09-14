"""The checks over the HTTP APIs the QA services depend on."""

import time
from collections.abc import Callable
from typing import Any, TypeIs, override

import httpx

from qatools_health.checks.primitives import HttpHealthCheck
from qatools_health.result import HealthCheckResult
from qatools_health.status import HealthCheckStatus, Severity

GITHUB_API_URL = "https://api.github.com"
GITHUB_LOW_BUDGET_FRACTION = 0.1
GITHUB_DEFAULT_WAIT_SECONDS = 60.0
ANTHROPIC_API_URL = "https://api.anthropic.com"
ANTHROPIC_VERSION = "2023-06-01"
ANTHROPIC_STATUS_URL = "https://status.claude.com/api/v2/summary.json"
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


def json_object(response: httpx.Response) -> dict[str, Any] | None:
    """Return the body as a JSON object, or None when the body is not one.

    An HTML interstitial, an empty body and a JSON list all give None, so a
    caller grades a malformed answer instead of raising out of the check.
    """
    try:
        payload = response.json()
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def api_error_message(response: httpx.Response) -> str:
    """Pull the human-readable error out of a JSON error body."""
    detail = (json_object(response) or {}).get("error")
    if isinstance(detail, dict) and isinstance(detail.get("message"), str) and detail["message"]:
        return detail["message"]
    if isinstance(detail, str) and detail:
        return detail
    return response.reason_phrase


def is_whole_number(value: object) -> TypeIs[int]:
    """Report whether a JSON value is an integer, which a boolean is not."""
    return isinstance(value, int) and not isinstance(value, bool)


def github_message(response: httpx.Response) -> str:
    """Return the message of a GitHub error body, or the reason phrase when it has none."""
    payload = json_object(response) or {}
    message = payload.get("message")
    if isinstance(message, str) and message:
        return message
    return api_error_message(response)


def wait_text(seconds: float) -> str:
    """Render a wait as whole seconds under two minutes, and as minutes above that."""
    seconds = max(0.0, seconds)
    if seconds < 120:
        return f"{seconds:.0f}s"
    return f"{seconds / 60:.0f}m"


def header_number(response: httpx.Response, name: str) -> int | None:
    """Return a header that holds a whole number, or None when it holds anything else."""
    raw = response.headers.get(name, "").strip()
    return int(raw) if raw.isdigit() else None


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

    The check follows the GitHub rate limit rules. A 403 or a 429 with
    x-ratelimit-remaining at 0 hits the primary rate limit, and the check sends
    no request before x-ratelimit-reset. A 403 or a 429 with retry-after hits a
    secondary rate limit, and the check waits that many seconds. Any other 429,
    or a 403 whose message names a rate limit, waits one minute. A core budget
    of 0 in the rate_limit body also waits for its reset. The check reports
    UNHEALTHY for the whole wait.
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
        clock: Callable[[], float] = time.time,
        **kwargs: Any,
    ) -> None:
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }
        self.base_url = base_url
        self.expected_login = expected_login
        self.low_budget_fraction = low_budget_fraction
        self._clock = clock
        self._wait_until = 0.0
        self._wait_reason = ""
        self._wait_label = ""
        super().__init__(join(base_url, "rate_limit"), headers=headers, client=client, **kwargs)

    @override
    async def perform_check(self) -> Any:
        """Read the rate limit, then compare the login when one is expected.

        While a rate limit wait is in force, the check sends no request and
        reports the wait.
        """
        waiting = self._waiting()
        if waiting is not None:
            return waiting

        response = await self.request(self.url)
        refused = self._refusal("rate_limit", response)
        if refused is not None:
            return refused

        payload = json_object(response)
        resources = payload.get("resources") if payload is not None else None
        core = resources.get("core") if isinstance(resources, dict) else None
        if not isinstance(core, dict):
            return HealthCheckResult.unhealthy("rate_limit answered without a core budget")
        budget = f"{core.get('remaining', '?')}/{core.get('limit', '?')} core requests left"
        spent = self._budget_verdict(core, budget)
        if spent is not None:
            return spent
        if self.expected_login is None:
            return HealthCheckResult.healthy(budget)
        return await self._compare_the_login(budget)

    def _waiting(self) -> HealthCheckResult | None:
        left = self._wait_until - self._clock()
        if left <= 0:
            return None
        return HealthCheckResult.unhealthy(
            f"{self._wait_reason}, {self._wait_label} {wait_text(left)}, no request sent"
        )

    def _wait(self, until: float, reason: str, label: str) -> HealthCheckResult:
        self._wait_until = until
        self._wait_reason = reason
        self._wait_label = label
        return HealthCheckResult.unhealthy(f"{reason}, {label} {wait_text(until - self._clock())}")

    def _refusal(self, route: str, response: httpx.Response) -> HealthCheckResult | None:
        status = response.status_code
        if status in self.expect:
            return None
        if status not in {403, 429}:
            return HealthCheckResult.unhealthy(f"{route} answered {status}")

        now = self._clock()
        remaining = header_number(response, "x-ratelimit-remaining")
        reset = header_number(response, "x-ratelimit-reset")
        retry_after = header_number(response, "retry-after")

        if remaining == 0:
            until = float(reset) if reset is not None else now + GITHUB_DEFAULT_WAIT_SECONDS
            return self._wait(until, f"{route} answered {status}, the GitHub primary rate limit is spent", "resets in")
        if retry_after is not None:
            return self._wait(
                now + retry_after, f"{route} answered {status}, a GitHub secondary rate limit is hit", "retry in"
            )
        message = github_message(response)
        if status == 429 or "rate limit" in message.lower():
            return self._wait(
                now + GITHUB_DEFAULT_WAIT_SECONDS,
                f"{route} answered {status}, a GitHub secondary rate limit is hit",
                "retry in",
            )
        return HealthCheckResult.unhealthy(f"{route} answered {status}: {message}")

    def _budget_verdict(self, core: dict[str, Any], budget: str) -> HealthCheckResult | None:
        remaining = core.get("remaining")
        reset = core.get("reset")
        if remaining == 0 and is_whole_number(reset):
            return self._wait(float(reset), f"the GitHub rate limit is spent, {budget}", "resets in")
        if remaining == 0:
            return HealthCheckResult.unhealthy(f"the GitHub rate limit is spent, {budget}")
        if self._is_low(remaining, core.get("limit")):
            window = f", resets in {wait_text(reset - self._clock())}" if is_whole_number(reset) else ""
            return HealthCheckResult.degraded(f"the GitHub rate limit is nearly spent, {budget}{window}")
        return None

    async def _compare_the_login(self, budget: str) -> HealthCheckResult:
        identity = await self.request(join(self.base_url, "user"))
        refused = self._refusal("user", identity)
        if refused is not None:
            return refused
        login = (json_object(identity) or {}).get("login")
        if login != self.expected_login:
            return HealthCheckResult.unhealthy(f"the token belongs to {login!r}, expected {self.expected_login!r}")
        return HealthCheckResult.healthy(f"{login}, {budget}")

    def _is_low(self, remaining: object, limit: object) -> bool:
        if not is_whole_number(remaining) or not is_whole_number(limit) or limit <= 0:
            return False
        return remaining <= limit * self.low_budget_fraction


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

    @override
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
        components = (json_object(response) or {}).get("components")
        if not isinstance(components, list):
            return None
        for component in components:
            if not isinstance(component, dict) or component.get("name") != self.component:
                continue
            indicator = str(component.get("status", ""))
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
