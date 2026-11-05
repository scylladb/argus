# ARGUS-263 — implementation plan

**Spec:** `tasks/ARGUS-263/spec.md`

A decision during the build that changes what the spec states updates the
spec in the same commit. A line in its `Decisions` section records the
decision when the Design section does not state the reason. This paragraph
stays in every plan built from a spec.

## Rules

- Frontend only. Svelte 5 runes in new components.
- Copy through `navigator.clipboard.writeText` and a
  `sendMessage("success", ...)` toast, as the run card does.
- The popover is a Bootstrap dropdown (`data-bs-toggle="dropdown"`), as the
  run header's mobile *Actions* menu is.

## Task 1 — Build the commands

**Files:**
- Modify: `frontend/Common/RunUtils.js`
- Test: `frontend/Common/RunUtils.test.js`

**Internals:** `isMonitorResource(resource)` and
`buildMonitorCommands(testId, runningMonitor, runFinished)`, which returns
`[{ label, commands }]`, each command with the `hydra` and the
`uv run sct.py` prefix: the Grafana and Prometheus tunnels for a running
monitor, and `show-monitor` for a finished run.

- [x] Write the failing test: a running monitor, a finished run with and
  without a running monitor, a run in progress without one, and the monitor
  rule.
- [x] Run it and confirm the failure.
- [x] Write the smallest change that passes it.

## Task 2 — Render the monitor popover

**Files:**
- Create: `frontend/TestRun/MonitorConnect.svelte`
- Modify: `frontend/TestRun/TestRunInfo.svelte`

**Internals:** `MonitorConnect` takes `testId`, `monitor`, `runFinished` and
`label`, lists each command with a copy button, and renders nothing when
there is no command. The run card renders it in the slot of *Hydra Show
Monitor*, labelled *Grafana via tunnel* for a running monitor without a
public IP, *Hydra Tunnel* for one with a public IP, and *Hydra Show Monitor*
otherwise. *Open Grafana* stays only for a public IP.

- [x] Run `yarn test` and `yarn build`.
- [x] Preview the run card in a browser.
- [x] Run the verify sequence from the `Commands` section of `CLAUDE.md`.
- [x] Commit, with the boxes of both tasks checked.
