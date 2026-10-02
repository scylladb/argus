# ARGUS-209 — implementation plan

**Spec:** `tasks/ARGUS-209/spec.md`

## Constraints

- Imports sit at the top of the module.
- No comments or docstrings that justify the change.
- Tests create and read rows through the services or the API, never through
  `Model.save()` or `find()` in a test body.
- Mock the remote Jira client and keep ScyllaDB real. Every backend test needs Docker.
- No `allow_filtering()` on the new reads. Each read restricts an indexed
  column alone, with no extra filter next to it.
- Commits:
  - commitlint header `feature(issues): …` or `docs(issues): …`
  - a body of at least 30 characters
  - the last line is `Task: ARGUS-209`
  - `git add` by explicit path only
- Leave the code uncommitted until the user reviews it.

## Task 1 — Index the issue key and the link's issue id

**Files:**
- Modify: `argus/backend/models/github_issue.py:63`
- Modify: `argus/backend/models/jira.py:16`

**Internals:**
- `IssueLink.issue_id: Annotated[UUID, ClusteringKey(), Indexed()]`. The same form already exists
  at `argus/backend/models/web.py:156`.
- `JiraIssue.key: Annotated[str, Indexed()]`.
- `sync_models` names the indexes `issue_link_issue_id_idx` and `jira_issue_key_idx`. The test
  fixture `argus_db` applies them with `sync_models`.

- [ ] Change both annotations.
- [ ] Run `uv run pytest argus/backend/tests/issues` and confirm that the suite still passes with the indexes.

## Task 2 — Resolve an issue key to its links and runs

**Files:**
- Modify: `argus/backend/service/jira_service.py`: add `KEY_PATTERN`, `is_issue_key` and
  `get_issues_by_key` next to `get_issue`.
- Modify: `argus/backend/service/issue_service.py`: add `IssueServiceException`, `get_issue_links`
  and `_resolve_link_runs`.
- Test: `argus/backend/tests/issues/test_issues.py`, a new section
  `# Listing the runs linked to an issue`. It reuses `mocked_issue_service`, `run`, `submit_run`,
  `fake_remote_jira_issue` and `JIRA_SERVER` from that module.

**Internals:**

`JiraService`:
- `KEY_PATTERN = re.compile(r"[A-Z][A-Z0-9_]*-[0-9]+")`
- `is_issue_key(key: str) -> bool` returns whether `KEY_PATTERN.fullmatch(key)` matches.
- `get_issues_by_key(key: str) -> list[JiraIssue]` returns `await JiraIssue.find(key=key).all()`.

`issue_service.py` declares `class IssueServiceException(Exception)`, as the other services name
theirs, and `LINKED_RUN_COLUMNS` at module level. The candidates are a local map from subtype to
tracker service, in the order in which they are tried. A new tracker adds an entry and leaves the
signature alone.

```python
LINKED_RUN_COLUMNS = ("id", "build_id", "build_number", "status", "start_time", "scylla_version", "product_version")

async def get_issue_links(self, key: str) -> dict:
    normalized = key.upper()
    trackers = {"jira": self.jira}
    candidates = [(subtype, tracker) for subtype, tracker in trackers.items() if tracker.is_issue_key(normalized)]
    if not candidates:
        raise IssueServiceException(f"Not an issue key: {key!r}. Expected a Jira key such as SCT-1234.")
    for subtype, tracker in candidates:
        rows = await tracker.get_issues_by_key(normalized)
        if not rows:
            continue
        batches = await asyncio.gather(*(IssueLink.find(issue_id=row.id).all() for row in rows))
        links = {link.run_id: link for batch in batches for link in batch}
        issue = max(rows, key=lambda row: row.added_on)
        runs = await self._resolve_link_runs(list(links.values()))
        return {
            "issue": {**issue.model_dump(), "subtype": subtype},
            "links": sorted(runs, key=lambda run: run["start_time"], reverse=True),
        }
    return {"issue": None, "links": []}
```

`_resolve_link_runs(links: list[IssueLink]) -> list[dict]`:
1. Read the tests with `ArgusTest.find(id__in=batch).all()`, per `chunk()` of the distinct
   `link.test_id`, into `{test.id: test}`.
2. Keep the pairs `(link, test)` whose test exists and whose `test.plugin_name` is in
   `AVAILABLE_PLUGINS`.
3. Run `gather_limited(select_rows(AVAILABLE_PLUGINS[test.plugin_name].model.find(id=link.run_id), *LINKED_RUN_COLUMNS) for …)`.
   `select_rows` (`argus/backend/util/common.py:38`) returns dicts. `.only()` would build models
   that lack required fields such as `build_job_url`.
4. For each pair with a row, build the `LinkedRun` dict of the spec without `url`: `run_id`,
   `test_id`, `test_name=test.name`, `plugin_name`, `status`, `start_time`, `build_id`,
   `build_number`, `scylla_version`, `product_version`, and `linked_on=link.added_on`.

**Tests** (`async def`, same style as the module):
- `test_issue_links_return_the_issue_and_its_run`: one Jira issue linked to `run`. Asserts the issue
  `key`, `summary`, `state`, `permalink` and `subtype == "jira"`. Asserts one link with the run id,
  test id, `test_name`, `plugin_name == "scylla-cluster-tests"`, `status`, `start_time`, `build_id`
  and `linked_on`.
- `test_issue_links_list_every_linked_run_newest_first`: two runs linked to one key. Asserts both
  run ids, and that `start_time` does not increase down the list.
- `test_issue_links_leave_out_runs_of_another_issue`: two keys, one run each. Each key returns only
  its own run.
- `test_issue_links_for_an_unknown_key_are_empty`: returns `{"issue": None, "links": []}`.
- `test_issue_links_match_a_lowercase_key`.
- `test_issue_links_reject_a_value_that_is_no_issue_key`: `SCT1234` raises `IssueServiceException`.
- `test_issue_links_merge_rows_that_share_a_key`:
  - Link `run` through `{JIRA_SERVER}/browse/{key}`. Then link `run` and a second run through the
    same URL with a trailing slash, which stores a second `JiraIssue` row with that key.
  - Asserts that `get_issues_by_key` returns two rows, and that the links hold each run once.

- [ ] Write the tests.
- [ ] Run them and confirm the failure (`AttributeError` on `get_issue_links`).
- [ ] Add the two service methods.
- [ ] Run `uv run pytest argus/backend/tests/issues` until it passes.

## Task 3 — Serve the endpoint

**Files:**
- Modify: `argus/backend/controller/testrun_api.py`: add the route after `issues_get` (l.260–279).
  Import `url_for` from `argus.backend.rendering`.
- Test: `argus/backend/tests/issues/test_issues.py`, in the same section. It uses `api_client`
  against the real `IssueService`. A read never touches the Jira client, so the router's own
  `IssueService()` needs no mock.

**Internals:**

```python
@router.get("/issues/{key}/links", name="api.testrun_api.issue_links")
async def issue_links(asgi_request: Request, key: str, user: User = Depends(api_current_user)):
    result = await IssueService().get_issue_links(key=key)
    base_url = str(asgi_request.base_url).rstrip("/")
    for link in result["links"]:
        link["url"] = base_url + url_for(asgi_request, "main.get_run_by_build",
                                         build_id=link["build_id"], build_number=link["build_number"])
    return APIResponse({"status": "ok", "response": result})
```

**Tests:**
- `test_issue_links_endpoint_returns_run_urls`:
  - Link `run` through `mocked_issue_service`, then call `GET /api/v1/issues/{key}/links`.
  - Asserts `status == "ok"`, the issue key, and `url == f"http://testserver/test/{run.build_id}/{run.build_number}"`.
- `test_issue_links_endpoint_answers_ok_for_an_unknown_key`: `response == {"issue": None, "links": []}`.
- `test_issue_links_endpoint_rejects_a_value_that_is_no_issue_key`: `GET /api/v1/issues/SCT1234/links`
  gives HTTP 200 with `status == "error"`.

- [ ] Write the tests.
- [ ] Run them and confirm the failure (HTTP 404 for the route).
- [ ] Add the route.
- [ ] Run `uv run pytest argus/backend/tests/issues argus/backend/tests/testrun_api` until it passes.

## Task 4 — Document the contract

**Files:**
- Modify: `docs/api_usage.md`: a new entry at the end of `## Current endpoints`, before
  `## Email reporting API` (l.270), in the form of the entries above it.

**Content:**
- `GET /api/v1/issues/{key}/links`
- The parameter table (`key`: a Jira key, any case; a value that is no issue key returns
  `status: error`).
- A curl example with the token header.
- The response example from the spec, and the empty result for an unknown key.
- Two lines of rules:
  - links are newest first
  - the issue state follows the periodic Jira sync
  - unknown fields are to be ignored

- [ ] Write the entry.

## Task 5 — Verify

- [ ] Run `uv run pre-commit run --all-files`, `uv run pytest` and `yarn test`.
- [ ] Run `uv run python -m argus.backend.cli sync-models` against the dev database, and check
  `issue_link_issue_id_idx` and `jira_issue_key_idx` in `DESCRIBE TABLE`.
- [ ] On the dev server, call `/api/v1/issues/<KEY>/links` with an API token:
  - for a Jira issue that has linked runs, and open one returned `url`
  - for an unknown key
  - for a value that is no issue key
- [ ] Hand the diff to the user for review. After approval, commit:
  - Tasks 1–3 as one `feature(issues): …` commit
  - Task 4 as `docs(issues): …`
- [ ] The PR body names the deploy step:
  - `sync-models` creates the two indexes
  - the list can be partial while ScyllaDB builds them
  - the body ends with `closes ARGUS-209`
