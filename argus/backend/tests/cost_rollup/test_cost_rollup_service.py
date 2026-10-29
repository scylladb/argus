import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from uuid import UUID

import pytest

from argus.backend.models.run_cost_rollup import UNASSIGNED_RELEASE, RunCostReleaseSpan
from argus.backend.plugins.sct.service import SCTService
from argus.backend.plugins.sct.testrun import SCTTestRunSubmissionRequest
from argus.backend.service.cost_rollup_service import CostRollupService
from argus.backend.service.run_cost_service import CostItemRequest, RunCostService
from argus.backend.tests.cost_rollup.helpers import rollup_rows, submitted_run as _submitted_run


@pytest.fixture(scope="session")
def run_cost_service(argus_db) -> RunCostService:
    return RunCostService()


async def _resource(sct_service: SCTService, run_id: UUID, name: str, resource_type: str = "db_node") -> None:
    await sct_service.create_resource(run_id, {
        "name": name,
        "state": "running",
        "resource_type": resource_type,
        "instance_details": {"instance_type": "i3.large", "provider": "aws", "region": "us-east-1",
                             "public_ip": "1.2.3.4", "private_ip": "10.0.0.1"},
    })


async def test_refresh_writes_one_row_keyed_by_month_release_and_run(client_service, run_cost_service,
                                                                     fake_test):
    _, run_id = await _submitted_run(client_service, fake_test)
    await run_cost_service.set_estimated_cost(run_id, 40.0)
    await run_cost_service.submit_cost_items(run_id, [
        CostItemRequest(name="db-node-1", category="db_node", cost=10.0, pricing_tier="spot"),
        CostItemRequest(name="loader-1", category="loader", cost=5.0, pricing_tier="on-demand"),
        CostItemRequest(name="db-node-9", category="db_node", cost=2.5, leaked=True),
    ])

    row = await run_cost_service.refresh_rollup(run_id)

    assert row.month == datetime.now(UTC).strftime("%Y-%m")
    assert row.release_id == fake_test.release_id
    assert row.group_id == fake_test.group_id
    assert row.test_id == fake_test.id
    assert row.plugin_name == "scylla-cluster-tests"
    assert row.build_id == fake_test.build_system_id
    assert row.estimated_cost == pytest.approx(40.0)
    assert row.actual_cost == pytest.approx(17.5)
    assert row.spot_cost == pytest.approx(10.0)
    assert row.on_demand_cost == pytest.approx(5.0)
    assert row.untiered_cost == pytest.approx(2.5)
    assert row.leaked_cost == pytest.approx(2.5)
    assert row.item_count == 3
    assert row.leaked_count == 1
    stored = await rollup_rows(run_id, row.release_id, row.month)
    assert len(stored) == 1
    assert stored[0].actual_cost == pytest.approx(17.5)


async def test_refresh_twice_keeps_a_single_row(client_service, run_cost_service, fake_test):
    _, run_id = await _submitted_run(client_service, fake_test)
    await run_cost_service.submit_cost_items(run_id, [CostItemRequest(name="db-node-1", category="db_node", cost=1.0)])
    first = await run_cost_service.refresh_rollup(run_id)
    await run_cost_service.submit_cost_items(run_id, [CostItemRequest(name="db-node-2", category="db_node", cost=2.0)])

    second = await run_cost_service.refresh_rollup(run_id)

    stored = await rollup_rows(run_id, second.release_id, second.month)
    assert len(stored) == 1
    assert stored[0].actual_cost == pytest.approx(3.0)
    assert stored[0].item_count == 2
    assert first.start_time == second.start_time


async def test_refresh_returns_none_for_an_unknown_run(run_cost_service):
    assert await run_cost_service.refresh_rollup(uuid.uuid4()) is None


async def test_refresh_uses_the_unassigned_sentinel_without_release(client_service, run_cost_service):
    run_id = str(uuid.uuid4())
    await client_service.submit_run("scylla-cluster-tests", asdict(SCTTestRunSubmissionRequest(
        schema_version="1.0.0", run_id=run_id, job_name=f"unregistered-job-{run_id}",
        job_url="http://example.com/job/1", started_by="nobody", commit_id="deadbeef", sct_config=None)))

    row = await run_cost_service.refresh_rollup(UUID(run_id))

    assert row.release_id == UNASSIGNED_RELEASE
    assert row.group_id is None
    assert row.test_id is None
    assert row.coverage == "none"
    assert row.actual_cost is None


async def test_refresh_counts_coverage_from_sct_resources(client_service, sct_service, run_cost_service,
                                                          fake_test):
    _, run_id = await _submitted_run(client_service, fake_test)
    await _resource(sct_service, run_id, "db-node-1")
    await _resource(sct_service, run_id, "loader-1", resource_type="loader")
    await _resource(sct_service, run_id, "sct-runner", resource_type="sct-runner")
    await run_cost_service.submit_cost_items(run_id, [CostItemRequest(name="db-node-1", category="db_node", cost=3.0)])

    partial = await run_cost_service.refresh_rollup(run_id)
    assert partial.resource_count == 2
    assert partial.priced_count == 1
    assert partial.coverage == "partial"

    await run_cost_service.submit_cost_items(run_id, [CostItemRequest(name="loader-1", category="loader", cost=1.0)])
    complete = await run_cost_service.refresh_rollup(run_id)
    assert complete.priced_count == 2
    assert complete.coverage == "complete"


async def test_refresh_reports_no_coverage_for_a_run_without_items(client_service, sct_service, run_cost_service,
                                                                   fake_test):
    _, run_id = await _submitted_run(client_service, fake_test)
    await _resource(sct_service, run_id, "db-node-1")

    row = await run_cost_service.refresh_rollup(run_id)

    assert row.resource_count == 1
    assert row.priced_count == 0
    assert row.coverage == "none"
    assert row.item_count == 0


async def test_refresh_copies_the_backend_and_the_region(client_service, run_cost_service, fake_test):
    _, run_id = await _submitted_run(client_service, fake_test,
                                     sct_config={"cluster_backend": "aws", "region_name": "eu-west-1 us-east-1"})

    row = await run_cost_service.refresh_rollup(run_id)

    assert row.backend == "aws"
    assert row.region == "eu-west-1"
    assert row.spot_terminated is False
    assert row.status == "created"


def test_month_of_treats_a_naive_datetime_as_utc():
    assert CostRollupService.month_of(datetime(2026, 10, 31, 23, 30)) == "2026-10"
    assert CostRollupService.month_of(datetime(2026, 10, 31, 23, 30, tzinfo=UTC)) == "2026-10"


@pytest.mark.parametrize(("resource_count", "priced_count", "item_count", "expected"), [
    (None, 0, 0, "none"),
    (None, 0, 2, "complete"),
    (0, 0, 2, "complete"),
    (3, 0, 0, "none"),
    (3, 0, 2, "partial"),
    (3, 1, 1, "partial"),
    (3, 3, 3, "complete"),
    (2, 3, 4, "complete"),
])
def test_coverage_verdict(resource_count, priced_count, item_count, expected):
    assert CostRollupService.coverage(resource_count, priced_count, item_count) == expected


async def test_refresh_extends_the_release_span(client_service, run_cost_service, fake_test):
    _, first = await _submitted_run(client_service, fake_test)
    _, second = await _submitted_run(client_service, fake_test)

    first_row = await run_cost_service.refresh_rollup(first)
    second_row = await run_cost_service.refresh_rollup(second)

    span = await RunCostReleaseSpan.get(release_id=fake_test.release_id)
    assert CostRollupService.month_of(span.first_start) == first_row.month
    assert span.first_start.replace(tzinfo=UTC) <= first_row.start_time
    assert span.last_start.replace(tzinfo=UTC) >= second_row.start_time
