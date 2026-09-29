# ARGUS-245 — Browsers use outdated frontend bundles after a deployment

## Problem

After a deployment, a user's browser can keep the JavaScript and CSS bundles
from the previous release. The page then runs old code against the new backend
or loads files that no longer exist on the server, and parts of the frontend
break. The breakage is worst after large updates. It stays until the cached
files expire or the user forces a reload.

## Who it affects

Every Argus web user who has a page open or cached assets during a deployment.

## Evidence

Jira issue ARGUS-245:

```
Currently each deployment can cause bundle cache issues for users, leading to
broken frontend after large updates. We need to support proper tagging of
assets and invalidate them via ETags.
```

## What good looks like

- After a deployment, the first page load in a browser uses the new bundles
  and the new stylesheet, with no forced reload.
- No page fails to load a script or a stylesheet because of a deployment.
- Bundles that did not change between releases can stay cached.

## Out of scope

- Service worker or offline caching.
- Reloading pages that are already open when the deployment happens.
- CDN setup.
