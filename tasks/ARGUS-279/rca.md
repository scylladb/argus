# ARGUS-279 — Screenshots tab hides the part of the screenshot we read

**Date**: 2026-11-12

## Root cause

PR #1141 changed how the thumbnail is cropped and made the viewer open a
screenshot fitted to the window.

1. **Crop.** Before `fb2ac5ed`, the thumbnail was a `background-image` with
   `background-size: cover`. A background takes `background-position: 0% 0%`
   by default, so `cover` kept the top-left corner. After it, the thumbnail is
   an `<img class="object-fit-cover">` in
   `frontend/TestRun/Screenshots.svelte:27`. An image takes
   `object-position: 50% 50%` by default, so `cover` keeps the centre and cuts
   the top, which holds the CPU and requests panels.
2. **Fitted viewer.** `frontend/TestRun/Components/ScreenshotModal.svelte`
   starts every screenshot at `view = FIT` (line 24, and `show()` at line 36
   resets to it). The image has `max-width: 100%; max-height: 100%`, so `FIT`
   shrinks a large monitor screenshot to the window. Actual pixels are only on
   the `1` key and the button, through `actual()`, which zooms around the
   centre of the stage (`{ x: 0, y: 0 }`), so it also opens on the middle of
   the screenshot.

## Approaches

1. **Selected: restore the old defaults inside the new components.** Set
   `object-position: top left` on the thumbnail image, call `actual()` on the image
   `load` event, and make `actual()` zoom around the top-left corner of the
   fitted image so the top of the screenshot is in view. It is two lines and
   keeps the responsive grid, zoom, pan, keys and swipe from #1141. Risk: a
   large screenshot opens zoomed, and a touch swipe used to fire only at
   `scale === 1`, so it panned instead of moving to the next screenshot. The
   swipe now also moves when it starts with the image already at its pan
   limit in the swipe direction, which is where a screenshot opens for the
   previous one and where a pan to the right edge leaves it for the next.
2. **Revert #1141.** It brings back the old layout exactly, but also the
   384px tiles that overflow a narrow window and the viewer without zoom,
   keys or error handling, which ARGUS-260 fixed. Rejected.
3. **Add a setting for the default view.** It lets each user choose, but it
   adds a setting and storage for one preference nobody has asked to vary.
   Rejected.

## Regression test

- `frontend/TestRun/Screenshots.test.ts`, case `renders a numbered button per
  screenshot with the proxied image`: asserts `object-position: top left` on
  every thumbnail. It fails before the fix.
- `frontend/TestRun/Components/ScreenshotModal.test.ts`, case `opens a loaded
  screenshot at actual pixels from its top-left corner`: fires `load` and
  asserts `scale(1.92)` and `translate(460px, 140px)`, which puts the top-left
  corner of a 1920px image at the top-left of a 1000×800 stage. It fails
  before the fix.

## Risks

| Risk | Response |
|---|---|
| A touch swipe pans a zoomed screenshot instead of moving to the next one | A swipe that starts at the pan limit in its direction moves to the neighbour, so a second swipe after the pan reaches the edge steps on. The arrow buttons and keys still move, and `0` or the fit button returns to fit, where every swipe steps. |
| A screenshot smaller than the window would be scaled up | `actual()` divides the natural width by the laid-out width, which equals the natural width when the image fits, so the scale is 1. |
| `load` fires again on each new screenshot | That is intended: every screenshot opens at actual size from the top. |
