# Frontend Rollup Warning Remediation

## Context

Running `yarn rollup -c` completes successfully, but emits a large number of frontend warnings from
Svelte compilation, TypeScript-to-Svelte type imports, and the Sass/build pipeline.

The current objective is to reduce repo-owned warning noise without taking on intrusive build-system
changes.

---

## Problem Statement

The frontend build currently mixes three different classes of warnings:

1. Repo-owned Svelte warnings that point to concrete markup, accessibility, or reactivity issues in
   application code.
2. Type import and missing export warnings that indicate incorrect cross-file type usage.
3. Sass and build-pipeline deprecation warnings caused by the current Rollup/PostCSS/Sass stack.

The first two groups are actionable inside the existing app structure and should be cleaned up.
The Sass/build-pipeline warnings should be documented but treated as out of scope for this work,
because removing them cleanly requires a broader tooling change rather than a localized fix.

---

## Build Findings

The latest `yarn rollup -c` run produced the following notable warning groups.

### 1. Repo-owned reactivity and state usage warnings

These are the highest-signal warnings because they can point to stale UI state or updates that do
not trigger correctly under Svelte 5 rune semantics.

- `frontend/Views/Views.svelte`
  `Tab` is reported as updated without `$state(...)`, but this appears to be a false positive from
  the enum compilation pattern and should not be treated as a real remediation item.
- `frontend/TestRun/TestRun.svelte`
  `activeTab` is referenced in a way that only captures its initial value.
- `frontend/ReleasePlanner/DutyPlanner.svelte`
  `newScheduleDate` is referenced in a way that only captures its initial value.
- `frontend/ReleasePlanner/ReleasePlanCopyForm.svelte`
  `selectedRelease` is referenced in a way that only captures its initial value.
- `frontend/TestRun/DriverMatrixTestRun.svelte`
  `activeTab` warning.
- `frontend/TestRun/Sirenada/SirenadaTestRun.svelte`
  `activeTab` warning.
- `frontend/TestRun/Generic/GenericTestRun.svelte`
  `activeTab` warning.
- `frontend/TestRun/Components/Cell.svelte`
  `value` is referenced in a way that captures only the initial value.
- `frontend/TestRun/EventsTab.svelte`
  `eventContainer` is updated but not declared with `$state(...)`.
- `frontend/Views/Widgets/ViewHighlights/ViewHighlights.svelte`
  `newGroupName` and `groupCreationError` are reported as non-reactive updates, but these should be
  reviewed before introducing `$state(...)` because they may not need reactive declaration.

### 2. Repo-owned markup and accessibility warnings

Most of these are straightforward cleanup items: missing labels, icon-only buttons without labels,
and a small number of syntax or dead-code warnings.

- Missing `aria-label` or text on buttons:
    - `frontend/Alerts/AlertWidget.svelte`
    - `frontend/ReleasePlanner/ReleasePlan.svelte`
    - `frontend/WorkArea/JobConfigureModal.svelte`
    - `frontend/Common/ModalWindow.svelte`
    - `frontend/TestRun/Jenkins/JenkinsCloneModal.svelte`
    - `frontend/TestRun/Jenkins/JenkinsBuildModal.svelte`
    - `frontend/Profile/NotificationCommentWrapper.svelte`
    - `frontend/Teams/TeamDetail.svelte`
    - `frontend/Teams/TeamShort.svelte`
    - `frontend/AdminPanel/ViewWidget.svelte`
    - `frontend/AdminPanel/ViewListItem.svelte`
    - `frontend/ReleasePlanner/Schedule.svelte`
    - `frontend/WorkArea/JobConfigureModal.svelte`
- Labels not associated with controls:
    - `frontend/TestRun/ArtifactTab.svelte`
    - `frontend/TestRun/ResultsGraphs.svelte`
    - `frontend/Views/WidgetSettingTypes/CheckValue.svelte`
    - `frontend/Views/WidgetSettingTypes/StringValue.svelte`
    - `frontend/Views/WidgetSettingTypes/IntegerValue.svelte`
    - `frontend/TestRun/Jenkins/CloneTargetSelector.svelte`
    - `frontend/TestRun/Jenkins/DummyCheckParam.svelte`
- Invalid self-closing non-void HTML tags:
    - `frontend/ReleasePlanner/Schedule.svelte`
- Quoted component/custom element attributes that will stringify in future Svelte versions:
    - `frontend/Teams/TeamMember.svelte`
- Empty block:
    - `frontend/Views/Widgets/PytestWidget/PytestFlatHelper.svelte`
- Unused CSS selectors:
    - `frontend/TestRun/PackagesInfo.svelte`
    - `frontend/Discussion/Comment.svelte`
    - `frontend/Discussion/CommentEditor.svelte`
    - `frontend/TestRun/Components/Filters.svelte`
    - `frontend/Views/Widgets/ViewGraphedStats.svelte`

### 3. Incorrect type import / missing export warnings

These are correctness issues in how types are imported from `.svelte` files or adjacent modules.

- `frontend/Views/Widgets/ViewGraphedStats/StackTracePreview.svelte`
  imports `TestRun` from `./Interfaces`, but `Interfaces.ts` does not export it.
- `frontend/Views/Widgets/ViewGraphedStats/StatusBadge.svelte`
  same missing `TestRun` export.
- `frontend/Views/Widgets/PytestWidget/PytestResultRow.svelte`
  imports `PytestResult` from `ViewPytestOverview.svelte`.
- `frontend/Profile/PlannedJob.svelte`
  imports `PlannedTest` from `PlannedJobs.svelte`.
- `frontend/ReleaseDashboard/TestDashboard.test.ts`
  imports named exports from `TestDashboard.svelte` that are not exported as module exports.

### 4. Build/tooling warnings observed but not targeted here

- `rollup.config.js`
  Node warns that the file is parsed as ESM without `"type": "module"` in `package.json`.
- `frontend/argus.css`
  Sass `@import` and transitive Bootstrap Sass deprecation warnings.
- `frontend/font-awesome.css`
  Sass `@import` deprecation warning.
- `node_modules/svelte-select/Select.svelte`
  third-party self-closing `<select />` warning.
- Svelte internal circular dependency warnings emitted from `node_modules/svelte`.

---

## Out Of Scope

### Sass legacy JS API and SCSS import deprecations

The Sass deprecation warnings are real, but removing them cleanly is out of scope for this plan.

Reason:

- The repo is currently built with `rollup-plugin-postcss`, `@csstools/postcss-sass`, and
  `svelte-preprocess`.
- The latest published versions of those packages still use Sass legacy APIs such as
  `sass.render(...)` or `renderSync(...)`.
- Eliminating these warnings cleanly would require one of the following intrusive changes:
    - replacing the current Sass compilation path with a custom Rollup integration,
    - moving more of the frontend build to Vite,
    - replacing SCSS entry imports with prebuilt vendor CSS,
    - or refactoring Svelte SCSS preprocessing away from the current stack.

That work is larger than a warning cleanup pass and carries material risk to frontend asset output,
theme behavior, and dev workflow. It should be handled as a separate build-system migration.

### Third-party warnings from `node_modules`

Warnings emitted from `node_modules/svelte-select` and Svelte's internal package graph are also out
of scope for this plan. These should only be revisited if dependency upgrades or replacements are
already being evaluated.

### Interactive-element accessibility warnings

The current plan does not include broad remediation of warnings around clickable non-interactive
elements. Instead, these should be globally ignored in the Svelte warning pipeline.

Recommended ignored warning codes:

- `a11y_click_events_have_key_events`
- `a11y_no_static_element_interactions`
- `a11y_no_noninteractive_element_interactions`
- `a11y_no_noninteractive_element_to_interactive_role`
- `a11y_missing_attribute` for anchor-as-button patterns where the team intentionally uses `<a>`
  without `href`

The least invasive implementation is to add a global filter in the Svelte Rollup configuration so
these warnings do not appear in `yarn rollup -c` output. This should be treated as build-policy
configuration rather than source cleanup.

---

## Suggested Fixes

### Phase 1: Fix correctness and type warnings

These changes have the best signal-to-risk ratio and should be addressed first.

1. Move shared interfaces out of `.svelte` module scripts when another file needs to import them.
   Suggested targets:
    - move `PytestResult` and related interfaces from
      `frontend/Views/Widgets/PytestWidget/ViewPytestOverview.svelte` into a dedicated `.ts` module.
    - move `PlannedTest` and `LastRun` from `frontend/Profile/PlannedJobs.svelte` into a dedicated
      `.ts` module.
2. Add the missing `TestRun` export to
   `frontend/Views/Widgets/ViewGraphedStats/Interfaces.ts`, or update importing files to use the
   correct existing type if `RunDetails` was intended.
3. Decide whether `getAssigneesForTest` and `shouldFilterOutByUser` in
   `frontend/ReleaseDashboard/TestDashboard.svelte` should be:
    - exported from a `<script module>` block, or
    - moved into a plain `.ts` helper module that both the component and tests import.
4. Remove invalid script attributes such as `type="ts"` from
   `frontend/Views/Widgets/SummaryWidget/RunIssues.svelte`.

### Phase 2: Fix state/reactivity warnings

1. Ignore the `frontend/Views/Views.svelte` enum warning unless follow-up inspection shows actual
   reactive state misuse.
2. Convert locally captured `$state(...)` reads into:
    - closures,
    - `$derived(...)` values,
    - or recomputation inside functions/effects, depending on intent.
3. Introduce `$state(...)` only where the value is expected to participate in UI updates. Do not
   assume every warning in this bucket should be fixed by adding `$state(...)`.

Primary files:

- `frontend/TestRun/TestRun.svelte`
- `frontend/ReleasePlanner/DutyPlanner.svelte`
- `frontend/ReleasePlanner/ReleasePlanCopyForm.svelte`
- `frontend/TestRun/DriverMatrixTestRun.svelte`
- `frontend/TestRun/Sirenada/SirenadaTestRun.svelte`
- `frontend/TestRun/Generic/GenericTestRun.svelte`
- `frontend/TestRun/Components/Cell.svelte`
- `frontend/TestRun/EventsTab.svelte`
- `frontend/Views/Widgets/ViewHighlights/ViewHighlights.svelte`

### Phase 3: Fix low-risk accessibility and markup warnings

1. Add `aria-label` to icon-only buttons and spinner-only buttons.
2. Associate labels with form controls using `for`/`id` or by nesting the relevant input.
3. Replace self-closing non-void elements with explicit open/close tags.
4. Remove empty blocks and dead CSS selectors.
5. Remove quoted expressions on component/custom-element props where the value is meant to remain a
   non-string expression.

These changes are mostly mechanical and should be grouped to keep the diff reviewable.

### Phase 4: Add global ignore for interactive-element a11y warnings

Instead of remediating clickable non-interactive element warnings across the codebase, configure the
Svelte warning pipeline to suppress this warning family globally.

Suggested approach:

1. Add a warning filter in `rollup.config.js` for the agreed interactive-element warning codes.
2. Keep the filter narrowly scoped to the chosen a11y warnings rather than suppressing all Svelte
   accessibility warnings.
3. Re-run `yarn rollup -c` and confirm that only the targeted warning family disappears.

### Phase 5: Evaluate Rollup-to-Vite migration

This should be treated as a separate build modernization phase, not as part of the initial warning
cleanup. The goal is to replace `rollup.config.js` with `vite.config.ts` only after the warning
cleanup work is stable enough to make build parity easy to verify.

Current migration constraints:

- the Flask templates are tightly coupled to fixed asset names under `/s/dist`, such as
  `main.bundle.js`, `globalAlert.bundle.js`, `notificationCounter.bundle.js`, and `styles.css`
- the frontend currently uses many independent entry files rather than a single SPA entry
- some templates still assume classic script loading instead of module loading, such as
  `templates/flash_debug.html.j2`
- `frontend/view-user-resolver.js` still imports from `svelte/internal`, which should be cleaned up
  before or during any tooling migration

Recommended migration path:

1. Start with Vite in build mode only.
2. Preserve `public/dist` as the output directory.
3. Preserve current entry names with `[name].bundle.js` where possible.
4. Keep Flask templates unchanged during the first parity pass.
5. Validate shared CSS output expectations from `templates/base.html.j2`.
6. Only after parity is proven, evaluate whether to keep fixed names or move to a Vite manifest.
7. Update local development documentation after the new build path is stable.

Expected difficulty:

- build-parity migration: medium
- full Vite-native integration with manifest and dev-server/HMR workflow: medium-high

Important limitation:

Moving to Vite is likely to improve the build stack, but it should not be presented as a complete
warning-removal step by itself. It will not automatically remove Sass `@import` deprecations,
Bootstrap SCSS deprecations, or third-party warnings from dependencies.

---

## Validation Plan

After each phase:

1. Run `yarn rollup -c`.
2. Compare the warning set to ensure the targeted class of warnings actually dropped.
3. If the warning-filter phase is applied, confirm the filter is scoped only to the intended
   interactive-element warning codes.

---

## Recommended Scope For The First Implementation Pass

For the lowest-risk cleanup pass, start with:

1. Phase 1: correctness and type warnings.
2. Phase 2: state/reactivity warnings.
3. Phase 3: low-risk accessibility and markup warnings.

Defer Phase 4 unless the team explicitly wants the interactive-element warning family hidden in the
build output.
Treat Phase 5 as a separate follow-up effort once the warning cleanup phases have settled.
