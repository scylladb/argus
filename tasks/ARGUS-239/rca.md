# ARGUS-239 — Job clone fails with a release_id type error

**Date**: 2026-09-28

## Root cause

Commit 838afb79 ported `ArgusRelease`, `ArgusGroup` and `ArgusTest` to coodie.
The coodie mapper does not convert a string to a UUID for a UUID column. The
clone flow has two call sites that give the mapper the wrong type.

**Cause 1: the groups request.** The dialog sends the release ID as a query
string. `GET /api/v1/jenkins/clone/groups` reads it as `str` and passes it on
unchanged:

- `argus/backend/controller/testrun_api.py:519`:
  `target_id: str = Query(..., alias="targetId")`
- `argus/backend/service/jenkins_service.py:226`:
  `groups = list(ArgusGroup.find(release_id=release_id).all())`

The driver rejects the string for the `release_id` UUID column. This is the
error in `intent.md`:

```
Received an argument of invalid type for column "release_id". Expected: <class 'cassandra.cqltypes.UUIDType'>, Got: <class 'str'>
```

**Cause 2: the clone request.** This cause blocks the clone after the groups
load. `JenkinsCloneRequest.currentTestId` has the type `UUID`
(`argus/backend/controller/testrun_api.py:70`). Pydantic gives the service a
`UUID` object. `clone_job` wraps it in `UUID()` again
(`argus/backend/service/jenkins_service.py:312`):

```python
cloned_test: ArgusTest = ArgusTest.get(id=UUID(current_test_id))
```

The `UUID` constructor accepts only a string, so the call fails:

```
AttributeError: 'UUID' object has no attribute 'replace'
```

`POST /api/v1/jenkins/clone/create` then returns an error, and no job is
created.

The other methods in the clone flow do not have this problem.
`get_releases_for_clone` converts its string argument. `get_advanced_settings`
and `adjust_job_settings` read `build_system_id`, which is a text column.

**Other defects in `clone_job`.** These defects do not block the clone, but
they make its result incorrect:

- The check that stops a clone onto its own source compares
  `target_group.id` with `cloned_test.id`, a group ID with a test ID. The
  check is always false. `create_job` then fails with a Jenkins error for the
  existing job.
- `if display_name:` tests the truth value of an XML element. An element with
  no child elements is false, so the new job keeps the display name of the
  source job.
- `clone_job` saves the new test and does not call
  `validate_build_system_id()`. A clone can write a second test with the same
  `build_system_id`. `ArgusTest.get(build_system_id=...)` then fails for that
  job.

## Approaches

1. **Convert the type in the service.** Selected. `get_groups_for_release`
   converts the release ID with `UUID(release_id)`. `clone_job` takes
   `current_test_id` as a `UUID` and passes it to the mapper unchanged. This
   is the same pattern that `get_releases_for_clone` and `clone_job` use for
   the other IDs. The change is two lines. The API contract and the error
   shape that the dialog reads do not change.
2. **Type the router parameter as `UUID`.** FastAPI converts the query string
   before the service runs. An incorrect ID then gets a FastAPI 422 response
   with a different body. The dialog reads `error.response.arguments[0]`, so
   this changes the error contract. It also leaves cause 2 unchanged.
   ARGUS-240 does this for all API routes.

`clone_job` also compares `target_group.id` with `cloned_test.group_id`,
tests `display_name is not None`, and calls `validate_build_system_id()`
before `create_job`.

## Regression test

New file `argus/backend/tests/testrun_api/test_jenkins_clone_api.py`. The tests
use the real `JenkinsService` against the ScyllaDB test container, with a fake
python-jenkins client.

- `test_clone_groups_returns_groups_of_target_release`: sends
  `GET /api/v1/jenkins/clone/groups?targetId=<release id>` and expects the
  group of that release. It fails before the fix with the `release_id` type
  error.
- `test_clone_job_creates_test_in_target_group`: sends
  `POST /api/v1/jenkins/clone/create` and expects a new `ArgusTest` in the
  target group and release, with the new display name in the job config. It
  fails before the fix with the `AttributeError`.
- `test_clone_job_rejects_source_group_and_name`: clones a test into its own
  group with its own name, and expects the "source and destination are the
  same" error.
- `test_clone_job_rejects_used_build_system_id`: clones to a path that another
  test uses, and expects the "Build Id is already used by another test"
  error. Jenkins gets no `create_job` call.

## Risks

| Risk | Response |
|---|---|
| Another call site from the coodie port gives a string to a UUID column. | Out of scope. ARGUS-240 types the IDs at the router. |
| A malformed ID raises a bare `ValueError`, which the API reports as a server error. | Out of scope. ARGUS-240 returns a validation error. |
