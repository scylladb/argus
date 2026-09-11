## CSS

### Bootstrap First
Bootstrap 5 provides the layout and the components. Use a Bootstrap utility or
component before you write a rule. Do not override a framework rule when a
variant already exists.

### Color Pairs Stay Together
A severity badge, a status indicator and an alert class set
`background-color` and `color` in the same rule. The pair keeps the element
readable on any background. Keep them together when you add a class.

An element that depends on the inherited page background is the exception, and
it needs a check in both themes.

### Scope a Style to Its Component
Put a rule in the component that owns it. A Svelte style block is scoped by
default. Use a global rule only for a Bootstrap override that must cross the
boundary, and state why.

### Consistent Values
Reuse the Bootstrap spacing, color and typography scales. Introduce a custom
value only when the scale has no match.

### Minimize Custom CSS
Less custom CSS means fewer theme regressions. Delete a rule that no selector
uses.
