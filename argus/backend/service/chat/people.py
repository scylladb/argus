from collections.abc import Iterable
from uuid import UUID

from argus.backend.models.web import User
from argus.backend.util.common import chunk, gather_limited

People = dict[UUID, User]


async def load_people(user_ids: Iterable[UUID | str | None]) -> People:
    wanted = list({UUID(str(user_id)) for user_id in user_ids if user_id})
    batches = await gather_limited(User.find(id__in=batch).all() for batch in chunk(wanted))
    return {user.id: user for batch in batches for user in batch}


def person(user_id: UUID | str | None, people: People) -> dict | None:
    """How a tool names a user to the model: the username and the full name, never the email."""
    if not user_id:
        return None
    user = people.get(UUID(str(user_id)))
    if user is None:
        return {"id": str(user_id), "unknown": True}
    return {"id": str(user.id), "username": user.username, "name": user.full_name or user.username}
