import uuid
from datetime import UTC, datetime

import pytest
from starlette.testclient import TestClient

from argus.backend.models.chat import GLOBAL_SCOPE, ChatConfiguration, ChatIdentity, ChatMcpServer, ChatSkill
from argus.backend.models.web import User, UserRoles
from argus.backend.service.chat import config as chat_config
from argus.backend.service.chat.config import ChatConfigService, DefaultModel
from argus.backend.tests.chat.helpers import ScriptedClient
from argus.backend.tests.conftest import g
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
    await ChatIdentity.find(scope=GLOBAL_SCOPE).delete()
    await ChatSkill.find(scope=GLOBAL_SCOPE).delete()
    await ChatMcpServer.find(scope=GLOBAL_SCOPE).delete()
    monkeypatch.setitem(Config.CONFIG, "CHAT_MODELS", [])
    ChatConfigService._fallback_probes.clear()
    yield
    await ChatConfiguration.find(scope=GLOBAL_SCOPE).delete()
    await ChatIdentity.find(scope=GLOBAL_SCOPE).delete()
    await ChatSkill.find(scope=GLOBAL_SCOPE).delete()
    await ChatMcpServer.find(scope=GLOBAL_SCOPE).delete()
    ChatConfigService._fallback_probes.clear()


@pytest.fixture
async def chat_model(scripted_client, clean_chat_config, logged_in_user) -> ScriptedClient:
    """A default model on a scripted client; tests push turns on the returned client."""
    service = ChatConfigService()
    await service.save_connection("scripted", "https://model.test/api", "sk-test", logged_in_user)
    await service.set_default(DefaultModel("scripted", "test-model", 8000, True, False), logged_in_user)
    return scripted_client


@pytest.fixture
def chat_client(asgi_app, api_client):
    """A client that keeps one event loop for its whole life, so background
    chat tasks outlive the request that started them, as under uvicorn."""
    with TestClient(asgi_app, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture
def normal_user_identity():
    previous_roles = list(g.user.roles)
    g.user.roles = ["ROLE_USER"]
    yield
    g.user.roles = previous_roles


@pytest.fixture
async def chat_people() -> list[User]:
    """Two stored users, for tools that name people."""
    people = []
    for name in ("Alice Smith", "Bob Jones"):
        username = f"{name.split()[0].lower()}_{uuid.uuid4().hex[:8]}"
        user = User(id=uuid.uuid4(), username=username, full_name=name, email=f"{username}@scylladb.com",
                    password="hash:placeholder", roles=[UserRoles.User.value], registration_date=datetime.now(UTC))
        await user.save()
        people.append(user)
    yield people
    for user in people:
        await user.delete()


@pytest.fixture
async def zeus_user() -> User:
    """The service account Zeus posts its reports with."""
    username = f"zeus_bot_{uuid.uuid4().hex[:8]}"
    user = User(id=uuid.uuid4(), username=username, full_name="Zeus", email=f"{username}@scylladb.com",
                password="hash:placeholder", roles=[UserRoles.User.value], registration_date=datetime.now(UTC),
                service_user=True)
    await user.save()
    yield user
    await user.delete()
