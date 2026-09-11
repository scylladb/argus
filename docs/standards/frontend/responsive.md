## Responsive Layout

Argus is a dense dashboard. A release view, a run list and a results table
carry many columns, and a desktop browser is the primary target. The rules
below keep a narrow window usable without a redesign.

### Use the Bootstrap Grid
Lay out a page with the Bootstrap container, row and column classes. Use the
Bootstrap breakpoints rather than a custom media query.

### Let a Wide Table Scroll
Wrap a wide table in a horizontal scroll container. Do not shrink a column
until the content becomes unreadable.

### Fluid Containers
Size a panel in a percentage or a flexible unit. A fixed pixel width breaks the
layout on a smaller window.

### Relative Units
Prefer `rem` over a pixel value for spacing and type, so a browser zoom keeps
the proportions.

### Readable Type
Keep the font size readable at every breakpoint. A dashboard is read for a long
time.

### Content Priority
Show the status, the identity of the run and the failure first. Move a detail
panel below the fold on a narrow window.

### Check Two Widths
Check a change at a desktop width and at a narrow window before you open the
pull request.
