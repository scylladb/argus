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
- `UserService.PREFERENCE_DEFAULTS: dict[str, bool] = {"event_summaries": False}`.
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
  - `GET /api/v1/user/preferences` returns `{"event_summaries": false}` for a new user.
  - Posting `event_summaries=on` returns 302, and the API then returns `true`.
  - Posting the form with no field turns the setting back off.
  - The setting stays on after `/profile/update/username` changes the username.
  - `GET /profile/` renders the switch `checked` when the setting is on.
- [x] Run `uv run pytest argus/backend/tests/main_api/test_profile.py` and confirm the
      failures.
- [x] Write the service methods, the routes and the template section.
- [x] Run the tests again and confirm they pass.

## Task 2 — Summary view on the event card

**Files:**
- Modify: `frontend/TestRun/SCT/SctEvents.svelte` (the `SCTEvent` interface, `onMount`, the
  `<SctEvent>` call)
- Modify: `frontend/TestRun/SCT/SctEvent.svelte` (props, the body block, styles)
- Test: `frontend/TestRun/SCT/SctEvent.test.ts`

**Internals:**
- `SCTEvent.summary?: string | null`.
- `SctEvents`: `let showSummaries = $state(false)` and a `fetchPreferences()` called at the
  start of `onMount`. It sets `showSummaries` from `response.event_summaries === true`. On a
  failure it calls `console.log` and leaves the value off. The component passes
  `{showSummaries}` to `<SctEvent>`.
- `SctEvent`: a new prop `showSummaries: boolean`, `let showOriginal = $state(false)`,
  `let hasSummary = $derived(showSummaries && !!event.summary)`, and
  `let summaryView = $derived(hasSummary && !showOriginal)`.
- Body, when `summaryView` is true: a header row with a `badge ai-summary-badge` reading
  "AI summary" and a `btn btn-sm btn-light` "Show original", then
  `<pre class="font-monospace p-2 rounded m-1 bg-light-two">{event.summary}</pre>`.
- Body, otherwise: today's `<pre>`, unchanged. When `hasSummary` is true, add a
  `btn btn-sm btn-light` "Show summary" before it.
- `.ai-summary-badge` sets a `background-color` and `color` pair, with a dark-theme override
  under `:global([data-bs-theme="dark"])`.
- The copy button, `parsedMessage` and `shouldFilter` keep reading `event.message`.

- [x] Write the failing tests, rendering `SctEvent` with a minimal event, run and props.
      Mock `../../Stores/AlertStore` and stub `SctSimilarEvents` if it fetches on mount.
  - With `showSummaries` false and a summary present, the card shows the message, with no
    badge and no summary button.
  - With `showSummaries` true, the card shows the summary and the "AI summary" badge, and
    the message text is absent. "Show original" shows the message, and "Show summary"
    switches back.
  - With `showSummaries` true and `summary: null`, the card shows the message with no badge
    and no button.
  - In summary view, the copy button calls `navigator.clipboard.writeText` with
    `event.message`.
- [x] Run `yarn test frontend/TestRun/SCT` and confirm the failures.
- [x] Write the `SctEvents` and `SctEvent` changes.
- [x] Run the tests again and confirm they pass.

## Task 3 — Verify

- [x] Run `uv run pre-commit run --all-files`, `uv run pytest`, `yarn test` and `yarn build`.
- [x] Live check on the running dev server (find it with `ss`):
  - [x] The profile switch persists after a reload.
  - [x] A run with summarized ERROR events shows the summary view with the setting on, and the
    page as before with it off.
  - [x] Check the light and dark themes.
  - [ ] Check the copy button. Headless Chrome has no clipboard; the Vitest test covers it.
- [x] Leave the code uncommitted for review. The commit carries the checked boxes.
