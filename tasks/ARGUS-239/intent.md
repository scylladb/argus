# ARGUS-239 — Job clone fails with a release_id type error

## Problem

Users cannot clone a job in Argus. The clone dialog loads the groups of the
target release. That request fails, and the dialog shows an error. The user
cannot select a target group, so the clone cannot start.

## Who it affects

Every Argus user who clones a job into a release.

## Evidence

Jira issue ARGUS-239. The clone dialog shows:

```
An error occurred.
API Error when fetching groups. Message: Received an argument of invalid type for column "release_id". Expected: <class 'cassandra.cqltypes.UUIDType'>, Got: <class 'str'>; (Got a non-UUID object for a UUID value)
Source: CloneTargetSelector::fetchCategoriesForTarget
```

## What good looks like

- A user selects a target release in the clone dialog, and the groups load
  with no error.
- A user clones a job into the selected target group.
- Job cloning works in production Argus.

## Out of scope

- Changes to the clone dialog layout.
- Other endpoints that take a release ID, unless they fail in the same clone
  flow.
