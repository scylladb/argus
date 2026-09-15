# <KEY> — <short title>

**Date**: <YYYY-MM-DD>

## Design drivers

What the design must get right. A driver is a constraint the design must
satisfy. A goal is a deliverable. One bullet each. Typical drivers: a complex
artifact, a multi-step collection of data, a bound on load or latency, a
consumer that must read the result the right way, a maintenance cost. The
Design section answers each one. The problem itself stays in `intent.md`.

## Goals

What this change delivers. One line each.

## Non-goals

What this change leaves alone. The list is not exhaustive. It shows what the
team drops on purpose. It holds an implementer to the ask, since an
implementer tends to do more than the ask.

## Design

The components that take part, and what each one does. One paragraph.

One Mermaid diagram per flow the change adds or alters. A sequence diagram
for a call chain, a flowchart for a decision. Name components, not functions.
No diagram for a single linear flow.

The decision rules the design adopts. A flowchart when a decision has more
than two branches. The failure behavior the design adopts: what happens when
a source is down, a lookup fails, or an input is partial.

## Contracts

### Inputs

Each external source the change reads: the endpoint or the CLI command, and
the fields used. `None` when the change reads nothing new.

### Outputs

Each surface another party uses: a generated file, a metric, a message, an
endpoint, a command. A generated file comes with its format and a short
excerpt. The rules a consumer follows to read a generated file sit next to
its format. `None` when the change produces nothing new.

### Module API

Each signature another module calls. The whole public API of a new module.
`None` when no other module imports it.

## Risks

| Risk | Response |
|---|---|
| | |

## Deferred work

The work planned for later that shapes the design now: a module boundary
that must hold, an API that must grow, a data source that will arrive. The
design leaves room for it and does not build it.

---

Files, internal functions, tests, and line numbers go to `plan.md`. On the
spike path the code diff carries them, and the spec keeps this shape. A spec
near 150 lines, diagrams included, reads in one sitting. Above that, consider
a split and propose it in the spec. This footer stays in every spec.
