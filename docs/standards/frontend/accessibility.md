## Accessibility

### Semantic HTML
Use the element that carries the meaning: `nav`, `main`, `button`, `table`. A
`div` with a click handler tells a screen reader nothing.

### Keyboard Navigation
Make every interactive element reachable by keyboard. Keep the focus indicator
visible.

### Color Contrast
Keep a contrast ratio of 4.5 to 1 for normal text. Never carry meaning by color
alone. A status needs a label or an icon as well.

### Labels and Alt Text
Give every form input a label. Give every meaningful image a description.

### Heading Structure
Use the heading levels in order. The outline of the page comes from them.

### ARIA When Needed
Add an ARIA attribute where semantic HTML cannot express the component. Prefer
the semantic element first.

### Focus Management
Move the focus into a modal when it opens, and back to the trigger when it
closes. A dynamic update must not lose the focus.
