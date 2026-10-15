# ARGUS-240 — API routes take entity IDs as strings

## Problem

The coodie mapper binds a query or a save parameter as given. It does not
convert a string to a UUID for a UUID column. Many API routes take an
entity ID as `str`, at the router or inside a request body, and leave the
conversion to the service. The services handle it in three different ways:

- They call `UUID(x)` on the argument. A malformed ID then raises a bare
  `ValueError`, and the API reports it as an unexpected server error.
- They call `UUID(x) if isinstance(x, str) else x`, a guard that never
  fires where the router already gives a `UUID`.
- They forget the conversion. The driver then rejects the string with a
  type error, as in ARGUS-239.

A service that calls `UUID(x)` with no guard also breaks the moment its
router starts to give it a `UUID`. It fails with
`'UUID' object has no attribute 'replace'`.

The same gap leaves live failures in flows that a user or a client reaches
today:

- An SCT Gemini submission with a status other than `PASSED`, and a
  performance submission that finds a regression, write the run event with
  the string run ID.
- Editing a run comment that has mentions saves the string IDs into a
  `list<uuid>` column.
- Submitting a run comment with mention IDs mixes strings and `User`
  objects and fails on `m.id`.
- Changing the owner of a release plan saves the string owner into a UUID
  column.
- Copying a release plan looks up the hand-mapped replacements with UUID
  keys in a string-keyed map. The mapped tests and groups are dropped from
  the copy, with no error.
- The run details widget keys its error entry by a `UUID`, which the JSON
  encoder rejects, so one failed run fails the whole response.

## Who it affects

- Users of the Argus web UI: the clone dialog, run comments, the release
  planner, the view widgets and the admin release manager.
- The Python client and the Go CLI, which submit runs, events, results and
  comments.
- SCT pipelines that report Gemini and performance results.
- Operators who read the error logs and the exception metric. A malformed
  ID from a client shows there as a server fault.

## Evidence

From the Jira issue:

```
The coodie mapper does not convert a string to a UUID. Many API routes take an ID as `str` at the router, and the service converts it with `UUID()` at each call site. A call site that does not convert fails with a driver type error, as in ARGUS-239. A malformed ID raises a bare ValueError, and the API reports it as an unexpected server error.

The clone routes in argus/backend/controller/testrun_api.py are examples: `targetId` in get_groups_for_target, and `target` and `group` in JenkinsCloneRequest. About 27 route parameters in argus/backend/controller/ take an ID as `str`. Some routes already use `UUID = Query(...)`, for example api.py and admin_api.py.
```

The clone routes:

```
argus/backend/controller/testrun_api.py:  async def get_groups_for_target(target_id: str = Query(..., alias="targetId"),
argus/backend/controller/testrun_api.py:      target: str
argus/backend/controller/testrun_api.py:      group: str
argus/backend/service/jenkins_service.py: groups = await ArgusGroup.find(release_id=UUID(release_id)).all()
```

The client and SCT plugin routers alone declare `run_id: str` 36 times.

The live failures:

```
argus/backend/plugins/sct/service.py:   }, user_id=user.id, run_id=run_id, release_id=run.release_id, test_id=run.test_id)
argus/backend/service/event_service.py: event = ArgusEvent.model_construct()
argus/backend/service/event_service.py: event.run_id = run_id
argus/backend/service/testrun.py:       comment.mentions = mentions
argus/backend/service/testrun.py:       comment.mentions = [m.id for m in mentions]
argus/backend/service/planner_service.py:   plan.owner = plan_request.owner
argus/backend/service/planner_service.py:   new_test_id = new_test.id if new_test else payload.replacements.get(
argus/backend/service/planner_service.py:   replacements: dict[str, str]
argus/backend/service/views_widgets/graphed_stats.py:   result[run_id] = {
```

## What good looks like

- Every ID parameter of an API route has the type `UUID`, in the router
  signature or in the request model.
- The services take `UUID` for these IDs and do not call `UUID()` on them.
- A malformed ID gets the `RequestValidationError` response, and the logs
  and the exception metric treat it as a client error.
- The Gemini and performance submissions, comment mentions, the plan owner
  change, the plan copy replacements and the run details widget work.
- The backend tests pass.

## Out of scope

- Values that are not UUIDs: build IDs, Jira keys, release names, image
  IDs, the pytest result timestamp ID, and the `RunConfigParam.run_id` text
  column.
- Plan references, which accept a plan UUID or a plan key.
- The per-plugin run submission payloads and the email report payloads,
  which stay untyped dictionaries.
- Server-rendered UI pages, which parse their IDs by hand to flash an error.
- The legacy schedule endpoints, which are stubs and do not read their IDs.
