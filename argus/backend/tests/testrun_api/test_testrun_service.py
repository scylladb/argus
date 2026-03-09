import json
import time
from uuid import UUID, uuid4

import pytest
from flask.testing import FlaskClient
from flask.wrappers import Response

from argus.backend.models.web import ArgusTest

API_PREFIX = "/api/v1"

# Fields returned when `full` is NOT set (as defined in TestRunService.get_runs_by_test_id)
META_FIELDS = frozenset(
    [
        "id",
        "test_id",
        "group_id",
        "release_id",
        "status",
        "start_time",
        "build_number",
        "build_job_url",
        "build_id",
        "assignee",
        "end_time",
        "investigation_status",
        "heartbeat",
        "build_number",
    ]
)

FULL_ONLY_FIELD = "packages"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _submit_run(flask_client: FlaskClient, fake_test: ArgusTest, *, run_id: str | None = None, build_number: int = 1) -> str:
    """Submit a single SCT run against `fake_test` and return its run_id.

    `build_number` is embedded in the job URL so that `get_build_number()` can
    parse it correctly (the function extracts the last path segment as an int).
    """
    run_id = run_id or str(uuid4())
    payload = {
        "run_id": run_id,
        "job_name": fake_test.build_system_id,
        "job_url": f"http://ci.example.com/job/{build_number}",
        "started_by": "test_user",
        "commit_id": "deadbeef",
        "origin_url": "http://example.com/repo.git",
        "branch_name": "main",
        "sct_config": {"cluster_backend": "aws"},
        "schema_version": "v8",
    }
    resp = flask_client.post(
        f"{API_PREFIX}/client/testrun/scylla-cluster-tests/submit",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.text
    assert resp.json["status"] == "ok"
    return run_id


def _submit_package(flask_client: FlaskClient, run_id: str) -> None:
    """Submit one package entry to an existing SCT run.

    This ensures the `packages` list column has real data, making it possible
    to distinguish between the column being fetched (non-empty) vs not fetched
    (empty list returned by CQLEngine for unfetched list columns).
    """
    payload = {
        "packages": [
            {
                "name": "scylla-server",
                "version": "99.0.0",
                "commit_id": "deadbeef",
                "origin": "scylla",
            }
        ],
        "schema_version": "v8",
    }
    resp = flask_client.post(
        f"{API_PREFIX}/client/sct/{run_id}/packages/submit",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.text
    assert resp.json["status"] == "ok"


def _get_runs(flask_client: FlaskClient, test_id: UUID, **params) -> Response:
    """GET /api/v1/test/{test_id}/runs with optional query parameters."""
    return flask_client.get(
        f"{API_PREFIX}/test/{test_id}/runs",
        query_string=params,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def run_id(flask_client: FlaskClient, fake_test: ArgusTest) -> str:
    """Submit a single run and return its UUID string."""
    return _submit_run(flask_client, fake_test)


@pytest.fixture
def run_id_with_package(flask_client: FlaskClient, fake_test: ArgusTest) -> str:
    """Submit a run with one package entry so `packages` is non-empty when fully fetched."""
    rid = _submit_run(flask_client, fake_test)
    _submit_package(flask_client, rid)
    return rid


@pytest.fixture
def run_ids(flask_client: FlaskClient, fake_test: ArgusTest) -> list[str]:
    """Submit three runs against the same test.  Returns the list of run UUIDs."""
    return [_submit_run(flask_client, fake_test, build_number=i + 1) for i in range(3)]


# ---------------------------------------------------------------------------
# Tests – no query parameters / basic smoke
# ---------------------------------------------------------------------------

@pytest.mark.docker_required
def test_get_runs_no_params_returns_ok(flask_client: FlaskClient, run_id: str, fake_test: ArgusTest) -> None:
    """Basic smoke: the endpoint returns status=ok and a list."""
    resp = _get_runs(flask_client, fake_test.id)

    assert resp.status_code == 200
    assert resp.json["status"] == "ok"
    assert isinstance(resp.json["response"], list)


@pytest.mark.docker_required
def test_get_runs_no_params_contains_submitted_run(flask_client: FlaskClient, run_id: str, fake_test: ArgusTest) -> None:
    """Without any filters the submitted run must appear in the response."""
    resp = _get_runs(flask_client, fake_test.id)

    assert resp.status_code == 200
    returned_ids = [r["id"] for r in resp.json["response"]]
    assert run_id in returned_ids


@pytest.mark.docker_required
def test_get_runs_response_has_meta_fields(flask_client: FlaskClient, run_id: str, fake_test: ArgusTest) -> None:
    """Each entry in the default (non-full) response must contain all expected meta fields."""
    resp = _get_runs(flask_client, fake_test.id)

    assert resp.status_code == 200
    runs = resp.json["response"]
    assert len(runs) > 0

    for run in runs:
        for field in META_FIELDS:
            assert field in run, f"Expected meta field '{field}' missing from run {run.get('id')}"


# ---------------------------------------------------------------------------
# Tests – `limit` parameter
# ---------------------------------------------------------------------------

@pytest.mark.docker_required
def test_get_runs_default_limit_is_ten(flask_client: FlaskClient, fake_test: ArgusTest) -> None:
    """When `limit` is omitted, at most 10 runs are returned by default."""
    # Submit 12 runs with distinct build numbers so there is something to limit
    for i in range(12):
        _submit_run(flask_client, fake_test, build_number=i + 100)

    resp = _get_runs(flask_client, fake_test.id)

    assert resp.status_code == 200
    assert len(resp.json["response"]) <= 10


@pytest.mark.docker_required
def test_get_runs_explicit_limit_respected(flask_client: FlaskClient, run_ids: list[str], fake_test: ArgusTest) -> None:
    """Passing `limit=1` must return at most 1 run even when more exist."""
    resp = _get_runs(flask_client, fake_test.id, limit=1)

    assert resp.status_code == 200
    assert len(resp.json["response"]) <= 1


@pytest.mark.docker_required
def test_get_runs_limit_larger_than_total(flask_client: FlaskClient, run_ids: list[str], fake_test: ArgusTest) -> None:
    """When `limit` exceeds the total number of runs, all runs are returned."""
    resp = _get_runs(flask_client, fake_test.id, limit=1000)

    assert resp.status_code == 200
    returned_ids = {r["id"] for r in resp.json["response"]}
    # All three runs submitted by the `run_ids` fixture must be present
    for rid in run_ids:
        assert rid in returned_ids


# ---------------------------------------------------------------------------
# Tests – `before` parameter
# ---------------------------------------------------------------------------

@pytest.mark.docker_required
def test_get_runs_before_far_past_returns_empty(flask_client: FlaskClient, run_id: str, fake_test: ArgusTest) -> None:
    """before=1.0 (Unix epoch) must exclude all freshly-submitted runs."""
    resp = _get_runs(flask_client, fake_test.id, before=1.0)

    assert resp.status_code == 200
    assert resp.json["response"] == []


@pytest.mark.docker_required
def test_get_runs_before_far_future_includes_runs(flask_client: FlaskClient, run_id: str, fake_test: ArgusTest) -> None:
    """before set to a timestamp far in the future must include current runs."""
    far_future = time.time() + 10 * 365 * 24 * 3600  # ~10 years from now

    resp = _get_runs(flask_client, fake_test.id, before=far_future)

    assert resp.status_code == 200
    returned_ids = [r["id"] for r in resp.json["response"]]
    assert run_id in returned_ids


@pytest.mark.docker_required
def test_get_runs_before_invalid_format_returns_error(flask_client: FlaskClient, run_id: str, fake_test: ArgusTest) -> None:
    """Passing a non-numeric `before` value must result in a non-ok response."""
    resp = _get_runs(flask_client, fake_test.id, before="not_a_timestamp")

    # The service raises TestRunServiceException which the error handler serialises to JSON
    assert resp.json["status"] != "ok"


# ---------------------------------------------------------------------------
# Tests – `after` parameter
# ---------------------------------------------------------------------------

@pytest.mark.docker_required
def test_get_runs_after_far_future_returns_empty(flask_client: FlaskClient, run_id: str, fake_test: ArgusTest) -> None:
    """after set to a timestamp far in the future must exclude all current runs."""
    far_future = time.time() + 10 * 365 * 24 * 3600

    resp = _get_runs(flask_client, fake_test.id, after=far_future)

    assert resp.status_code == 200
    assert resp.json["response"] == []


@pytest.mark.docker_required
def test_get_runs_after_far_past_includes_runs(flask_client: FlaskClient, run_id: str, fake_test: ArgusTest) -> None:
    """after=1.0 (Unix epoch) must include all freshly-submitted runs."""
    resp = _get_runs(flask_client, fake_test.id, after=1.0)

    assert resp.status_code == 200
    returned_ids = [r["id"] for r in resp.json["response"]]
    assert run_id in returned_ids


@pytest.mark.docker_required
def test_get_runs_after_invalid_format_returns_error(flask_client: FlaskClient, run_id: str, fake_test: ArgusTest) -> None:
    """Passing a non-numeric `after` value must result in a non-ok response."""
    resp = _get_runs(flask_client, fake_test.id, after="not_a_timestamp")

    assert resp.json["status"] != "ok"


# ---------------------------------------------------------------------------
# Tests – `before` + `after` combined
# ---------------------------------------------------------------------------

@pytest.mark.docker_required
def test_get_runs_before_and_after_both_far_includes_runs(flask_client: FlaskClient, run_id: str, fake_test: ArgusTest) -> None:
    """before (far future) and after (far past) together must still include current runs."""
    far_future = time.time() + 10 * 365 * 24 * 3600

    resp = _get_runs(flask_client, fake_test.id, before=far_future, after=1.0)

    assert resp.status_code == 200
    returned_ids = [r["id"] for r in resp.json["response"]]
    assert run_id in returned_ids


@pytest.mark.docker_required
def test_get_runs_before_and_after_exclusive_returns_empty(flask_client: FlaskClient, run_id: str, fake_test: ArgusTest) -> None:
    """A window that does not contain any run's start_time must return an empty list.

    We use before=2.0 and after=1.0.  All real runs have start_time in the current
    epoch (>1_700_000_000), so the resulting 1-second window in 1970 is always empty.
    """
    resp = _get_runs(flask_client, fake_test.id, before=2.0, after=1.0)

    assert resp.status_code == 200
    assert resp.json["response"] == []


# ---------------------------------------------------------------------------
# Tests – `full` parameter
# ---------------------------------------------------------------------------

@pytest.mark.docker_required
def test_get_runs_without_full_extra_fields_are_empty(flask_client: FlaskClient, run_id_with_package: str, fake_test: ArgusTest) -> None:
    """Without `full`, CQLEngine returns an empty list for unfetched list columns.

    We submit a package so the column has real data on disk.  The meta-only
    response must still return an empty list for `packages` because the column
    is excluded via `.only(limited_fields)`.  This distinguishes the two modes.
    """
    resp = _get_runs(flask_client, fake_test.id)

    assert resp.status_code == 200
    runs = resp.json["response"]
    target_run = next((r for r in runs if r["id"] == run_id_with_package), None)
    assert target_run is not None, f"Run {run_id_with_package} not found in response"
    assert target_run[FULL_ONLY_FIELD] == [], (
        f"'{FULL_ONLY_FIELD}' should be an empty list (unfetched) in limited-mode response, "
        f"got {target_run[FULL_ONLY_FIELD]!r}"
    )


@pytest.mark.docker_required
def test_get_runs_with_full_returns_extra_fields(flask_client: FlaskClient, run_id_with_package: str, fake_test: ArgusTest) -> None:
    """With full=1, full-model-only fields such as 'packages' must be populated.

    We submit a package before fetching so the column has real data.  The full
    response must return a non-empty list, distinguishing it from meta-only mode
    which returns an empty list for unfetched list columns.
    """
    resp = _get_runs(flask_client, fake_test.id, full=1)

    assert resp.status_code == 200
    runs = resp.json["response"]
    target_run = next((r for r in runs if r["id"] == run_id_with_package), None)
    assert target_run is not None, f"Run {run_id_with_package} not found in response"
    assert len(target_run[FULL_ONLY_FIELD]) > 0, (
        f"'{FULL_ONLY_FIELD}' must be a non-empty list when full=1 and a package was submitted"
    )


@pytest.mark.docker_required
def test_get_runs_full_response_is_superset_of_meta(flask_client: FlaskClient, run_id: str, fake_test: ArgusTest) -> None:
    """full=1 response must still contain all the standard meta fields."""
    resp = _get_runs(flask_client, fake_test.id, full=1)

    assert resp.status_code == 200
    runs = resp.json["response"]
    assert len(runs) > 0

    for run in runs:
        for field in META_FIELDS:
            assert field in run, (
                f"Meta field '{field}' missing from full-mode run {run.get('id')}"
            )


# ---------------------------------------------------------------------------
# Tests – `additionalRuns[]` parameter
# ---------------------------------------------------------------------------

@pytest.mark.docker_required
def test_additional_runs_bypass_before_filter(flask_client: FlaskClient, run_id: str, fake_test: ArgusTest) -> None:
    """A run ID in additionalRuns[] must appear even when `before` would exclude it.

    Strategy: before=1.0 (Unix epoch) makes the regular filter return nothing.
    Passing run_id in additionalRuns[] must force it to appear in the response.
    """
    resp = _get_runs(
        flask_client,
        fake_test.id,
        before=1.0,
        **{"additionalRuns[]": run_id},
    )

    assert resp.status_code == 200
    returned_ids = [r["id"] for r in resp.json["response"]]
    assert run_id in returned_ids, (
        "additionalRuns[] run must appear even when `before` filter excludes all runs"
    )


@pytest.mark.docker_required
def test_additional_runs_bypass_after_filter(flask_client: FlaskClient, run_id: str, fake_test: ArgusTest) -> None:
    """A run ID in additionalRuns[] must appear even when `after` would exclude it."""
    far_future = time.time() + 10 * 365 * 24 * 3600

    resp = _get_runs(
        flask_client,
        fake_test.id,
        after=far_future,
        **{"additionalRuns[]": run_id},
    )

    assert resp.status_code == 200
    returned_ids = [r["id"] for r in resp.json["response"]]
    assert run_id in returned_ids, (
        "additionalRuns[] run must appear even when `after` filter excludes all runs"
    )


@pytest.mark.docker_required
def test_additional_runs_multiple_ids(flask_client: FlaskClient, run_ids: list[str], fake_test: ArgusTest) -> None:
    """Multiple run IDs can be passed in additionalRuns[].

    We use before=1.0 so the regular filter is empty, then force all three
    previously-submitted runs through additionalRuns[].
    """
    resp = flask_client.get(
        f"{API_PREFIX}/test/{fake_test.id}/runs",
        query_string=[("before", "1.0")] + [("additionalRuns[]", rid) for rid in run_ids],
    )

    assert resp.status_code == 200
    returned_ids = {r["id"] for r in resp.json["response"]}
    for rid in run_ids:
        assert rid in returned_ids, f"additionalRun {rid} missing from response"


@pytest.mark.docker_required
def test_additional_runs_not_duplicated_when_already_in_results(flask_client: FlaskClient, run_id: str, fake_test: ArgusTest) -> None:
    """If the run is already in the regular result set, passing it in additionalRuns[]
    must not result in it appearing twice.
    """
    resp = _get_runs(
        flask_client,
        fake_test.id,
        **{"additionalRuns[]": run_id},
    )

    assert resp.status_code == 200
    returned_ids = [r["id"] for r in resp.json["response"]]
    assert returned_ids.count(run_id) == 1, (
        "A run must not appear more than once even when it is in both the filter result and additionalRuns[]"
    )


# ---------------------------------------------------------------------------
# Tests – edge cases
# ---------------------------------------------------------------------------

@pytest.mark.docker_required
def test_get_runs_nonexistent_test_returns_error(flask_client: FlaskClient) -> None:
    """Requesting runs for an unknown test_id must not succeed silently."""
    fake_id = str(uuid4())
    resp = flask_client.get(f"{API_PREFIX}/test/{fake_id}/runs")

    # The service raises an ORM DoesNotExist → serialised as an error response
    assert resp.json["status"] != "ok"


@pytest.mark.docker_required
def test_get_runs_response_is_sorted_by_build_number_desc(flask_client: FlaskClient, fake_test: ArgusTest) -> None:
    """Runs must be returned in descending order of build_number (newest first).

    We create runs with distinct, parseable build numbers (1, 2, 3) so the
    service can sort them deterministically.
    """
    build_numbers_in = [10, 20, 30]
    for bn in build_numbers_in:
        _submit_run(flask_client, fake_test, build_number=bn)

    resp = _get_runs(flask_client, fake_test.id, limit=50)

    assert resp.status_code == 200
    runs = resp.json["response"]
    build_numbers_out = [r["build_number"] for r in runs if r["build_number"] in build_numbers_in]
    assert build_numbers_out == sorted(build_numbers_out, reverse=True), (
        "Runs must be sorted by build_number descending"
    )
