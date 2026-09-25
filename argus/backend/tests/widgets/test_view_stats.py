import pytest

from argus.backend.tests.widgets.conftest import SeededView


@pytest.mark.docker_required
def test_view_stats_last_runs_carry_linked_issues_and_comments(api_client, seeded_view_with_run: SeededView,
                                                                linked_github_issue):
    resp = api_client.post(
        f"/api/v1/test/{seeded_view_with_run.test_id}/run/{seeded_view_with_run.run_id}/comments/submit",
        json={"message": "stats comment", "reactions": {}, "mentions": []},
    )
    assert resp.json()["status"] == "ok", resp.text

    res = api_client.get(f"/api/v1/views/stats?viewId={seeded_view_with_run.view_id}").json()
    assert res["status"] == "ok", res

    groups = res["response"]["groups"]
    test_stats = next(group["tests"][seeded_view_with_run.test_id]
                      for group in groups.values() if seeded_view_with_run.test_id in group["tests"])
    last_run = next(run for run in test_stats["last_runs"] if run["id"] == seeded_view_with_run.run_id)
    assert [issue["url"] for issue in last_run["issues"]] == [linked_github_issue["issue"].url]
    assert [issue["subtype"] for issue in last_run["issues"]] == ["github"]
    assert [comment["message"] for comment in last_run["comments"]] == ["stats comment"]
    assert test_stats["hasBugReport"] is True
    assert test_stats["hasComments"] is True
