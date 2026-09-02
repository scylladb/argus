"""Metrics tests.

Every request lands in the shared series exactly once — matched routes
under their route name, unmatched ones too — and /metrics serves the
shared registry. The former flask-exporter default series
(http_request_total, http_request_duration_seconds,
http_request_exceptions_total, exporter_info) keep their numeric status
labels; the custom by_* counters keep werkzeug's "200 OK" format.
"""
from fastapi import APIRouter
from prometheus_client import REGISTRY
from pytest import fixture


probe = APIRouter()


@probe.get("/metrics-probe", name="asgi.metrics_probe")
def metrics_probe():
    return {"status": "ok"}


@probe.get("/metrics-probe-boom", name="asgi.metrics_probe_boom")
def metrics_probe_boom():
    raise RuntimeError("probe exploded")


@fixture(scope="module", autouse=True)
def probe_routes(asgi_app, include_router_before_fallback):
    include_router_before_fallback(asgi_app, probe)
    yield
    asgi_app.router.routes = [
        route for route in asgi_app.routes
        if not getattr(route, "path", "").startswith("/metrics-probe")
    ]


def _sample(name: str, labels: dict) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


def test_fastapi_route_is_recorded_once_under_its_route_name(api_client):
    labels = {"endpoint": "asgi.metrics_probe", "method": "GET", "status": "200 OK"}
    before = _sample("http_request_by_endpoint_total", labels)
    response = api_client.get("/metrics-probe")
    assert response.status_code == 200
    assert _sample("http_request_by_endpoint_total", labels) == before + 1


def test_default_series_use_numeric_status_labels(api_client):
    total_labels = {"method": "GET", "status": "200"}
    before = _sample("http_request_total", total_labels)
    response = api_client.get("/metrics-probe")
    assert response.status_code == 200
    assert _sample("http_request_total", total_labels) == before + 1
    assert _sample("http_request_duration_seconds_count",
                   {"method": "GET", "endpoint": "asgi.metrics_probe", "status": "200"}) >= 1


def test_unmatched_request_is_recorded_once(api_client):
    total_labels = {"method": "GET", "status": "404"}
    before = _sample("http_request_total", total_labels)
    response = api_client.get("/definitely-not-a-route-anywhere")
    assert response.status_code == 404
    assert _sample("http_request_total", total_labels) == before + 1


def test_unhandled_exception_increments_exceptions_total(api_client):
    labels = {"method": "GET", "status": "500"}
    before = _sample("http_request_exceptions_total", labels)
    response = api_client.get("/metrics-probe-boom")
    # rendered through the api exception handler (argus error contract)
    assert response.status_code == 200
    assert response.json()["response"]["exception"] == "RuntimeError"
    assert _sample("http_request_exceptions_total", labels) == before + 1


def test_metrics_endpoint_serves_the_shared_registry(api_client):
    api_client.get("/metrics-probe")
    response = api_client.get("/metrics")
    assert response.status_code == 200
    assert "http_request_by_endpoint_total" in response.text
    assert 'endpoint="asgi.metrics_probe"' in response.text
    assert "exporter_info" in response.text
