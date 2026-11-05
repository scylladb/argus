import struct
import time

import pytest
from starlette.testclient import TestClient

from argus.backend.service.chat.identity import PICTURE_LIMIT, ChatIdentityError, check_picture, picture_dimensions
from argus.backend.tests.chat.helpers import seed_entity_release, text_turn

API = "/admin/api/v1/chat"


def png(width: int, height: int, padding: int = 0) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", width, height) + b"\0" * (
        5 + padding)


def jpeg(width: int, height: int) -> bytes:
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\0" + b"\0" * 9
    sof = b"\xff\xc0" + struct.pack(">HBHH", 11, 8, height, width) + b"\x01\x01\x11\x00"
    return b"\xff\xd8" + app0 + sof


def webp(chunk: bytes, body: bytes) -> bytes:
    return b"RIFF" + b"\0" * 4 + b"WEBP" + chunk + struct.pack("<I", len(body)) + body


@pytest.mark.parametrize(("data", "expected"), [
    (png(64, 32), ("image/png", 64, 32)),
    (b"GIF89a" + struct.pack("<HH", 48, 48) + b"\0" * 8, ("image/gif", 48, 48)),
    (jpeg(120, 120), ("image/jpeg", 120, 120)),
    (webp(b"VP8 ", b"\0\0\0\x9d\x01\x2a" + struct.pack("<HH", 96, 96)), ("image/webp", 96, 96)),
    (webp(b"VP8L", b"\x2f" + ((99 << 14) | 99).to_bytes(4, "little") + b"\0" * 8), ("image/webp", 100, 100)),
    (webp(b"VP8X", b"\0" * 4 + (255).to_bytes(3, "little") + (127).to_bytes(3, "little")), ("image/webp", 256, 128)),
])
def test_picture_dimensions_come_from_the_header(data, expected):
    assert picture_dimensions(data) == expected


def test_a_picture_must_be_square_small_and_an_image():
    assert check_picture(png(80, 80)) == "image/png"
    with pytest.raises(ChatIdentityError, match="square"):
        check_picture(png(80, 40))
    with pytest.raises(ChatIdentityError, match="1 MB"):
        check_picture(png(80, 80, padding=PICTURE_LIMIT))
    with pytest.raises(ChatIdentityError, match="PNG, JPEG"):
        check_picture(b"<svg xmlns='http://www.w3.org/2000/svg'/>")


def ok(response) -> dict | list | None:
    body = response.json()
    assert body["status"] == "ok", body
    return body["response"]


def save_identity(client: TestClient, connection: str, name: str, picture: bytes | None = None, **form):
    files = {"picture": ("avatar.png", picture, "image/png")} if picture is not None else None
    return client.post(f"{API}/connection/{connection}/identity", data={"assistant_name": name, **form},
                       files=files)


@pytest.mark.docker_required
async def test_an_active_identity_names_the_assistant(chat_client: TestClient, chat_model, release_manager_service):
    seeded = await seed_entity_release(release_manager_service)
    base = f"/api/v1/chat/release/{seeded.release.id}"

    saved = ok(save_identity(chat_client, "scripted", "  Argos  ", png(64, 64)))
    assert ok(chat_client.get(base))["assistant"] is None
    ok(chat_client.post(f"{API}/identity/active", json={"connection": "scripted"}))
    chat_model.turns = [text_turn("hello")]
    ok(chat_client.post(f"{base}/messages", json={"content": "who are you?"}))
    deadline = time.monotonic() + 10
    while ok(chat_client.get(base))["busy"] is not None and time.monotonic() < deadline:
        time.sleep(0.05)

    conversation = ok(chat_client.get(base))
    picture = chat_client.get(saved["picture_url"])
    listed = ok(chat_client.get(f"{API}/connections"))
    assert saved["name"] == "Argos"
    assert conversation["assistant"] == saved
    assert picture.status_code == 200 and picture.headers["content-type"] == "image/png"
    assert picture.content == png(64, 64)
    assert listed["active_identity"] == "scripted" and listed["identities"] == [saved]
    assert chat_model.requests[0].messages[0].content.startswith("You are Argos, the assistant of Argus")


@pytest.mark.docker_required
@pytest.mark.usefixtures("chat_model")
def test_an_identity_is_checked_and_follows_its_connection(chat_client: TestClient):
    assert save_identity(chat_client, "scripted", "Argos", png(64, 32)).json()["status"] == "error"
    assert save_identity(chat_client, "missing", "Argos").json()["status"] == "error"
    assert save_identity(chat_client, "scripted", " ").json()["status"] == "error"
    assert chat_client.post(f"{API}/identity/active", json={"connection": "scripted"}).json()["status"] == "error"

    ok(save_identity(chat_client, "scripted", "Argos", png(64, 64)))
    ok(chat_client.post(f"{API}/identity/active", json={"connection": "scripted"}))
    renamed = ok(save_identity(chat_client, "scripted", "Hermes"))
    removed = ok(save_identity(chat_client, "scripted", "Hermes", remove_picture="true"))
    ok(chat_client.delete(f"{API}/connection/scripted"))

    listed = ok(chat_client.get(f"{API}/connections"))
    assert renamed["picture_url"] is not None
    assert removed["picture_url"] is None
    assert listed["identities"] == [] and listed["active_identity"] is None
