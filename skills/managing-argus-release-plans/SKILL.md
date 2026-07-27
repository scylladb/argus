---
name: managing-argus-release-plans
description: Use when creating or updating an Argus release test plan (argus planner create/update), building a plan from a Confluence test-plan/strategy page, mapping Confluence-named tests/categories to real Argus tests via argus search, resolving people named in a doc to Argus usernames via argus users search/get, or setting up label-based test triggering (argus test execute --plan-id --label) for a release. Also covers reading an existing plan as a template (argus planner get) and the confirmation checklist before writing anything.
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
- Resolving people named in a doc (display names, `@mention`s, emails) to Argus usernames via `argus users search`/`get`
- Setting up or validating label-based test triggering (`argus test execute --plan-id --label`)
- Comparing a new release's plan against a prior release's plan for scope parity
- Publishing a finished plan to Confluence as a companion page next to its source doc

## When NOT to Use

- Deleting a release plan — this skill deliberately excludes plan deletion guidance; only use `planner delete` ad hoc on plans you created yourself for testing, never as a documented workflow
- Triggering a real (non-dry-run) Jenkins build outside of an already-reviewed, intentional test run
- General Jenkins/Argus test-result questions unrelated to plan/label management (see other Argus docs)
- Confluence operations beyond reading a source doc and drafting companion-page content — there's no `acli` write path, so actually creating/editing pages is the user's action, not this skill's

## Mandatory clarification checklist

These are decisions, not lookups — do not guess or silently reuse a prior
release's values. Settle them before writing anything. Note what is *not* on
this list: anything the source doc or a CLI lookup can answer (assignees,
test membership) you resolve yourself and only escalate on failure.

1. **Release name** — confirm the exact `scylla-X.Y` name; don't assume it
   mirrors a prior release's naming.
2. **Plan owner** — a different person each release and *not* derivable from
   the source doc, so it stays a question. But you only need who, not their
   Argus username: take a display name or email and resolve it yourself (see
   "Resolving people to Argus usernames" below).
3. **Per-entity assignees** — do **not** ask for these. The source doc names
   them next to each category/test; resolve those names yourself. A test with
   no name of its own **inherits its parent category's assignee**; `$owner`
   applies only when neither the test nor its category names anyone. Only
   names that fail to resolve go back to the user, via the problems table.
4. **Label scheme** — labels are an interactive design decision *for the
   release owner*, not a taxonomy to invent from a spec doc. Don't propose a
   label set unless asked; ask whether to add labels now or leave the plan
   unlabeled for the owner to design later.
5. **Ambiguous/missing test mappings** — see "Reporting problems" below;
   surface these, don't silently pick or silently drop.

## Resolving people to Argus usernames

`argus users` turns a display name or email into an Argus username, so you
never hand a list of names back to the user asking them to map it:

- `argus users search "<term>" --non-interactive` — case- **and
  diacritic-insensitive** substring match across username, full name and
  email. `michal` matches `Michał Kowalski`, which in turn matches
  `michalkowalski`. Prints a JSON array (`--text` for a table).
- `argus users get --username X | --email X | --uuid X --non-interactive` —
  exact single-user lookup, errors on 0 or >1 matches. Read-only, so unlike
  `planner create/update` it's safe to run just to confirm a username.
- `argus users list --non-interactive` — everyone; rarely what you want.

`users` is a recent subcommand. If `argus users --help` reports an unknown
command, the installed CLI predates it — tell the user to update, and fall
back to asking for usernames for that session rather than guessing.

**Resolution algorithm**, per name collected from the doc:

| `search "<Full Name>"` returns | Do |
|---|---|
| exactly 1 | use its `username` |
| 0 | retry `search "<Surname>"`, then `search "<Firstname>"` |
| >1 | prefer an exact `full_name` match; else the one whose email local-part matches the name; else ask |
| still 0, or still ambiguous | problems table — never guess |

Always check the **result count**, not just the first row. Traps observed on
a live release page:

- `search "Yelena Sokolova"` → **0 hits**. Argus stores that `full_name` as
  just `"Elena"` — a different transliteration, and a first name only;
  `search "Sokolova"` then finds `elenasokolova` via the email. A zero-hit
  full-name search is *not* proof the person has no account — doc spelling
  and Argus `full_name` routinely disagree.
- `search "michal"` → **3 hits**, including the bot `atlas`
  (`michal.kowalski+atlas@scylladb.com`). Bot/service accounts share a
  human's email prefix and pollute name searches; never take the first row
  blind.
- `search "Marek Zielinski"` → 0, and `search "Zielinski"` → 0 as well. That
  one genuinely has no Argus account: problems table.

The users list is disk-cached. Before declaring someone unresolved, retry the
search once with `--no-cache` — a recently onboarded person may be missing
from the cached copy.

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
   person's name as its link text (e.g. `<a ...>Adam Novak</a>`), so it
   survives `html2text` inline exactly where it appears — e.g. a line like
   `Tier1 longevities (vnodes) - Adam_Novak` or a bullet ending in a name. Test
   plan docs commonly tag a category or individual test with its owner this
   way; missing `--body-format view` means missing every one of those
   assignments, not just formatting noise.
   ```bash
   acli confluence page view --id <id> --json --body-format view \
     | jq -r '.body.view.value' > page.html
   html2text -utf8 page.html > page.txt
   ```
   **`-utf8` is not optional.** Without it `html2text` re-decodes the UTF-8
   body as latin-1 and mangles exactly the names that matter:
   `Michał Kowalski` becomes `MichaÅ Kowalski`, which diacritic-folds to
   `michaa` and matches nothing — a silent zero-hit on every non-ASCII name.
4. **Positions come from the text, spellings from the HTML.** The text
   outline tells you *which* test/category a name sits next to, but is a poor
   source for the name itself: `html2text` renders mention anchor text with
   spaces as underscores (`Adam_Novak`), wraps names across table-cell line
   breaks (`Tomas` / `Horak`), and sometimes glues one onto the preceding
   test name with no separator
   (`longevity-mv-synchronous-updates-12h-vnodes-testDana_Reyes`). Pull
   the canonical spellings from the HTML instead — every `@mention` is an
   anchor carrying the person's real name:
   ```bash
   python3 -c "
   import re, html
   h = open('page.html', encoding='utf-8').read()
   pat = r'<a[^>]*class=\"confluence-userlink[^\"]*\"[^>]*>([^<]*)</a>'
   for n in sorted({html.unescape(m).strip() for m in re.findall(pat, h)}):
       print(n)"
   ```
   Then match **from the clean list into the text**, not the other way round:
   for each known name build both `First_Last` and `First Last` and substring-
   search each line (after collapsing `\n\s+` to a single space to re-join
   wrapped lines). Do not try to parse the assignee *out* of a line — "it's
   the last token" and "split on ` - `" both fail on the glued form above,
   where there is no separator to split on. Anchors are also not full coverage
   on their own — some assignees are typed as plain text rather than
   `@mention`s — so sweep the text for those too. Verified on the 2026.3 page:
   every name in the plan section is line-local and underscore-joined, and all
   of them matched this way.
5. **Scope name extraction to the plan section.** Not every person on the
   page is an assignee — the Change Log author and the Signoff table are
   people, not assignments. Plan membership assignees live under "Argus Test
   Plan" ("Standard"/"Additional Regression Testing" and friends). The "New
   Features" table is a different animal: it is multi-column, and `html2text`
   interleaves the adjacent column's text *between* the halves of a wrapped
   name (`Export_to_S3 Michał using_smeared Kowalski scan`), which no amount
   of line-joining repairs. If you need names from that table, take them from
   the anchors and the HTML table structure, never from the text rendering.
6. **Resolve every collected name via `argus users search`** (see "Resolving
   people to Argus usernames" above) and build the assignment map yourself.
   Apply the inheritance rule: a bare test under an assigned category takes
   that category's assignee (e.g. under `Scale Tests Sam_Baker`, all four
   `scale-*` tests are `sambaker`); `$owner` only when nothing in the chain
   names anyone. Only unresolved or ambiguous names go to the user.
7. **Treat category names as pointers to Argus groups, not literal test
   lists** — a doc line like "Tier1 longevities (tablets) -" means "the whole
   Tier1 group", even with no tests spelled out. Only *specific* test names in
   the doc (e.g. a bulleted list under "Tier2 Longevities") are literal test
   references to verify individually.
8. **Resolve categories/tests against the current release, not the doc.**
   Tests get renamed/added/dropped between releases — the doc is a snapshot of
   intent, `argus planner overview --release X --non-interactive` (dumps every
   `"Group/test": "build_system_id"` for the release) and
   `argus search "type:group release:X <keyword>" --non-interactive` (fuzzy
   group/test discovery, prints `build_system_id`) are ground truth. Use
   `overview` for exact-name lookups (fast, one call) and `search` when the
   doc's spelling doesn't match anything (renamed group/test, or picking the
   right group among several same-named duplicates — `search`'s `group:`/
   `release:` facets and the returned `build_system_id` path disambiguate).
9. **If a prior release's plan exists, use it as a structural cross-check —
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
10. **Whole-group membership**: `--assign "<Group Name>=$owner"` (or a bare
    group key in a template file) fans out to every *enabled* test in that
    group at create/update time. This is convenient but is a materially
    different scope decision than replicating a prior plan's exact per-test
    membership — confirm which one the user actually wants (see point 9).

## Reporting problems

Never silently guess a mapping or drop something. When a Confluence-named
test/category doesn't resolve cleanly — missing, renamed, ambiguous between
duplicate group names, or a category that's new/removed relative to a prior
release's plan — **or when a person named in the doc doesn't resolve to
exactly one Argus user** — stop and show the user a table before writing the
plan:

| Item | Issue | Options |
|---|---|---|
| `<name from doc>` | not found / renamed / ambiguous (N matches) / new vs prior release | what you'd do by default vs alternatives |

A real example from the 2026.3 page, after running the resolution algorithm
over all 20 mentions (18 resolved to a single user with no user input):

| Item | Issue | Options |
|---|---|---|
| `Marek Zielinski` (New Features row) | no Argus account — 0 hits on full name, surname and first name | leave `$owner`, or give me the right username |
| `Yelena Sokolova` (Performance) | full-name search 0 hits; Argus `full_name` is `"Elena"`, surname search resolved `elenasokolova` — confirm it's the same person | use `elenasokolova` (default), or correct me |

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

## Publishing the plan to Confluence

Once a plan is created/updated to the point the release owner is happy with
it, propose mirroring it to Confluence as a companion page — don't wait to be
asked, and don't do it unprompted either; it's a proposal, not an automatic
step.

1. **Placement**: name it `<Release> Argus Test Plan` (e.g.
   "2026.3 Argus Test Plan") and place it as a sibling of the source
   test-plan/strategy page the plan was built from. If sibling placement
   isn't practical (permissions, unclear parent space), nest it under that
   same source page instead.
2. **`acli confluence page` has no write path — only `view`.** There is no
   `create`/`update`/`edit` subcommand in this CLI (checked directly:
   `acli confluence page --help` lists only `view`). Don't assume one exists
   because `space`/`blog` have `create` — `page` doesn't. So: generate the
   page content yourself (table + Labels section, below) and ask the user to
   either create the page and paste it in, or create an empty page and give
   you its ID — but say plainly that giving you the ID only lets you `view`
   it back to confirm content, not edit it; they still have to paste the
   content themselves.
3. **Content — a table**: `Group | Test | Labels | Assignee`, one row per
   test in the plan (expand any whole-group entries to their member tests so
   each row is a single test, not a group). Source it from
   `planner get --plan-id <key> --resolved` (or the template form) — Group is
   the key's prefix before `/`, Test the suffix, Labels from the entity's
   `options.labels` (empty if none), Assignee from `assignee` (`$owner` shown
   as the owner's name, or blank).
4. **Content — a Labels section**, explaining what each label means, e.g.:

   ```markdown
   # Labels
   * **triggered**: This test is triggered either by a package build or a weekly trigger.

   ### Week 1
   * Tablets tier 2
   * Vnodes tier 1 and tier 2
   * Non-triggered longevities

   ### Week 2
   * Feature tests
   * Scale tests
   * Customer test cases

   ### Week 3
   * Alternator tests

   ### Week 4
   * Gemini
   * Jepsen
   ```

   This is a *format* example, not a fixed taxonomy — the groupings (weeks,
   or whatever scheme) and which categories fall under each are whatever the
   release owner actually decided when the label scheme was designed (see
   the clarification checklist above); write down their real decision, don't
   default to this example's specific mapping for a different release.

## Common mistakes

| Mistake | Fix |
|---|---|
| Running `argus ...` without `--non-interactive` | Hangs ~2min on a silent re-auth prompt with no output |
| Fetching a Confluence page with anything but `acli` | It's auth-walled; a generic web-fetch tool returns a login page or refuses outright — not the page content |
| Fetching Confluence with `--body-format storage` | `@mention`s carry no display-name text in that format and vanish on conversion; use `--body-format view` |
| Running `html2text` without `-utf8` | Mangles non-ASCII names (`Michał`→`MichaÅ`), which then silently match zero users |
| Asking the user to hand-map display names to Argus usernames | `argus users search "<Full Name>"` resolves them; only escalate what returns 0 or >1 |
| Taking the first row of `users search` | It's a substring match — `michal` returns 3 users incl. a bot; check the count, prefer an exact `full_name` hit |
| Concluding "no such user" from one 0-hit full-name search | Argus `full_name` often differs from the doc; retry surname, then first name, then `--no-cache` |
| Giving `$owner` to a bare test listed under an assigned category | It inherits the category's assignee; `$owner` is only for when nothing in the chain names anyone |
| Parsing the assignee as "the last token" of a doc line | Mentions glue to the test name with no separator (`...-12h-test` + `Dana_Reyes`); match known names into the line instead |
| Assuming `acli confluence page` can create/edit a page | It only has `view`; generate the content and ask the user to create/paste it |
| Passing a `/wiki/x/<code>` tinylink as `--id` | `acli` needs a numeric ID; resolve the redirect or ask the user |
| Inventing a label taxonomy from a spec doc | Ask the release owner — labels are their interactive call |
| Assuming a Confluence test name is exact | Verify against `planner overview`/`search` for the *current* release; names drift |
| Re-running `create`/`update` to inspect output | Creates a real duplicate; capture output from the one call you need |
| Treating a duplicate group name as unambiguous | Same `name` can appear under `releng-testing/`, `oss/`, or root prefixes — disambiguate by `build_system_id` path depth/prefix, or cross-check against a prior release's plan |
