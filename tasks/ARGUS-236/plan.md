# ARGUS-236 — implementation plan

**Spec:** `tasks/ARGUS-236/spec.md`

## Constraints

Every task below inherits these.

- Svelte 5 runes only. Never reassign a `$derived`
  (`docs/standards/frontend/components.md`).
- Bootstrap 5 utilities first. A custom badge or button rule carries its own
  `background-color` and `color` pair (`docs/standards/frontend/css.md`).
- Sorting is display-only. Do not reorder the `events` store;
  `fetchEvents` reads its cursor from `old[0].ts` at
  `frontend/TestRun/SCT/SctEvents.svelte:232`.
- No backend change.
- Line numbers below are against `upstream/master` at the time of writing.

## Task 1 — Make `TimelineEvent.id` unique and key the timeline loop

`TimelineEvent.id` is `${type}-${severity}-${ts}`, so two events of one
severity sharing a millisecond collide. The reorder needs a keyed loop for
`bind:this={eventMap[...]}` to re-bind, and a keyed loop with a duplicate key
throws. The same collision makes `remainder` drop an event the nemesis branch
did not consume, at `:271-272`.

**Files:**
- Modify: `frontend/TestRun/SCT/SctEvents.svelte:52-61`, `:343`
- Test: `frontend/TestRun/SCT/SctEvents.test.ts`

**Internals:** the constructor gains a discriminator — `event_id` for an event,
`name` and `start_time` for a nemesis.

- [ ] Write a test asserting two `TimelineEvent`s built from distinct events
      with identical `severity` and `ts` get distinct `id`s.
- [ ] Run it and confirm the failure.
- [ ] Apply the constructor change and key the loop as `(event.id)`.
- [ ] Confirm by hand that `focusDuplicate` still scrolls and highlights on a
      run with duplicate events. `SctNemesis.svelte:77` composes its `eventMap`
      key from this id and `:174` reads it back with a substring match.
- [ ] Run the verify sequence from the `Commands` section of `CLAUDE.md`.
- [ ] Commit.

## Task 2 — Sort state, comparator and the toggle button

**Files:**
- Modify: `frontend/TestRun/SCT/SctEvents.svelte` — module script near `:64`,
  instance script `:75`, `:90`, `:252-277`, markup `:322-332`
- Test: `frontend/TestRun/SCT/SctEvents.test.ts`

**Internals:** a `SortOrder` type, a `sortOrder` state, a `byTimestamp`
comparator built once inside `createTimeline` from a `direction` factor, and a
`handleSortClick` that flips the order and returns `container` to the top.

The toggle is the first child of the severity row at `:322`, carrying `me-auto`
so it pins left while the severity buttons stay right-aligned. It reuses
`faArrowUp` and `faArrowDown`, already imported in `SctNemesis.svelte:5`, and
carries `aria-pressed` and a `title`. Plain `btn-outline-secondary`, so no new
CSS rule.

- [ ] Write the failing tests: classic mode oldest, classic mode newest, and a
      regression case pinning the default to today's output.
- [ ] Run them and confirm the failure.
- [ ] Add the state, thread `sortOrder` through `createTimeline` and the
      `$derived` at `:277`, and add the button.
- [ ] Verify the toggle in both `eventDisplayMode` values.
- [ ] Run the verify sequence.
- [ ] Commit.

## Task 3 — Sort the events nested inside a nemesis block

`innerEvents` is assigned from a filter over the flattened store at `:266-267`
and never sorted, so it reads severity-grouped. Sorting the copy — not the
filtered array, which `consumedEvents` still needs for membership — with the
same comparator fixes that and carries the order inward.

This changes the default view: nested events become chronological where they
are severity-grouped today. Intended, and stated in the pull request.

**Files:**
- Modify: `frontend/TestRun/SCT/SctEvents.svelte:262-270`
- Modify: `frontend/TestRun/SCT/SctNemesis.svelte:75`
- Test: `frontend/TestRun/SCT/SctEvents.test.ts`

- [ ] Write the failing tests: `innerEvents` ascending at the default with a
      severity-mixed fixture, and descending under newest-first.
- [ ] Run them and confirm the failure.
- [ ] Sort the copy, and key the `innerEvents` loop as `(event.id)`.
- [ ] Run the verify sequence.
- [ ] Commit.

## Task 4 — Hold the reading position across the 60-second refresh

The timer at `:283-290` replaces the store every 60 seconds while the run is
not terminal. Under newest-first the list grows above the viewport, so a reader
scrolled into it gets pushed down.

**Files:**
- Modify: `frontend/TestRun/SCT/SctEvents.svelte:70`, `:279-291`
- Test: `frontend/TestRun/SCT/SctEvents.test.ts`

**Internals:** a `refreshEvents` function extracted from the interval callback.
It records `scrollHeight` and `scrollTop`, replaces the store, and under
newest-first with a non-zero `scrollTop` offsets `scrollTop` by the height
delta after a `tick()`. At `scrollTop` 0 it leaves the reader at the head.

- [ ] Write the failing tests: anchor held mid-list under newest-first, head
      held at 0, and `scrollTop` untouched under oldest-first.
- [ ] Run them and confirm the failure.
- [ ] Extract `refreshEvents` and apply the compensation.
- [ ] Run the verify sequence.
- [ ] Commit.

## Task 5 — Make the ordering testable

`createTimeline` is a `const` in the instance script and cannot be imported.
It is pure apart from `testRun.end_time` at `:264`. Move it into the existing
`<script module>` block, export it, and take `endTime` as a parameter. Tasks 1
to 4 depend on this, so land it first or fold it into Task 1.

**Files:**
- Modify: `frontend/TestRun/SCT/SctEvents.svelte` — `<script module>`, and the
  `$derived` call at `:277`
- Create: `frontend/TestRun/SCT/SctEvents.test.ts`

Cases, beyond the per-task ones above:

- [ ] A nemesis-window event appears once, in `innerEvents`, not also in the
      remainder. Guards the Task 1 id fix.
- [ ] Nemesis mode under newest-first interleaves blocks and loose events
      correctly.
- [ ] An empty `events` store returns `[]` without throwing.
- [ ] A `@testing-library/svelte` render case: both button labels,
      `aria-pressed` flips, rendered order reverses.

## Verify

```bash
yarn test
yarn build
uv run pre-commit run --all-files
```

Then, in the browser:

- [ ] A finished run, oldest-first: the classic timeline matches today.
- [ ] The toggle flips both `Timeline` and `Nemesis Timeline`.
- [ ] Nested nemesis events are chronological at the default, reversed under
      newest-first.
- [ ] Severity filters still work in both orders.
- [ ] Duplicate highlight still scrolls to its target.
- [ ] A live run, newest-first: after a 60-second refresh new events are at the
      top and the event being read has not moved.
- [ ] A finished run starts no timer and no scroll handling runs.
- [ ] Two viewport widths: the button stays left-pinned when the severity row
      wraps (`docs/standards/frontend/responsive.md`).

## Follow-ups to file

Not part of this task. Found while writing it.

- The mobile tab select contradicts the desktop tab bar.
  `frontend/TestRun/TestRun.svelte:386` labels the legacy tab `Events` while
  `:392` labels this one `Events (Experimental)`; `:347` and `:352` say the
  opposite.
- `updateCounters` at `:222` runs once in `onMount` and never on refresh, so
  the severity counts freeze during a live run.
- `PER PARTITION LIMIT` over an ascending clustering key drops the newest
  events past the 10000-per-severity cap. Confirm with
  `DESCRIBE TABLE sct_event` first.
