from uuid import UUID, uuid1

from argus.backend.models.chat import ChatHistory, ChatState
from argus.backend.models.web import User
from argus.backend.service.chat import tasks
from argus.backend.service.chat.actions import Seed, adjust_start, claim, execute, locate_card, refresh_zeus
from argus.backend.service.chat.agent import ChatAgent
from argus.backend.service.chat.config import ChatConfigService, ChatNotConfiguredError, ResolvedModel
from argus.backend.service.chat.conversation import conversation_json, node_json, state_event
from argus.backend.service.chat.entity import ChatEntity
from argus.backend.service.chat.history import ChatHistoryError, ChatHistoryService, active_path, as_utc
from argus.backend.service.chat.hub import ChatHub, default_hub
from argus.backend.service.chat.identity import ChatIdentityService, identity_json
from argus.backend.service.chat.memory import ChatMemoryService

MAX_QUESTION_LENGTH = 8000


class ChatService:
    def __init__(self, hub: ChatHub | None = None) -> None:
        self.hub = hub or default_hub

    @staticmethod
    async def _model() -> ResolvedModel:
        model = await ChatConfigService().resolve()
        if model is None:
            raise ChatNotConfiguredError("No chat model is configured. An administrator picks one in the "
                                         "Admin Panel, under Chat.")
        return model

    async def conversation(self, entity: ChatEntity) -> dict:
        state, nodes = await ChatHistoryService(entity).read()
        return conversation_json(entity, state, nodes, await ChatConfigService().resolve(),
                                 await ChatMemoryService().scopes(entity),
                                 identity_json(await ChatIdentityService().active()))

    async def meta(self, entity: ChatEntity) -> dict:
        _, nodes = await ChatHistoryService(entity).read()
        questions = [node for node in nodes if node.role == "user" and not node.hidden]
        last = max(questions, key=lambda node: node.node.time, default=None)
        return {"configured": await ChatConfigService().resolve() is not None, "messages": len(questions),
                "last": {"user_id": last.user_id, "at": as_utc(last.created_at)} if last else None}

    async def _publish_state(self, entity: ChatEntity, history: ChatHistoryService,
                             model: ResolvedModel | None) -> None:
        state, nodes = await history.read()
        self.hub.publish(entity.id, state_event(state, nodes, model))

    async def _start(self, entity: ChatEntity, user: User, model: ResolvedModel, history: ChatHistoryService,
                     node: UUID, build) -> tuple[ChatHistory | None, ChatHistory]:
        """Append the nodes of a new turn under the lock, then hand them to a background task."""
        await history.acquire(user, node)
        try:
            state, nodes = await history.read()
            asked, started = await build(state, nodes)
            if not await history.move_head(state.head, started.node):
                raise ChatHistoryError("The conversation changed meanwhile; try again")
        except BaseException:
            await history.release(node)
            raise
        for created in (asked, started):
            if created is not None:
                self.hub.publish(entity.id, {"type": "node", "node": node_json(created)})
        await self._publish_state(entity, history, model)
        return asked, started

    async def send(self, entity: ChatEntity, content: str, user: User, auto: bool = False) -> dict:
        content = content.strip()
        if not content:
            raise ChatHistoryError("Ask a question first")
        if len(content) > MAX_QUESTION_LENGTH:
            raise ChatHistoryError(f"A question holds at most {MAX_QUESTION_LENGTH} characters")
        model = await self._model()
        history = ChatHistoryService(entity)
        question_node, answer_node = uuid1(), uuid1()

        async def build(state: ChatState, nodes: list[ChatHistory]):
            asked = await history.append(node=question_node, role="user", content=content, user_id=user.id,
                                         parent=state.head)
            answer = await history.append(node=answer_node, role="assistant", status="streaming",
                                          user_id=user.id, parent=asked.node, model_name=model.model, auto=auto)
            return asked, answer

        asked, answer = await self._start(entity, user, model, history, answer_node, build)
        tasks.spawn(ChatAgent(entity, user, model, self.hub).answer(answer), name=f"chat-answer-{answer.node}")
        return {"user_node": node_json(asked), "assistant_node": node_json(answer)}

    async def regenerate(self, entity: ChatEntity, user: User, auto: bool = False) -> dict:
        model = await self._model()
        history = ChatHistoryService(entity)
        answer_node = uuid1()

        async def build(state: ChatState, nodes: list[ChatHistory]):
            question = next((node for node in reversed(active_path(nodes, state.head)) if node.role == "user"), None)
            if question is None:
                raise ChatHistoryError("There is no question to answer again")
            answer = await history.append(node=answer_node, role="assistant", status="streaming",
                                          user_id=user.id, parent=question.node, model_name=model.model, auto=auto)
            return None, answer

        _, answer = await self._start(entity, user, model, history, answer_node, build)
        tasks.spawn(ChatAgent(entity, user, model, self.hub).answer(answer), name=f"chat-answer-{answer.node}")
        return {"user_node": None, "assistant_node": node_json(answer)}

    async def compact(self, entity: ChatEntity, user: User) -> dict:
        model = await self._model()
        history = ChatHistoryService(entity)
        summary_node = uuid1()

        async def build(state: ChatState, nodes: list[ChatHistory]):
            if state.head is None:
                raise ChatHistoryError("There is nothing to compact yet")
            summary = await history.append(node=summary_node, role="summary", status="streaming",
                                           user_id=user.id, parent=state.head, model_name=model.model)
            return None, summary

        _, summary = await self._start(entity, user, model, history, summary_node, build)
        tasks.spawn(ChatAgent(entity, user, model, self.hub).compact(summary), name=f"chat-compact-{summary.node}")
        return {"user_node": None, "assistant_node": node_json(summary)}

    async def _after_tree_change(self, entity: ChatEntity) -> dict:
        conversation = await self.conversation(entity)
        self.hub.publish(entity.id, {"type": "snapshot", "conversation": conversation})
        return conversation

    async def undo(self, entity: ChatEntity) -> dict:
        await ChatHistoryService(entity).undo()
        return await self._after_tree_change(entity)

    async def set_head(self, entity: ChatEntity, node: UUID) -> dict:
        await ChatHistoryService(entity).set_head(node)
        return await self._after_tree_change(entity)

    async def fork(self, entity: ChatEntity, node: UUID) -> dict:
        await ChatHistoryService(entity).fork(node)
        return await self._after_tree_change(entity)

    async def wipe(self, entity: ChatEntity) -> dict:
        await ChatHistoryService(entity).wipe()
        return await self._after_tree_change(entity)

    async def stop(self, entity: ChatEntity) -> UUID | None:
        history = ChatHistoryService(entity)
        state = await history.state()
        if state.busy is None:
            return None
        await ChatState(entity_id=entity.id).update(stop_requested=state.busy)
        return state.busy

    async def _publish_card(self, entity: ChatEntity, card: ChatHistory) -> dict:
        node = node_json(card)
        self.hub.publish(entity.id, {"type": "node", "node": node})
        return node

    async def confirm(self, entity: ChatEntity, node: UUID, user: User) -> dict:
        card, action = await claim(entity, node, user, "running")

        async def run() -> None:
            await execute(entity, card, action, user)
            await self._publish_card(entity, card)

        tasks.spawn(run(), name=f"chat-action-{node}")
        return await self._publish_card(entity, card)

    async def adjust(self, entity: ChatEntity, node: UUID, tests: dict[str, dict[str, str]],
                     seed: Seed | None = None) -> dict:
        card, _ = await adjust_start(entity, node, replace=tests, seed=seed)
        return await self._publish_card(entity, card)

    async def dismiss(self, entity: ChatEntity, node: UUID, user: User) -> dict:
        card, _ = await claim(entity, node, user, "dismissed")
        return await self._publish_card(entity, card)

    async def refresh(self, entity: ChatEntity, node: UUID) -> dict:
        card = await locate_card(entity, node)
        await refresh_zeus(entity, card)
        return await self._publish_card(entity, card)
