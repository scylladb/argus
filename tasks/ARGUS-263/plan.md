# ARGUS-263 — implementation plan

**Spec:** `tasks/ARGUS-263/spec.md`

A decision during the build that changes what the spec states updates the
spec in the same commit. A line in its `Decisions` section records the
decision when the Design section does not state the reason. This paragraph
stays in every plan built from a spec.

## Rules

- Frontend only. Svelte 5 runes in new components.
- Copy through `navigator.clipboard.writeText` and a
  `sendMessage("success", ...)` toast, as `ResourcesInfo.svelte` does.
- The popover is a Bootstrap dropdown (`data-bs-toggle="dropdown"`), as the
  run header's mobile *Actions* menu is.

## Task 1 — Build the commands

**Files:**
- Modify: `frontend/Common/RunUtils.js`
- Test: `frontend/Common/RunUtils.test.js`

**Internals:** `isMonitorResource(resource)` and
`buildMonitorCommands(testId, monitor, runFinished)`, which returns
`[{ label, command }]`: the Grafana, Prometheus and shell commands for a
running monitor of a run in progress, else the one `show-monitor` command.

- [ ] Write the failing test: a running monitor, a terminated monitor, a
  running monitor of a finished run, and the monitor rule.
- [ ] Run it and confirm the failure.
- [ ] Write the smallest change that passes it.

## Task 2 — Render the Connect popover

**Files:**
- Create: `frontend/TestRun/MonitorConnect.svelte`
- Modify: `frontend/TestRun/ResourcesInfo.svelte`
- Modify: `frontend/TestRun/TestRunInfo.svelte`
- Modify: `frontend/TestRun/TestRun.svelte`, to pass the run status to
  `ResourcesInfo`

**Internals:** `MonitorConnect` takes `testId`, `monitor`, `runFinished` and
an optional `label`, and lists each command with a copy button. The
Resources tab renders it in the name cell of each monitor row. The run header
picks the running monitor, else the first monitor, shows *Open Grafana* only
for a running monitor with a public IP, and labels the popover *Grafana via
tunnel* for a running monitor without one.

- [ ] Run `yarn test` and `yarn build`.
- [ ] Run the verify sequence from the `Commands` section of `CLAUDE.md`.
- [ ] Commit, with the boxes of both tasks checked.
