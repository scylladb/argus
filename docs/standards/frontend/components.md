## Components

### Svelte 5 Runes
Runes are on by default. 206 of the 212 components use them, and 45 files still
import `svelte/legacy`. Write a new component with runes.

- Use `$props`, `$state`, `$derived` and `$effect`. Do not reach for the legacy
  `$:` label when a rune states the intent.
- `$state` makes a deep reactive proxy, so `.push()` on a `$state` array
  triggers an update. Reassignment is not needed.
- Never reassign a `$derived` variable. Derive it from its inputs.

### Reach the DOM Through Bindings
Use `bind:this` or an action (`use:...`). Never call `Node.querySelector` inside
a component. Track a node through a binding or a store.

Wrap an escape hatch, such as a Bootstrap collapse, a portal or an external
widget, in a reusable action or helper. That keeps the behavior testable.

### Compose, Do Not Mutate
Prefer composition, a snippet and an `{@const}` or `{@render}` block over an
imperative DOM update. Use `await tick()` when the code must wait for the DOM
after a state change.

### Keep Data Out of the Markup
Transform data in the script block and pass plain data to the markup. Never
derive a clipboard payload or an export payload by reading rendered HTML.

### Layout
One directory per feature area under `frontend/`, in PascalCase, with the main
component named after the directory. `Stores/` holds shared state. `Common/`
holds a helper and a type definition. Keep a UI helper next to the component
that uses it.

A page entry point goes in `vite.config.ts` and loads from a Jinja template in
`templates/`. Add both in the same change.

### Types
Use a typed prop and `import type` when the code binds a component instance or
a DOM node. A component that needs types declares `lang="ts"`.

### Single Responsibility
A component does one thing. Split it when the props list grows long.

### Local State
Keep state next to its use. Lift it into `Stores/` only when two feature areas
need it.

### Clear Interface
Declare explicit props with a sensible default. Keep the implementation
private.
