"""Unit tests for the Prometheus label callbacks.

No database and no app factory: the callbacks read only ``flask.request``, so a
bare test request context is enough.
"""

import pytest
from flask import Flask

from argus.backend import metrics_labels

app = Flask(__name__)


def _labels(**headers):
    with app.test_request_context("/api/v1/client/ssh/tunnel", headers=headers):
        return {
            "ssh_tunnel": metrics_labels.ssh_tunnel(),
            "build_id": metrics_labels.build_id(),
            "job_name": metrics_labels.job_name(),
        }


def test_tunneled_ci_request_is_attributed_to_its_job():
    labels = _labels(
        **{
            "X-SSH-Tunnel-Origin": "argus-tunnel-1.example.com",
            "X-Argus-Build-Id": "scylla-master/byo/byo_build_tests_dtest#42",
        }
    )

    assert labels == {
        "ssh_tunnel": "yes",
        "build_id": "scylla-master/byo/byo_build_tests_dtest#42",
        "job_name": "scylla-master/byo/byo_build_tests_dtest",
    }


def test_direct_ci_request_is_attributed_to_its_job():
    """The case the metrics could not express before: a job skipping the tunnel."""
    labels = _labels(**{"X-Argus-Build-Id": "scylla-master/longevity#7"})

    assert labels == {
        "ssh_tunnel": "no",
        "build_id": "scylla-master/longevity#7",
        "job_name": "scylla-master/longevity",
    }


def test_request_without_attribution_is_unknown():
    assert _labels() == {"ssh_tunnel": "no", "build_id": "unknown", "job_name": "unknown"}


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
