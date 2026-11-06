from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from coodie.exceptions import DocumentNotFound

from argus.backend.error_handlers import APIException
from argus.backend.models.web import ArgusRelease, ArgusUserView
from argus.backend.service.views import UserViewService

EntityType = Literal["release", "view"]


class ChatEntityError(APIException):
    pass


@dataclass(slots=True, frozen=True)
class ChatEntity:
    id: UUID
    type: EntityType
    name: str
    release_ids: tuple[UUID, ...]
    test_ids: frozenset[UUID] | None

    def reaches_test(self, test_id: UUID) -> bool:
        return self.test_ids is None or test_id in self.test_ids

    def reaches_release(self, release_id: UUID) -> bool:
        return release_id in self.release_ids


async def resolve_entity(entity_type: str, entity_id: UUID) -> ChatEntity:
    match entity_type:
        case "release":
            try:
                release = await ArgusRelease.get(id=entity_id)
            except DocumentNotFound as exception:
                raise ChatEntityError(f"Release {entity_id} does not exist") from exception
            return ChatEntity(id=release.id, type="release", name=release.name, release_ids=(release.id,),
                              test_ids=None)
        case "view":
            try:
                view = await ArgusUserView.get(id=entity_id)
            except DocumentNotFound as exception:
                raise ChatEntityError(f"View {entity_id} does not exist") from exception
            tests = await UserViewService().resolve_tests_by_id(view.tests)
            release_ids = tuple(sorted({test.release_id for test in tests}, key=str))
            return ChatEntity(id=view.id, type="view", name=view.display_name or view.name,
                              release_ids=release_ids, test_ids=frozenset(test.id for test in tests))
        case _:
            raise ChatEntityError(f"Unknown chat entity type {entity_type}")
