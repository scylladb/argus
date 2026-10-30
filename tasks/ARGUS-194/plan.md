# ARGUS-194 — implementation plan

**Spec:** `tasks/ARGUS-194/spec.md`

A decision during the build that changes what the spec states updates the
spec in the same commit. A line in its `Decisions` section records the
decision when the Design section does not state the reason. This paragraph
stays in every plan built from a spec.

## Rules

- The change stays in `cli/`. Run `make fmt`, `make lint` and
  `go test -race ./...` in `cli/` before the commit.
- Follow the `NemesisResponse` pattern in `cli/internal/models/runs.go`: the
  output mode is a field with the tag `json:"-"` on the response value.
- The cache and `deduplicateEvents` stay as they are. They keep the full
  `SCTEvent`.

## Task 1 — Show the summary or the message, and add `--raw`

**Files:**
- Modify: `cli/internal/models/runs.go` (`SCTEventsResponse`, its `Headers`,
  `Rows` and `MarshalJSON`)
- Modify: `cli/cmd/run_nemeses_events.go` (the `RunE` of `runEventsCmd`, its
  `Long` help text, and its flags in `init`)
- Test: `cli/internal/models/runs_test.go`
- Test: `cli/cmd/run_nemeses_events_test.go`

**Internals:**
- `SCTEventsResponse.Raw bool` with the tag `json:"-"`.
- `func (e SCTEvent) DisplayText(raw bool) string`: returns `e.Message` when
  `raw` is true or `e.Summary` is empty, else `e.Summary`.
- `sctEventOutput`, an unexported type that embeds `SCTEvent` and adds
  `Message *string` and `Summary *string`, both with `omitempty`. The outer
  fields shadow the embedded ones in `encoding/json`. `MarshalJSON` sets
  exactly one of the two pointers for each event, so an event with an empty
  message still has the `message` key. The tags of `SCTEvent` stay the same,
  so the cache format stays the same.
- `Headers` returns one text column, `Message`. `Rows` fills it with
  `truncateEventText(e.DisplayText(r.Raw))`.
- `runEventsCmd` gets the flag `--raw` (bool, default `false`, help text
  "Show the original message of each event instead of its summary"). `RunE`
  reads it and sets `Raw` on the response. The `Long` text gets one
  paragraph: the output shows the summary of an event when it has one, and
  `--raw` shows the original message.

**Tests** (replace `TestSCTEventsResponseJSONSummary` and
`TestSCTEventsResponseRowsSummary`, which assert the old two-column shape):
- JSON, default: an event with a summary has `summary` and no `message`. An
  event with a null summary has `message` and no `summary`. An event with an
  empty summary and an empty message has the `message` key.
- JSON, `Raw`: every event has `message` and no `summary`.
- Rows, default and `Raw`: seven columns, the last one holds the selected
  text. A text longer than 200 bytes ends with `...`.
- `deduplicateEvents` followed by the default JSON: an orphan duplicate with
  no summary is promoted, and the output shows its message.

- [x] Write the failing tests.
- [x] Run them and confirm the failure.
- [x] Write the smallest change that passes them.
- [x] Run `make fmt`, `make lint` and `go test -race ./...` in `cli/`, and
      `uv run pre-commit run --all-files` at the root.
- [x] Commit, with the boxes of this task checked.
