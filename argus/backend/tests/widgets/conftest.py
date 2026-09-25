"""Shared widget seeding fixtures.

These fixtures construct the minimal database state required to exercise the
"full data shape" branches of the view-widget controllers (rows 15-19 in the
controller coverage matrix). Each fixture cleans up its own rows in teardown.

All fixtures are function-scoped so tests don't accidentally share view ids
or run ids.
"""
from __future__ import annotations

import json
import time as _time
import uuid
from datetime import UTC, datetime
from typing import NamedTuple

import pytest

from coodie.exceptions import DocumentNotFound

from argus.backend.models.github_issue import GithubIssue, IssueLink
from argus.backend.models.result import (
    ArgusGenericResultData,
    ArgusGenericResultMetadata,
    ArgusGraphView,
)
from argus.backend.models.pytest import PytestResultTable, PytestUserField
from argus.backend.models.web import ArgusTest, ArgusUserView
from argus.backend.plugins.sct.testrun import SCTTestRun


class SctRun(NamedTuple):
    run_id: str
    test_id: str
    package_name: str
    package_version: str
    package_date: str
    package_revision_id: str
    test_method: str


class SeededView(NamedTuple):
    view_id: str
    test_id: str
    run_id: str


@pytest.fixture
async def sct_run(api_client, fake_test) -> SctRun:
    """Submit a single SCT run + scylla-server package version.

    Mirrors the canonical seeding sequence used by ``tests/sct_api/test_sct_api.py``:
    POST to the SCT plugin's submit endpoint, then attach a package via the
    ``/packages/submit`` route. Returns the run id, test id and package version
    so tests can assert against them.
    """
    run_id = str(uuid.uuid4())
    submit_payload = {
        "run_id": run_id,
        "job_name": fake_test.build_system_id,
        "job_url": "http://example.com/job/42",
        "started_by": "widget_test_user",
        "commit_id": "deadbeef",
        "origin_url": "http://example.com/repo.git",
        "branch_name": "main",
        "sct_config": {"cluster_backend": "aws", "test_method": "widget_seed_module.WidgetSeedTest.test_widget"},
        "schema_version": "v8",
    }
    resp = api_client.post(
        "/api/v1/client/testrun/scylla-cluster-tests/submit",
        json=submit_payload,
    )
    assert resp.status_code == 200, resp.text

    # The run is cleaned up from here on, even if a subsequent seeding step
    # (e.g. the packages POST) fails.
    try:
        package_payload = {
            "packages": [
                {
                    "name": "scylla-server",
                    "version": "6.0.0",
                    "date": "20260101",
                    "revision_id": "deadbeef",
                    "build_id": "build-1",
                }
            ],
            "schema_version": "v8",
        }
        resp = api_client.post(
            f"/api/v1/client/sct/{run_id}/packages/submit",
            json=package_payload,
        )
        assert resp.status_code == 200, resp.text

        yield SctRun(
            run_id=run_id,
            test_id=str(fake_test.id),
            package_name="scylla-server",
            package_version="6.0.0",
            package_date="20260101",
            package_revision_id="deadbeef",
            test_method="widget_seed_module.WidgetSeedTest.test_widget",
        )
    finally:
        try:
            await (await SCTTestRun.get(id=uuid.UUID(str(run_id)))).delete()
        except DocumentNotFound:
            pass


@pytest.fixture
async def seeded_view_with_run(api_client, sct_run: SctRun) -> SeededView:
    """Create an ``ArgusUserView`` that points at the seeded SCT run's test.

    Uses the public ``/api/v1/views/create`` endpoint so the view is built the
    same way the UI builds it.
    """
    name = f"widget_view_{uuid.uuid4().hex[:8]}"
    resp = api_client.post(
        "/api/v1/views/create",
        json={"name": name, "items": [f"test:{sct_run.test_id}"], "settings": "{}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok", body
    view_id = body["response"]["id"]

    yield SeededView(view_id=view_id, test_id=sct_run.test_id, run_id=sct_run.run_id)

    try:
        await (await ArgusUserView.get(id=uuid.UUID(view_id))).delete()
    except DocumentNotFound:
        pass


@pytest.fixture
def sct_run_with_nemesis(api_client, sct_run: SctRun) -> SctRun:
    """Extend ``sct_run`` with a finalized ``SCTNemesis`` row.

    Uses the canonical submit -> finalize sequence; nemesis name is one that
    ``argus.backend.util.nemesis_map.get_nemesis_name`` knows how to render.
    """
    submit_payload = {
        "nemesis": {
            "name": "NoCorruptRepairMonkey",
            "class_name": "NemesisNoCorruptRepairMonkey",
            "start_time": int(_time.time()),
            "node_name": "node-1",
            "node_ip": "10.0.0.1",
            "node_shards": 8,
            "description": "widget seeding nemesis",
        },
        "schema_version": "v8",
    }
    resp = api_client.post(
        f"/api/v1/client/sct/{sct_run.run_id}/nemesis/submit",
        json=submit_payload,
    )
    assert resp.status_code == 200, resp.text

    finalize_payload = {
        "nemesis": {
            "name": "NoCorruptRepairMonkey",
            "start_time": submit_payload["nemesis"]["start_time"],
            "status": "succeeded",
            "message": "done",
        }
    }
    resp = api_client.post(
        f"/api/v1/client/sct/{sct_run.run_id}/nemesis/finalize",
        json=finalize_payload,
    )
    assert resp.status_code == 200, resp.text

    yield sct_run


class SeededGenericResults(NamedTuple):
    test_id: str
    run_id: str
    table_name: str
    column_name: str
    row_name: str


@pytest.fixture
async def generic_results_for_run(sct_run: SctRun) -> SeededGenericResults:
    """Insert one ``ArgusGenericResultMetadata`` + one cell of data.

    The column name is ``"P99 read"`` so it lands in the
    ``argus_service.summary`` controller's ``key_metrics`` filter.
    """
    table_name = "Latency Table"
    column_name = "P99 read"
    row_name = "row1"
    test_uuid = uuid.UUID(sct_run.test_id)
    run_uuid = uuid.UUID(sct_run.run_id)

    metadata = ArgusGenericResultMetadata(
        test_id=test_uuid,
        name=table_name,
        description="widget seed metadata",
        columns_meta=[
            {"name": column_name, "unit": "ms", "type": "FLOAT", "higher_is_better": False, "visible": True}
        ],
        rows_meta=[row_name],
        sut_package_name="scylla-server",
    )
    await metadata.save()

    cell = ArgusGenericResultData(
        test_id=test_uuid,
        name=table_name,
        run_id=run_uuid,
        column=column_name,
        row=row_name,
        sut_timestamp=datetime.now(tz=UTC),
        value=12.5,
        value_text="12.5",
        status="PASS",
    )
    await cell.save()

    yield SeededGenericResults(
        test_id=sct_run.test_id,
        run_id=sct_run.run_id,
        table_name=table_name,
        column_name=column_name,
        row_name=row_name,
    )

    try:
        await cell.delete()
    except Exception:
        pass
    try:
        await metadata.delete()
    except Exception:
        pass


@pytest.fixture
async def graph_view_for_test(generic_results_for_run: SeededGenericResults):
    """Insert an ``ArgusGraphView`` whose ``graphs`` map references the seeded cell.

    The widget controller filters by exact title ``"<table_name> - <column_name>"``,
    so the key here must match what ``generic_results_for_run`` produced.
    """
    test_uuid = uuid.UUID(generic_results_for_run.test_id)
    graph_view = ArgusGraphView(
        test_id=test_uuid,
        id=uuid.uuid4(),
        name="widget seed view",
        description="widget seed graph view",
        graphs={
            f"{generic_results_for_run.table_name} - {generic_results_for_run.column_name}": "{}"
        },
    )
    await graph_view.save()

    yield graph_view

    try:
        await graph_view.delete()
    except Exception:
        pass


@pytest.fixture
async def seeded_pytest_row(client_service, fake_test):
    """Insert a single ``PytestResultTable`` + ``PytestUserField`` via the client service."""
    name = f"pytest.widget_{uuid.uuid4().hex[:8]}"
    timestamp = _time.time()
    payload = {
        "run_id": uuid.uuid4(),
        "name": name,
        "status": "passed",
        "test_type": "unit",
        "timestamp": timestamp,
        "session_timestamp": timestamp,
        "markers": ["widget_seed"],
        "user_fields": {"SCYLLA_MODE": "release"},
        "message": "",
        "duration": 1.5,
    }
    inserted = await client_service.submit_pytest_result(payload)

    yield {
        "name": inserted["name"],
        "id": inserted["id"],
        "iso_id": inserted["id"].isoformat(),
        "status": "passed",
    }

    # Best-effort cleanup; pytest tables are partition-keyed by name so
    # a delete-by-PK is safe.
    try:
        await PytestResultTable.find(name=inserted["name"]).delete()
    except Exception:
        pass
    try:
        await PytestUserField.find(name=inserted["name"]).delete()
    except Exception:
        pass


@pytest.fixture
async def linked_github_issue(sct_run: SctRun):
    """Insert a ``GithubIssue`` and link it to the seeded SCT run."""
    issue = GithubIssue.model_construct()
    issue.user_id = uuid.uuid4()
    issue.type = "issues"
    issue.owner = "scylladb"
    issue.repo = "scylladb"
    issue.number = 12345
    issue.state = "open"
    issue.title = "widget seed issue"
    issue.url = f"https://github.com/scylladb/scylladb/issues/12345?seed={uuid.uuid4().hex[:6]}"
    await issue.save()

    test = await ArgusTest.get(id=uuid.UUID(sct_run.test_id))
    link = IssueLink(
        run_id=uuid.UUID(sct_run.run_id),
        issue_id=issue.id,
        test_id=test.id,
        release_id=test.release_id,
        group_id=test.group_id,
        type="github",
    )
    await link.save()

    yield {"issue": issue, "link": link, "run_id": sct_run.run_id, "test_id": sct_run.test_id}

    try:
        await link.delete()
    except Exception:
        pass
    try:
        await issue.delete()
    except Exception:
        pass
