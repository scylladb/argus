import uuid
from types import SimpleNamespace
from unittest.mock import patch

from argus.backend.service.testrun import TestRunService


def _run(test_id: uuid.UUID | None) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), test_id=test_id,
                           build_id="scylla-staging/user/unregistered-job")


def test_run_view_redirects_when_run_has_no_test(api_client):
    run = _run(test_id=None)
    with patch.object(TestRunService, "get_run", return_value=run):
        res = api_client.get(f"/tests/scylla-cluster-tests/{run.id}", follow_redirects=False)
        assert res.status_code == 302
        assert "/error" in res.headers["Location"]

        page = api_client.get(res.headers["Location"])

    assert page.status_code == 200
    assert run.build_id in page.text


def test_run_view_renders_when_run_has_test(api_client):
    run = _run(test_id=uuid.uuid4())
    with patch.object(TestRunService, "get_run", return_value=run):
        res = api_client.get(f"/tests/scylla-cluster-tests/{run.id}", follow_redirects=False)

    assert res.status_code == 200
    assert str(run.test_id) in res.text
