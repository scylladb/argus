import httpx

from argus.backend.util.config import Config

ZEUS_TIMEOUT_SECONDS = 30


class ZeusError(Exception):
    pass


class ZeusClient:
    """The investigation API of Zeus: queue a question about a run, then read its task."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        config = Config.load_yaml_config()
        self._host = config.get("ZEUS_HOST")
        self._schema = config.get("ZEUS_SCHEMA") or "http"
        self._token = config.get("ZEUS_TOKEN")
        self._transport = transport

    def configured(self) -> bool:
        return bool(self._host and self._token)

    async def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        if not self.configured():
            raise ZeusError("Zeus is not configured: ZEUS_HOST and ZEUS_TOKEN are missing")
        async with httpx.AsyncClient(base_url=f"{self._schema}://{self._host}", transport=self._transport,
                                     headers={"Authorization": f"Bearer {self._token}"},
                                     timeout=ZEUS_TIMEOUT_SECONDS) as client:
            try:
                response = await client.request(method, path, json=payload)
            except httpx.HTTPError as exception:
                raise ZeusError(f"Zeus could not be reached: {exception}") from exception
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail")
            except ValueError:
                detail = response.text[:200]
            raise ZeusError(f"Zeus answered {response.status_code}: {detail}")
        return response.json()

    async def investigate(self, prompt: str) -> str:
        return (await self._request("POST", "/investigate", {"prompt": prompt}))["task_id"]

    async def status(self, task_id: str) -> dict:
        return await self._request("GET", f"/investigate/{task_id}")
