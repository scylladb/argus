import json
from datetime import UTC, datetime
from uuid import uuid4

from argus.backend.service.stats import summarize_release_stats
from argus.backend.util.encoders import ArgusJSONProvider
from argus.common import enums


def _status_map(**counts: int) -> dict:
    return {status: counts.get(status.value, 0) for status in enums.TestStatus}


def _fresh_stats(group_id: str, ran_id: str, never_ran_id: str) -> dict:
    ran = {
        "test": {"id": ran_id},
        "status": enums.TestStatus.FAILED,
        "investigation_status": enums.TestInvestigationStatus.NOT_INVESTIGATED,
        "last_runs": [{"id": uuid4(), "status": enums.TestStatus.FAILED}],
        "start_time": datetime(2026, 10, 1, 10, 0, tzinfo=UTC),
        "hasBugReport": False,
    }
    never_ran = {
        "test": {"id": never_ran_id},
        "status": enums.TestStatus.NOT_RUN,
        "investigation_status": enums.TestInvestigationStatus.NOT_INVESTIGATED,
        "last_runs": [],
        "start_time": datetime.fromtimestamp(0),
        "hasBugReport": False,
    }
    return {
        "release": {"name": "scylla-master"},
        "groups": {
            group_id: {
                "group": {"id": group_id},
                "total": 2,
                **_status_map(failed=1, not_run=1),
                "tests": {ran_id: ran, never_ran_id: never_ran},
                enums.TestInvestigationStatus.NOT_INVESTIGATED: {
                    enums.TestStatus.FAILED: 1,
                    enums.TestStatus.NOT_RUN: 1,
                },
            },
        },
        "total": 2,
        **_status_map(failed=1, not_run=1),
        "not_investigated": {status.value: 0 for status in enums.TestStatus} | {"failed": 1, "not_run": 1},
        "investigated": {status.value: 0 for status in enums.TestStatus},
    }


def _as_snapshot(stats: dict) -> dict:
    return json.loads(json.dumps(stats, default=ArgusJSONProvider.default))


def test_snapshot_and_fresh_stats_give_the_same_summary():
    group_id, ran_id, never_ran_id = str(uuid4()), str(uuid4()), str(uuid4())
    fresh = _fresh_stats(group_id, ran_id, never_ran_id)

    summary = summarize_release_stats(fresh)

    assert summary == summarize_release_stats(_as_snapshot(fresh))
    assert summary == {
        "total": 2, "created": 0, "running": 0, "failed": 1, "test_error": 0, "error": 0, "passed": 0,
        "aborted": 0, "not_planned": 0, "not_run": 1, "to_investigate": 1,
        "groups": {
            group_id: {
                "total": 2, "created": 0, "running": 0, "failed": 1, "test_error": 0, "error": 0, "passed": 0,
                "aborted": 0, "not_planned": 0, "not_run": 1, "to_investigate": 1,
                "tests": {
                    ran_id: {"status": "failed", "investigation_status": "not_investigated",
                             "start_time": "2026-10-01T10:00:00.000Z"},
                    never_ran_id: {"status": "not_run", "investigation_status": "not_investigated",
                                   "start_time": None},
                },
            },
        },
    }


def test_test_without_runs_has_no_start_time():
    group_id, ran_id, never_ran_id = str(uuid4()), str(uuid4()), str(uuid4())

    summary = summarize_release_stats(_as_snapshot(_fresh_stats(group_id, ran_id, never_ran_id)))

    assert summary["groups"][group_id]["tests"][never_ran_id]["start_time"] is None


def test_group_without_uninvestigated_tests_has_nothing_to_investigate():
    group_id, ran_id, never_ran_id = str(uuid4()), str(uuid4()), str(uuid4())
    stats = _fresh_stats(group_id, ran_id, never_ran_id)
    del stats["groups"][group_id][enums.TestInvestigationStatus.NOT_INVESTIGATED]

    summary = summarize_release_stats(stats)

    assert summary["groups"][group_id]["to_investigate"] == 0


def test_dormant_release_passes_through():
    assert summarize_release_stats({"dormant": True}) == {"dormant": True}
