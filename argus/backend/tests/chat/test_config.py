import pytest

from argus.backend.db import ScyllaCluster
from argus.backend.service.chat.config import ChatConfigError, ChatConfigService, DefaultModel
from argus.backend.service.chat.llm import ChatModelError, Finished, ProbedModel, TextDelta, ToolCall, ToolCallsReady
from argus.backend.tests.chat.helpers import yaml_connections

pytestmark = [pytest.mark.docker_required, pytest.mark.usefixtures("clean_chat_config")]

YAML_ENTRY = {"name": "yaml-webui", "endpoint": "https://yaml.test/api", "token": "sk-yaml", "model": "Gemma-4"}


async def test_yaml_and_database_connections_are_listed_together(monkeypatch, logged_in_user):
    yaml_connections(monkeypatch, YAML_ENTRY)
    service = ChatConfigService()
    await service.save_connection("db-webui", "https://db.test/api/", "sk-db", logged_in_user)

    connections, default = await service.connections()

    by_name = {connection.name: connection for connection in connections}
    assert by_name["yaml-webui"].source == "config"
    assert by_name["db-webui"].source == "database"
    assert by_name["db-webui"].endpoint == "https://db.test/api"
    assert by_name["db-webui"].token_set and by_name["db-webui"].token_readable
    assert by_name["db-webui"].updated_by == logged_in_user.id
    assert default is None


async def test_a_yaml_name_cannot_be_saved_or_deleted(monkeypatch, logged_in_user):
    yaml_connections(monkeypatch, YAML_ENTRY)

    with pytest.raises(ChatConfigError):
        await ChatConfigService().save_connection("yaml-webui", "https://other.test", "sk", logged_in_user)
    with pytest.raises(ChatConfigError):
        await ChatConfigService().delete_connection("yaml-webui")


async def test_an_endpoint_must_be_http(logged_in_user):
    with pytest.raises(ChatConfigError):
        await ChatConfigService().save_connection("bad", "ftp://model.test", "sk", logged_in_user)


async def test_saving_without_a_token_keeps_the_old_one(scripted_client, logged_in_user):
    service = ChatConfigService()
    await service.save_connection("db-webui", "https://db.test/api", "sk-first", logged_in_user)
    await service.save_connection("db-webui", "https://db2.test/api", None, logged_in_user)

    await service.client_for("db-webui")

    assert scripted_client.credentials == [("https://db2.test/api", "sk-first")]


async def test_a_token_from_another_secret_key_shows_as_unreadable(logged_in_user, monkeypatch):
    service = ChatConfigService()
    await service.save_connection("db-webui", "https://db.test/api", "sk-first", logged_in_user)
    await service.set_default(DefaultModel("db-webui", "Gemma-4", 65536, True, True), logged_in_user)
    monkeypatch.setitem(ScyllaCluster.get().config, "SECRET_KEY", "rotated-secret")

    connections, _ = await service.connections()

    assert next(c for c in connections if c.name == "db-webui").token_readable is False
    assert await service.resolve() is None


async def test_the_default_model_is_stored_and_resolved(scripted_client, logged_in_user):
    service = ChatConfigService()
    await service.save_connection("db-webui", "https://db.test/api", "sk-db", logged_in_user)

    saved = await service.set_default(DefaultModel("db-webui", "Gemma-4", 65536, True, True), logged_in_user)
    resolved = await service.resolve()

    assert (saved.model, saved.set_by) == ("Gemma-4", logged_in_user.id)
    assert (resolved.connection, resolved.model, resolved.context_window, resolved.tools) == (
        "db-webui", "Gemma-4", 65536, True)
    assert resolved.client is scripted_client
    assert scripted_client.credentials == [("https://db.test/api", "sk-db")]


async def test_the_default_needs_a_known_connection(logged_in_user):
    with pytest.raises(ChatConfigError):
        await ChatConfigService().set_default(DefaultModel("missing", "m", 1000, True, False), logged_in_user)


async def test_deleting_the_default_connection_clears_the_default(logged_in_user):
    service = ChatConfigService()
    await service.save_connection("db-webui", "https://db.test/api", "sk-db", logged_in_user)
    await service.set_default(DefaultModel("db-webui", "Gemma-4", 65536, True, True), logged_in_user)

    await service.delete_connection("db-webui")

    connections, default = await service.connections()
    assert default is None
    assert all(connection.name != "db-webui" for connection in connections)
    assert await service.resolve() is None


async def test_without_a_default_the_first_yaml_model_is_used(monkeypatch, scripted_client):
    yaml_connections(monkeypatch, {"name": "no-model", "endpoint": "https://a.test"}, YAML_ENTRY)
    scripted_client.models = [ProbedModel("Gemma-4", "Gemma-4", 65536, True, False)]

    resolved = await ChatConfigService().resolve()

    assert (resolved.connection, resolved.model, resolved.context_window, resolved.tools) == (
        "yaml-webui", "Gemma-4", 65536, True)


async def test_nothing_configured_resolves_to_none():
    assert await ChatConfigService().resolve() is None


async def test_the_probe_lists_the_models(scripted_client, logged_in_user):
    await ChatConfigService().save_connection("db-webui", "https://db.test/api", "sk-db", logged_in_user)
    scripted_client.models = [ProbedModel("a", "a", None, None, None)]

    assert await ChatConfigService().probe("db-webui") == scripted_client.models


async def test_the_tool_test_reports_a_tool_call(scripted_client, logged_in_user):
    await ChatConfigService().save_connection("db-webui", "https://db.test/api", "sk-db", logged_in_user)
    scripted_client.turns = [[ToolCallsReady([ToolCall("c", "get_time", "{}")]), Finished("tool_calls")],
                             [TextDelta("It is noon"), Finished("stop")],
                             [ChatModelError("model not loaded")]]
    service = ChatConfigService()

    called = await service.test_tools("db-webui", "Gemma-4")
    answered = await service.test_tools("db-webui", "Gemma-3")
    failed = await service.test_tools("db-webui", "Missing")

    assert called.tools is True
    assert (answered.tools, "It is noon" in answered.detail) == (False, True)
    assert (failed.tools, failed.detail) == (False, "model not loaded")
    assert scripted_client.requests[0].tools[0].name == "get_time"
