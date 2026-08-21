"""Unit tests for the Prometheus label helpers.

No database and no app factory: the helpers are pure functions over a header
mapping shared by the Flask hook and the FastAPI middleware.
"""

import pytest

from argus.backend import metrics_labels


def _labels(**headers):
    return {
        "ssh_tunnel": metrics_labels.ssh_tunnel(headers),
        "build_id": metrics_labels.build_id(headers),
        "job_name": metrics_labels.job_name(headers),
        "branch": metrics_labels.branch(headers),
        "client_version": metrics_labels.client_version(headers),
    }


def test_tunneled_ci_request_is_attributed_to_its_job():
    labels = _labels(
        **{
            "X-SSH-Tunnel-Origin": "argus-tunnel-1.example.com",
            "X-Argus-Build-Id": "scylla-master/byo/byo_build_tests_dtest#42",
            "X-Argus-Client-Version": "0.16.1",
        }
    )

    assert labels == {
        "ssh_tunnel": "yes",
        "build_id": "scylla-master/byo/byo_build_tests_dtest#42",
        "job_name": "scylla-master/byo/byo_build_tests_dtest",
        "branch": "scylla-master",
        "client_version": "0.16.1",
    }


def test_direct_ci_request_is_attributed_to_its_job():
    """The case the metrics could not express before: a job skipping the tunnel."""
    labels = _labels(
        **{
            "X-Argus-Build-Id": "scylla-2026.1/gating-dtest-release-with-tablets#7",
            "X-Argus-Client-Version": "0.15.7",
        }
    )

    assert labels == {
        "ssh_tunnel": "no",
        "build_id": "scylla-2026.1/gating-dtest-release-with-tablets#7",
        "job_name": "scylla-2026.1/gating-dtest-release-with-tablets",
        "branch": "scylla-2026.1",
        "client_version": "0.15.7",
    }


def test_request_without_attribution_is_unknown():
    assert _labels() == {
        "ssh_tunnel": "no",
        "build_id": "unknown",
        "job_name": "unknown",
        "branch": "unknown",
        "client_version": "unknown",
    }


@pytest.mark.parametrize(
    "build_id, expected_job",
    [
        ("job#42", "job"),
        # Only a trailing build number is stripped; a '#' inside the path stays.
        ("folder/job#with#hash#7", "folder/job#with#hash"),
        # No build number at all (a job started outside Jenkins).
        ("manual-run", "manual-run"),
        # A digit run that is not a build number suffix.
        ("release-2.1", "release-2.1"),
    ],
)
def test_job_name_strips_only_the_build_number(build_id, expected_job):
    assert _labels(**{"X-Argus-Build-Id": build_id})["job_name"] == expected_job


def test_oversized_build_id_cannot_mint_a_series():
    oversized = "x" * (metrics_labels.MAX_BUILD_ID_LEN + 1)

    labels = _labels(**{"X-Argus-Build-Id": oversized})

    assert labels["build_id"] == "unknown"
    assert labels["job_name"] == "unknown"


@pytest.mark.parametrize(
    "user_agent, expected",
    [
        ("argus-client-ssh-tunnel/1.0", "argus-client-tunnel"),
        ("python-requests/2.32.3", "argus-client"),
        ("Go-http-client/2.0", "argus-cli-go"),
        ("Mozilla/5.0 (Macintosh)", "browser"),
        ("curl/8.7.1", "curl"),
        ("something-else", "other"),
        ("", "unknown"),
    ],
)
def test_user_agent_categories(user_agent, expected):
    assert metrics_labels.categorize_user_agent(user_agent) == expected


@pytest.mark.parametrize(
    "build_id, expected_branch",
    [
        ("scylla-master/byo/byo_build_tests_dtest#42", "scylla-master"),
        ("scylla-2026.3/gating-dtest-release-with-tablets#5", "scylla-2026.3"),
        # A job outside any folder is its own release line.
        ("manual-run", "manual-run"),
        ("unknown", "unknown"),
    ],
)
def test_branch_is_the_first_job_path_segment(build_id, expected_branch):
    assert _labels(**{"X-Argus-Build-Id": build_id})["branch"] == expected_branch


def test_branch_rejects_a_segment_that_could_mint_a_series():
    oversized = "x" * 65

    assert _labels(**{"X-Argus-Build-Id": f"{oversized}/job#1"})["branch"] == "unknown"


@pytest.mark.parametrize(
    "version, expected",
    [
        ("0.16.1", "0.16.1"),
        ("0.15.7", "0.15.7"),
        # setuptools-scm builds these off a tag, and CI installs one.
        ("0.16.1.dev3+g1a2b3c4", "0.16.1.dev3+g1a2b3c4"),
        ("0.16.1.dev12+g0abc123.d20260802", "0.16.1.dev12+g0abc123.d20260802"),
        # A client old enough to predate the header sends nothing.
        ("", "unknown"),
        # Anything unbounded is one time series per request.
        ("not a version", "unknown"),
        ("9" * 64, "unknown"),
    ],
)
def test_client_version_accepts_only_a_version(version, expected):
    headers = {"X-Argus-Client-Version": version} if version else {}

    assert _labels(**headers)["client_version"] == expected
