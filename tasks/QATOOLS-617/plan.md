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
- Modify: `pyproject.toml`, `uv.lock` (`openai` in the `web-backend` extra)
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

- [x] Write the failing tests:
  - secrets round trip; a wrong key raises
  - `normalize_model` on the OpenWebUI/Lemonade shape, a plain OpenAI entry and a vLLM `max_model_len`
  - the `OpenAIChatClient` stream against an `httpx2.MockTransport` of streamed chunks with split tool-call deltas and `reasoning_content`
  - YAML and database merge; a name collision rejected; the token never returned; an update without a token keeps the old one
  - default set and resolved; the fallback default
  - `test_tools` with the scripted client
  - admin routes refuse a non-admin
- [ ] Run them and confirm the failures.
- [x] Write the code.
- [x] Run the verify sequence.
- [x] Commit `feature(chat-mode): connect Argus to OpenAI-compatible chat models`.

## Task 2 — Entities, the message tree, and the state table

**Files:**
- Modify: `argus/backend/models/chat.py` (`ChatState`, `ChatPresence`, `ChatHistory`, `ChatMemory`, `ChatMemoryRevision`)
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

- [x] Write the failing tests:
  - append and read in order
  - the active path after a retry, a branch switch and an undo
  - a second `acquire` raises `ChatBusyError`; a stale lock is taken over; `release` frees it
  - `move_head` with a wrong expected value is not applied
  - a view entity resolves its tests and releases; an unknown id raises
- [x] Run them and confirm the failures.
- [x] Write the code.
- [x] Run the verify sequence.

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

- [x] Write the failing tests:
  - create, edit, delete, and history in order with authors
  - revert of each action
  - a view sees its releases' memories, and a write to a release outside the view is refused
  - the summary routes return `findings`, and a recompute (a new run, then a read) keeps them
- [x] Run them and confirm the failures.
- [x] Write the code.
- [x] Run the verify sequence.

## Task 4 — The agent, the read tools, and the conversation routes

**Files:**
- Create: `argus/backend/service/chat/prompts/system.md`, `prompt.py`, `tools.py`, `agent.py`, `tasks.py`, `hub.py`, `service.py`
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
  - `run(assistant_node)`, the loop of the spec:
    - It streams the model, publishes `delta`/`tool`/`node` events to the hub, and flushes the node and `touch`es the state row every 0.5 s.
    - Each tool call gets a `tool` node; each proposal gets an `action` node.
    - At most 8 model calls.
    - It checks `stop_requested` on each flush.
    - It finishes the node and releases the lock in `finally`.
  - `compact(...)` uses the same loop with a summarization instruction and no tools, and writes a `summary` node.
- `service.py`:
  - `ChatService` as in the spec.
  - `send`, `regenerate` and `compact` take the lock, write the nodes, `tasks.spawn(agent.run(...))`, and return `Started`.
- `tasks.py`:
  - `spawn(coro, name)` keeps a strong reference until the task is done and logs its failure.
  - `shutdown()` cancels the running tasks. It is wired into the app lifespan, so an interrupted node ends `stopped`.
- `hub.py`, `ChatHub` (a module singleton per worker):
  - It keeps one `asyncio.Queue` per open stream, grouped by entity, and one watcher task per entity with a local stream.
  - The watcher reads `ChatState` for the entity and its releases every 0.5 s. When `changed_at` moves, it reads the partition and pushes the nodes whose `updated_at` moved, plus a `state` event. When `memory_changed_at` moves, it pushes a `memory` event. Every 2 s it reads `ChatPresence` and pushes `presence` when the list changes.
  - Each stream refreshes its presence row with `USING TTL 45` every 15 s.
  - `publish` puts to local stream queues only and never blocks: a full queue ends that stream, and the client reconnects into a fresh snapshot.
  - `touch(entity_id, memory=False)` writes `changed_at` or `memory_changed_at`.
- Routes:
  - The commands use `APIResponse`. `ChatBusyError` and `ChatNotConfiguredError` are `APIException`s.
  - `GET /events` uses `Depends(api_current_user)` and returns `StreamingResponse(media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})`. It yields `retry: 1000`, the `snapshot`, then the events of the subscription, and a `heartbeat` event every 10 s. A stream ends after 25 s, or at once when `close_streams_on_exit` sees the server's shutdown signal. The generator's `finally` unsubscribes, so a client that leaves frees its queue and its presence.

- [x] Write the failing tests:
  - the prompt holds the memories of the view and of its release, the summary counts, the user prefix, and starts at a summary node
  - each read tool on seeded data; out-of-scope refused
  - the agent with a scripted turn of text writes the user and assistant nodes, usage and the memory snapshot
  - a scripted tool call writes `tool` nodes and a second model call; `write_memory` makes a revision with `source=chat` and `source_node`
  - the 8-call limit
  - an endpoint error marks the node `error` and frees the lock
  - stop
  - route: send returns `Started` and the stream gets `node`, `delta` and the final `node`/`state`; a second send while busy is refused; regenerate adds a sibling; undo; set_head; compact
  - a stream subscribed before a write made through another hub instance (a second worker) gets the changed node from the watcher
  - presence lists two users with the chat open
  - the event stream sends a `snapshot` first, and refuses an unknown entity
  - not configured
- [x] Run them and confirm the failures.
- [x] Write the code.
- [x] Run the verify sequence.
- [x] Committed tasks 2–4 in `feature(chat-mode): add the shared chat of releases and views`.

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
  - Stores the results on the card and sets `done`; the prompt turns a done or dismissed card into an `[Argus]` note.
- `dismiss_action` moves the state from `pending` to `dismissed` with an LWT.

- [x] Write the failing tests:
  - reference resolution order and ambiguity
  - label resolution, with a group fan-out and the available labels on no match
  - `backend=gce` against choices without gce is rejected with a reason
  - an unknown parameter is rejected
  - a valid override is merged over the last build's values
  - a test outside a view is refused
  - confirm builds each job once, as the confirming user; a second confirm and a confirm after dismiss are refused
  - Jenkins errors are recorded per test
  - link and unlink through the card
- [x] Run them and confirm the failures.
- [x] Write the code.
- [x] Run the verify sequence.
- [x] Committed in `feature(chat-mode): add the shared chat of releases and views`, with its frontend in `feature(frontend): add the chat modal and the chat admin panel`.

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
- [x] Write the failing tests: rendering the merged list; the probe on select; set default posts the chosen model; the token is never prefilled.
- [ ] Run them and confirm the failures.
- [x] Write the code.
- [x] Run `yarn test` and `yarn build`.

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
- `chatEvents.ts`: `connectChat(url, handlers)` wraps `EventSource`. It parses each `data:` JSON and tracks `live`: true after any event or heartbeat, false after 40 s of silence or an error, so the modal polls `GET` every 3 s while it is not live.
- `chatState.ts`: `applyEvent(conversation, event)`, a pure reducer over the spec's `ServerEvent`.
- `chatTree.ts`: `activePath`, `siblingsOf`, `childrenOf`.
- `markdown.ts`: `renderMarkdown(text)` = `DOMPurify.sanitize(marked.parse(...))`.
- The modal:
  - It opens the event stream while it is open and closes it on destroy.
  - It applies events to a local `$state` copy through `applyEvent`.
  - The header shows the presence avatars and the connection state.
  - Tool and action nodes fold into their assistant turn.
  - Answers are collapsed except the one being streamed.
- Style: a `bg-light-one` inset with borderless `shadow-sm` white cards.

- [x] Write the failing tests:
  - `applyEvent` for each event type, deltas followed by a replacing `node`
  - `connectChat` parses events and drops to not-live after silence, with a fake `EventSource`
  - `activePath` and siblings
  - an answer collapsed by default that expands
  - the sibling switcher posts `/head`
  - the action card's Run and Dismiss
  - memory history revert
  - the anchor with the "not configured" state
  - the summary findings card
- [ ] Run them and confirm the failures.
- [x] Write the code.
- [x] Run `yarn test` and `yarn build`.
- [x] Committed tasks 6–7 in `feature(frontend): add the chat modal and the chat admin panel`.

## Task 8 — Docs

**Files:**
- Create: `docs/release_chat.md`
- Modify: `docs/release_summary.md` (Findings), `docs/api_usage.md` (chat and admin routes), `docs/project/architecture.md` (the chat service, background tasks, the first server-sent event stream and its buffering header, the model adapter), `docs/INDEX.md`

- [x] Write the docs: the chat, memories and findings, the requests with examples, how memories shape answers, connections and the default model.
- [x] Run `uv run pre-commit run --all-files`.
- [x] Commit `docs(chat-mode): describe the release and view chat`.

## Task 10 — Queue Zeus investigations from the chat

**Files:**
- Create: `argus/backend/service/zeus_client.py`, `argus/backend/service/chat/people.py`
- Modify: `argus/backend/service/chat/actions.py` (propose, confirm and refresh a `zeus_investigation` card), `tools.py` (`investigate_runs`, `get_investigation`, offered only when Zeus is configured), `prompt.py` (the card note), `service.py` and `controller/chat_api.py` (`POST /actions/{node}/refresh`)
- Modify: `frontend/Chat/ChatActionCard.svelte`, `ChatMessage.svelte`, `ChatModal.svelte`, `types.ts`
- Test: `argus/backend/tests/chat/test_zeus.py`, `frontend/Chat/ChatActionCard.test.ts`

**Internals:**
- `ZeusClient`: reads `ZEUS_SCHEMA`, `ZEUS_HOST` and `ZEUS_TOKEN` from the config; `configured()`, `investigate(prompt) -> task_id`, `status(task_id) -> dict`. `ZeusError` carries Zeus's `detail`.
- `zeus_prompt(run, test, release, entity, user, question)`.
- `refresh_zeus(entity, card, force=False)`: skipped when `refreshed_at` is younger than 15 s and not forced; reads every task that is not completed or failed, stores the status, the report and the error, and flushes the card.
- `Tool.available`: a callable that hides a tool from the model.
- `load_people(ids)` and `person(id, people)`: one batched user read per tool call; `get_users` and `get_assignees` (active plans as the run assignment reads them, the test's and the group's assignees, the last run); the run, plan and memory tools name people with them.

- [x] Write the failing tests:
  - `ZeusClient` against an `httpx` mock transport: the bearer token, 202, 503 with its detail, status
  - a proposal for runs in scope, with the prompt; a run outside the chat refused; more than 5 runs refused
  - confirm queues each run once; a 503 for one run is recorded and the others are queued
  - refresh stores a completed report; a second refresh within 15 s reads nothing; a failed Zeus call keeps the last status
  - `get_investigation` returns the reports and refreshes stale cards
  - the tools are hidden without Zeus configuration
  - the prompt note of a done card carries the start of the report
  - the card in the frontend shows each task's status and the report, and refreshes while a task is open
  - `get_users` names stored users and marks unknown ids; `get_assignees` follows a group's plan assignment; `read_run` and `get_runs` name the assignee
  - `get_run_events` lists an SCT run's errors by severity and names who changed a run; `read_run` carries the error digest; `get_runs` shows and filters the version
- [x] Run them and confirm the failures.
- [x] Write the code.
- [x] Run the verify sequence.
- [x] Committed in `feature(chat-mode): add the shared chat of releases and views`, with its frontend in `feature(frontend): add the chat modal and the chat admin panel`.

## Task 11 — Wide references and `show_run`

**Files:**
- Modify: `argus/backend/service/chat/resolve.py` (`Scope.find_releases`, `find_groups`, `find_tests`, `resolve_release`, `resolve_group`, `resolve_tests`, `resolve_run_reference`, `run_url`; `run_in_scope` moves here), `tools.py` (every tool takes a reference string; `show_run`), `actions.py`, `agent.py` (`ToolOutcome.card_state`), `prompt.py`
- Modify: `frontend/Chat/ChatActionCard.svelte`, `types.ts`
- Test: `argus/backend/tests/chat/test_references.py`, the renamed arguments in `test_tools.py`, `test_actions.py`, `test_zeus.py`, `frontend/Chat/ChatActionCard.test.ts`

- [x] Write the failing tests: every form of each reference; a shared name asks for its group; a group or a release expands to its enabled tests; a run by id, `build_id#n`, `group/test#n`, `pretty name #n`, a Jenkins build URL; a test without a number lists its builds; `run_url` falls back to the plugin route; the show-run card opens in a new tab and asks for nothing.
- [x] Run them and confirm the failures.
- [x] Write the code.
- [x] Run the verify sequence.
- [x] Committed in `feature(chat-mode): add the shared chat of releases and views`, with its frontend in `feature(frontend): add the chat modal and the chat admin panel`.

## Task 12 — Zeus reports from the run discussion

**Files:**
- Modify: `argus/backend/service/chat/tools.py` (`read_discussion`, `get_investigation` reads the discussion and returns a `zeus_report` card; `is_zeus`, `discussion_report`), `prompt.py`
- Modify: `frontend/Chat/ChatActionCard.svelte`, `types.ts`
- Test: `argus/backend/tests/chat/test_discussion.py`, `test_zeus.py`, `frontend/Chat/ChatActionCard.test.ts`

- [x] Write the failing tests: the discussion names its authors and marks Zeus; the latest report joins its pieces and skips the notice; the card is ready and carries the whole report; no report is said plainly; reading needs no Zeus connection; the card renders the report with its author and the run link.
- [x] Run them and confirm the failures.
- [x] Write the code.
- [x] Run the verify sequence.
- [x] Committed in `feature(chat-mode): add the shared chat of releases and views`, with its frontend in `feature(frontend): add the chat modal and the chat admin panel`.

## Task 13 — The assistant's identity

**Files:**
- Create: `argus/backend/service/chat/identity.py` (`ChatIdentityService`, `picture_dimensions`, `check_picture`, `identity_json`)
- Modify: `argus/backend/models/chat.py` (`ChatIdentity`), `controller/admin_api.py`, `controller/chat_api.py` (`identity_router`), `controller/api.py`, `service/chat/agent.py`, `conversation.py`, `hub.py`, `service.py`, `prompt.py`, `prompts/system.md`
- Create: `frontend/AdminPanel/ChatIdentityEditor.svelte`, `AvatarCropper.svelte`, `avatarCrop.ts`, `frontend/Chat/AssistantAvatar.svelte`
- Modify: `frontend/AdminPanel/ChatConfigManager.svelte`, `frontend/Chat/ChatMessage.svelte`, `ChatModal.svelte`, `types.ts`
- Test: `argus/backend/tests/chat/test_identity.py`, `frontend/AdminPanel/avatarCrop.test.ts`, `ChatConfigManager.test.ts`, `frontend/Chat/ChatMessage.test.ts`

- [x] Write the tests: the size of each picture format comes from its header; a picture that is not square, too large or not an image is refused; an active identity names the assistant in the conversation and the system prompt, and its picture is served; an identity needs a known connection and a name, and goes with its connection; the crop stays on the picture and zooms around the middle; the panel shows each identity and makes one active; the editor saves a name.
- [x] Write the code.
- [x] Run the verify sequence and `sync-models` on the dev cluster.
- [x] Committed in `feature(chat-mode): add the shared chat of releases and views`, with its frontend in `feature(frontend): add the chat modal and the chat admin panel`.

## Task 14 — Start parameters: seeds, wizard rules, adjusting a card

**Files:**
- Create: `argus/backend/service/chat/sct_params.py`: the wizard's rules from `frontend/TestRun/Jenkins/SCTParameterWizard.svelte`. It holds the backends and their region parameter and values, the `provision_type` and `post_behavior_*` values, the version-source families with their formats, and the `email_recipients` default. It exposes `normalize_sct(params, overrides)`, `check_sct(params)` (with BYO through `GithubService.validate_repo`) and `sct_fields(params, job)`.
- Modify: `argus/backend/service/chat/actions.py`:
  - `_check_start` takes the seed, the shared overrides and each test's own overrides.
  - `propose_start` takes `per_test`.
  - New `adjust_start(entity, card, user, changes)`, written with an LWT on `pending`.
- Modify: `argus/backend/service/chat/tools.py`: `get_job_params`, `adjust_run_params`; `execute_tests` and `execute_plan_tests` gain `seed`, `build_number` and `per_test`, and `execute_plan_tests` gains `dry_run`.
- Modify: `argus/backend/service/chat/service.py` (`adjust`), `controller/chat_api.py` (`POST /actions/{node}/params`).
- Test: `argus/backend/tests/chat/test_run_params.py`

- [x] Write the tests:
  - A `defaults` seed differs from `last_build`, and a build number reads that build.
  - Overriding `scylla_version` blanks a stale `scylla_repo`.
  - A new backend fills its region.
  - An unsupported region, a malformed AMI, or a BYO repository that GitHub does not know is rejected with the reason.
  - Per-test overrides win over the shared ones.
  - `get_job_params` groups an SCT job's parameters and lists their allowed values.
  - `dry_run` lists tests and makes no card.
  - `adjust_run_params` rewrites the latest pending card, and is refused on a confirmed one.
  - The params route re-validates choices.
- [x] Write the code.
- [x] Run the verify sequence.

## Task 15 — Plan labels and plan edits

**Files:**
- Create: `argus/backend/service/chat/plans.py`, with `plan_labels` and `build_plan_diff`. It ports `BuildUpdateRequest`, `applyOptionsDiff`, the participants rule and the empty-plan check from `cli/internal/services/planner.go`.
- Modify: `argus/backend/service/chat/tools.py` (`get_plan_labels`, `edit_plan`), `actions.py` (executing `edit_plan` with the `last_updated` check), `prompt.py` (`_result_text`).
- Test: `argus/backend/tests/chat/test_plan_edits.py`

- [x] Write the tests:
  - Labels per entity, with disabled entities marked.
  - Adding and removing labels gives the final set, and an emptied set removes the options.
  - Assigning a test adds it.
  - The participants are the final assignees minus the owner.
  - A user is found by username or by full name.
  - An edit that empties the plan is refused.
  - Confirming applies the diff through `update_plan`.
  - A plan changed after the proposal fails the card.
- [x] Write the code.
- [x] Run the verify sequence.
- [x] Commit tasks 14–15: `feature(chat-mode): adjust run parameters and edit plans from the chat`.

## Task 16 — Skills and the system prompt

**Files:**
- Modify: `argus/backend/models/chat.py` (`ChatSkill`, with the template as static columns).
- Create: `argus/backend/service/chat/skills.py` (`SkillService`, template validation).
- Modify: `prompt.py` (`build_system_prompt` takes the template and the skills), `agent.py`, `tools.py` (`load_skill`), `prompts/system.md` (`{skills}`), `controller/admin_api.py`.
- Test: `argus/backend/tests/chat/test_skills.py`

- [x] Write the tests:
  - An `always` skill joins the prompt.
  - An `on_demand` skill is listed, and `load_skill` returns it.
  - `load_skill` is offered only when such a skill exists.
  - An unknown placeholder, a missing required one, or a stray brace is refused.
  - A template without `{skills}` gets them appended.
  - Reset restores the default.
  - The routes are admin-only.
- [x] Write the code.
- [x] Run the verify sequence.
- [x] Commit `feature(chat-mode): add skills and system prompt editing`.

## Task 17 — MCP servers

**Files:**
- Modify: `pyproject.toml` and `uv.lock` (`mcp` in the `web-backend` extra; mcp 2.x runs on `httpx2` and leaves `starlette` as it is), `argus/backend/models/chat.py` (`ChatMcpServer`).
- Create: `argus/backend/service/chat/mcp.py`, with `McpServerService`, the `McpClient` seam, `make_mcp_client` and `mcp_tools`.
- Modify: `tools.py` (the registry takes the per-answer MCP tools; a raw schema skips the Pydantic arguments model), `agent.py`, `actions.py` (`mcp_call`), `prompt.py` (one tool rule; `_result_text`), `controller/admin_api.py`.
- Test: `argus/backend/tests/chat/test_mcp.py`

- [x] Write the tests:
  - A probe stores the catalog, new tools start `off`, and a later probe keeps the modes.
  - Headers are never returned.
  - Names are sanitised and unique.
  - A `direct` tool returns text, and an error result is marked as an error.
  - A `confirm` tool makes a card, and confirming it calls the tool once.
  - A disabled server offers no tools.
  - An adapter test runs against an in-process FastMCP server over the SDK's memory transport.
- [x] Write the code.
- [x] Run the verify sequence.
- [x] Commit `feature(chat-mode): connect MCP servers to the chat`.

## Task 18 — Auto mode

**Files:**
- Modify: `argus/backend/models/chat.py` (`ChatHistory.auto`), `service.py` (`send` and `regenerate` take `auto`), `agent.py` (claim and execute a pending card inside an auto answer, then return the outcome as the tool result), `actions.py` (`claim` records `auto`), `prompt.py` (the auto tool rule), `controller/chat_api.py`.
- Test: `argus/backend/tests/chat/test_auto_mode.py`

- [x] Write the tests:
  - An auto question's card is confirmed as the asker and executed once, and the model sees the outcome.
  - A question without auto leaves its card pending.
  - A manual confirm of an auto card is refused.
- [x] Write the code.
- [x] Run the verify sequence.
- [x] Commit `feature(chat-mode): confirm cards automatically in auto mode`.

## Task 19 — Frontend: cards and Auto mode

**Files:**
- Modify: `frontend/Chat/ChatActionCard.svelte`:
  - The start card's "Edit parameters" mode, with the fields grouped as the wizard groups them and selects for the allowed values.
  - The `edit_plan` and `mcp_call` cards.
  - The "Confirmed automatically" label.
- Modify: `ChatComposer.svelte` (the Auto mode checkbox, kept in `sessionStorage`), `ChatModal.svelte`, `types.ts`.
- Create: `frontend/Chat/StartParamsEditor.svelte`.
- Test: `ChatActionCard.test.ts`, `ChatComposer.test.ts`

- [x] Write the tests:
  - Editing a parameter posts the overrides, and a rejection shows its reason.
  - The plan card lists its changes.
  - The MCP card shows the arguments and then the result.
  - The auto label shows.
  - The Auto checkbox is sent with the question.
- [x] Write the code.
- [x] Run `yarn test` and `yarn build`.
- [x] Commit `feature(frontend): edit run parameters and plans in chat cards, and auto mode`.

## Task 20 — Frontend: MCP servers, prompt and skills in the Admin Panel

**Files:**
- Modify: `frontend/AdminPanel/ChatConfigManager.svelte`, which becomes three tabs: Models, MCP servers, Prompt & skills.
- Create: `ChatMcpManager.svelte`, `ChatPromptManager.svelte`.
- Test: `ChatMcpManager.test.ts`, `ChatPromptManager.test.ts`

- [x] Write the tests:
  - Probing lists the tools, and changing a mode posts it.
  - Header values are never shown.
  - A template error from the server shows, and Reset restores the default.
  - A skill's mode is saved.
- [x] Write the code.
- [x] Run `yarn test` and `yarn build`.
- [x] Commit `feature(frontend): manage MCP servers, skills and the system prompt`.

## Task 21 — Docs and the live check

- [ ] `docs/release_chat.md` covers adjusting a start, plan edits, Auto mode, MCP servers, skills and the system prompt. `docs/api_usage.md` gets the new routes; `docs/project/architecture.md` the MCP client and the skills.
- [ ] `sync-models` on the dev cluster.
- [ ] Live check on the dev server:
  - A plan edit applied on a dev plan.
  - A start card adjusted by the model and in the card, then dismissed.
  - A local FastMCP server in the scratchpad: probe it, set the modes, run its read tool directly, and run its write tool through a card.
  - An `always` skill and an `on_demand` skill, each seen in an answer.
  - The system prompt edited, then reset.
  - Auto mode confirming the MCP write tool or the plan edit.
  - Screenshots at two widths.
- [ ] The full verify sequence.
- [ ] Commit `docs(chat-mode): describe MCP servers, skills, run parameters and plan edits`.

## Task 9 — Full verify and the live check

- [x] `uv run pre-commit run --all-files`, `uv run pytest`, `yarn test`, `yarn build`.
- [x] Run `sync-models` on the dev cluster.
- [x] On the running dev server, set up the model:
  - add the `https://ai.komachi.sh/api` connection in the Admin Panel
  - probe it
  - set Gemma-4-12B-it-GGUF as the default
  - test tool calling
- [x] Release chat on `scylla-2025.1`:
  - ask what failed on the newest rc and compare with the summary
  - try again, switch branches, undo, compact
  - add a finding through the chat and see it in the summary
  - a second session sees the answer live and shows both users in presence
  - with the event stream blocked, the modal falls back to polling
- [x] View chat: the view's memories and its release's memories reach the answer.
- [ ] A start proposal card with a rejected setting, dismissed. (Proposal and dismiss checked; no rejection, because SCT's `backend` is a free-text parameter with no choices.)
- [x] The `tools: false` path with Gemma-3-4b-it-GGUF.
- [x] Headless Chrome at 1600 and 900 pixels.
- [ ] Record the results in the pull request body.
