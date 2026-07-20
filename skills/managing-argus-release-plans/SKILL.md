---
name: managing-argus-release-plans
description: Use when creating or updating an Argus release test plan (argus planner create/update), building a plan from a Confluence test-plan/strategy page, mapping Confluence-named tests/categories to real Argus tests via argus search, or setting up label-based test triggering (argus test execute --plan-id --label) for a release. Also covers reading an existing plan as a template (argus planner get) and the confirmation checklist before writing anything.
---

# Managing Argus Release Plans

## Overview

Argus release plans (`argus planner`) group a release's tests/groups with an
owner, per-entity assignees, and optional **labels** — free-form tags on a
test/group used later to trigger a batch of builds by label
(`argus test execute --plan-id ... --label ...`). Full flag reference lives in
`argus planner <cmd> --help` and `argus test execute --help` — read those
before guessing at a flag; they are long and authoritative, this skill covers
the workflow and judgment calls around them.

**Every `argus` call needs `--non-interactive`.** Without it, an expired
cached credential silently opens an interactive re-auth prompt and the command
hangs with no output until it times out.

## When to Use

- Creating a new release plan (`argus planner create`) for a release cycle
- Updating an existing plan's membership, assignees, or labels (`argus planner update`)
- Building a plan's test/group membership from a Confluence test-plan/strategy doc
- Mapping Confluence-named tests or categories to real Argus tests/groups via `argus search`/`argus planner overview`
- Setting up or validating label-based test triggering (`argus test execute --plan-id --label`)
- Comparing a new release's plan against a prior release's plan for scope parity

## When NOT to Use

- Deleting a release plan — this skill deliberately excludes plan deletion guidance; only use `planner delete` ad hoc on plans you created yourself for testing, never as a documented workflow
- Triggering a real (non-dry-run) Jenkins build outside of an already-reviewed, intentional test run
- General Jenkins/Argus test-result questions unrelated to plan/label management (see other Argus docs)
- Confluence operations unrelated to fetching a test-plan doc's content (e.g. writing/editing pages)

## Mandatory clarification checklist

The user/release owner decides these — do not guess or silently reuse a prior
release's values. Ask before writing anything:

1. **Release name** — confirm the exact `scylla-X.Y` name; don't assume it
   mirrors a prior release's naming.
2. **Owner username** — the plan owner is a new person each release. There is
   no lookup-by-name/email mechanism; if a doc names someone ("Jane Doe"), ask
   the user for that person's **Argus username**, then verify it resolves
   (see Verifying a username below) before using it anywhere.
3. **Per-entity assignees** — same rule: ask for real Argus usernames per
   category/test, or explicitly confirm "leave everything unassigned
   (`$owner`) for now, assign later via `planner update --assign`."
4. **Label scheme** — labels are an interactive design decision *for the
   release owner*, not a taxonomy to invent from a spec doc. Don't propose a
   label set unless asked; ask whether to add labels now or leave the plan
   unlabeled for the owner to design later.
5. **Ambiguous/missing test mappings** — see "Reporting problems" below;
   surface these, don't silently pick or silently drop.

## Verifying a username

There's no lookup-by-name/email mechanism and no separate "does this user
exist" check — names resolve to UUIDs server-side as part of the real
`create`/`update` call. Unknown *tests* are reported and skipped (the plan is
still created); unknown *users* may behave differently and haven't been
verified either way. If you're not confident a username is correct, confirm
it with the user rather than guessing or running a throwaway call to find
out.

## Building a plan from a Confluence source doc

1. **Get the numeric page ID.** `acli confluence page view` takes only a
   numeric `--id`, never a URL. A `/wiki/x/<code>` tinylink must be resolved —
   ask the user to open it and paste the resolved URL (shows
   `/pages/<id>/...`) or the numeric ID; that's the reliable path. A decode
   fallback exists but is fiddly — see
   [references/confluence-page-id.md](references/confluence-page-id.md) only
   if the user can't get you the ID directly.
2. **Confluence is auth-walled — `acli` is mandatory, not optional.** A
   generic web-fetch tool cannot read it (it either refuses authenticated
   URLs outright or gets bounced to a login page with no page content) and
   `curl`/browser automation won't have `acli`'s OAuth session. If a page
   fetch didn't go through `acli confluence page view`, it didn't actually
   read the page — don't trust or act on that output. Auth itself is a
   user-run browser step: if `acli confluence auth status` reports
   unauthorized, tell the user to run `acli confluence auth login --web`
   themselves (or provide an API token) — don't attempt it yourself, it's an
   interactive OAuth flow.
3. **Fetch with `--body-format view`, never `storage`.** Both are JSON with a
   `.body.<format>.value` string to run through `html2text` (or equivalent)
   for a readable outline — but `storage` represents an `@mention` as a bare
   `<ac:link><ri:user ri:account-id="..."/></ac:link>` with **no display-name
   text**, so it silently vanishes when converted to text. `view` is
   server-rendered HTML where the same mention is a real anchor with the
   person's name as its link text (e.g. `<a ...>Petr Hala</a>`), so it
   survives `html2text` inline exactly where it appears — e.g. a line like
   `Tier1 longevities (vnodes) - Petr_Hala` or a bullet ending in a name. Test
   plan docs commonly tag a category or individual test with its owner this
   way; missing `--body-format view` means missing every one of those
   assignments, not just formatting noise.
   ```bash
   acli confluence page view --id <id> --json --body-format view \
     | jq -r '.body.view.value' > page.html
   html2text page.html > page.txt
   ```
4. **Mentions found this way are display names, not Argus usernames** — the
   same "ask, don't guess" rule from the clarification checklist applies:
   collect the names next to each category/test, then ask the user for each
   person's Argus username before writing any assignment. Don't assume a
   display name maps 1:1 to a username by pattern-matching.
5. **Treat category names as pointers to Argus groups, not literal test
   lists** — a doc line like "Tier1 longevities (tablets) -" means "the whole
   Tier1 group", even with no tests spelled out. Only *specific* test names in
   the doc (e.g. a bulleted list under "Tier2 Longevities") are literal test
   references to verify individually.
6. **Resolve categories/tests against the current release, not the doc.**
   Tests get renamed/added/dropped between releases — the doc is a snapshot of
   intent, `argus planner overview --release X --non-interactive` (dumps every
   `"Group/test": "build_system_id"` for the release) and
   `argus search "type:group release:X <keyword>" --non-interactive` (fuzzy
   group/test discovery, prints `build_system_id`) are ground truth. Use
   `overview` for exact-name lookups (fast, one call) and `search` when the
   doc's spelling doesn't match anything (renamed group/test, or picking the
   right group among several same-named duplicates — `search`'s `group:`/
   `release:` facets and the returned `build_system_id` path disambiguate).
7. **If a prior release's plan exists, use it as a structural cross-check —
   including per-group *test counts*, not just group names.** Diff the prior
   plan's group set against the current release's `overview` output; groups
   present in both by exact name carry over, groups in the old plan but
   missing from the new overview (or vice versa) go in the problems table
   below. Critically: **count how many tests the prior plan assigned per
   group, and compare that to how many the group has enabled now.** A prior
   plan is very often a curated subset (e.g. 18 of a group's tests), not every
   enabled test in that group — whole-group fan-out (below) silently produces
   a *superset* of the prior plan's scope in that case. That gap (e.g. "prior
   plan had 18 in this group, group now has 77 enabled, fan-out picks up all
   77") is exactly the kind of thing to report and let the user decide, not
   something to resolve by assuming "similar to last time" means "every
   enabled test."
8. **Whole-group membership**: `--assign "<Group Name>=$owner"` (or a bare
   group key in a template file) fans out to every *enabled* test in that
   group at create/update time. This is convenient but is a materially
   different scope decision than replicating a prior plan's exact per-test
   membership — confirm which one the user actually wants (see point 7).

## Reporting problems

Never silently guess a mapping or drop something. When a Confluence-named
test/category doesn't resolve cleanly — missing, renamed, ambiguous between
duplicate group names, or a category that's new/removed relative to a prior
release's plan — stop and show the user a table before writing the plan:

| Item | Issue | Options |
|---|---|---|
| `<name from doc>` | not found / renamed / ambiguous (N matches) / new vs prior release | what you'd do by default vs alternatives |

Let the user decide each row; don't proceed past this table on assumptions.

## Creating / updating

- `argus planner get --plan-id <key>` emits the editable template schema
  (`{name, release, owner, target_version, assignments}`) — the same shape
  `create --file` reads. Good baseline to edit for a near-duplicate plan.
- `argus planner create --file plan.json --non-interactive` for a fresh plan;
  flags overlay onto the file (flags win on scalars, `--assign`/`--label`
  augment). Never send raw UUIDs — everything is by name/build_system_id.
- `argus planner update --plan-id <key> --file diff.json ...` sends a diff,
  not a full replacement — only changed fields go over the wire. `--label`/
  `--unlabel entity=label` add/remove one label; membership follows
  labels/assignment (labeling a test not yet in the plan adds it).
- Don't re-run `create`/`update` "just to check" something (e.g. to see
  warning output) — it's a real write and creates a duplicate plan or
  duplicate side effect every time. Use `-vv` on the same call you already
  need, or `get`/`list` afterward, never a throwaway repeat of a mutating call.

## Triggering tests by label

`argus test execute --plan-id <key> --label <label> [--label <label2>
--match-all] --dry-run --non-interactive` resolves every plan test carrying
any (or, with `--match-all`, every) given label and prints what would run —
**always dry-run first** to confirm the label selects the intended tests
before dropping `--dry-run` to actually trigger Jenkins builds. `--wait`
blocks until builds start and reports URLs.

## Common mistakes

| Mistake | Fix |
|---|---|
| Running `argus ...` without `--non-interactive` | Hangs ~2min on a silent re-auth prompt with no output |
| Fetching a Confluence page with anything but `acli` | It's auth-walled; a generic web-fetch tool returns a login page or refuses outright — not the page content |
| Fetching Confluence with `--body-format storage` | `@mention`s carry no display-name text in that format and vanish on conversion; use `--body-format view` |
| Passing a `/wiki/x/<code>` tinylink as `--id` | `acli` needs a numeric ID; resolve the redirect or ask the user |
| Inventing a label taxonomy from a spec doc | Ask the release owner — labels are their interactive call |
| Assuming a Confluence test name is exact | Verify against `planner overview`/`search` for the *current* release; names drift |
| Re-running `create`/`update` to inspect output | Creates a real duplicate; capture output from the one call you need |
| Treating a duplicate group name as unambiguous | Same `name` can appear under `releng-testing/`, `oss/`, or root prefixes — disambiguate by `build_system_id` path depth/prefix, or cross-check against a prior release's plan |
