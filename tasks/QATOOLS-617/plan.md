# QATOOLS-617 — implementation plan

**Spec:** `tasks/QATOOLS-617/spec.md`

A decision during the build that changes what the spec states updates the
spec in the same commit. A line in its `Decisions` section records the
decision when the Design section does not state the reason. This paragraph
stays in every plan built from a spec.

## Rules

- Follow `docs/standards/`. Backend: one router per feature, an
  `api.<module>.<function>` route name, `Depends(api_current_user)`, the
  `APIResponse` envelope, typed exceptions raised and never returned.
  Frontend: Svelte 5 runes, TypeScript, Bootstrap first, no `querySelector`.
- Backend tests live in `argus/backend/tests/chat/` and carry
  `pytestmark = pytest.mark.docker_required`. They create and read rows
  through services and routes, never through `Model.save()` or `find()` in
  the test body.
- The model endpoint is never called in tests. `ScriptedClient` in
  `argus/backend/tests/chat/helpers.py` implements `ChatModelClient` and plays
  back a list of turns. The tests patch the client factory in
  `service/chat/config.py`.
- Jenkins is patched with the existing `mock_jenkins_service` pattern, here
  at the `argus.backend.service.chat.actions.JenkinsService` import site.
- Commit scopes need at least 5 characters, so the code commits use
  `chat-mode`. Every import sits at the top of the module.
- Verify with `uv run pre-commit run --all-files`, `uv run pytest
  argus/backend/tests/chat` (the full suite before the last commit),
  `yarn test`, and `yarn build`.

## Task 1 — Model connections, the adapter, and the admin API

**Files:**
- Modify: `pyproject.toml`, `uv.lock` (`uv add openai`)
- Create: `argus/backend/util/secrets.py`
- Create: `argus/backend/models/chat.py` (`ChatConfiguration`, plus the tables of task 2, so that one file holds the chat schema)
- Modify: `argus/backend/models/web.py` (`USED_MODELS`)
- Create: `argus/backend/service/chat/__init__.py`, `llm.py`, `config.py`
- Modify: `argus/backend/controller/admin_api.py`
- Modify: `argus_web.example.yaml` (`CHAT_MODELS`)
- Test: `argus/backend/tests/chat/helpers.py`, `test_secrets.py`, `test_llm.py`, `test_config.py`, `test_admin_chat_api.py`

**Internals:**
- `secrets.py`:
  - `encrypt(text) -> str` and `decrypt(token) -> str`, using Fernet with an HKDF-SHA256 key from `SECRET_KEY` (info `b"argus-chat-token"`).
  - `SecretUnreadable` is raised on `InvalidToken`.
- `llm.py`:
  - the spec's `ToolCall`, `ChatMessage`, `ToolSpec`
  - the stream events `TextDelta(text)`, `ReasoningDelta(text)`, `ToolCallsReady(calls)`, `Usage(prompt_tokens, completion_tokens)`, `Finished(reason)`
  - `ProbedModel`
  - the `ChatModelClient` protocol
  - `OpenAIChatClient`:
    - `AsyncOpenAI(base_url, api_key, timeout=300)`
    - `stream()` merges `tool_calls` deltas by index and reads `reasoning_content` from `delta.model_extra`.
    - `list_models()` uses raw `client.get("/models")` so the extra fields survive.
  - `normalize_model(entry: dict) -> ProbedModel`, the probe rules of the spec.
- `config.py`:
  - `ChatModelsConfig` (Pydantic list of `ConfiguredConnection{name, endpoint, token, model?}`), read from `Config.load_yaml_config()["CHAT_MODELS"]`.
  - `ChatConfigService` as in the spec's Module API.
  - `ResolvedModel{connection, model, context_window, tools, vision, client}`.
  - `make_client(endpoint, token) -> ChatModelClient` is the seam that tests patch.
  - `ChatConfigError(APIException)`.
  - `test_tools` sends one user message and one dummy tool `get_time`, and reports whether a `ToolCallsReady` arrived.
  - When no default row exists, `resolve()` falls back to the first YAML entry with a `model`, and probes it once per process for its context window and tools.
- Admin routes as in the spec, named `admin.admin_api.chat_*`.

- [ ] Write the failing tests:
  - secrets round trip; a wrong key raises
  - `normalize_model` on the OpenWebUI/Lemonade shape, a plain OpenAI entry and a vLLM `max_model_len`
  - the `OpenAIChatClient` stream against an `httpx.MockTransport` of SSE chunks with split tool-call deltas and `reasoning_content`
  - YAML and database merge; a name collision rejected; the token never returned; an update without a token keeps the old one
  - default set and resolved; the fallback default
  - `test_tools` with the scripted client
  - admin routes refuse a non-admin
- [ ] Run them and confirm the failures.
- [ ] Write the code.
- [ ] Run the verify sequence.
- [ ] Commit `feature(chat-mode): connect Argus to OpenAI-compatible chat models`.

## Task 2 — Entities, the message tree, and the state table

**Files:**
- Modify: `argus/backend/models/chat.py` (`ChatState`, `ChatHistory`, `ChatMemory`, `ChatMemoryRevision`)
- Create: `argus/backend/service/chat/entity.py`, `history.py`
- Test: `argus/backend/tests/chat/test_history.py`

**Internals:**
- `entity.py`:
  - `ChatEntity` (from the spec).
  - `async resolve_entity(entity_type, entity_id) -> ChatEntity`. A release gets all of its tests (`test_ids=None`). A view gets `view.tests` through `UserViewService.resolve_view_tests`, and the distinct `release_id` of those tests.
  - `ChatEntityError(APIException)` for an unknown type or id.
- `history.py`, `ChatHistoryService(entity)`:
  - Reads: `read() -> (state, nodes)`, `active_path(nodes, head) -> list`.
  - Writes: `append(node_fields) -> ChatHistory` (a `uuid1()` node), `flush(node, **fields)`, `finish(node, status, ...)`.
  - Head and lock:
    - `move_head(expected, new) -> bool` is an LWT on `ChatState`.
    - `acquire(user, node) -> None` creates the state row with `IF NOT EXISTS`, then sets `busy` with an LWT `IF busy = null`, or `IF busy = <stale>` when `busy_since` is more than 5 minutes old. Otherwise it raises `ChatBusyError` (409, naming the asker).
    - `release(node)` is an LWT `IF busy = node`.
  - Tree operations:
    - `undo(user)`: head moves to the parent of the last user node on the path, which is marked `hidden` with its descendants.
    - `set_head(node)`: moves to the newest visible leaf below `node`.
  - Helpers: `siblings(nodes, node)`, `node_json(row) -> dict`.

- [ ] Write the failing tests:
  - append and read in order
  - the active path after a retry, a branch switch and an undo
  - a second `acquire` raises `ChatBusyError`; a stale lock is taken over; `release` frees it
  - `move_head` with a wrong expected value is not applied
  - a view entity resolves its tests and releases; an unknown id raises
- [ ] Run them and confirm the failures.
- [ ] Write the code.
- [ ] Run the verify sequence.

## Task 3 — Memories, their routes, and findings in the summary

**Files:**
- Create: `argus/backend/service/chat/memory.py`
- Create: `argus/backend/controller/chat_api.py` (memory routes first; registered in `argus/backend/controller/api.py` next to the other included routers)
- Modify: `argus/backend/service/release_summary.py` (`get`, `get_for_view` add `findings`)
- Test: `argus/backend/tests/chat/test_memory.py`, `test_memory_api.py`, and a findings case in `argus/backend/tests/release_summary/test_release_summary_api.py`

**Internals:**
- `ChatMemoryService` as in the spec.
  - `scope` is the target entity id. It must be the entity itself, or for a view, one of its releases.
  - Each change writes a `ChatMemoryRevision` and sets `ChatMemory.revision`.
  - `revert(revision)` restores the `before` value (a revert of a `create` deletes, of a `delete` restores) and writes a `revert` revision with `reverts`.
  - `list()` reads the partitions of the entity and its releases with `gather_limited`, skips deleted entries, and adds `entity_name`.
  - `findings(entity_id)` returns `kind=finding` entries.
- `ChatMemoryError(APIException)`.

- [ ] Write the failing tests:
  - create, edit, delete, and history in order with authors
  - revert of each action
  - a view sees its releases' memories, and a write to a release outside the view is refused
  - the summary routes return `findings`, and a recompute (a new run, then a read) keeps them
- [ ] Run them and confirm the failures.
- [ ] Write the code.
- [ ] Run the verify sequence.

## Task 4 — The agent, the read tools, and the conversation routes

**Files:**
- Create: `argus/backend/service/chat/prompts/system.md`, `prompt.py`, `tools.py`, `agent.py`, `service.py`
- Modify: `argus/backend/controller/chat_api.py`
- Test: `argus/backend/tests/chat/test_prompt.py`, `test_tools.py`, `test_agent.py`, `test_chat_api.py`

**Internals:**
- `prompt.py`:
  - `build_system_prompt(entity, memories, summary, now) -> str` fills the template with `str.format_map`.
  - `compact_summary(summary_response, limit=40) -> str`.
  - `to_messages(path) -> list[ChatMessage]` starts at the newest `summary` node, adds the user prefix, and truncates tool content to 6000 characters.
  - `estimate_tokens(text) = len(text) // 4`.
  - `context_stats(path, model) -> dict`.
- `tools.py`:
  - `ToolContext{entity, user, node, history}`.
  - A registry `TOOLS: dict[str, Tool]`, where `Tool{spec: ToolSpec, args: type[BaseModel], run: Callable}`. The JSON schema comes from `model_json_schema()`.
  - Read tools and `write_memory`, as the spec's table.
  - `ToolScopeError` turns into an error result.
  - `run_tool(ctx, call) -> ToolOutcome{content, action}`. Unknown tools and validation errors come back as error content.
- `agent.py`:
  - `ChatAgent(entity, user, resolved_model)`.
  - `run(assistant_node, queue)`, the loop of the spec:
    - It streams the model and flushes about every second, or every 400 characters.
    - Each tool call gets a `tool` node; each proposal gets an `action` node.
    - At most 8 model calls.
    - It checks `stop_requested` on each flush.
    - It finishes the node and releases the lock in `finally`.
  - `compact(...)` uses the same loop with a summarization instruction and no tools, and writes a `summary` node.
- `service.py`:
  - `ChatService` as in the spec.
  - The streaming methods start `asyncio.create_task(agent.run(...))` and keep it in a module-level set until done, then yield SSE frames from the queue.
  - `sse(event, data) -> str`.
- Routes:
  - SSE through `StreamingResponse(media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})`.
  - The others use `APIResponse`.
  - `ChatNotConfiguredError` maps to an error response.

- [ ] Write the failing tests:
  - the prompt holds the memories of the view and of its release, the summary counts, the user prefix, and starts at a summary node
  - each read tool on seeded data; out-of-scope refused
  - the agent with a scripted turn of text writes the user and assistant nodes, usage and the memory snapshot
  - a scripted tool call writes `tool` nodes and a second model call; `write_memory` makes a revision with `source=chat` and `source_node`
  - the 8-call limit
  - an endpoint error marks the node `error` and frees the lock
  - stop
  - route: the SSE event order on send; 409 while busy; regenerate adds a sibling; undo; set_head; compact; a second user sees the conversation
  - not configured
- [ ] Run them and confirm the failures.
- [ ] Write the code.
- [ ] Run the verify sequence.
- [ ] Commit tasks 2–4: `feature(chat-mode): add the shared chat with memories`.

## Task 5 — Actions: start tests and link issues with confirmation

**Files:**
- Create: `argus/backend/service/chat/actions.py`
- Modify: `argus/backend/service/chat/tools.py` (the four action tools), `service.py` (`confirm`, `dismiss`), `chat_api.py`
- Test: `argus/backend/tests/chat/test_actions.py`

**Internals:**
- Resolution:
  - `resolve_test_reference(tests, groups, ref) -> ArgusTest`: `build_system_id`, then `group/test`, then a unique name. An ambiguous name gets a candidate list.
  - `resolve_labeled_tests(plan, labels, match_all) -> list[ArgusTest]`: a port of `ResolveLabeledTests`. It reads `ArgusReleasePlan.options` and fans a group out to its enabled tests. With no match, it lists the available labels.
- `propose_start(ctx, tests, overrides) -> Action`:
  - `JenkinsService().retrieve_job_parameters(build_id, None)` for each test, 5 at a time.
  - The overrides are checked against the parameter names and the `choices`.
  - `validate_sct_version_source` runs for SCT tests.
  - The result is proposed and rejected lists.
- `propose_link(ctx, run_id, url)` and `propose_unlink(ctx, run_id, issue)`: the run must be in scope; unlink resolves the issue by key or URL through `IssueService().get(filter_key="run_id", ...)`.
- `confirm_action(entity, node, user)`:
  - Moves `action_state` from `pending` to `running` with an LWT on the history row.
  - Runs `build_job(build_system_id, params, requested_by=user)` 5 at a time, or `IssueService().submit` / `delete`.
  - Stores the results, sets `done`, and appends a `tool` node with the outcome under the action node.
- `dismiss_action` moves the state from `pending` to `dismissed` with an LWT.

- [ ] Write the failing tests:
  - reference resolution order and ambiguity
  - label resolution, with a group fan-out and the available labels on no match
  - `backend=gce` against choices without gce is rejected with a reason
  - an unknown parameter is rejected
  - a valid override is merged over the last build's values
  - a test outside a view is refused
  - confirm builds each job once, as the confirming user; a second confirm and a confirm after dismiss are refused
  - Jenkins errors are recorded per test
  - link and unlink through the card
- [ ] Run them and confirm the failures.
- [ ] Write the code.
- [ ] Run the verify sequence.
- [ ] Commit `feature(chat-mode): start tests and link issues from the chat`.

## Task 6 — Admin Panel: connections and the model picker

**Files:**
- Create: `frontend/AdminPanel/ChatConfigManager.svelte`, `ChatModelPicker.svelte`, `ChatConfigManager.test.ts`
- Modify: `frontend/AdminPanel/AdminPanel.svelte` (the `chat` route and tab)
- Create: `frontend/Chat/types.ts` (the admin types and the conversation types of the spec)

**Internals:**
- The manager:
  - a connections card (YAML rows read-only; database rows editable with a token field showing "set" or "not set")
  - a default model card
  - `ModalWindow` for the picker
- The picker:
  - a connection select that probes on change
  - a filter
  - a table with context and badges, "?" for unknown
  - "Test tool calling" per row
  - editable context and tools where the probe found nothing
  - "Set as default"
  - a warning when tools are off
- [ ] Write the failing tests: rendering the merged list; the probe on select; set default posts the chosen model; the token is never prefilled.
- [ ] Run them and confirm the failures.
- [ ] Write the code.
- [ ] Run `yarn test` and `yarn build`.

## Task 7 — The chat modal, the anchor, and the findings card

**Files:**
- Create in `frontend/Chat/`:
  - `chatApi.ts`, `chatTree.ts`, `markdown.ts`
  - `ChatAnchor.svelte`, `ChatModal.svelte`, `ChatThread.svelte`, `ChatMessage.svelte`, `ChatComposer.svelte`, `ChatActionCard.svelte`, `ChatMemories.svelte`, `ChatContextStats.svelte`
  - tests for the two utility modules and the main components
- Modify:
  - `frontend/Common/ViewTypes.js` (`chat`)
  - `frontend/ReleaseDashboard/ReleaseDashboard.svelte` (the anchor in the header row)
  - `frontend/Views/Widgets/ReleaseSummary/ReleaseSummary.svelte`, `types.ts` (the Findings card)

**Internals:**
- `chatApi.ts`: `streamPost(url, body, onEvent, signal)` reads `response.body` and parses `event:`/`data:` frames.
- `chatTree.ts`: `activePath`, `siblingsOf`, `childrenOf`.
- `markdown.ts`: `renderMarkdown(text)` = `DOMPurify.sanitize(marked.parse(...))`.
- The modal:
  - It polls `GET` every 2 s while another user's generation runs, and every 10 s otherwise, with `setInterval` in `onMount` and cleanup in `onDestroy`.
  - It applies stream events to a local `$state` copy.
  - Tool and action nodes fold into their assistant turn.
  - Answers are collapsed except the one being streamed.
- Style: a `bg-light-one` inset with borderless `shadow-sm` white cards.

- [ ] Write the failing tests:
  - the SSE parser over split chunks
  - `activePath` and siblings
  - an answer collapsed by default that expands
  - the sibling switcher posts `/head`
  - the action card's Run and Dismiss
  - memory history revert
  - the anchor with the "not configured" state
  - the summary findings card
- [ ] Run them and confirm the failures.
- [ ] Write the code.
- [ ] Run `yarn test` and `yarn build`.
- [ ] Commit tasks 6–7: `feature(frontend): add the chat modal and the chat model picker`.

## Task 8 — Docs

**Files:**
- Create: `docs/release_chat.md`
- Modify: `docs/release_summary.md` (Findings), `docs/api_usage.md` (chat and admin routes), `docs/project/architecture.md` (the chat service, the first SSE route, the model adapter), `docs/INDEX.md`

- [ ] Write the docs: the chat, memories and findings, the requests with examples, how memories shape answers, connections and the default model.
- [ ] Run `uv run pre-commit run --all-files`.
- [ ] Commit `docs(chat-mode): describe the release and view chat`.

## Task 9 — Full verify and the live check

- [ ] `uv run pre-commit run --all-files`, `uv run pytest`, `yarn test`, `yarn build`.
- [ ] Run `sync-models` on the dev cluster.
- [ ] On the running dev server, set up the model:
  - add the `https://ai.komachi.sh/api` connection in the Admin Panel
  - probe it
  - set Gemma-4-12B-it-GGUF as the default
  - test tool calling
- [ ] Release chat on `scylla-2025.1`:
  - ask what failed on the newest rc and compare with the summary
  - try again, switch branches, undo, compact
  - add a finding through the chat and see it in the summary
  - a second session sees the conversation
- [ ] View chat: the view's memories and its release's memories reach the answer.
- [ ] A start proposal card with a rejected setting, dismissed.
- [ ] The `tools: false` path with Gemma-3-4b-it-GGUF.
- [ ] Headless Chrome at 1600 and 900 pixels.
- [ ] Record the results in the pull request body.
