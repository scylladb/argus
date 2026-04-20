# Mini-Plan Template

Mini-plans are lightweight alternatives to full 7-section plans. Use them for small, single-PR changes under ~1K LOC.

## Key Differences from Full Plans

| Aspect                 | Full Plan                                                          | Mini-Plan                                  |
| ---------------------- | ------------------------------------------------------------------ | ------------------------------------------ |
| Sections               | 7 (Problem, Current State, Goals, Phases, Testing, Success, Risks) | 4 (Problem, Approach, Files, Verification) |
| YAML frontmatter       | Required                                                           | None                                       |
| MASTER.md registration | Required                                                           | None                                       |
| progress.json entry    | Required                                                           | None                                       |
| Location               | `docs/plans/`                                                      | `docs/plans/mini-plans/`                   |
| Filename               | `kebab-case-name.md`                                               | `YYYY-MM-DD-kebab-case-name.md`            |
| Lifecycle              | Tracked until archived                                             | Disposable after PR merge or 30 days       |

## Template

```markdown
# Mini-Plan: <Title>

**Date:** YYYY-MM-DD
**Estimated LOC:** <number>
**Related PR:** #<number> (if applicable)

## Problem

<1-3 sentences: what needs to change and why>

## Approach

<Bulleted list of steps, in order>

## Files to Modify

- `path/to/file.py` -- <what changes>

## Verification

- [ ] <How to verify the change works>
- [ ] `uv run ruff check` passes
```

## Example

```markdown
# Mini-Plan: Add Pagination to Release API

**Date:** 2026-04-20
**Estimated LOC:** 80
**Related PR:** #256

## Problem

The GET /api/v1/releases endpoint returns all releases in a single response,
causing slow load times when there are 500+ releases in the system.

## Approach

- Add `page` and `per_page` query parameters to the releases endpoint
- Add pagination metadata to response (`total`, `page`, `per_page`, `pages`)
- Update frontend ReleaseList component to use paginated requests

## Files to Modify

- `argus/backend/controller/api.py` -- Add pagination params to releases route
- `argus/backend/service/releases_service.py` -- Add paginated query method
- `frontend/WorkArea/ReleaseList.svelte` -- Add pagination controls

## Verification

- [ ] `uv run pytest argus/backend/tests/ -v` passes
- [ ] API returns paginated results with correct metadata
- [ ] `uv run ruff check` passes
```

## Rules

1. **File paths must be code-verified** — use file-reading tools to confirm paths exist before listing them.
2. **Verification must be concrete** — every checkbox should be something a person can actually check or run.
3. **No YAML frontmatter** — mini-plans are intentionally lightweight.
4. **No MASTER.md or progress.json** — mini-plans are not tracked in the plan registry.
