import logging
import time
from typing import Any

import requests

from argus.client.tunnel_models import DEFAULT_TUNNEL_TIMEOUT, TunnelClientError, TunnelConfig
from argus.client.tunnel_state import (
    generate_keypair_if_needed,
    get_tunnel_state_paths,
    is_key_valid,
    read_cached_tunnel_config,
    write_key_meta,
    write_tunnel_cache,
)


LOGGER = logging.getLogger(__name__)
TUNNEL_API_RETRIES = 3


def resolve_tunnel_config(
    auth_token: str,
    base_url: str,
    force_refresh: bool = False,
    ttl_seconds: int | None = None,
) -> TunnelConfig | None:
    config, _reason = resolve_tunnel_config_with_reason(
        auth_token=auth_token,
        base_url=base_url,
        force_refresh=force_refresh,
        ttl_seconds=ttl_seconds,
    )
    return config


def resolve_tunnel_config_with_reason(
    auth_token: str,
    base_url: str,
    force_refresh: bool = False,
    ttl_seconds: int | None = None,
) -> tuple[TunnelConfig | None, str | None]:
    """
    Resolve tunnel configuration while keeping Cloudflare bootstrap calls minimal.

    Order:
    1. Use cached config when key/cache are still valid and refresh is not forced.
    2. Use GET /client/ssh/tunnel when key exists and remains valid.
    3. Register/re-register via POST /client/ssh/tunnel.
    """
    paths = get_tunnel_state_paths()

    if not force_refresh:
        cached = read_cached_tunnel_config(paths)
        if cached is not None and is_key_valid(paths):
            return cached, None

    if is_key_valid(paths):
        try:
            config = _get_tunnel_connection(auth_token=auth_token, base_url=base_url)
            write_tunnel_cache(paths, config)
            return config, None
        except TunnelClientError as exc:
            LOGGER.warning("Unable to refresh tunnel connection details via API: %s", exc)

    try:
        generate_keypair_if_needed(paths)
        public_key = paths.public_key.read_text(encoding="utf-8").strip()
        config = _register_tunnel(
            auth_token=auth_token,
            base_url=base_url,
            public_key=public_key,
            ttl_seconds=ttl_seconds,
        )
        write_key_meta(paths, config.expires_at)
        write_tunnel_cache(paths, config)
        return config, None
    except (OSError, TunnelClientError) as exc:
        LOGGER.warning("Unable to resolve SSH tunnel configuration: %s", exc)
        return None, str(exc)


def _register_tunnel(auth_token: str, base_url: str, public_key: str, ttl_seconds: int | None = None) -> TunnelConfig:
    payload: dict[str, Any] = {"public_key": public_key}
    if ttl_seconds is not None:
        payload["ttl_seconds"] = ttl_seconds
    response = _call_tunnel_api(
        method="POST",
        url=f"{base_url}/api/v1/client/ssh/tunnel",
        auth_token=auth_token,
        payload=payload,
    )
    return TunnelConfig.from_api_response(response)


def _get_tunnel_connection(auth_token: str, base_url: str) -> TunnelConfig:
    response = _call_tunnel_api(
        method="GET",
        url=f"{base_url}/api/v1/client/ssh/tunnel",
        auth_token=auth_token,
        payload=None,
    )
    return TunnelConfig.from_api_response(response)


def _call_tunnel_api(method: str, url: str, auth_token: str, payload: dict[str, Any] | None) -> dict[str, Any]:
    headers = {
        "Authorization": f"token {auth_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    last_exception: TunnelClientError | None = None
    for attempt in range(1, TUNNEL_API_RETRIES + 1):
        try:
            if method == "POST":
                response = requests.post(url=url, json=payload, headers=headers, timeout=DEFAULT_TUNNEL_TIMEOUT)
            elif method == "GET":
                response = requests.get(url=url, headers=headers, timeout=DEFAULT_TUNNEL_TIMEOUT)
            else:
                raise TunnelClientError(f"Unsupported tunnel API method: {method}")
        except requests.RequestException as exc:
            last_exception = TunnelClientError(f"Tunnel API call failed ({method} {url}): {exc}")
            if attempt < TUNNEL_API_RETRIES:
                time.sleep(0.5 * (2 ** (attempt - 1)))
                continue
            raise last_exception from exc

        if response.status_code != 200:
            last_exception = TunnelClientError(
                f"Tunnel API call returned unexpected status code {response.status_code} ({method} {url})"
            )
            if attempt < TUNNEL_API_RETRIES:
                time.sleep(0.5 * (2 ** (attempt - 1)))
                continue
            raise last_exception

        try:
            response_payload = response.json()
        except ValueError as exc:
            last_exception = TunnelClientError(f"Tunnel API response is not JSON ({method} {url})")
            if attempt < TUNNEL_API_RETRIES:
                time.sleep(0.5 * (2 ** (attempt - 1)))
                continue
            raise last_exception from exc

        if response_payload.get("status") != "ok":
            response_error = response_payload.get("response")
            if isinstance(response_error, dict):
                message = response_error.get("message")
            else:
                message = response_error
            raise TunnelClientError(f"Tunnel API returned error: {message}")

        response_data = response_payload.get("response")
        if not isinstance(response_data, dict):
            last_exception = TunnelClientError("Tunnel API response payload has invalid format")
            if attempt < TUNNEL_API_RETRIES:
                time.sleep(0.5 * (2 ** (attempt - 1)))
                continue
            raise last_exception

        return response_data

    raise last_exception or TunnelClientError("Tunnel API call failed unexpectedly")
