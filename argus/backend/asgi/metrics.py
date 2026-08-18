"""Request-metrics middleware for the FastAPI side of the strangler.

Increments the same prometheus_client series as the Flask hooks (see
backend/metrics.py). Requests that fall through the WSGI mount are skipped —
Flask's own after_request hook records those — so nothing double-counts.

The endpoint label uses the matched route's name; migrated routes are named
after their Flask endpoints (e.g. "api.client_api.submit_run") to keep the
label values, and thus the dashboards, stable across the migration.
"""
import time

from starlette.datastructures import Headers

from argus.backend.metrics import record_request, status_line


class MetricsMiddleware:
    def __init__(self, app, skip_endpoints: tuple = ()):
        self.app = app
        self.skip_endpoints = skip_endpoints

    @staticmethod
    def _endpoint_name(scope) -> str:
        route = scope.get("route")
        if route is not None and getattr(route, "name", None):
            return route.name
        endpoint = scope.get("endpoint")
        if endpoint is not None:
            return getattr(endpoint, "__name__", None) or type(endpoint).__name__.lower()
        return scope.get("path", "unknown")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()

        async def send_wrapper(message):
            if message["type"] == "http.response.start" and scope.get("endpoint") not in self.skip_endpoints:
                client = scope.get("client")
                record_request(
                    endpoint=self._endpoint_name(scope),
                    method=scope["method"],
                    status=status_line(message["status"]),
                    remote_addr=client[0] if client else None,
                    headers=Headers(scope=scope),
                    duration=time.perf_counter() - started,
                )
            await send(message)

        await self.app(scope, receive, send_wrapper)
