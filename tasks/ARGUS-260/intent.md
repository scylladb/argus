# ARGUS-260 — Screenshots are too wide after clicking

## Problem

A click on a screenshot thumbnail of a run opens the image at its natural
size. An SCT Grafana capture is 1920 pixels wide, and a full-page capture is
several times taller than a window, so on a laptop or a phone the image runs
past the right edge of the window and the viewer only scrolls vertically.
The viewer gives no way to see the whole screenshot, and no way to look at a
detail of it at a readable size: it has no zoom and no pan.

The viewer shows one screenshot at a time, with no way to move to the next
or the previous one. Each look at another screenshot means closing the
viewer, finding the thumbnail again and opening it. The only key the viewer
answers is Escape. The close control is not a button, so it cannot be
reached from the keyboard, and the focus does not move into the viewer when
it opens or back to the thumbnail when it closes.

The thumbnails of the Screenshots tab are a fixed 384 by 384 pixels. On a
window narrower than that they overflow the tab as well.

## Who it affects

- Engineers who triage an SCT run from its Screenshots tab on a laptop
  screen or a phone, and anyone who opens a screenshot from a results table
  through its "view" button, on the run page or in a view widget.
- Engineers who want to read a number or a legend in a Grafana capture, who
  today open the original in another tab and zoom the browser.
- Keyboard and screen reader users, who cannot operate the viewer.

## Evidence

Jira issue ARGUS-260:

```
screenshots are wider than my screen. Click one on e.g. https://argus.scylladb.com/tests/scylla-cluster-tests/21bac188-beff-4191-9520-c2f22a435161/screenshots
```

The viewer renders the image with a class that no stylesheet defines, so the
image keeps its natural size, `frontend/TestRun/Components/ScreenshotModal.svelte`:

```svelte
        <div class="d-flex align-items-center justify-content-center my-2">
            <img
                    class="screenshot-modal-image"
                    src={selectedScreenshot}
                    alt="Screenshot"
            />
        </div>
```

The overlay scrolls on one axis only:

```css
    .screenshot-modal {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        overflow-y: scroll;
```

The thumbnails have a fixed size, `frontend/TestRun/Screenshots.svelte`:

```css
    .screenshot-thumb {
        border: solid 2px rgb(122, 122, 122);
        border-radius: 4px;
        width: 384px;
        height: 384px;
```

## What good looks like

- A screenshot opens fitted to the window, whole and centred, on any window
  size.
- The mouse wheel and a trackpad or touch-screen pinch zoom the screenshot
  around the pointer, and a left-mouse drag or a one-finger drag pans it.
  A zoomed screenshot never leaves the window empty, and it goes back to the
  fitted size on request.
- The viewer moves to the previous and the next screenshot of the run
  without closing, from the keyboard, from buttons, and from a swipe on a
  touch screen, and it tells which screenshot of how many is shown.
- The keyboard closes the viewer, moves between the screenshots, zooms in
  and out, and jumps to the fitted size and to the actual pixel size.
- The focus moves into the viewer when it opens and back to the thumbnail
  that opened it when it closes, and every control is a button a screen
  reader names.
- The thumbnails fill the width of the tab in rows that adapt to the window,
  and keep their square shape.
- A screenshot opened from a results table keeps working as today, as a
  single image.

## Out of scope

- A real download of a screenshot. The link the viewer offers opens the
  original, and the proxy route has no download mode.
- Moving between the screenshots of several results tables from one viewer.
- The results tables of the summary widget, whose "view" buttons open no
  viewer today.
- Trapping the keyboard focus inside the viewer.
- The screenshots in the run report email.
