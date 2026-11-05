import struct
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import quote
from uuid import UUID

from argus.backend.error_handlers import APIException
from argus.backend.models.chat import GLOBAL_SCOPE, ChatIdentity
from argus.backend.models.web import User
from argus.backend.service.chat.config import ChatConfigService
from argus.backend.util.common import select_rows

PICTURE_LIMIT = 1024 * 1024
NAME_LIMIT = 40
IDENTITY_COLUMNS = ("connection", "name", "picture_type", "updated_by", "updated_at", "active")
JPEG_FRAME_MARKERS = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
JPEG_BARE_MARKERS = {0x01, *range(0xD0, 0xD8)}


class ChatIdentityError(APIException):
    pass


@dataclass(slots=True, frozen=True)
class Identity:
    connection: str
    name: str
    has_picture: bool
    updated_by: UUID | None = None
    updated_at: datetime | None = None


def _jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    index = 2
    while index + 9 <= len(data):
        if data[index] != 0xFF:
            return None
        marker = data[index + 1]
        if marker == 0xFF:
            index += 1
            continue
        if marker in JPEG_BARE_MARKERS:
            index += 2
            continue
        if marker in JPEG_FRAME_MARKERS:
            height, width = struct.unpack(">HH", data[index + 5:index + 9])
            return width, height
        index += 2 + struct.unpack(">H", data[index + 2:index + 4])[0]
    return None


def picture_dimensions(data: bytes) -> tuple[str, int, int]:
    """The media type, the width and the height of a PNG, JPEG, GIF or WebP picture, read from its header."""
    size = None
    if data.startswith(b"\x89PNG\r\n\x1a\n") and data[12:16] == b"IHDR" and len(data) >= 24:
        media_type, size = "image/png", struct.unpack(">II", data[16:24])
    elif data[:6] in (b"GIF87a", b"GIF89a") and len(data) >= 10:
        media_type, size = "image/gif", struct.unpack("<HH", data[6:10])
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP" and len(data) >= 30:
        media_type = "image/webp"
        match data[12:16]:
            case b"VP8 ":
                width, height = struct.unpack("<HH", data[26:30])
                size = width & 0x3FFF, height & 0x3FFF
            case b"VP8L":
                bits = int.from_bytes(data[21:25], "little")
                size = (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
            case b"VP8X":
                size = int.from_bytes(data[24:27], "little") + 1, int.from_bytes(data[27:30], "little") + 1
    elif data[:2] == b"\xff\xd8":
        media_type, size = "image/jpeg", _jpeg_dimensions(data)
    if size is None:
        raise ChatIdentityError("The picture must be a PNG, JPEG, GIF or WebP image")
    return media_type, *size


def check_picture(data: bytes) -> str:
    if len(data) > PICTURE_LIMIT:
        raise ChatIdentityError("The picture must be 1 MB or smaller")
    media_type, width, height = picture_dimensions(data)
    if width != height or width == 0:
        raise ChatIdentityError(f"The picture must be square; this one is {width}×{height}")
    return media_type


def identity_json(identity: Identity | None) -> dict | None:
    if identity is None:
        return None
    picture_url = None
    if identity.has_picture:
        version = int(identity.updated_at.timestamp()) if identity.updated_at else 0
        picture_url = f"/api/v1/chat/identity/{quote(identity.connection, safe='')}/picture?v={version}"
    return {"connection": identity.connection, "name": identity.name, "picture_url": picture_url,
            "updated_by": identity.updated_by, "updated_at": identity.updated_at}


class ChatIdentityService:
    """The assistant's name and picture: one identity per connection, one of them active."""

    @staticmethod
    async def _rows() -> list[dict]:
        return await select_rows(ChatIdentity.find(scope=GLOBAL_SCOPE), *IDENTITY_COLUMNS)

    async def identities(self) -> tuple[list[Identity], str | None]:
        rows = await self._rows()
        identities = [Identity(connection=row["connection"], name=row["name"], has_picture=bool(row["picture_type"]),
                               updated_by=row["updated_by"], updated_at=row["updated_at"])
                      for row in rows if row["connection"] is not None and row["name"]]
        return identities, rows[0]["active"] if rows else None

    async def active(self) -> Identity | None:
        identities, active = await self.identities()
        return next((identity for identity in identities if identity.connection == active), None)

    async def save(self, connection: str, name: str, picture: bytes | None, remove_picture: bool,
                   user: User) -> Identity:
        connections, _ = await ChatConfigService().connections()
        if not any(known.name == connection for known in connections):
            raise ChatIdentityError(f"No connection named {connection}")
        name = name.strip()
        if not name or len(name) > NAME_LIMIT:
            raise ChatIdentityError(f"The name must have 1 to {NAME_LIMIT} characters")
        fields = {"name": name, "updated_by": user.id, "updated_at": datetime.now(UTC)}
        if picture:
            fields |= {"picture": picture, "picture_type": check_picture(picture)}
        elif remove_picture:
            fields |= {"picture": None, "picture_type": None}
        await ChatIdentity(connection=connection).update(**fields)
        identities, _ = await self.identities()
        return next(identity for identity in identities if identity.connection == connection)

    async def delete(self, connection: str) -> None:
        rows = await self._rows()
        if not any(row["connection"] == connection for row in rows):
            return
        await ChatIdentity(connection=connection).delete()
        if rows[0]["active"] == connection:
            await ChatIdentity.find(scope=GLOBAL_SCOPE).update(active=None)

    async def set_active(self, connection: str | None) -> Identity | None:
        if connection is not None:
            identities, _ = await self.identities()
            if not any(identity.connection == connection for identity in identities):
                raise ChatIdentityError(f"The connection {connection} has no identity")
        await ChatIdentity.find(scope=GLOBAL_SCOPE).update(active=connection)
        return await self.active()

    async def picture(self, connection: str) -> tuple[bytes, str] | None:
        rows = await select_rows(ChatIdentity.find(scope=GLOBAL_SCOPE, connection=connection),
                                 "picture", "picture_type")
        if not rows or not rows[0]["picture"]:
            return None
        return rows[0]["picture"], rows[0]["picture_type"]
