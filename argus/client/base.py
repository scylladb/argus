import re
import logging
import os
import threading
import time
import atexit
from dataclasses import asdict
from typing import Any, Type
from uuid import UUID

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from argus.common.enums import TestStatus
from argus.client.tunnel import (
    SSHTunnel,
    TunnelConfig,
    delete_cached_tunnel_state,
    resolve_tunnel_config_with_reason,
)
from argus.client.generic_result import GenericResultTable
from argus.client.sct.types import LogLink

JSON = dict[str, Any] | list[Any] | int | str | float | bool | Type[None]
LOGGER = logging.getLogger(__name__)
TUNNEL_COOLDOWN_SECONDS = 30
DEFAULT_TUNNEL_MONITOR_INTERVAL_SECONDS = 5.0


class ArgusClientError(Exception):
    pass


class ArgusClient:
    schema_version: str | None = None

    class Routes():
        SUBMIT = "/testrun/$type/submit"
        GET = "/testrun/$type/$id/get"
        HEARTBEAT = "/testrun/$type/$id/heartbeat"
        GET_STATUS = "/testrun/$type/$id/get_status"
        SET_STATUS = "/testrun/$type/$id/set_status"
        SET_PRODUCT_VERSION = "/testrun/$type/$id/update_product_version"
        SUBMIT_LOGS = "/testrun/$type/$id/logs/submit"
        SUBMIT_RESULTS = "/testrun/$type/$id/submit_results"
        FETCH_RESULTS = "/testrun/$type/$id/fetch_results"
        FINALIZE = "/testrun/$type/$id/finalize"

    def __init__(self, auth_token: str, base_url: str, api_version="v1", extra_headers: dict | None = None,
                 timeout: int = 60, max_retries: int = 3, use_tunnel: bool | None = None) -> None:
        self._auth_token = auth_token
        self._original_base_url = base_url
        self._base_url = base_url
        self._api_ver = api_version
        self._timeout = timeout
        self._use_tunnel = self._resolve_use_tunnel(use_tunnel)
        self._tunnel: SSHTunnel | None = None
        self._tunnel_config: TunnelConfig | None = None
        self._tunnel_warning_emitted = False
        self._last_tunnel_failure_reason: str | None = None
        self._tunnel_disabled_until = 0.0
        self._tunnel_lock = threading.RLock()
        self._monitor_stop_event = threading.Event()
        self._monitor_thread: threading.Thread | None = None
        self._tunnel_monitor_interval = self._resolve_tunnel_monitor_interval()
        self.session = requests.Session()

        # Configure retry strategy
        retry_strategy = Retry(
            total=max_retries,
            connect=max_retries,
            read=max_retries,
            status=0,
            backoff_factor=1,
            status_forcelist=(),
            allowed_methods=["GET", "POST"],
        )

        # Mount adapter with retry strategy for both http and https
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        if extra_headers:
            self.session.headers.update(extra_headers)

        if self._use_tunnel:
            self._start_tunnel_monitor()

    @staticmethod
    def _resolve_use_tunnel(use_tunnel: bool | None) -> bool:
        if use_tunnel is not None:
            return use_tunnel
        return os.environ.get("ARGUS_USE_TUNNEL", "").strip().lower() in ("1", "true", "yes", "on")

    def _resolve_tunnel_monitor_interval(self) -> float:
        raw_value = os.environ.get("ARGUS_TUNNEL_MONITOR_INTERVAL")
        if raw_value is None:
            return DEFAULT_TUNNEL_MONITOR_INTERVAL_SECONDS
        try:
            interval = float(raw_value)
            if interval <= 0:
                raise ValueError("interval must be positive")
            return interval
        except ValueError:
            LOGGER.warning(
                "Invalid ARGUS_TUNNEL_MONITOR_INTERVAL=%s, using default %.1fs",
                raw_value,
                DEFAULT_TUNNEL_MONITOR_INTERVAL_SECONDS,
            )
            return DEFAULT_TUNNEL_MONITOR_INTERVAL_SECONDS

    def _start_tunnel_monitor(self) -> None:
        if self._monitor_thread and self._monitor_thread.is_alive():
            return
        self._monitor_stop_event.clear()
        self._monitor_thread = threading.Thread(
            target=self._tunnel_monitor_loop,
            name="argus-tunnel-monitor",
            daemon=True,
        )
        self._monitor_thread.start()
        atexit.register(self._stop_tunnel_monitor)

    def _stop_tunnel_monitor(self) -> None:
        self._monitor_stop_event.set()
        monitor = self._monitor_thread
        if monitor and monitor.is_alive() and monitor is not threading.current_thread():
            monitor.join(timeout=1.0)

    def _tunnel_monitor_loop(self) -> None:
        while not self._monitor_stop_event.wait(self._tunnel_monitor_interval):
            try:
                self._monitor_tunnel_health_once()
            except Exception:  # noqa: BLE001
                LOGGER.debug("SSH tunnel monitor loop failed", exc_info=True)

    def _monitor_tunnel_health_once(self) -> None:
        if not self._use_tunnel:
            return

        tunnel = self._tunnel
        if tunnel is None:
            return

        if tunnel.is_alive():
            return

        LOGGER.warning("SSH tunnel monitor detected dead tunnel; attempting reconnection")
        self._ensure_tunnel()

    def _is_using_tunnel_base_url(self) -> bool:
        return self._base_url.startswith("http://127.0.0.1:")

    def _warn_and_backoff_tunnel(self, reason: str) -> None:
        with self._tunnel_lock:
            self._last_tunnel_failure_reason = reason
            if not self._tunnel_warning_emitted:
                LOGGER.warning(
                    "SSH tunnel unavailable (%s); falling back to direct connection: %s",
                    reason,
                    self._original_base_url,
                )
                self._tunnel_warning_emitted = True

            if self._tunnel:
                self._tunnel.shutdown()

            self._tunnel = None
            self._tunnel_config = None
            self._base_url = self._original_base_url
            self._tunnel_disabled_until = time.monotonic() + TUNNEL_COOLDOWN_SECONDS

    def _ensure_tunnel(self) -> None:
        with self._tunnel_lock:
            if not self._use_tunnel:
                return

            if time.monotonic() < self._tunnel_disabled_until:
                return

            if self._tunnel and self._tunnel.is_alive() and self._tunnel.local_port is not None:
                self._base_url = f"http://127.0.0.1:{self._tunnel.local_port}"
                return

            if self._tunnel and self._tunnel_config:
                reconnected_port, reconnect_reason = self._tunnel.reconnect(self._tunnel_config)
                if reconnected_port is not None:
                    self._base_url = f"http://127.0.0.1:{reconnected_port}"
                    self._tunnel_warning_emitted = False
                    self._last_tunnel_failure_reason = None
                    return
                if reconnect_reason:
                    LOGGER.warning("SSH tunnel reconnect failed: %s", reconnect_reason)

            force_refresh = self._tunnel is not None
            config, config_reason = resolve_tunnel_config_with_reason(
                auth_token=self._auth_token,
                base_url=self._original_base_url,
                force_refresh=force_refresh,
            )
            if config is None:
                delete_cached_tunnel_state()
                reason = config_reason or "failed to resolve tunnel configuration"
                self._warn_and_backoff_tunnel(reason)
                return

            tunnel = SSHTunnel()
            local_port, establish_reason = tunnel.establish(config)

            if local_port is None and not force_refresh:
                config, config_reason = resolve_tunnel_config_with_reason(
                    auth_token=self._auth_token,
                    base_url=self._original_base_url,
                    force_refresh=True,
                )
                if config is not None:
                    local_port, establish_reason = tunnel.establish(config)
                else:
                    establish_reason = config_reason

            if local_port is None:
                delete_cached_tunnel_state()
                reason = establish_reason or "failed to establish tunnel"
                self._warn_and_backoff_tunnel(reason)
                return

            self._tunnel = tunnel
            self._tunnel_config = config
            self._base_url = f"http://127.0.0.1:{local_port}"
            self._tunnel_warning_emitted = False
            self._last_tunnel_failure_reason = None
            self._tunnel_disabled_until = 0.0

    def close(self) -> None:
        self._stop_tunnel_monitor()
        with self._tunnel_lock:
            if self._tunnel:
                self._tunnel.shutdown()
                self._tunnel = None
                self._tunnel_config = None
        self.session.close()

    def _request_with_tunnel_recovery(
        self,
        method: str,
        endpoint: str,
        location_params: dict | None,
        params: dict | None,
        body: dict | None,
    ) -> requests.Response:
        url = self.get_url_for_endpoint(endpoint=endpoint, location_params=location_params)
        request_kwargs = {
            "url": url,
            "params": params,
            "headers": self.request_headers,
            "timeout": self._timeout,
        }
        if method == "POST":
            request_kwargs["json"] = body

        request_fn = self.session.get if method == "GET" else self.session.post

        try:
            return request_fn(**request_kwargs)
        except requests.ConnectionError as exc:
            if not self._use_tunnel or not self._is_using_tunnel_base_url():
                raise

            LOGGER.warning(
                "%s request through SSH tunnel failed (%s); attempting reconnect and one retry",
                method,
                exc,
            )

            self._ensure_tunnel()
            retry_url = self.get_url_for_endpoint(endpoint=endpoint, location_params=location_params)
            request_kwargs["url"] = retry_url

            try:
                return request_fn(**request_kwargs)
            except requests.ConnectionError as retry_exc:
                self._warn_and_backoff_tunnel(f"request retry failed: {retry_exc}")
                request_kwargs["url"] = self.get_url_for_endpoint(endpoint=endpoint, location_params=location_params)
                return request_fn(**request_kwargs)

    @property
    def auth_token(self) -> str:
        return self._auth_token

    def verify_location_params(self, endpoint: str, location_params: dict[str, str]) -> bool:
        required_params: list[str] = re.findall(r"\$[\w_]+", endpoint)
        for param in required_params:
            if param.lstrip("$") not in location_params.keys():
                raise ArgusClientError(f"Missing required location argument for endpoint {endpoint}: {param}")

        return True

    @staticmethod
    def check_response(response: requests.Response, expected_code: int = 200):
        if response.status_code != expected_code:
            raise ArgusClientError(
                f"Unexpected HTTP Response encountered - expected: {expected_code}, got: {response.status_code}",
                expected_code,
                response.status_code,
                response.request,
            )

        response_data: JSON = response.json()
        LOGGER.debug("API Response: %s", response_data)
        if response_data.get("status") != "ok":
            exc_args = response_data["response"]["arguments"]
            raise ArgusClientError(
                f"API Error encountered using endpoint: {response.request.method} {response.request.path_url}",
                exc_args[0] if len(exc_args) > 0 else response_data.get("response", {}).get("exception", "#NoMessage"),
            )

    def get_url_for_endpoint(self, endpoint: str, location_params: dict[str, str] | None) -> str:
        if self.verify_location_params(endpoint, location_params):
            for param, value in location_params.items():
                endpoint = endpoint.replace(f"${param}", str(value))
        return f"{self._base_url}/api/{self._api_ver}/client{endpoint}"

    @property
    def generic_body(self) -> dict:
        return {
            "schema_version": self.schema_version
        }

    @property
    def request_headers(self):
        return {
            "Authorization": f"token {self.auth_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def get(self, endpoint: str, location_params: dict[str, str] = None, params: dict = None) -> requests.Response:
        self._ensure_tunnel()
        url = self.get_url_for_endpoint(endpoint=endpoint, location_params=location_params)
        LOGGER.debug("GET Request: %s, params: %s", url, params)
        response = self._request_with_tunnel_recovery(
            method="GET",
            endpoint=endpoint,
            location_params=location_params,
            params=params,
            body=None,
        )
        LOGGER.debug("GET Response: %s %s", response.status_code, response.url)

        return response

    def post(
        self,
        endpoint: str,
        location_params: dict = None,
        params: dict = None,
        body: dict = None,
    ) -> requests.Response:
        self._ensure_tunnel()
        url = self.get_url_for_endpoint(endpoint=endpoint, location_params=location_params)
        LOGGER.debug("POST Request: %s, params: %s, body: %s", url, params, body)
        response = self._request_with_tunnel_recovery(
            method="POST",
            endpoint=endpoint,
            location_params=location_params,
            params=params,
            body=body,
        )
        LOGGER.debug("POST Response: %s %s", response.status_code, response.url)

        return response

    def submit_run(self, run_type: str, run_body: dict) -> requests.Response:
        return self.post(endpoint=self.Routes.SUBMIT, location_params={"type": run_type}, body={
            **self.generic_body,
            **run_body
        })

    def get_run(self, run_type: str = None, run_id: UUID | str = None) -> requests.Response:

        if not run_type and hasattr(self, "test_type"):
            run_type = self.test_type

        if not run_id and hasattr(self, "run_id"):
            run_id = self.run_id

        if not (run_type and run_id):
            raise ValueError("run_type and run_id must be set in func params or object attributes")

        response = self.get(endpoint=self.Routes.GET, location_params={"type": run_type, "id": run_id})
        self.check_response(response)

        return response.json()["response"]

    def get_status(self, run_type: str = None, run_id: UUID = None) -> TestStatus:
        if not run_type and hasattr(self, "test_type"):
            run_type = self.test_type

        if not run_id and hasattr(self, "run_id"):
            run_id = self.run_id

        if not (run_type and run_id):
            raise ValueError("run_type and run_id must be set in func params or object attributes")

        response = self.get(
            endpoint=self.Routes.GET_STATUS,
            location_params={"type": run_type, "id": str(run_id)},
        )
        self.check_response(response)
        return TestStatus(response.json()["response"])

    def set_status(self, run_type: str, run_id: UUID, new_status: TestStatus) -> requests.Response:
        return self.post(
            endpoint=self.Routes.SET_STATUS,
            location_params={"type": run_type, "id": str(run_id)},
            body={
                **self.generic_body,
                "new_status": new_status.value
            }
        )

    def update_product_version(self, run_type: str, run_id: UUID, product_version: str) -> requests.Response:
        return self.post(
            endpoint=self.Routes.SET_PRODUCT_VERSION,
            location_params={"type": run_type, "id": str(run_id)},
            body={
                **self.generic_body,
                "product_version": product_version
            }
        )

    def submit_logs(self, run_type: str, run_id: UUID, logs: list[LogLink]) -> requests.Response:
        return self.post(
            endpoint=self.Routes.SUBMIT_LOGS,
            location_params={"type": run_type, "id": str(run_id)},
            body={
                **self.generic_body,
                "logs": [asdict(l) for l in logs]
            }
        )

    def finalize_run(self, run_type: str, run_id: UUID, body: dict = None) -> requests.Response:
        body = body if body else {}
        return self.post(
            endpoint=self.Routes.FINALIZE,
            location_params={"type": run_type, "id": str(run_id)},
            body={
                **self.generic_body,
                **body,
            }
        )

    def heartbeat(self, run_type: str, run_id: UUID) -> None:
        response = self.post(
            endpoint=self.Routes.HEARTBEAT,
            location_params={"type": run_type, "id": str(run_id)},
            body={
                **self.generic_body,
            }
        )
        self.check_response(response)

    def submit_results(self, result: GenericResultTable) -> None:
        response = self.post(
            endpoint=self.Routes.SUBMIT_RESULTS,
            location_params={"type": self.test_type, "id": str(self.run_id)},
            body={
                **self.generic_body,
                "run_id": str(self.run_id),
                ** result.as_dict(),
            }
        )
        self.check_response(response)
