import asyncio
import sqlite3
import sys

import httpx
import pytest

from qatools_health import HealthCheckStatus
from qatools_health.checks.primitives import first_line
from qatools_health.checks import (
    AnthropicApiHealthCheck,
    HeadroomProxyHealthCheck,
    MaiaApiHealthCheck,
    ArgusApiHealthCheck,
    BinaryHealthCheck,
    GhCliHealthCheck,
    GitHubApiHealthCheck,
    HttpHealthCheck,
    JenkinsApiHealthCheck,
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
    assert check.critical is True


async def test_jira_probes_myself():
    handler = responder(200)
    check = JiraApiHealthCheck("https://jira.test", "a@b.test", "token", client=stub_client(handler))
    await check.perform_check()
    assert handler.requests[0].url.path == "/rest/api/3/myself"
    assert check.critical is False


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
            return httpx.Response(200, json={"resources": {"core": {"remaining": 1, "limit": 5000}}})
        return httpx.Response(200, json={"login": "someone-else"})

    check = GitHubApiHealthCheck("token", "zeus-bot", client=stub_client(handle))
    result = await check.perform_check()
    assert result.status is UNHEALTHY
    assert "someone-else" in result.message


async def test_github_accepts_the_expected_login():
    def handle(request):
        if request.url.path == "/rate_limit":
            return httpx.Response(200, json={"resources": {"core": {"remaining": 1, "limit": 5000}}})
        return httpx.Response(200, json={"login": "zeus-bot"})

    check = GitHubApiHealthCheck("token", "zeus-bot", client=stub_client(handle))
    assert (await check.perform_check()).status is HEALTHY


async def test_github_fails_when_rate_limit_refuses():
    check = GitHubApiHealthCheck("token", client=stub_client(responder(401)))
    assert (await check.perform_check()).status is UNHEALTHY


async def test_argus_sends_the_token_and_the_access_headers():
    handler = responder(200)
    check = ArgusApiHealthCheck("https://argus.test", "abc", "cf-id", "cf-secret", client=stub_client(handler))
    await check.perform_check()
    request = handler.requests[0]
    assert request.url.path == "/api/v1/notifications/get_unread"
    assert request.headers["Authorization"] == "token abc"
    assert request.headers["CF-Access-Client-Id"] == "cf-id"


async def test_anthropic_lists_models():
    handler = responder(200)
    check = AnthropicApiHealthCheck("key", client=stub_client(handler))
    await check.perform_check()
    assert handler.requests[0].url.path == "/v1/models"
    assert handler.requests[0].headers["x-api-key"] == "key"
    assert check.name == "llm_api"


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
    assert (OpencodeHealthCheck().name, OpencodeHealthCheck().critical) == ("opencode", True)
    assert GhCliHealthCheck().name == "gh"


async def test_gh_skips_the_auth_probe_by_default():
    check = GhCliHealthCheck(name="gh")
    assert check.verify_auth is False


async def test_sqlite_check_queries_a_live_connection():
    connection = sqlite3.connect(":memory:")
    check = SqliteHealthCheck(connection, name="sqlite:context")
    result = await check.perform_check()
    assert result.status is HEALTHY
    assert check.name == "sqlite:context"
    connection.close()


async def test_sqlite_check_names_itself_from_a_path(tmp_path):
    db_path = tmp_path / "context.db"
    sqlite3.connect(db_path).close()
    check = SqliteHealthCheck(db_path)
    assert check.name == "sqlite:context"
    assert (await check.perform_check()).status is HEALTHY


async def test_sqlite_check_raises_on_a_broken_query():
    connection = sqlite3.connect(":memory:")
    check = SqliteHealthCheck(connection, query="SELECT * FROM missing", name="sqlite:broken")
    with pytest.raises(sqlite3.OperationalError):
        await check.perform_check()
    connection.close()


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


async def test_headroom_probes_the_url_it_was_given():
    handler = responder(200)
    check = HeadroomProxyHealthCheck("https://headroom.test/status", client=stub_client(handler))
    await check.perform_check()
    assert str(handler.requests[0].url) == "https://headroom.test/status"
    assert check.name == "headroom_proxy"


async def test_maia_sends_the_bearer_token():
    handler = responder(200)
    check = MaiaApiHealthCheck("https://maia.test", "token", path="api/v1/me", client=stub_client(handler))
    await check.perform_check()
    assert handler.requests[0].headers["Authorization"] == "Bearer token"
    assert handler.requests[0].url.path == "/api/v1/me"
    assert check.name == "maia_api"


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
            return httpx.Response(200, json={"resources": {"core": {"remaining": 1, "limit": 5000}}})
        return httpx.Response(403)

    check = GitHubApiHealthCheck("token", "zeus-bot", client=stub_client(handle))
    result = await check.perform_check()
    assert result.status is UNHEALTHY
    assert "user answered 403" in result.message
