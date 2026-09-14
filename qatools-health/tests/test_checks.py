import asyncio
import json
import logging
import sys
import time
from pathlib import Path

import aiosqlite
import httpx
import pytest

from qatools_health import HealthCheckRunner, HealthCheckStatus, Severity
from qatools_health.checks.http_apis import (
    ANTHROPIC_PROBE_MODEL,
    ANTHROPIC_STATUS_COMPONENT,
    ANTHROPIC_STATUS_URL,
    base_of,
    wait_text,
)
from qatools_health.checks.primitives import first_line
from qatools_health.checks import (
    AcliHealthCheck,
    AnthropicApiHealthCheck,
    ArgusApiHealthCheck,
    ArgusCliHealthCheck,
    BinaryHealthCheck,
    GhCliHealthCheck,
    GitHubApiHealthCheck,
    HttpHealthCheck,
    JenkinsApiHealthCheck,
    JenkinsCliHealthCheck,
    JiraApiHealthCheck,
    OpencodeHealthCheck,
    SqliteHealthCheck,
    StalenessHealthCheck,
    TcpHealthCheck,
)

HEALTHY = HealthCheckStatus.HEALTHY
DEGRADED = HealthCheckStatus.DEGRADED
UNHEALTHY = HealthCheckStatus.UNHEALTHY


def stub_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def responder(status=200, json=None):
    def handle(request):
        handle.requests.append(request)
        return httpx.Response(status, json=json if json is not None else {})

    handle.requests = []
    return handle


async def test_http_check_reports_the_status_code():
    handler = responder(200)
    check = HttpHealthCheck("https://example.test/ping", name="ping", client=stub_client(handler))
    assert (await check.perform_check()).status is HEALTHY


@pytest.mark.parametrize("status", [200, 201, 202, 204])
async def test_http_check_accepts_every_success_code(status):
    check = HttpHealthCheck("https://example.test/ping", name="ping", client=stub_client(responder(status)))
    result = await check.perform_check()
    assert result.status is HEALTHY
    assert str(status) in result.message


async def test_http_check_fails_on_an_unexpected_status():
    check = HttpHealthCheck("https://example.test/ping", name="ping", client=stub_client(responder(503)))
    result = await check.perform_check()
    assert result.status is UNHEALTHY
    assert "503" in result.message


async def test_http_check_degrades_over_its_latency_budget():
    async def slow(request):
        await asyncio.sleep(0.02)
        return httpx.Response(200)

    check = HttpHealthCheck(
        "https://example.test/ping",
        name="ping",
        latency_budget=0.001,
        client=stub_client(slow),
    )
    assert (await check.perform_check()).status is DEGRADED


async def test_http_check_never_closes_a_client_it_received():
    client = stub_client(responder(200))
    check = HttpHealthCheck("https://example.test/ping", name="ping", client=client)
    await check.aclose()
    assert client.is_closed is False
    await client.aclose()


async def test_http_check_closes_a_client_it_built():
    check = HttpHealthCheck("https://example.test/ping", name="ping")
    built = check.client()
    await check.aclose()
    assert built.is_closed is True


async def test_jenkins_probes_the_cheap_mode_read():
    handler = responder(200)
    check = JenkinsApiHealthCheck("https://jenkins.test/", "user", "token", client=stub_client(handler))
    await check.perform_check()
    assert str(handler.requests[0].url) == "https://jenkins.test/api/json?tree=mode"
    assert check.name == "jenkins_api"
    assert check.severity is Severity.IMPORTANT


async def test_jira_probes_myself():
    handler = responder(200)
    check = JiraApiHealthCheck("https://jira.test", "a@b.test", "token", client=stub_client(handler))
    await check.perform_check()
    assert handler.requests[0].url.path == "/rest/api/3/myself"


async def test_github_reports_the_remaining_budget():
    handler = responder(200, {"resources": {"core": {"remaining": 4200, "limit": 5000}}})
    check = GitHubApiHealthCheck("token", client=stub_client(handler))
    result = await check.perform_check()
    assert result.status is HEALTHY
    assert "4200/5000" in result.message
    assert len(handler.requests) == 1


async def test_github_compares_the_login_when_one_is_expected():
    def handle(request):
        if request.url.path == "/rate_limit":
            return httpx.Response(200, json={"resources": {"core": {"remaining": 4200, "limit": 5000}}})
        return httpx.Response(200, json={"login": "someone-else"})

    check = GitHubApiHealthCheck("token", "zeus-bot", client=stub_client(handle))
    result = await check.perform_check()
    assert result.status is UNHEALTHY
    assert "someone-else" in result.message


async def test_github_accepts_the_expected_login():
    def handle(request):
        if request.url.path == "/rate_limit":
            return httpx.Response(200, json={"resources": {"core": {"remaining": 4200, "limit": 5000}}})
        return httpx.Response(200, json={"login": "zeus-bot"})

    check = GitHubApiHealthCheck("token", "zeus-bot", client=stub_client(handle))
    assert (await check.perform_check()).status is HEALTHY


async def test_github_fails_when_rate_limit_refuses():
    check = GitHubApiHealthCheck("token", client=stub_client(responder(401)))
    assert (await check.perform_check()).status is UNHEALTHY


async def test_github_reports_a_spent_rate_limit():
    reset = int(time.time()) + 900
    handler = responder(200, {"resources": {"core": {"remaining": 0, "limit": 5000, "reset": reset}}})
    check = GitHubApiHealthCheck("token", "zeus-bot", client=stub_client(handler))
    result = await check.perform_check()
    assert result.status is UNHEALTHY
    assert "rate limit is spent" in result.message
    assert "0/5000" in result.message
    assert "resets in 15m" in result.message
    assert len(handler.requests) == 1


async def test_github_degrades_before_the_rate_limit_runs_out():
    handler = responder(200, {"resources": {"core": {"remaining": 400, "limit": 5000}}})
    result = await GitHubApiHealthCheck("token", client=stub_client(handler)).perform_check()
    assert result.status is DEGRADED
    assert "nearly spent" in result.message


async def test_github_names_the_rate_limit_behind_a_refusal():
    def handle(request):
        return httpx.Response(
            403, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(int(time.time()) + 60)}
        )

    result = await GitHubApiHealthCheck("token", client=stub_client(handle)).perform_check()
    assert result.status is UNHEALTHY
    assert "403" in result.message
    assert "rate limit is spent" in result.message


async def test_argus_sends_the_token_and_the_access_headers():
    handler = responder(200)
    check = ArgusApiHealthCheck("https://argus.test", "abc", "cf-id", "cf-secret", client=stub_client(handler))
    await check.perform_check()
    request = handler.requests[0]
    assert request.url.path == "/api/v1/notifications/get_unread"
    assert request.headers["Authorization"] == "token abc"
    assert request.headers["CF-Access-Client-Id"] == "cf-id"


def anthropic_stub(component="operational", messages_status=200, messages_json=None, components=None):
    listed = components if components is not None else [{"name": ANTHROPIC_STATUS_COMPONENT, "status": component}]

    def handle(request):
        handle.requests.append(request)
        if request.url.host == "status.claude.com":
            return httpx.Response(200, json={"components": listed})
        return httpx.Response(messages_status, json=messages_json if messages_json is not None else {})

    handle.requests = []
    return handle


async def test_anthropic_probes_the_status_page_then_the_key():
    handler = anthropic_stub()
    check = AnthropicApiHealthCheck("key", client=stub_client(handler))
    result = await check.perform_check()
    assert result.status is HEALTHY
    assert [str(request.url) for request in handler.requests] == [
        ANTHROPIC_STATUS_URL,
        "https://api.anthropic.com/v1/messages",
    ]
    probe = handler.requests[1]
    assert probe.method == "POST"
    assert probe.headers["x-api-key"] == "key"
    assert json.loads(probe.content) == {
        "model": ANTHROPIC_PROBE_MODEL,
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "ping"}],
    }
    assert check.name == "llm_api"
    assert check.severity is Severity.CRITICAL


async def test_anthropic_never_sends_the_key_to_the_status_page():
    handler = anthropic_stub()
    await AnthropicApiHealthCheck("key", client=stub_client(handler)).perform_check()
    assert "x-api-key" not in handler.requests[0].headers


@pytest.mark.parametrize(
    ("component", "expected"),
    [("degraded_performance", DEGRADED), ("partial_outage", DEGRADED), ("major_outage", UNHEALTHY)],
)
async def test_anthropic_stops_at_a_platform_outage(component, expected):
    handler = anthropic_stub(component)
    result = await AnthropicApiHealthCheck("key", client=stub_client(handler)).perform_check()
    assert result.status is expected
    assert component.replace("_", " ") in result.message
    assert len(handler.requests) == 1


async def test_anthropic_probes_the_key_when_the_component_is_absent():
    handler = anthropic_stub(components=[{"name": "Console", "status": "major_outage"}])
    result = await AnthropicApiHealthCheck("key", client=stub_client(handler)).perform_check()
    assert result.status is HEALTHY
    assert len(handler.requests) == 2


async def test_anthropic_probes_the_key_when_the_status_page_is_unreachable():
    def handle(request):
        handle.requests.append(request)
        if request.url.host == "status.claude.com":
            raise httpx.ConnectError("no route", request=request)
        return httpx.Response(200, json={})

    handle.requests = []
    result = await AnthropicApiHealthCheck("key", client=stub_client(handle)).perform_check()
    assert result.status is HEALTHY


async def test_anthropic_reports_a_rejected_key():
    handler = anthropic_stub(
        messages_status=401,
        messages_json={"error": {"type": "authentication_error", "message": "invalid x-api-key"}},
    )
    result = await AnthropicApiHealthCheck("key", client=stub_client(handler)).perform_check()
    assert result.status is UNHEALTHY
    assert "invalid x-api-key" in result.message


async def test_anthropic_reports_an_empty_credit_balance():
    handler = anthropic_stub(
        messages_status=400,
        messages_json={"error": {"type": "invalid_request_error", "message": "credit balance is too low"}},
    )
    result = await AnthropicApiHealthCheck("key", client=stub_client(handler)).perform_check()
    assert result.status is UNHEALTHY
    assert "credit balance is too low" in result.message


@pytest.mark.parametrize("status", [429, 529])
async def test_anthropic_only_degrades_on_a_transient_refusal(status):
    handler = anthropic_stub(messages_status=status, messages_json={"error": {"message": "slow down"}})
    result = await AnthropicApiHealthCheck("key", client=stub_client(handler)).perform_check()
    assert result.status is DEGRADED
    assert "slow down" in result.message


def test_anthropic_keeps_the_probe_model_in_its_identity():
    key = "key"
    assert AnthropicApiHealthCheck(key).identity() != AnthropicApiHealthCheck(key, model="claude-opus-5").identity()


async def test_tcp_check_reaches_a_listening_port():
    server = await asyncio.start_server(lambda reader, writer: writer.close(), "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        check = TcpHealthCheck("127.0.0.1", port, name="tunnel")
        assert (await check.perform_check()).status is HEALTHY


async def test_tcp_check_raises_on_a_closed_port():
    with pytest.raises(OSError):
        await TcpHealthCheck("127.0.0.1", 1, name="tunnel", timeout=1).perform_check()


async def test_binary_check_reports_the_version():
    check = BinaryHealthCheck(sys.executable, version_args=("--version",), name="python")
    result = await check.perform_check()
    assert result.status is HEALTHY
    assert "Python" in result.message


async def test_binary_check_fails_when_the_binary_is_missing():
    check = BinaryHealthCheck("qatools-health-no-such-binary", name="missing")
    result = await check.perform_check()
    assert result.status is UNHEALTHY
    assert "not on PATH" in result.message


async def test_binary_check_fails_on_a_non_zero_exit():
    check = BinaryHealthCheck(sys.executable, version_args=("-c", "raise SystemExit(3)"), name="python")
    result = await check.perform_check()
    assert result.status is UNHEALTHY
    assert "exited 3" in result.message


def test_binary_check_needs_a_binary():
    with pytest.raises(ValueError, match="no binary"):
        BinaryHealthCheck(name="empty")


def test_the_cli_classes_carry_their_defaults():
    assert OpencodeHealthCheck().name == "opencode"
    assert OpencodeHealthCheck().severity is Severity.CRITICAL
    assert GhCliHealthCheck().name == "gh"
    assert GhCliHealthCheck().severity is Severity.IMPORTANT


async def test_gh_skips_the_auth_probe_by_default():
    check = GhCliHealthCheck(name="gh")
    assert check.verify_auth is False


async def test_sqlite_check_queries_a_live_connection():
    connection = await aiosqlite.connect(":memory:")
    check = SqliteHealthCheck(connection, name="sqlite:context")
    result = await check.perform_check()
    assert result.status is HEALTHY
    assert check.name == "sqlite:context"
    await connection.close()


async def test_sqlite_check_names_itself_from_a_path(tmp_path):
    db_path = tmp_path / "context.db"
    async with aiosqlite.connect(db_path):
        pass
    check = SqliteHealthCheck(db_path)
    assert check.name == "sqlite:context"
    assert (await check.perform_check()).status is HEALTHY


async def test_sqlite_check_fails_on_a_missing_file_without_creating_it(tmp_path):
    db_path = tmp_path / "absent.db"
    check = SqliteHealthCheck(db_path)
    result = await check.perform_check()
    assert result.status is UNHEALTHY
    assert "does not exist" in result.message
    assert not db_path.exists()


async def test_sqlite_check_never_creates_the_file_it_opens(tmp_path, monkeypatch):
    db_path = tmp_path / "vanishing.db"
    check = SqliteHealthCheck(db_path)
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    with pytest.raises(aiosqlite.OperationalError):
        await check.perform_check()
    assert not db_path.exists()


async def test_sqlite_check_raises_on_a_broken_query():
    connection = await aiosqlite.connect(":memory:")
    check = SqliteHealthCheck(connection, query="SELECT * FROM missing", name="sqlite:broken")
    with pytest.raises(aiosqlite.OperationalError):
        await check.perform_check()
    await connection.close()


async def test_staleness_reports_the_three_bands():
    now = 1_000_000.0
    check = StalenessHealthCheck(lambda: now - 10, 60, 600, name="jenkins_poll", clock=lambda: now)
    assert (await check.perform_check()).status is HEALTHY

    check = StalenessHealthCheck(lambda: now - 100, 60, 600, name="jenkins_poll", clock=lambda: now)
    assert (await check.perform_check()).status is DEGRADED

    check = StalenessHealthCheck(lambda: now - 1000, 60, 600, name="jenkins_poll", clock=lambda: now)
    assert (await check.perform_check()).status is UNHEALTHY


async def test_staleness_handles_a_missing_timestamp():
    check = StalenessHealthCheck(lambda: None, 60, 600, name="jenkins_poll")
    assert (await check.perform_check()).status is UNHEALTHY


async def test_staleness_awaits_an_async_getter():
    async def last_poll():
        return 1_000_000.0

    check = StalenessHealthCheck(last_poll, 60, 600, name="jenkins_poll", clock=lambda: 1_000_010.0)
    assert (await check.perform_check()).status is HEALTHY


def test_staleness_needs_a_name():
    with pytest.raises(ValueError, match="has no name"):
        StalenessHealthCheck(lambda: 0.0, 60, 600)


def test_staleness_rejects_an_inverted_window():
    with pytest.raises(ValueError, match="warn_after"):
        StalenessHealthCheck(lambda: 0.0, 600, 60, name="jenkins_poll")


async def test_http_check_honours_a_custom_method():
    handler = responder(200)
    check = HttpHealthCheck("https://example.test/ping", method="HEAD", name="ping", client=stub_client(handler))
    await check.perform_check()
    assert handler.requests[0].method == "HEAD"


async def test_gh_merges_the_auth_probe_when_asked():
    check = GhCliHealthCheck(binary=sys.executable, version_args=("--version",), name="gh", verify_auth=True)
    result = await check.perform_check()
    assert result.status is UNHEALTHY
    assert "gh auth status exited" in result.message


async def test_gh_reports_a_missing_binary_before_the_auth_probe():
    check = GhCliHealthCheck(binary="qatools-health-no-such-binary", name="gh", verify_auth=True)
    assert "not on PATH" in (await check.perform_check()).message


def test_first_line_ignores_blank_output():
    assert first_line("\n   \n") == ""
    assert first_line("gh version 2.40.0\nhttps://example") == "gh version 2.40.0"


async def test_gh_reports_an_authenticated_cli(tmp_path, monkeypatch):
    fake = tmp_path / "gh"
    fake.write_text('#!/bin/sh\nif [ "$1" = "--version" ]; then echo \'gh version 2.40.0\'; fi\nexit 0\n')
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    result = await GhCliHealthCheck(verify_auth=True).perform_check()
    assert result.status is HEALTHY
    assert result.message.endswith("authenticated")


async def test_github_fails_when_the_identity_read_refuses():
    def handle(request):
        if request.url.path == "/rate_limit":
            return httpx.Response(200, json={"resources": {"core": {"remaining": 4200, "limit": 5000}}})
        return httpx.Response(403)

    check = GitHubApiHealthCheck("token", "zeus-bot", client=stub_client(handle))
    result = await check.perform_check()
    assert result.status is UNHEALTHY
    assert "user answered 403" in result.message


async def test_jenkins_takes_its_base_url_from_the_client_it_was_given():
    handler = responder(200)
    client = httpx.AsyncClient(base_url="https://jenkins.test", transport=httpx.MockTransport(handler))
    check = JenkinsApiHealthCheck(client=client)
    await check.perform_check()
    assert str(handler.requests[0].url) == "https://jenkins.test/api/json?tree=mode"


def test_one_jenkins_reached_two_ways_is_one_dependency():
    client = httpx.AsyncClient(base_url="https://jenkins.test")
    assert (
        JenkinsApiHealthCheck(client=client, user="user", token="token").identity()
        == JenkinsApiHealthCheck("https://jenkins.test", "user", "token").identity()
    )


def test_two_jenkins_credentials_are_two_dependencies():
    assert (
        JenkinsApiHealthCheck("https://jenkins.test", "user", "one").identity()
        != JenkinsApiHealthCheck("https://jenkins.test", "user", "two").identity()
    )


def test_the_transport_client_never_reaches_the_identity():
    first = httpx.AsyncClient(base_url="https://jenkins.test")
    second = httpx.AsyncClient(base_url="https://jenkins.test")
    assert JenkinsApiHealthCheck(client=first).identity() == JenkinsApiHealthCheck(client=second).identity()


def test_an_api_check_needs_a_base_url_from_somewhere():
    with pytest.raises(ValueError, match="needs a base URL"):
        JenkinsApiHealthCheck()
    with pytest.raises(ValueError, match="needs a base URL"):
        base_of(None, httpx.AsyncClient(), "jira_api")


def test_two_urls_are_two_http_dependencies():
    first = HttpHealthCheck("https://one.test/ping", name="ping")
    second = HttpHealthCheck("https://two.test/ping", name="ping")
    assert first.identity() != second.identity()


def test_the_expected_login_is_part_of_the_github_identity():
    assert GitHubApiHealthCheck("token").identity() != GitHubApiHealthCheck("token", "zeus-bot").identity()


def test_a_class_default_and_the_same_value_passed_are_one_dependency():
    assert (
        HttpHealthCheck("https://one.test/ping", name="ping").identity()
        == HttpHealthCheck("https://one.test/ping", name="ping", method="GET").identity()
    )
    assert (
        BinaryHealthCheck("gh", name="gh").identity()
        == BinaryHealthCheck("gh", name="gh", version_args=("--version",)).identity()
    )
    assert GhCliHealthCheck().identity() == GhCliHealthCheck(verify_auth=False).identity()


def test_a_class_default_overridden_is_another_dependency():
    assert GhCliHealthCheck().identity() != GhCliHealthCheck(verify_auth=True).identity()
    assert (
        HttpHealthCheck("https://one.test/ping", name="ping").identity()
        != HttpHealthCheck("https://one.test/ping", name="ping", method="HEAD").identity()
    )


def test_a_subclass_of_a_shipped_check_is_another_dependency():
    class GitHubEnterpriseHealthCheck(GitHubApiHealthCheck):
        pass

    base = GitHubApiHealthCheck("token")
    derived = GitHubEnterpriseHealthCheck("token")
    assert base.identity_fields() == derived.identity_fields()
    assert base.identity() != derived.identity()


def test_a_subclass_that_changes_a_default_is_another_dependency():
    class SlowHttpHealthCheck(HttpHealthCheck):
        method = "HEAD"

    base = HttpHealthCheck("https://one.test/ping", name="ping")
    derived = SlowHttpHealthCheck("https://one.test/ping", name="ping")
    assert base.identity_fields() != derived.identity_fields()
    assert base.identity() != derived.identity()


def test_behavior_and_bookkeeping_stay_out_of_the_identity():
    fields = GitHubApiHealthCheck("token").identity_fields()
    assert "perform_check" not in fields
    assert not [key for key in fields if key.startswith("_")]
    assert not [key for key in fields if callable(fields[key])]


def test_two_github_tokens_are_two_dependencies():
    assert GitHubApiHealthCheck("token", "zeus-bot").identity() != GitHubApiHealthCheck("other", "zeus-bot").identity()
    assert GitHubApiHealthCheck("token").identity() != GitHubApiHealthCheck("other").identity()


def test_one_github_token_registered_twice_is_one_dependency():
    assert GitHubApiHealthCheck("token", "zeus-bot").identity() == GitHubApiHealthCheck("token", "zeus-bot").identity()


def test_two_enterprise_hosts_are_two_dependencies():
    assert (
        GitHubApiHealthCheck("token", base_url="https://one.test/api/v3").identity()
        != GitHubApiHealthCheck("token", base_url="https://two.test/api/v3").identity()
    )


def test_two_anthropic_keys_are_two_dependencies():
    assert AnthropicApiHealthCheck("key-one").identity() != AnthropicApiHealthCheck("key-two").identity()


def test_two_probe_models_are_two_dependencies():
    assert (
        AnthropicApiHealthCheck("key", model="claude-haiku-4-5").identity()
        != AnthropicApiHealthCheck("key", model="claude-sonnet-5").identity()
    )


def test_one_host_on_two_ports_is_two_dependencies():
    assert TcpHealthCheck("db.test", 5432, name="a").identity() != TcpHealthCheck("db.test", 5433, name="b").identity()


def test_the_policy_never_reaches_the_identity():
    assert (
        GitHubApiHealthCheck("token", interval=10, severity=Severity.CRITICAL, timeout=1).identity()
        == GitHubApiHealthCheck("token", interval=600, severity=Severity.OPTIONAL, timeout=9).identity()
    )


async def test_the_sqlite_check_is_critical():
    connection = await aiosqlite.connect(":memory:")
    assert SqliteHealthCheck(connection, name="sqlite:context").severity is Severity.CRITICAL
    await connection.close()


@pytest.mark.parametrize("status", [301, 302, 304, 307, 308])
async def test_http_check_fails_on_a_redirect(status):
    def handle(request):
        return httpx.Response(status, headers={"location": "https://example.test/login"})

    result = await HttpHealthCheck("https://example.test/ping", name="ping", client=stub_client(handle)).perform_check()
    assert result.status is UNHEALTHY
    assert str(status) in result.message


async def test_http_check_never_follows_a_redirect_even_on_a_following_client():
    def handle(request):
        handle.paths.append(request.url.path)
        if request.url.path == "/ping":
            return httpx.Response(302, headers={"location": "https://example.test/login"})
        return httpx.Response(200)

    handle.paths = []
    client = httpx.AsyncClient(transport=httpx.MockTransport(handle), follow_redirects=True)
    result = await HttpHealthCheck("https://example.test/ping", name="ping", client=client).perform_check()
    assert result.status is UNHEALTHY
    assert handle.paths == ["/ping"]


async def test_http_check_keeps_the_auth_of_a_client_it_received():
    handler = responder(200)
    client = httpx.AsyncClient(
        base_url="https://jenkins.test",
        auth=httpx.BasicAuth("user", "pass"),
        transport=httpx.MockTransport(handler),
    )
    assert (await JenkinsApiHealthCheck(client=client).perform_check()).status is HEALTHY
    assert handler.requests[0].headers["Authorization"] == httpx.BasicAuth("user", "pass")._auth_header


async def test_http_check_sends_its_own_auth_over_the_client_auth():
    handler = responder(200)
    client = httpx.AsyncClient(
        base_url="https://jenkins.test",
        auth=httpx.BasicAuth("client", "secret"),
        transport=httpx.MockTransport(handler),
    )
    await JenkinsApiHealthCheck(client=client, user="check", token="token").perform_check()
    assert handler.requests[0].headers["Authorization"] == httpx.BasicAuth("check", "token")._auth_header


@pytest.mark.parametrize(
    ("check_class", "name", "binary"),
    [
        (OpencodeHealthCheck, "opencode", "opencode"),
        (GhCliHealthCheck, "gh", "gh"),
        (AcliHealthCheck, "acli", "acli"),
        (ArgusCliHealthCheck, "argus_cli", "argus"),
        (JenkinsCliHealthCheck, "jenkins_cli", "jenkins-cli"),
    ],
)
def test_every_cli_class_keeps_its_declared_name(check_class, name, binary):
    check = check_class()
    assert (check.name, check.binary) == (name, binary)


def test_a_bare_binary_check_takes_the_binary_as_its_name():
    assert BinaryHealthCheck("kubectl").name == "kubectl"
    assert BinaryHealthCheck("kubectl", name="k8s").name == "k8s"


async def test_a_cancelled_binary_check_kills_the_process(monkeypatch):
    spawned = []
    original = asyncio.create_subprocess_exec

    async def capture(*argv, **kwargs):
        process = await original(*argv, **kwargs)
        spawned.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", capture)
    check = BinaryHealthCheck(sys.executable, version_args=("-c", "import time; time.sleep(30)"), name="hung")
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(check.perform_check(), 0.5)
    assert spawned[0].returncode is not None


async def test_github_names_a_spent_rate_limit_in_the_transition_log(caplog):
    reset = int(time.time()) + 600
    handler = responder(200, {"resources": {"core": {"remaining": 0, "limit": 5000, "reset": reset}}})
    runner = HealthCheckRunner(service="zeus")
    subscription = runner.register(GitHubApiHealthCheck("token", client=stub_client(handler)))
    with caplog.at_level(logging.INFO, logger="qatools_health"):
        runner.start()
        result = await subscription.wait_for(UNHEALTHY, timeout=2)
    await runner.stop()
    assert "the GitHub rate limit is spent, 0/5000 core requests left, resets in 10m" in result.message
    warning = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert "rate limit is spent" in warning[0].getMessage()


async def test_github_names_the_secondary_rate_limit():
    def handle(request):
        return httpx.Response(429, headers={"retry-after": "60"})

    result = await GitHubApiHealthCheck("token", client=stub_client(handle)).perform_check()
    assert result.status is UNHEALTHY
    assert "secondary rate limit is hit, retry in 60s" in result.message


@pytest.mark.parametrize("body", [b"<html>maintenance</html>", b"[]", b'{"resources": []}', b""])
async def test_github_reports_a_malformed_rate_limit_body(body):
    def handle(request):
        return httpx.Response(200, content=body)

    result = await GitHubApiHealthCheck("token", client=stub_client(handle)).perform_check()
    assert result.status is UNHEALTHY
    assert "without a core budget" in result.message


async def test_github_reports_a_malformed_identity_body():
    def handle(request):
        if request.url.path == "/rate_limit":
            return httpx.Response(200, json={"resources": {"core": {"remaining": 4200, "limit": 5000}}})
        return httpx.Response(200, content=b"<html></html>")

    result = await GitHubApiHealthCheck("token", "zeus-bot", client=stub_client(handle)).perform_check()
    assert result.status is UNHEALTHY
    assert "None" in result.message


@pytest.mark.parametrize(
    "body",
    [b"<html>checking your browser</html>", b"[]", b'{"components": "none"}', b'{"components": ["x", 1]}'],
)
async def test_anthropic_probes_the_key_when_the_status_page_is_malformed(body):
    def handle(request):
        handle.requests.append(request)
        if request.url.host == "status.claude.com":
            return httpx.Response(200, content=body)
        return httpx.Response(200, json={})

    handle.requests = []
    result = await AnthropicApiHealthCheck("key", client=stub_client(handle)).perform_check()
    assert result.status is HEALTHY
    assert len(handle.requests) == 2


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({"error": "overloaded"}, "overloaded"),
        ({"error": {"message": 5}}, "Service Unavailable"),
        ({"detail": "nope"}, "Service Unavailable"),
    ],
)
async def test_anthropic_reads_an_error_body_of_any_shape(body, expected):
    handler = anthropic_stub(messages_status=503, messages_json=body)
    result = await AnthropicApiHealthCheck("key", client=stub_client(handler)).perform_check()
    assert result.status is UNHEALTHY
    assert result.message.endswith(expected)


async def test_sqlite_check_opens_a_path_with_uri_characters(tmp_path):
    db_path = tmp_path / "odd ?#% name.db"
    async with aiosqlite.connect(db_path):
        pass
    assert (await SqliteHealthCheck(db_path, name="sqlite:odd").perform_check()).status is HEALTHY


def test_the_anthropic_status_page_is_the_claude_status_host():
    assert httpx.URL(ANTHROPIC_STATUS_URL).host == "status.claude.com"


class GitHubStub:
    def __init__(self, clock):
        self.clock = clock
        self.requests = []
        self.answers = []
        self.core = {"remaining": 4200, "limit": 5000, "reset": int(clock.now) + 3600}

    def refuse(self, status, headers=None, json=None, path="/rate_limit"):
        self.answers.append((path, httpx.Response(status, headers=headers or {}, json=json or {})))

    def __call__(self, request):
        self.requests.append(request.url.path)
        for index, (path, response) in enumerate(self.answers):
            if path == request.url.path:
                del self.answers[index]
                return response
        if request.url.path == "/user":
            return httpx.Response(200, json={"login": "zeus-bot"})
        return httpx.Response(200, json={"resources": {"core": dict(self.core)}})


def github_check(stub, expected_login=None):
    return GitHubApiHealthCheck("token", expected_login, client=stub_client(stub), clock=stub.clock)


@pytest.mark.parametrize("status", [403, 429])
async def test_github_sends_nothing_before_the_primary_rate_limit_resets(clock, status):
    stub = GitHubStub(clock)
    reset = int(clock.now) + 900
    stub.refuse(status, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(reset)})
    check = github_check(stub)

    first = await check.perform_check()
    assert first.status is UNHEALTHY
    assert first.message == f"rate_limit answered {status}, the GitHub primary rate limit is spent, resets in 15m"

    clock.advance(600)
    waiting = await check.perform_check()
    assert waiting.status is UNHEALTHY
    assert waiting.message.endswith("resets in 5m, no request sent")
    assert stub.requests == ["/rate_limit"]

    clock.advance(301)
    assert (await check.perform_check()).status is HEALTHY
    assert stub.requests == ["/rate_limit", "/rate_limit"]


async def test_github_waits_a_minute_when_the_reset_header_is_missing(clock):
    stub = GitHubStub(clock)
    stub.refuse(403, headers={"x-ratelimit-remaining": "0"})
    check = github_check(stub)
    assert (await check.perform_check()).message.endswith("resets in 60s")
    clock.advance(59)
    assert (await check.perform_check()).message.endswith("no request sent")
    clock.advance(2)
    assert (await check.perform_check()).status is HEALTHY
    assert len(stub.requests) == 2


@pytest.mark.parametrize("status", [403, 429])
async def test_github_honours_retry_after_on_a_secondary_rate_limit(clock, status):
    stub = GitHubStub(clock)
    stub.refuse(status, headers={"retry-after": "30"})
    check = github_check(stub)
    result = await check.perform_check()
    assert result.message == f"rate_limit answered {status}, a GitHub secondary rate limit is hit, retry in 30s"
    clock.advance(29)
    assert (await check.perform_check()).message.endswith("retry in 1s, no request sent")
    clock.advance(2)
    assert (await check.perform_check()).status is HEALTHY
    assert len(stub.requests) == 2


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (429, {}),
        (403, {"message": "You have exceeded a secondary rate limit"}),
        (403, {"error": {"message": "API rate limit exceeded for installation"}}),
    ],
)
async def test_github_waits_a_minute_on_a_secondary_rate_limit_without_headers(clock, status, body):
    stub = GitHubStub(clock)
    stub.refuse(status, json=body)
    check = github_check(stub)
    assert (await check.perform_check()).message.endswith("secondary rate limit is hit, retry in 60s")
    clock.advance(30)
    assert (await check.perform_check()).message.endswith("retry in 30s, no request sent")
    clock.advance(31)
    assert (await check.perform_check()).status is HEALTHY
    assert len(stub.requests) == 2


async def test_github_retries_at_once_after_a_403_that_is_not_a_rate_limit(clock):
    stub = GitHubStub(clock)
    stub.refuse(403, json={"message": "Resource not accessible by integration"})
    check = github_check(stub)
    result = await check.perform_check()
    assert result.status is UNHEALTHY
    assert "rate limit" not in result.message
    assert result.message == "rate_limit answered 403: Resource not accessible by integration"
    assert (await check.perform_check()).status is HEALTHY
    assert len(stub.requests) == 2


async def test_github_waits_when_the_identity_read_hits_the_rate_limit(clock):
    stub = GitHubStub(clock)
    stub.refuse(
        403, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(int(clock.now) + 120)}, path="/user"
    )
    check = github_check(stub, "zeus-bot")
    result = await check.perform_check()
    assert result.message == "user answered 403, the GitHub primary rate limit is spent, resets in 2m"
    clock.advance(60)
    assert (await check.perform_check()).message.endswith("no request sent")
    clock.advance(61)
    assert (await check.perform_check()).status is HEALTHY
    assert stub.requests == ["/rate_limit", "/user", "/rate_limit", "/user"]


async def test_github_waits_for_the_reset_of_a_spent_core_budget(clock):
    stub = GitHubStub(clock)
    stub.core = {"remaining": 0, "limit": 5000, "reset": int(clock.now) + 300}
    check = github_check(stub, "zeus-bot")
    assert (await check.perform_check()).message == (
        "the GitHub rate limit is spent, 0/5000 core requests left, resets in 5m"
    )
    clock.advance(200)
    assert (await check.perform_check()).message.endswith("no request sent")
    stub.core = {"remaining": 5000, "limit": 5000, "reset": int(clock.now) + 3600}
    clock.advance(101)
    assert (await check.perform_check()).status is HEALTHY
    assert stub.requests == ["/rate_limit", "/rate_limit", "/user"]


def test_the_github_clock_stays_out_of_the_identity(clock):
    assert GitHubApiHealthCheck("token", clock=clock).identity() == GitHubApiHealthCheck("token").identity()


@pytest.mark.parametrize(
    ("seconds", "text"), [(0, "0s"), (-5, "0s"), (59.4, "59s"), (119, "119s"), (120, "2m"), (900, "15m")]
)
def test_wait_text_renders_seconds_then_minutes(seconds, text):
    assert wait_text(seconds) == text
