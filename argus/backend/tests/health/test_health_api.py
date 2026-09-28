from unittest.mock import patch

import httpx2
import pytest

from argus.backend.service.health_service import HealthSummaryService, health_client

HEALTH_ANSWER = {
    "service": "argus",
    "version": "0.16.4",
    "status": "degraded",
    "runner_up": True,
    "checks": [
        {"name": "scylla", "severity": "critical", "status": "healthy", "message": "3 of 3 hosts up",
         "stale": False, "last_run_timestamp": 1.0, "last_success_timestamp": 1.0},
        {"name": "jira_api", "severity": "important", "status": "unhealthy", "message": "myself answered 401",
         "stale": False, "last_run_timestamp": 1.0, "last_success_timestamp": 0.0},
    ],
}


class Recorder:
    def __init__(self, payload=None, status_code=200, error=None):
        self.payload = payload
        self.status_code = status_code
        self.error = error
        self.urls: list[str] = []

    def client(self) -> httpx2.AsyncClient:
        def handle(request: httpx2.Request) -> httpx2.Response:
            self.urls.append(str(request.url))
            if self.error is not None:
                raise self.error
            return httpx2.Response(self.status_code, json=self.payload)

        return httpx2.AsyncClient(transport=httpx2.MockTransport(handle))


@pytest.fixture
def enabled_config():
    return {"HEALTH_ENABLED": True, "HEALTH_HOST": "10.0.0.5", "HEALTH_PORT": 9300}


async def test_summary_is_disabled_without_a_request():
    recorder = Recorder(HEALTH_ANSWER)
    summary = await HealthSummaryService({}, client=recorder.client()).get_summary()
    assert summary == {"enabled": False, "status": "unknown", "failing": []}
    assert recorder.urls == []


async def test_summary_names_the_failing_checks(enabled_config):
    recorder = Recorder(HEALTH_ANSWER)
    summary = await HealthSummaryService(enabled_config, client=recorder.client()).get_summary()
    assert recorder.urls == ["http://10.0.0.5:9300/health"]
    assert summary == {
        "enabled": True,
        "status": "degraded",
        "failing": [
            {"name": "jira_api", "severity": "important", "status": "unhealthy"},
        ],
    }


async def test_healthy_summary_has_no_failing_check(enabled_config):
    healthy = dict(HEALTH_ANSWER, status="healthy", checks=HEALTH_ANSWER["checks"][:1])
    summary = await HealthSummaryService(enabled_config, client=Recorder(healthy).client()).get_summary()
    assert summary == {"enabled": True, "status": "healthy", "failing": []}


def pending(name: str, severity: str) -> dict:
    return {"name": name, "severity": severity, "status": "pending", "message": "", "stale": True,
            "last_run_timestamp": 0.0, "last_success_timestamp": 0.0}


async def test_summary_leaves_out_the_checks_that_have_not_run(enabled_config):
    starting = dict(
        HEALTH_ANSWER, status="unhealthy", checks=[HEALTH_ANSWER["checks"][0], pending("nginx", "important")],
    )
    summary = await HealthSummaryService(enabled_config, client=Recorder(starting).client()).get_summary()
    assert summary == {"enabled": True, "status": "healthy", "failing": []}


async def test_summary_counts_a_failed_check_next_to_a_pending_one(enabled_config):
    checks = [
        {**HEALTH_ANSWER["checks"][0], "status": "unhealthy"},
        pending("jira_api", "important"),
    ]
    starting = dict(HEALTH_ANSWER, status="unhealthy", checks=checks)
    summary = await HealthSummaryService(enabled_config, client=Recorder(starting).client()).get_summary()
    assert summary == {
        "enabled": True,
        "status": "unhealthy",
        "failing": [{"name": "scylla", "severity": "critical", "status": "unhealthy"}],
    }


async def test_summary_ignores_a_failed_optional_check(enabled_config):
    checks = [HEALTH_ANSWER["checks"][0], {**HEALTH_ANSWER["checks"][1], "severity": "optional"}]
    answer = dict(HEALTH_ANSWER, status="healthy", checks=checks)
    summary = await HealthSummaryService(enabled_config, client=Recorder(answer).client()).get_summary()
    assert summary["status"] == "healthy"
    assert [check["name"] for check in summary["failing"]] == ["jira_api"]


async def test_unreachable_health_process_reads_unknown(enabled_config):
    recorder = Recorder(error=httpx2.ConnectError("refused"))
    summary = await HealthSummaryService(enabled_config, client=recorder.client()).get_summary()
    assert summary == {"enabled": True, "status": "unknown", "failing": []}


async def test_error_status_reads_unknown(enabled_config):
    recorder = Recorder({}, status_code=500)
    summary = await HealthSummaryService(enabled_config, client=recorder.client()).get_summary()
    assert summary["status"] == "unknown"


async def test_wildcard_host_connects_to_loopback():
    recorder = Recorder(HEALTH_ANSWER)
    config = {"HEALTH_ENABLED": True, "HEALTH_HOST": "0.0.0.0"}
    await HealthSummaryService(config, client=recorder.client()).get_summary()
    assert recorder.urls == ["http://127.0.0.1:9300/health"]



async def test_ipv6_host_is_bracketed():
    recorder = Recorder(HEALTH_ANSWER)
    config = {"HEALTH_ENABLED": True, "HEALTH_HOST": "fd00::5"}
    await HealthSummaryService(config, client=recorder.client()).get_summary()
    assert recorder.urls == ["http://[fd00::5]:9300/health"]


async def test_invalid_host_reads_unknown():
    config = {"HEALTH_ENABLED": True, "HEALTH_HOST": "not:an:address"}
    summary = await HealthSummaryService(config, client=Recorder(HEALTH_ANSWER).client()).get_summary()
    assert summary == {"enabled": True, "status": "unknown", "failing": []}


@pytest.mark.parametrize("payload", [{"checks": [{"status": "unhealthy"}]}, {"checks": "broken"}, []])
async def test_malformed_answer_reads_unknown(enabled_config, payload):
    summary = await HealthSummaryService(enabled_config, client=Recorder(payload).client()).get_summary()
    assert summary == {"enabled": True, "status": "unknown", "failing": []}


def test_the_default_client_ignores_the_proxy_environment():
    assert HealthSummaryService({}).client is health_client()
    assert health_client().trust_env is False


def test_summary_route_answers_the_signed_in_user(api_client):
    disabled = {"enabled": False, "status": "unknown", "failing": []}
    with patch.object(HealthSummaryService, "get_summary", return_value=disabled):
        body = api_client.get("/api/v1/health/summary").json()
    assert body == {"status": "ok", "response": disabled}


def test_summary_route_requires_a_user(anon_client):
    response = anon_client.get("/api/v1/health/summary")
    assert response.json()["status"] == "error"
