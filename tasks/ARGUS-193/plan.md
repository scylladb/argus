# ARGUS-193 — implementation plan

**Spec:** `tasks/ARGUS-193/spec.md`

A decision during the build that changes what the spec states updates the
spec in the same commit. A line in its `Decisions` section records the
decision when the Design section does not state the reason. This paragraph
stays in every plan built from a spec.

## Rules

- Backend tests create and read rows through the profile routes and the API, never through
  `RuntimeStore.save()` or `RuntimeStore.get()` in the test body.
- Every import sits at the top of its module.
- The badge sets `background-color` and `color` in the same rule
  (`docs/standards/frontend/css.md`). Check it in both themes.
- The run-page bundles change, so `yarn build` runs in the verify sequence.

## Task 1 — Preferences in the user service, the profile page and the API

**Files:**
- Modify: `argus/backend/service/user.py` (`UserService`)
- Modify: `argus/backend/controller/main.py` (`profile`, new route after `update_full_name`)
- Modify: `argus/backend/controller/api.py` (new route after `user_planned_jobs`)
- Modify: `templates/profile.html.j2` (new section before "API Tokens")
- Test: `argus/backend/tests/main_api/test_profile.py`

**Internals:**
- `UserService.PREFERENCE_DEFAULTS: dict[str, bool] = {"event_summaries": True}`.
- `UserService._preference_key(user, key) -> str` returns `f"user_pref_{user.id}_{key}"`.
- `UserService.get_preferences(user) -> dict[str, bool]` reads each default key with
  `RuntimeStore.get(key=...)` and uses the default on `DocumentNotFound`.
- `UserService.set_preference(user, key, value: bool)` raises `UserServiceException` for a
  key missing from `PREFERENCE_DEFAULTS`. Otherwise it saves `RuntimeStore(key=...)` with
  `.value = value`.
- `profile()` passes `preferences` to the template.
- `POST /profile/update/preferences`, `name="main.update_preferences"`, takes
  `event_summaries: str | None = Form(None)`. It calls
  `set_preference(user, "event_summaries", event_summaries is not None)`, flashes
  "Preferences saved", and returns `_profile_redirect`.
- `GET /api/v1/user/preferences`, `name="api.user_preferences"`, uses
  `Depends(api_current_user)` and returns `APIResponse({"status": "ok", "response": prefs})`.
- Template: a form posting to `url_for('main.update_preferences')` with a
  `form-check form-switch` checkbox, `id="formEventSummaries"`, `name="event_summaries"`,
  and `checked` when `preferences.event_summaries` is true. The label is "Show AI summaries
  of SCT events in place of the full event text". A Save button submits the form.

- [x] Write the failing tests:
  - `GET /api/v1/user/preferences` returns `{"event_summaries": true}` for a new user.
  - Posting the form with no field returns 302, and the API then returns `false`.
  - Posting `event_summaries=on` turns the setting back on.
  - The setting stays off after `/profile/update/username` changes the username.
  - `GET /profile/` renders the switch `checked` when the setting is on, and unchecked when
    it is off.
- [x] Run `uv run pytest argus/backend/tests/main_api/test_profile.py` and confirm the
      failures.
- [x] Write the service methods, the routes and the template section.
- [x] Run the tests again and confirm they pass.

## Task 2 — Summary view on the event card

**Files:**
- Modify: `frontend/TestRun/SCT/SctEvents.svelte` (the `SCTEvent` interface,
  `TimelineEventType`, `TimelineEvent.id`, `onMount`, the timeline loop and its card calls)
- Modify: `frontend/TestRun/SCT/SctNemesis.svelte` (a new prop, the inner-events loop)
- Modify: `frontend/TestRun/SCT/SctEvent.svelte` (props, the body block, styles)
- Test: `frontend/TestRun/SCT/SctEvent.test.ts`
- Test: `frontend/TestRun/SCT/SctEvents.test.ts`

**Internals:**
- `SCTEvent.summary?: string | null`.
- `SctEvents`: `let showSummaries = $state(true)` and a `fetchPreferences()` started, not
  awaited, at the start of `onMount`. It sets `showSummaries` from
  `response.event_summaries !== false`. On a failure it calls `console.log` and leaves the
  value on. The component passes `{showSummaries}` to `<SctEvent>` and to `<SctNemesis>`.
- `SctNemesis`: a new prop `showSummaries: boolean`, passed to each inner `<SctEvent>`.
- Both timeline loops are keyed, `{#each timeline as event (event.id)}` and
  `{#each innerEvents as event (event.id)}`, so a card keeps its state when events are
  inserted above it. `TimelineEvent.id` becomes unique: `event-<event_id>` for an event, and
  `nemesis-<name>-<target node>-<ts>` for a nemesis.
- `TimelineEventType` becomes a const object with a type alias. Vite's TypeScript transform
  drops a module-script `enum` that the instance script still references.
- `SctEvent`: a new prop `showSummaries: boolean`,
  `let summaryChoice: boolean | null = $state(null)`,
  `let hasSummary = $derived(!!event.summary)`, and
  `let summaryView = $derived(hasSummary && (summaryChoice ?? showSummaries))`. The setting
  picks the view a card opens on, and a click on the card overrides it.
- When `hasSummary` is true, a header row above the body:
  - in summary view, a `badge ai-summary-badge` reading "AI summary" and a
    `btn btn-sm btn-light` "Show original", which sets `summaryChoice = false` and
    `fullMessage = true`, so the original opens without the 600-character cutoff;
  - otherwise, a `btn btn-sm btn-light` "Show summary", which sets `summaryChoice = true`.
- Body, in summary view:
  `<pre class="font-monospace p-2 rounded m-1 bg-light-two">{event.summary}</pre>`.
  Otherwise, today's `<pre>`, unchanged.
- `.ai-summary-badge` sets a `background-color` and `color` pair, with a dark-theme override
  under `:global([data-bs-theme="dark"])`.
- The copy button, `parsedMessage` and `shouldFilter` keep reading `event.message`.

- [x] Write the failing tests, rendering `SctEvent` with a minimal event, run and props.
      Mock `../../Stores/AlertStore` and stub `SctSimilarEvents` if it fetches on mount.
  - With `showSummaries` false and a summary present, the card shows the message with no
    badge. "Show summary" shows the summary and the badge.
  - With `showSummaries` true, the card shows the summary and the "AI summary" badge, and
    the message text is absent. "Show original" shows the message, and "Show summary"
    switches back.
  - "Show original" on an event longer than the cutoff shows the whole message.
  - With `summary: null`, the card shows the message with no badge and no button, with the
    setting on and with it off.
  - In summary view, the copy button calls `navigator.clipboard.writeText` with
    `event.message`.
  - `SctEvents.test.ts`, with `fetch` routed by URL: a saved `false` opens the cards on the
    original; a failed preferences request opens them on the summary; a card that showed
    the original keeps it after WARNING inserts an earlier event.
- [x] Run `yarn test frontend/TestRun/SCT` and confirm the failures.
- [x] Write the `SctEvents` and `SctEvent` changes.
- [x] Run the tests again and confirm they pass.

## Task 3 — Verify

- [x] Run `uv run pre-commit run --all-files`, `uv run pytest`, `yarn test` and `yarn build`.
- [x] Live check on the running dev server (find it with `ss`):
  - [x] The profile switch persists after a reload.
  - [x] A run with summarized ERROR events shows the summary view with the setting on, and
    the original with a "Show summary" button with it off. Both in the classic and the
    nemesis display mode.
  - [x] Check the light and dark themes.
  - [ ] Check the copy button. Headless Chrome has no clipboard; the Vitest test covers it.
- [x] Leave the code uncommitted for review. The commit carries the checked boxes.
