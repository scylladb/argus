# Upgrade Vite 6 → 8 + Supporting Dependencies

**Status: DONE**

## Problem

The frontend build toolchain is pinned to Vite 6 because `@sveltejs/vite-plugin-svelte` 6.x requires it as a peer dependency. Vite 8 (stable since March 2026) replaces the dual esbuild+Rollup pipeline with Rolldown, offering faster production builds and a unified bundler architecture. Staying on Vite 6 means missing these performance gains and falling behind on ecosystem support.

## Approach

Upgrade three packages together in a single PR:

| Package | Before | After |
|---------|--------|-------|
| `vite` | 6.x | ^8.0.0 |
| `@sveltejs/vite-plugin-svelte` | 6.2.4 | 7.0.0 |
| `svelte` | 5.37.3 | ^5.46.4 |

**Key findings during migration:**

1. **Rolldown compatibility layer** — `rollupOptions` is deprecated in Vite 8, renamed to `rolldownOptions`. Migrated `input` and `output` config directly. The `onwarn` handler for `SOURCEMAP_ERROR`/`INVALID_ANNOTATION` was removed — Rolldown does not emit these warnings.
2. **SCSS preprocessor** — The `api: "modern-compiler"` option no longer exists in Vite 8's types (it only supports the modern API now). Removed it; `silenceDeprecations` still works.
3. **Node.js** — Vite 8 requires Node 20.19+ or 22.12+. We run Node 22.22.0 — no issue.
4. **Svelte bump is minor** — 5.37→5.46 is a non-breaking minor version bump within Svelte 5.
5. **Yarn 1 resolution** — Added `"resolutions": { "vite": "^8.0.0" }` to fix a yarn 1 linking error with nested peer deps in vitest.

## Files

| File | Change |
|------|--------|
| `package.json` | Bump `vite`, `@sveltejs/vite-plugin-svelte`, `svelte`; add `resolutions` |
| `yarn.lock` | Regenerated |
| `vite.config.ts` | `rollupOptions` → `rolldownOptions`; remove `onwarn`; remove `api: "modern-compiler"` |

## Performance Results

| Metric | Vite 6 | Vite 8 (Rolldown) | Change |
|--------|--------|-------------------|--------|
| Build time | 12.54s | 4.17–4.84s | **~2.7x faster** |
| Dev build | — | 5.47s | — |
| Bundle count | 66 JS | 63 JS | -3 |
| Total size | 5.6M | 5.5M | ~same |
| Tests | ✓ | 210 passed (17 files) | ✓ |

Build time is now dominated by plugins (CSS 36%, Svelte compile 23%, Svelte load 21%, preprocess 10%) — the bundler itself is no longer a bottleneck.

## Verification

- [x] `yarn install` completes without peer dependency conflicts
- [x] `yarn build` produces bundles in `public/dist/` matching the expected entry names
- [x] `yarn build:dev` succeeds with sourcemaps
- [x] `yarn test` passes (210 tests, 17 files)
- [x] No deprecation warnings in build output
- [x] Bundle sizes are comparable (±20%) to pre-upgrade
- [ ] Application loads in browser — spot-check 2-3 pages (login, release dashboard, admin panel)
