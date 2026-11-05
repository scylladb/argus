import pytest

from argus.backend.models.chat import GLOBAL_SCOPE, ChatConfiguration
from argus.backend.service.chat import config as chat_config
from argus.backend.service.chat.config import ChatConfigService
from argus.backend.tests.chat.helpers import ScriptedClient
from argus.backend.util.config import Config


@pytest.fixture
def scripted_client(monkeypatch) -> ScriptedClient:
    client = ScriptedClient()

    def make_client(endpoint: str, token: str) -> ScriptedClient:
        client.credentials.append((endpoint, token))
        return client

    monkeypatch.setattr(chat_config, "make_client", make_client)
    return client


@pytest.fixture
async def clean_chat_config(monkeypatch):
    """Each test starts with no connection, no default and no YAML entry."""
    await ChatConfiguration.find(scope=GLOBAL_SCOPE).delete()
    monkeypatch.setitem(Config.CONFIG, "CHAT_MODELS", [])
    ChatConfigService._fallback_probes.clear()
    yield
    await ChatConfiguration.find(scope=GLOBAL_SCOPE).delete()
    ChatConfigService._fallback_probes.clear()
