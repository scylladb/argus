# Unify GitHub and Jira Issue Support

## Context

Argus tracks issues from two providers: GitHub and Jira. Both are modeled in the database
(`GithubIssue`, `JiraIssue`) and linked to test runs via a shared `IssueLink` table. A unified
`IssueService` facade dispatches CRUD operations to the correct provider based on the URL.

However, several backend code paths and most of the frontend were originally written for GitHub only,
with Jira support bolted on later. This has resulted in silent data loss (Jira issues dropped from
query results), broken rendering (Jira issues passed to GitHub-only components that access
nonexistent fields), and ~350 lines of copy-pasted code between two nearly identical Svelte
components.

---

## Problem Definition

### Backend: Jira issues silently dropped in two code paths

The SCT similar-runs feature (`plugins/sct/service.py:700-704`) and the graphed stats widget
(`service/views_widgets/graphed_stats.py:110-114`) only query the `GithubIssue` table when resolving
issue IDs from `IssueLink`. Any Jira issues linked to runs in these contexts are silently dropped —
they exist in the database but never appear in the API response.

The Jira URL parser (`service/jira_service.py:83`) uses a regex hardcoded to
`scylladb.atlassian.net`, even though the Jira server URL is already configurable via
`config["JIRA_SERVER"]` (line 38). The regex should be derived from the configured server URL
instead of being hardcoded.

### Frontend: Dead code and broken rendering in release dashboard area

`ReleaseGithubIssues.svelte` and `TestWithIssuesCard.svelte` form a GitHub-only rendering pipeline
(`ReleaseGithubIssues` → `TestWithIssuesCard` → `GithubIssue`), but they are **dead code** — not
imported or used anywhere. The actual release dashboard (`ReleaseDashboard.svelte:87`) uses the
generic `<Issues>` component which properly handles both subtypes. These dead files should be
deleted.

However, `TestPopoutSelector.svelte` (lines 164-185) **is** actively used (by
`ReleaseDashboard.svelte:123` and `ViewTestDashboard.svelte:32`) and has the same problem: it
hardcodes the GitHub icon and renders `{issue.owner}/{issue.repo}#{issue.number}` — producing
`undefined/undefined#undefined` for Jira issues.

### Frontend: Graphed stats badges assume GitHub shape

`IssuesCell.svelte` renders compact issue badges using `issue.number` as the keyed-each key (line
18), `issue.url` for the link (line 20), and `issue.state === 'open'` for coloring (line 22). For
Jira issues: `issue.number` is undefined (causing key collisions), the state check fails (Jira uses
states like "todo", "in progress", "done" — not "open"/"closed"), and `#{issue.number}` displays as
`#undefined`.

The corresponding `Interfaces.ts` (lines 15-20) defines `Issue` with only GitHub fields:
`number`, `state`, `title`, `url`.

### Frontend: ~350 lines of duplicated code

`GithubIssue.svelte` (351 lines) and `JiraIssue.svelte` (368 lines) are structurally identical
components with copy-pasted logic. The only differences are:

| Aspect      | GitHub                           | Jira                                        |
| ----------- | -------------------------------- | ------------------------------------------- |
| Icon        | `faGithub`                       | `faJira`                                    |
| Title field | `issue.title`                    | `issue.summary`                             |
| Identifier  | `issue.repo#issue.number`        | `issue.key`                                 |
| Link URL    | `issue.url`                      | `issue.permalink`                           |
| Label color | `#${label.color}` (hex from API) | `label2color(label)` (hash-based)           |
| State map   | 2 states (open, closed)          | 9 states (todo, in progress, blocked, etc.) |

Everything else is identical: `resolveRuns()`, `resolveFirstUserForAggregation()`, `deleteIssue()`,
run-list modal, delete confirmation modal, and all CSS.

### Frontend: No compact badge component

There is no reusable badge component for issues. `IssuesCell.svelte` has inline badge markup
hardcoded to GitHub fields. Other places that need compact issue display (e.g.,
`TestPopoutSelector`) also inline GitHub-specific markup.

### Frontend: Misleading "Github" names

Several files are named "Github" but handle (or should handle) both types:
`ViewGithubIssues.svelte`, `ViewTypes.js` key `githubIssues`. Shared
type definitions and helpers live in `frontend/Github/Issues.svelte`.

---

## Current State

### Backend

| Capability               | GitHub        | Jira          | Location                                                                                |
| ------------------------ | ------------- | ------------- | --------------------------------------------------------------------------------------- |
| DB model                 | `GithubIssue` | `JiraIssue`   | `models/github_issue.py`, `models/jira.py`                                              |
| Submit/link to run       | Yes           | Yes           | `service/issue_service.py` via facade                                                   |
| Delete link              | Yes           | Yes           | `service/issue_service.py` via facade                                                   |
| Fetch issues by filter   | Yes           | Yes           | `service/issue_service.py:get()` merges both                                            |
| Bulk refresh from remote | Yes           | Yes           | `cli.py:refresh_issues()` calls both                                                    |
| SCT similar-runs issues  | Yes           | **No**        | `plugins/sct/service.py:700-704` — only queries `GithubIssue`                           |
| Graphed stats widget     | Yes           | **No**        | `service/views_widgets/graphed_stats.py:110-114` — only queries `GithubIssue`           |
| Release-level stats      | Yes           | Yes           | `service/stats.py:181` queries both                                                     |
| Jira URL pattern         | N/A           | ScyllaDB only | `service/jira_service.py:83` — regex hardcoded instead of using `config["JIRA_SERVER"]` |

### Frontend

| Component / File                               | Purpose                          | Status                                                                                     |
| ---------------------------------------------- | -------------------------------- | ------------------------------------------------------------------------------------------ |
| `Github/Issues.svelte`                         | Container + shared types/helpers | Works for both (branches on subtype at lines 465-469)                                      |
| `Github/GithubIssue.svelte` (351 lines)        | Full issue card for GitHub       | Duplicated with Jira counterpart                                                           |
| `Jira/JiraIssue.svelte` (368 lines)            | Full issue card for Jira         | Duplicated with GitHub counterpart                                                         |
| `Github/IssuesCopyModal.svelte`                | Copy issues to clipboard         | Works for both (checks subtype at line 110)                                                |
| `ReleaseDashboard/ReleaseGithubIssues.svelte`  | Release issues page              | **Dead code:** not imported anywhere; delete                                               |
| `ReleaseDashboard/TestWithIssuesCard.svelte`   | Release issue cards              | **Dead code:** only consumer is `ReleaseGithubIssues`; delete                              |
| `ReleaseDashboard/TestPopoutSelector.svelte`   | Inline issue list in popout      | **Broken:** hardcoded GitHub icon + `issue.owner/issue.repo#issue.number` (lines 170, 184) |
| `TestRun/SCT/SctSimilarEvents.svelte`          | Similar runs issue list          | **Broken:** uses `issue.url`, `issue.number`, `issue.title` directly (lines 224-239)       |
| `TestRun/StructuredEvent.svelte`               | Structured event issue list      | **Broken:** uses `issue.url`, `issue.number`, `issue.title` directly (lines 262-271)       |
| `ViewGraphedStats/IssuesCell.svelte`           | Compact badge in stats table     | **Broken:** `issue.number` as key, GitHub-only state check, `#issue.number` display        |
| `ViewGraphedStats/Interfaces.ts`               | Issue type for stats             | **Broken:** only has `number/state/title/url`                                              |
| `Views/Widgets/ViewGithubIssues.svelte`        | View widget wrapper              | Works (delegates to `Issues.svelte`) but misleadingly named                                |
| `Views/Widgets/SummaryWidget/RunIssues.svelte` | Issue count badge                | Works (delegates to `IssuesCopyModal`) but has unused `GithubIssue` import                 |
| `Common/ViewTypes.js:95`                       | View type registry               | Key is `githubIssues`, friendly name "Github Scoped Issue View"                            |

---

## Plan

### Phase 1: Backend — Fix Jira gaps

#### 1a. SCT similar-runs: include Jira issues

**File:** `argus/backend/plugins/sct/service.py` (lines 698-704)

Currently only queries `GithubIssue.filter(id__in=batch_issue_ids)`. After the GitHub query, collect
any issue IDs not found in `issues_by_id`, and query `JiraIssue` for those. ~10 lines added.

#### 1b. Graphed stats widget: include Jira issues

**File:** `argus/backend/service/views_widgets/graphed_stats.py` (lines 107-114)

Same pattern: import `JiraIssue`, query for IDs not found in `GithubIssue`. Return a `subtype` field
in each issue dict so the frontend can render the correct badge. Normalize both types to include the
union of fields needed by the frontend (`number`/`key`, `state`, `title`/`summary`, `url`/`permalink`,
`subtype`).

#### 1c. Derive Jira URL regex from config

**File:** `argus/backend/service/jira_service.py` (line 83)

The Jira server is already configurable via `config["JIRA_SERVER"]` (used on line 38 for the JIRA
client). The URL validation regex on line 83 should derive from that same config value instead of
hardcoding `scylladb.atlassian.net`. Extract the hostname from `config["JIRA_SERVER"]`, escape it
for regex, and build the pattern dynamically:

```python
from urllib.parse import urlparse
server_host = re.escape(urlparse(config["JIRA_SERVER"]).hostname)
match = re.match(rf"http(s)?://{server_host}/browse/(?P<key>[A-Z]+-\d+)(/)?", issue_url)
```

Also update the error message from `"URL doesn't match ScyllaDB JIRA schema"` to a generic message.

---

### Phase 2: Frontend — Create unified components

#### 2a. Extract shared types to `frontend/Common/IssueTypes.ts`

Move the type definitions and helper functions from the `<script module>` block of
`Github/Issues.svelte` (lines 1-139) into a standalone TypeScript module:

- Types: `Issue`, `GithubSubtype`, `JiraSubtype`, `Label`, `Link`, `TestRun`, `StateFilter`,
  `GithubState`, `JiraState`, `State`, `RichAssignee`
- Helpers: `getTitle`, `getUrl`, `getKey`, `getNumber`, `getRepo`, `getAssignees`,
  `getAssigneesRich`, `label2color`
- State/icon maps from both card components: `GithubIssueColorMap`, `GithubIssueIcon`,
  `JiraIssueColorMap`, `JiraIssueIcon`

Update all imports across the codebase.

#### 2b. Create `frontend/Common/IssueCard.svelte`

A dispatch component that uses a component map to route to the correct subtype component. The map
is exported from the `<script module>` block so it can be imported separately if needed. An
`UnknownIssue` fallback renders raw JSON for unexpected subtypes.

```svelte
<script module>
import GithubIssue from "../Github/GithubIssue.svelte";
import JiraIssue from "../Jira/JiraIssue.svelte";
import UnknownIssue from "./UnknownIssue.svelte";

export const IssueComponents = {
    "jira": JiraIssue,
    "github": GithubIssue,
    "unknown": UnknownIssue,
};
</script>

<script>
let { issue, ...rest } = $props();
const Component = IssueComponents[issue.subtype] ?? IssueComponents.unknown;
</script>

<Component {issue} {...rest} />
```

The shared logic (`resolveRuns()`, `resolveFirstUserForAggregation()`, `deleteIssue()`) should be
extracted into `IssueTypes.ts` as helper functions so both card components import them instead of
duplicating them. Shared CSS should be extracted into a common stylesheet or kept in each component
(acceptable since styles may diverge).

#### 2c. Create `frontend/Common/IssueBadge.svelte`

A compact badge component for inline/table contexts. Currently no component exists for this —
`IssuesCell.svelte` uses raw markup hardcoded to GitHub fields.

```ts
interface Props {
    issue: Issue;
}
```

Displays:

- A colored `<a>` badge linking to the issue URL (via `getUrl()`)
- Shows `#number` for GitHub, `KEY` for Jira (via `getKey()`)
- State-based coloring that handles both GitHub (open/closed) and Jira (9 states)
- Tooltip with title/summary (via `getTitle()`)

---

### Phase 3: Frontend — Fix broken rendering and update consumers

#### 3a. `Github/Issues.svelte` (lines 464-469)

Replace the `{#if issue.subtype == "github"} <GithubIssue> {:else} <JiraIssue> {/if}` branching
with a single `<IssueCard {issue} ... />`.

#### 3b. `ReleaseDashboard/TestPopoutSelector.svelte` (lines 164-185) — **Fixes broken popout**

Replace the hardcoded `<Fa icon={faGithub} />` and `{issue.owner}/{issue.repo}#{issue.number}` with
`<IssueBadge {issue} />`. This replaces the entire inline issue rendering block with the compact
badge component, which handles icon, identifier, link URL, and state coloring for both subtypes.

#### 3c. `TestRun/SCT/SctSimilarEvents.svelte` (lines 216-241) — **Fixes broken similar events**

Uses `issue.url`, `issue.number`, `issue.title` directly with zero subtype checking, and
`issue.state === "open"` for button coloring (only works for GitHub's 2 states). For Jira issues:
`#{issue.number}` displays `#undefined`, `issue.title` displays `undefined`, `issue.url` is
undefined (broken link), and the attach button sends `undefined` as the URL.

Replace with `<IssueBadge>` or use polymorphic helpers (`getUrl`, `getKey`, `getTitle`). The state
coloring needs to support both GitHub (`open`/`closed`) and Jira states.

#### 3d. `TestRun/StructuredEvent.svelte` (lines 255-273) — **Fixes broken structured events**

Identical pattern to `SctSimilarEvents.svelte` — uses `issue.url`, `issue.number`, `issue.title`
directly. Same fix: replace with `<IssueBadge>` or polymorphic helpers.

#### 3e. `Views/Widgets/ViewGraphedStats/IssuesCell.svelte` — **Fixes broken badges**

Replace the inline badge markup (lines 18-26) with `{#each issues as issue (issue.id)} <IssueBadge
{issue} /> {/each}`. This fixes the undefined `issue.number` key, broken state coloring, and
`#undefined` display for Jira issues.

#### 3f. `Views/Widgets/ViewGraphedStats/Interfaces.ts` (lines 15-20)

Remove the local `Issue` interface and import the shared types from `IssueTypes.ts` instead of
redefining them. The `TestRun` interface's `issues` field should use the shared `Issue` union type
(`GithubSubtype | JiraSubtype`), and `RunDetails.issues` should do the same.

Coordinate with backend change 1b to return the `subtype` field in the graphed stats response.

#### 3g. `Views/Widgets/SummaryWidget/RunIssues.svelte` (line 4)

Remove unused `GithubIssue` import.

---

### Phase 4: Naming cleanup

#### 4a. Delete dead code

Delete `frontend/ReleaseDashboard/ReleaseGithubIssues.svelte` and
`frontend/ReleaseDashboard/TestWithIssuesCard.svelte`. Neither is imported anywhere — the release
dashboard uses the generic `<Issues>` component via `ReleaseDashboard.svelte`.

#### 4b. Rename files

| Old name                                         | New name                                   | Reason             |
| ------------------------------------------------ | ------------------------------------------ | ------------------ |
| `frontend/Views/Widgets/ViewGithubIssues.svelte` | `frontend/Views/Widgets/ViewIssues.svelte` | Handles both types |

Update all imports referencing the old name.

#### 4c. Deduplicate card component logic

Extract shared logic from `GithubIssue.svelte` and `JiraIssue.svelte` (`resolveRuns()`,
`resolveFirstUserForAggregation()`, `deleteIssue()`) into helper functions in `IssueTypes.ts`. Both
card components remain as separate files for independent styling, but import the shared logic instead
of duplicating it.

---

## Files to Create/Modify

| File                                                        | Action     | Phase  | Description                                                          |
| ----------------------------------------------------------- | ---------- | ------ | -------------------------------------------------------------------- |
| `argus/backend/plugins/sct/service.py`                      | **MODIFY** | 1a     | Import `JiraIssue`, query for missing issue IDs                      |
| `argus/backend/service/views_widgets/graphed_stats.py`      | **MODIFY** | 1b     | Import `JiraIssue`, query for missing IDs, add `subtype` to response |
| `argus/backend/service/jira_service.py`                     | **MODIFY** | 1c     | Derive URL regex from `config["JIRA_SERVER"]`                        |
| `frontend/Common/IssueTypes.ts`                             | **CREATE** | 2a     | Shared types, helpers, and state maps                                |
| `frontend/Common/IssueCard.svelte`                          | **CREATE** | 2b     | Unified full issue card                                              |
| `frontend/Common/IssueBadge.svelte`                         | **CREATE** | 2c     | Compact badge component                                              |
| `frontend/Github/Issues.svelte`                             | **MODIFY** | 2a, 3a | Remove `<script module>` types, use `<IssueCard>`                    |
| `frontend/Github/GithubIssue.svelte`                        | **MODIFY** | 4c     | Extract shared logic to `IssueTypes.ts`, import instead of duplicate |
| `frontend/Jira/JiraIssue.svelte`                            | **MODIFY** | 4c     | Extract shared logic to `IssueTypes.ts`, import instead of duplicate |
| `frontend/ReleaseDashboard/TestWithIssuesCard.svelte`       | **DELETE** | 4a     | Dead code — only consumer was `ReleaseGithubIssues`                  |
| `frontend/ReleaseDashboard/TestPopoutSelector.svelte`       | **MODIFY** | 3b     | Use helpers/badge — fixes broken popout                              |
| `frontend/TestRun/SCT/SctSimilarEvents.svelte`              | **MODIFY** | 3c     | Use helpers/badge — fixes broken similar events                      |
| `frontend/TestRun/StructuredEvent.svelte`                   | **MODIFY** | 3d     | Use helpers/badge — fixes broken structured events                   |
| `frontend/ReleaseDashboard/ReleaseGithubIssues.svelte`      | **DELETE** | 4a     | Dead code — not imported anywhere                                    |
| `frontend/Views/Widgets/ViewGraphedStats/IssuesCell.svelte` | **MODIFY** | 3e     | Use `<IssueBadge>` — fixes broken badges                             |
| `frontend/Views/Widgets/ViewGraphedStats/Interfaces.ts`     | **MODIFY** | 3f     | Remove local `Issue`, import from `IssueTypes.ts`                    |
| `frontend/Views/Widgets/SummaryWidget/RunIssues.svelte`     | **MODIFY** | 3g     | Remove unused import                                                 |
| `frontend/Views/Widgets/ViewGithubIssues.svelte`            | **RENAME** | 4b     | → `ViewIssues.svelte`                                                |

---

## Verification

1. **Backend:** `uv run pytest argus/backend/tests` — existing tests pass.
2. **Lint:** `uv run ruff check` — no new violations.
3. **Frontend build:** `yarn build` — compiles without errors.
4. **Manual verification:**
    - Submit a GitHub issue URL to a test run → issue card renders correctly.
    - Submit a Jira issue URL (any `*.atlassian.net` instance) → issue card renders correctly.
    - **Release dashboard** issues panel works correctly (uses generic `<Issues>` component).
    - **Test popout selector** shows correct icon and identifier for both types (previously: always showed GitHub icon + `undefined` fields for Jira).
    - **Graphed stats widget** shows both GitHub and Jira issues as badges with correct identifiers and state coloring (previously: Jira issues missing entirely from backend, or rendered as `#undefined` in frontend).
    - **SCT similar-runs** panel shows Jira issues alongside GitHub ones (previously: Jira issues silently dropped).
    - **SCT similar events** and **structured events** show correct identifiers and links for both types (previously: `#undefined` and broken links for Jira).
    - Deleting an issue (either type) from any context works correctly.
    - Label filtering works for both types in the main Issues view.
