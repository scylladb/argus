# ARGUS-212 — implementation plan

**Spec:** `tasks/ARGUS-212/spec.md`

A decision during the build that changes what the spec states updates the
spec in the same commit. A line in its `Decisions` section records the
decision when the Design section does not state the reason. This paragraph
stays in every plan built from a spec.

## Rules

- Backend only. Verify with `uv run pre-commit run --all-files`, then
  `uv run pytest argus/backend/tests/issues` while iterating and
  `uv run pytest` before the commit (Docker runs the ScyllaDB fixture). The
  change touches no frontend code, so `yarn test` has nothing new to cover. It
  still runs as part of the sequence.
- Every import sits at the top of the module. Add no comment that justifies
  the change.
- Tests mock the Jira client through the `mocked_issue_service` fixture, keep
  the database real, and create rows through the services.
- Catch `JIRAError` and `requests.RequestException` by name. No bare
  `except Exception`.
- Commits:
  - commitlint header `feature(jira): …`
  - a body of at least 30 characters
  - the last line is `Task: ARGUS-212`
  - no `Co-Authored-By` trailer
  - `git add` by explicit path only.
- Leave the code uncommitted until Komachi reviews it.

## Task 1 — Raise the counter when a run is first linked to a key

**Files:**
- Modify: `argus/backend/service/jira_service.py`
- Test: `argus/backend/tests/issues/test_issues.py`

**Internals:**
- `JiraService.SEEN_AGAIN_FIELD = "customfield_11252"` and
  `COUNTED_ISSUE_TYPE = "Bug"`, next to `LAST_RAN_KEY`.
- `async def _run_links_key(self, run_id: UUID, key: str) -> bool`: the ids of
  `get_issues_by_key(key)`, then `IssueLink.find(run_id=run_id).all()`. True
  when any link of the run points at one of those ids.
- `async def _adjust_seen_counter(self, key: str, delta: int) -> None`:
  1. Inside the `try`, `jira = await self._client()`, because building the
     client calls Jira. Return when it is `None`.
  2. `remote = await asyncio.to_thread(jira.issue, key, fields=f"{self.SEEN_AGAIN_FIELD},issuetype", expand="editmeta")`.
  3. When `remote.fields.issuetype.name != self.COUNTED_ISSUE_TYPE`,
     `LOGGER.info("%s is a %s, not a %s, Seen Again Counter skipped", ...)` and return.
  4. When `self.SEEN_AGAIN_FIELD not in remote.raw.get("editmeta", {}).get("fields", {})`,
     `LOGGER.info("%s has no Seen Again Counter, skipped", key)` and return.
  5. `current = getattr(remote.fields, self.SEEN_AGAIN_FIELD, None) or 0`,
     `value = max(0, int(current) + delta)`. Return when `value == current`.
     Jira may send the number as a float, and `3.0 == 3` holds.
  6. `await asyncio.to_thread(remote.update, fields={self.SEEN_AGAIN_FIELD: value})`.
     The library reads the issue back after the PUT. Jira emails the watchers.
  7. `except (JIRAError, RequestException)`:
     `LOGGER.warning("Seen Again Counter update failed for %s", key, exc_info=True)`.
- `submit_issue`: `first_link = not await self._run_links_key(run.id, issue.key)`
  before `link.save()`. After `invalidate_release_snapshots`, when
  `first_link`, `await self._adjust_seen_counter(issue.key, 1)`.
- Test helper: `fake_remote_jira_issue` gains `seen_again: float | None = None`
  `counter_on_screen: bool = False` and `issue_type: str = "Bug"`. It sets
  `fields.issuetype`, `fields.customfield_11252`,
  `raw = {"editmeta": {"fields": {...}}}` with the field only when it is on the
  screen, and `update = MagicMock()`. The default keeps the existing tests on
  the skip path.

- [x] Write the failing tests, each on a fresh `unique_jira_key()`:
  - [x] `test_first_jira_link_raises_seen_again_counter`: value 3 →
        `update(fields={F: 4})`.
  - [x] `test_first_jira_link_sets_seen_again_counter_from_empty`: value
        `None` → `update(fields={F: 1})`.
  - [x] `test_jira_link_skips_issue_without_seen_again_counter`: field off
        the screen → no `update`, the link exists, an INFO record names the key.
  - [x] `test_jira_link_skips_issue_that_is_not_a_bug`: a Story with the field
        on the screen → no `update`, the link exists, an INFO record names the
        key.
  - [x] `test_resubmitted_jira_link_counts_once`: the same URL twice for one
        run → one `update`.
  - [x] `test_jira_link_through_second_row_counts_once`: the same run, the
        key with and without a trailing `/` (two `JiraIssue` rows) → one
        `update`.
  - [x] `test_failed_seen_again_update_keeps_the_link`: `update` raises
        `JIRAError` → submit returns, the link exists, a WARNING record names
        the key.
  - [x] `test_jira_link_with_jira_disabled_makes_no_remote_call`: a key that
        another run already links, then the client set to `None` as a dry run
        does → the link exists and no remote call is made.
- [x] Update `test_submit_jira_issue_link_for_existing_issue`: replace
      `issue.assert_not_called()` with a check that `call(key)`, the metadata
      fetch, is not among the calls.
- [x] Update `test_submit_unknown_jira_issue_fetches_from_remote`: replace
      `assert_called_once_with(key)` with a check that the first call is
      `call(key)`.
- [x] Run them and confirm the failure.
      `test_jira_link_with_jira_disabled_makes_no_remote_call` passes before
      the change, because it checks that nothing is written.
      `test_jira_link_skips_issue_that_is_not_a_bug` came with the Bug gate
      after the real-issue check, so it never ran red.
- [x] Write the smallest change that passes them.
- [x] Run the verify sequence from the `Commands` section of `CLAUDE.md`.
- [x] Commit, with the boxes of this task checked.

## Task 2 — Lower the counter when a run's last link to a key goes

**Files:**
- Modify: `argus/backend/service/jira_service.py`
- Test: `argus/backend/tests/issues/test_issues.py`

**Internals:**
- `delete_issue`: after `link.delete()`, the orphan `issue.delete()` and
  `invalidate_release_snapshots`, when
  `not await self._run_links_key(run_id, issue.key)`,
  `await self._adjust_seen_counter(issue.key, -1)`. `issue.key` is read from
  the row loaded at the top, so the orphan delete does not affect it.

- [x] Write the failing tests:
  - [x] `test_deleting_last_jira_link_lowers_seen_again_counter`: value 4 →
        `update(fields={F: 3})`.
  - [x] `test_deleting_jira_link_at_zero_writes_nothing`: value 0 → no
        `update`.
  - [x] `test_deleting_one_of_two_rows_for_a_key_keeps_the_counter`: the run
        is linked to the key through two rows, and one link is deleted → no
        `update`.
- [x] Run them and confirm the failure. Only
      `test_deleting_last_jira_link_lowers_seen_again_counter` fails. The two
      others pass before the change, because they check that nothing is
      written.
- [x] Write the smallest change that passes them.
- [x] Run the verify sequence from the `Commands` section of `CLAUDE.md`.
- [x] Commit, with the boxes of this task checked.

## Task 3 — Document the counter

**Files:**
- Modify: `docs/project/architecture.md` (the Jira row of `External Integrations`)

- [x] Change the Jira purpose to: "Issues linked to test runs. Argus
      sets the Seen Again Counter of a bug when a run is first linked to it or
      loses its last link."
- [x] Run `uv run pre-commit run --all-files`.
- [x] Commit with the code.

## Real-issue check

Run with the production Jira token, through `JiraService._adjust_seen_counter`
called directly. The link and run-per-key logic is covered by the tests.

- [x] Read the edit screens: SCT-684 (Bug) and ARGUS-212 (Story) hold the same
      30 fields, the counter among them, both at `0.0`.
- [x] `notify=False` on SCT-684 → Jira 400, `To discard the user notification
      either admin or project admin permissions are required.` The WARNING was
      logged and the counter stayed `0`. Led to the two `(build)` decisions in
      the spec.
- [x] SCT-684 `+1` → `1.0`, confirmed with `acli`. `-1` → `0.0`, confirmed
      with `acli`.
- [x] ARGUS-212 `+1` → `ARGUS-212 is a Story, not a Bug, Seen Again Counter
      skipped`, the counter stays `0.0`.
- [ ] After the deploy, link a run to a real bug in Argus and confirm the
      counter grows by one.
