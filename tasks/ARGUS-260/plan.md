# ARGUS-260 — implementation plan

**Spec:** `tasks/ARGUS-260/spec.md`

A decision during the build that changes what the spec states updates the
spec in the same commit. A line in its `Decisions` section records the
decision when the Design section does not state the reason. This paragraph
stays in every plan built from a spec.

## Rules

- Follow `docs/standards/frontend/` and `docs/standards/testing/`. Svelte 5
  runes, typed props, no `querySelector` in a component, Bootstrap utilities
  before a custom rule, every control a named button.
- The action reads its params once: getters and callbacks only, no `$state`
  proxy in the param literal, no `update` method.
- Vitest runs in jsdom, which lays nothing out: a test stubs `clientWidth`,
  `clientHeight`, `offsetWidth`, `offsetHeight`, `naturalWidth` and
  `getBoundingClientRect` on the elements it needs, dispatches real
  `WheelEvent` and `PointerEvent` instances, and asserts the DOM, never a
  bound value. `setPointerCapture` does not exist there, so the code calls
  it optionally.
- A test file sits next to its component. Name a test for the behavior and
  the expectation.
- No backend change, no new dependency.
- Verify sequence: section `Commands` of `CLAUDE.md`, plus `yarn build`
  for the bundles.

## Task 1 — The view maths

**Files:**
- Create: `frontend/TestRun/Components/zoomPan.ts`
- Test: `frontend/TestRun/Components/zoomPan.test.ts`

**Internals:** `View`, `Bounds`, `FIT`, `measure(stage, image)` (client
size of the surface, offset size of the image, `maxScale = max(4,
naturalWidth / offsetWidth || 1)`), `clampView(view, bounds)` (scale into
`[1, maxScale]`, each offset into the half overflow of the scaled image,
degenerate bounds returned unchanged), `zoomAt(view, factor, point,
bounds)` (clamp the scale, move the centre by the clamped ratio so the
point stays fixed, clamp the offset), `panBy(view, dx, dy, bounds)`.

- [x] Write the failing tests: a fit view stays centred when the image is
  smaller than the surface; the pan is limited to the overflow of the zoomed
  image (surface 1000×800, image 1000×562.5, scale 2: ±500 and ±162.5);
  the scale is limited to `[1, maxScale]`; the point under the pointer stays
  fixed when zooming in (`{1,0,0}` ×2 at `(300, 0)` gives `{2, -300, 0}`);
  zooming back to fit re-centres; at `maxScale` the offset does not jump;
  `panBy` stops at the edge; degenerate bounds return the view unchanged;
  `measure` reads the sizes and the max scale from the elements.
- [x] Run them and confirm the failure.
- [x] Write the smallest change that passes them.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 2 — The gesture action

**Files:**
- Modify: `frontend/TestRun/Components/zoomPan.ts`
- Test: `frontend/TestRun/Components/zoomPan.test.ts`

**Internals:** `ZoomPanParams`, `zoomPan(node, params)`. Inside: the
pointer map keyed by `pointerId` with the last position of each pointer,
the pointerdown target, the moved distance and the two-pointer flag of the
current gesture; `pointAt(event)` relative to the surface centre; the wheel
factor (`deltaY` × 16 for `deltaMode` 1, × surface height for 2;
`exp(-deltaY * k)` with `k` 0.002, 0.01 with `ctrlKey`; clamped to
`[0.5, 2]`); the listeners of the spec's gesture flowchart (`wheel`
non-passive with `preventDefault`, `pointerdown` for mouse button 0 off a
button, `pointermove` pan or pinch, with the pointers captured once the
gesture passes the tap slop so that a click and a double-click keep their
natural target, `pointerup` and `pointercancel` on the window, a backdrop
tap closing on the `click` that follows it, a touch swipe at
scale 1, `dblclick` on the image toggles fit and
`max(2, actual)`, `gesturestart` and `gesturechange` prevented, window
`resize` re-clamps); `destroy` removes every listener. Constants: tap
slop 4 px, swipe 50 px.

- [x] Write the failing tests: a wheel notch zooms around the pointer and
  prevents the default; a line-mode wheel zooms by 16 px per line;
  ctrl+wheel zooms faster than a plain notch; a left-button drag pans the
  zoomed image and a right-button press does not; two pointers moving apart
  zoom around their midpoint, and lifting one continues as a pan without a
  jump; a tap on the backdrop calls `onTap` on the click that follows it,
  while a tap on the image, a press that started on a button, or a drag
  over 4 px does not; a mouse released outside the surface ends its
  gesture; a touch
  swipe at fit calls `onSwipe` with the direction and a mouse drag at fit
  does not; a double-click on the image toggles fit and actual pixels; a
  window resize re-clamps the view; the pointer is captured only once a
  drag starts; `destroy` removes the listeners.
- [x] Run them and confirm the failure.
- [x] Write the smallest change that passes them.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 3 — The viewer

**Files:**
- Modify: `frontend/TestRun/Components/ScreenshotModal.svelte` (whole file)
- Test: `frontend/TestRun/Components/ScreenshotModal.test.ts`

**Internals:** `Props { selectedScreenshot; screenshots? }`; state `view`
(`$state.raw`, replaced wholesale), `failed`, `stage`, `image`; derived
`index`, `hasPrev`, `hasNext`, `multiple`; `show(url)` (sets the URL,
resets `view` and `failed`), `close()`, `step(delta)`, `zoomBy(factor)`,
`fit()`, `actual()`, `handleKeyDown` (early return while closed or with a
modifier, the key table of the spec, `preventDefault` on a handled key), the inline action
`dialogOpen(node)` (remembers `document.activeElement`, focuses the node,
adds `overflow-hidden` to the body; on destroy removes the class and
refocuses the trigger when it is a connected `HTMLElement`). Markup: the
`{#if}` dialog with `role="dialog"`, `aria-modal`, `aria-label`,
`tabindex="-1"`; the toolbar with the counter, the five named buttons and
the open-original link without the download query; the surface with
`bind:this={stage}` and `use:zoomPan`, the previous and next buttons, the
image with `bind:this={image}`, `draggable="false"`, the transform style
and `onerror`; the failure message. Styles: backdrop and z-index, the
surface (`touch-action: none; user-select: none; overscroll-behavior:
contain; overflow: hidden`), the image fit, the grab cursors. The
`screenshot-button` rules go.

- [x] Write the failing tests: renders nothing when no screenshot is
  selected; shows the selected screenshot with the counter for a list and
  neither counter nor arrows for a single URL; closes on Escape; the arrows
  move through the list, update the counter and reset the transform;
  previous is disabled on the first and next on the last; `+` zooms in and
  `0` returns to fit; a key with a modifier is left to the browser; the
  shortcuts are ignored while closed; the focus
  moves to the dialog on open and back to the trigger on close; the body
  gets `overflow-hidden` while open and loses it on close; a failed image
  shows the message and keeps the open-original link.
- [x] Run them and confirm the failure.
- [x] Write the smallest change that passes them.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 4 — The gallery

**Files:**
- Modify: `frontend/TestRun/Screenshots.svelte:1-49`
- Test: `frontend/TestRun/Screenshots.test.ts`

**Internals:** typed `Props { screenshots?; testInfo; runId }`, `urls`
derived once from `createScreenshotUrl`; a Bootstrap `row row-cols-2
row-cols-md-3 row-cols-lg-4 row-cols-xxl-5 g-2 p-2` grid, one `col` with a
`button.ratio.ratio-1x1` per screenshot holding an
`img.object-fit-cover.w-100.h-100` with `loading="lazy"`,
`decoding="async"` and a numbered alt text; the empty-state line stays;
`<ScreenshotModal bind:selectedScreenshot screenshots={urls} />`. The
fixed-size thumbnail rules go.

- [x] Write the failing tests: one button per screenshot with a numbered
  alt text and the proxied URL; the empty message without screenshots; a
  click opens the viewer on that screenshot; `ArrowRight` moves to the next
  gallery entry; the focus returns to the thumbnail that opened the viewer.
- [x] Run them and confirm the failure.
- [x] Write the smallest change that passes them.
- [x] Run the verify sequence.
- [x] Commit, with the boxes of this task checked.

## Task 5 — Live check

**Files:** none.

Against the dev instance with the development bundle, on a seeded SCT run
that carries the screenshot links of the run named in the intent.

- [ ] At a desktop width: the screenshot opens fitted and centred; the
  wheel zooms around the pointer; ctrl+wheel pinches; a drag pans within
  the bounds; the arrows, the keys and the buttons move through the run;
  `0`, `1` and a double-click switch the zoom; the backdrop click and
  Escape close and the focus returns to the thumbnail; the page does not
  scroll behind the viewer.
- [ ] At a narrow width: the thumbnails wrap in two columns and stay
  square; the viewer fits the window; the toolbar stays reachable.
