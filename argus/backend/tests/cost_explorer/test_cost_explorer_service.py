import uuid
from datetime import UTC, datetime, timedelta

import pytest

from argus.backend.error_handlers import DataValidationError
from argus.backend.models.run_cost_rollup import UNASSIGNED_RELEASE
from argus.backend.service.cost_explorer_service import (
    TOP_RUNS,
    CostExplorerService,
    CostQuery,
    CostScope,
)
from argus.backend.tests.cost_explorer.helpers import END, START, create_view, seed, seed_span


@pytest.fixture(scope="session")
def explorer(argus_db) -> CostExplorerService:
    return CostExplorerService()


@pytest.fixture
def plugin() -> str:
    return f"plugin-{uuid.uuid4()}"


def query(plugin: str, start: datetime = START, end: datetime = END, **kwargs) -> CostQuery:
    return CostQuery(start=start, end=end, plugins=frozenset([plugin]), **kwargs)


def test_months_between_spans_a_year_boundary():
    months = CostExplorerService.months_between(datetime(2026, 11, 20, tzinfo=UTC), datetime(2027, 2, 1, tzinfo=UTC))
    assert months == ["2026-11", "2026-12", "2027-01"]


def test_bucket_keys_per_granularity():
    moment = datetime(2026, 10, 14, 15, 0, tzinfo=UTC)
    assert CostExplorerService.bucket_key(moment, "day") == "2026-10-14"
    assert CostExplorerService.bucket_key(moment, "week") == "2026-10-12"
    assert CostExplorerService.bucket_key(moment, "month") == "2026-10-01"
    assert CostExplorerService.bucket_keys(START, END, "week")[:2] == ["2026-10-19", "2026-10-26"]
    assert CostExplorerService.bucket_keys(START, END, "month") == ["2026-10-01", "2026-11-01"]
    assert len(CostExplorerService.bucket_keys(START, END, "day")) == 30


async def test_spend_sums_priced_runs_and_counts_the_rest(explorer, plugin):
    release_id = uuid.uuid4()
    await seed(plugin, START + timedelta(days=1), release_id, actual_cost=12.0)
    await seed(plugin, START + timedelta(days=2), release_id, actual_cost=8.0, status="test_error")
    await seed(plugin, START + timedelta(days=4), release_id, actual_cost=4.0, status="failed")
    await seed(plugin, START + timedelta(days=3), release_id, actual_cost=None)

    result = await explorer.explore(query(plugin, release_ids=frozenset([release_id])))

    assert result["tiles"]["spend"] == pytest.approx(24.0)
    assert result["tiles"]["errored_spend"] == pytest.approx(8.0)
    assert result["tiles"]["runs"] == 4
    assert result["tiles"]["priced_runs"] == 3
    assert result["tiles"]["weekly_run_rate"] == pytest.approx(24.0 / (30 / 7))
    assert result["coverage"] == {"complete": 3, "partial": 0, "none": 1}


async def test_previous_window_feeds_only_the_trend(explorer, plugin):
    release_id = uuid.uuid4()
    await seed(plugin, START + timedelta(days=5), release_id, actual_cost=5.0)
    await seed(plugin, START - timedelta(days=5), release_id, actual_cost=50.0)

    result = await explorer.explore(query(plugin, release_ids=frozenset([release_id])))

    assert result["tiles"]["spend"] == pytest.approx(5.0)
    assert result["tiles"]["previous_spend"] == pytest.approx(50.0)
    assert result["tiles"]["runs"] == 1


async def test_release_filter_reads_only_that_release(explorer, plugin):
    mine, other = uuid.uuid4(), uuid.uuid4()
    await seed(plugin, START + timedelta(days=1), mine, actual_cost=3.0)
    await seed(plugin, START + timedelta(days=1), other, actual_cost=7.0)

    filtered = await explorer.explore(query(plugin, release_ids=frozenset([mine])))
    everything = await explorer.explore(query(plugin))

    assert filtered["tiles"]["spend"] == pytest.approx(3.0)
    assert [release["id"] for release in filtered["releases"]] == [mine]
    assert everything["tiles"]["spend"] == pytest.approx(10.0)
    assert [release["id"] for release in everything["releases"]] == [other, mine]


async def test_tier_filter_uses_the_tier_sums(explorer, plugin):
    release_id = uuid.uuid4()
    await seed(plugin, START + timedelta(days=1), release_id, actual_cost=10.0, spot_cost=6.0, on_demand_cost=4.0,
               spot_count=2, on_demand_count=1)

    spot = await explorer.explore(query(plugin, release_ids=frozenset([release_id]), tiers=frozenset(["spot"])))
    on_demand = await explorer.explore(query(plugin, release_ids=frozenset([release_id]), tiers=frozenset(["on-demand"])))

    assert spot["tiles"]["spend"] == pytest.approx(6.0)
    assert on_demand["tiles"]["spend"] == pytest.approx(4.0)
    assert spot["tiers"] == {"spot": {"spend": 6.0, "items": 2}, "on_demand": {"spend": 4.0, "items": 1},
                             "untiered": {"spend": 0.0, "items": 0}}
    both = await explorer.explore(query(plugin, release_ids=frozenset([release_id]), tiers=frozenset(["spot", "on-demand"])))
    assert both["tiles"]["spend"] == pytest.approx(10.0)
    assert both["window"]["tiers"] == ["on-demand", "spot"]


async def test_series_stacks_by_backend_per_bucket(explorer, plugin):
    release_id = uuid.uuid4()
    await seed(plugin, datetime(2026, 10, 27, tzinfo=UTC), release_id, actual_cost=1.0, backend="aws")
    await seed(plugin, datetime(2026, 10, 28, tzinfo=UTC), release_id, actual_cost=2.0, backend="aws")
    await seed(plugin, datetime(2026, 11, 3, tzinfo=UTC), release_id, actual_cost=4.0, backend=None)

    result = await explorer.explore(query(plugin, release_ids=frozenset([release_id]), granularity="week"))

    buckets = result["series"]["buckets"]
    assert buckets[1] == "2026-10-26"
    assert result["series"]["backends"]["aws"][1] == pytest.approx(3.0)
    assert result["series"]["backends"]["unknown"][2] == pytest.approx(4.0)
    assert all(len(series) == len(buckets) for series in result["series"]["backends"].values())


async def test_breakdown_resolves_names_and_cost_per_run(explorer, plugin, release, group, fake_test):
    await seed(plugin, START + timedelta(days=1), release.id, actual_cost=10.0, group_id=group.id, test_id=fake_test.id)
    await seed(plugin, START + timedelta(days=2), release.id, actual_cost=20.0, group_id=group.id, test_id=fake_test.id)
    await seed(plugin, START + timedelta(days=3), release.id, actual_cost=None, group_id=group.id, test_id=fake_test.id)

    by_group = await explorer.explore(query(plugin, release_ids=frozenset([release.id])))
    by_test = await explorer.explore(query(plugin, release_ids=frozenset([release.id]), breakdown="test"))

    (release_entry,) = by_group["releases"]
    assert release_entry["name"] == release.pretty_name
    (row,) = release_entry["rows"]
    assert row["name"] == group.pretty_name
    assert row["runs"] == 3
    assert row["priced_runs"] == 2
    assert row["cost_per_run"] == pytest.approx(15.0)
    (test_row,) = by_test["releases"][0]["rows"]
    assert test_row["id"] == fake_test.id
    assert test_row["name"] == fake_test.pretty_name
    assert by_group["top_runs"][0]["test"] == fake_test.pretty_name


async def test_unassigned_release_and_group_are_named(explorer, plugin):
    await seed(plugin, START + timedelta(days=1), UNASSIGNED_RELEASE, actual_cost=2.0, group_id=None)

    result = await explorer.explore(query(plugin, release_ids=frozenset([UNASSIGNED_RELEASE])))

    assert result["releases"][0]["name"] == "Unassigned"
    assert result["releases"][0]["rows"][0]["name"] == "Unassigned"


async def test_top_runs_are_sorted_by_spend_and_limited(explorer, plugin):
    release_id = uuid.uuid4()
    for index in range(TOP_RUNS + 3):
        await seed(plugin, START + timedelta(hours=index), release_id, actual_cost=float(index))
    await seed(plugin, START + timedelta(days=2), release_id, actual_cost=None)

    result = await explorer.explore(query(plugin, release_ids=frozenset([release_id])))

    spends = [run["spend"] for run in result["top_runs"]]
    assert len(spends) == TOP_RUNS
    assert spends == sorted(spends, reverse=True)
    assert spends[0] == pytest.approx(TOP_RUNS + 2)


async def test_spot_terminations_count_rate_and_location(explorer, plugin):
    release_id = uuid.uuid4()
    await seed(plugin, START + timedelta(days=1), release_id, actual_cost=5.0, spot_cost=5.0, spot_count=1,
               spot_terminated=True, backend="aws", region="eu-west-1")
    await seed(plugin, START + timedelta(days=2), release_id, actual_cost=6.0, spot_cost=6.0, spot_count=1,
               spot_terminated=True, backend="aws", region="eu-west-1")
    await seed(plugin, START + timedelta(days=3), release_id, actual_cost=7.0, spot_cost=7.0, spot_count=1)
    await seed(plugin, START + timedelta(days=4), release_id, actual_cost=8.0, spot_cost=8.0, spot_count=1)
    await seed(plugin, START + timedelta(days=5), release_id, actual_cost=9.0)

    result = await explorer.explore(query(plugin, release_ids=frozenset([release_id])))

    assert result["spot_terminations"]["count"] == 2
    assert result["spot_terminations"]["spot_runs"] == 4
    assert result["spot_terminations"]["rate"] == pytest.approx(0.5)
    assert result["spot_terminations"]["spend"] == pytest.approx(11.0)
    assert result["spot_terminations"]["by_location"] == [
        {"backend": "aws", "region": "eu-west-1", "count": 2, "spend": 11.0},
    ]


async def test_span_covers_the_selected_releases(explorer, plugin):
    mine, other = uuid.uuid4(), uuid.uuid4()
    await seed_span(mine, datetime(2025, 3, 1, tzinfo=UTC), datetime(2025, 6, 1, tzinfo=UTC))
    await seed_span(other, datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 2, 1, tzinfo=UTC))

    one = await explorer.explore(query(plugin, release_ids=frozenset([mine])))
    both = await explorer.explore(query(plugin, release_ids=frozenset([mine, other])))
    none = await explorer.explore(query(plugin))

    assert one["span"] == {"from": datetime(2025, 3, 1, tzinfo=UTC), "to": datetime(2025, 6, 1, tzinfo=UTC)}
    assert both["span"] == {"from": datetime(2024, 1, 1, tzinfo=UTC), "to": datetime(2025, 6, 1, tzinfo=UTC)}
    assert none["span"] is None
    assert (await explorer.explore(query(plugin, release_ids=frozenset([uuid.uuid4()]))))["span"] is None


async def test_status_filter_keeps_the_listed_statuses(explorer, plugin):
    release_id = uuid.uuid4()
    await seed(plugin, START + timedelta(days=1), release_id, actual_cost=1.0, status="passed")
    await seed(plugin, START + timedelta(days=2), release_id, actual_cost=2.0, status="failed")
    await seed(plugin, START + timedelta(days=3), release_id, actual_cost=4.0, status="aborted")

    result = await explorer.explore(query(plugin, release_ids=frozenset([release_id]),
                                          statuses=frozenset(["failed", "aborted"])))

    assert result["tiles"]["spend"] == pytest.approx(6.0)
    assert result["tiles"]["runs"] == 2


async def test_leaked_spend_and_backend_filter(explorer, plugin):
    release_id = uuid.uuid4()
    await seed(plugin, START + timedelta(days=1), release_id, actual_cost=5.0, leaked_cost=1.5, leaked_count=1,
               backend="aws")
    await seed(plugin, START + timedelta(days=2), release_id, actual_cost=4.0, backend="gce")

    result = await explorer.explore(query(plugin, release_ids=frozenset([release_id]), backends=frozenset(["aws"])))

    assert result["tiles"]["spend"] == pytest.approx(5.0)
    assert result["tiles"]["leaked_spend"] == pytest.approx(1.5)
    assert result["tiles"]["leaked_count"] == 1


async def test_rejects_a_bad_window_or_option(explorer, plugin):
    with pytest.raises(DataValidationError):
        await explorer.explore(query(plugin, start=END, end=START))
    with pytest.raises(DataValidationError):
        await explorer.explore(query(plugin, start=START, end=START + timedelta(days=400)))
    with pytest.raises(DataValidationError):
        await explorer.explore(query(plugin, granularity="hour"))
    with pytest.raises(DataValidationError):
        await explorer.explore(query(plugin, tiers=frozenset(["free"])))


async def test_query_for_view_matches_any_of_the_view_ids(explorer, plugin, api_client):
    release_in_view, release_out, group_in_view, test_in_view = (uuid.uuid4() for _ in range(4))
    view_id = uuid.UUID(create_view(api_client, [f"release:{release_in_view}", f"group:{group_in_view}",
                                                 f"test:{test_in_view}"]))
    await seed(plugin, START + timedelta(days=1), release_in_view, actual_cost=1.0)
    await seed(plugin, START + timedelta(days=1), release_out, actual_cost=2.0, group_id=group_in_view)
    await seed(plugin, START + timedelta(days=1), release_out, actual_cost=4.0, test_id=test_in_view)
    await seed(plugin, START + timedelta(days=1), release_out, actual_cost=8.0)

    view_query = await explorer.query_for_view(view_id, start=START, end=END, plugins=frozenset([plugin]))
    result = await explorer.explore(view_query)

    assert view_query.scope == CostScope(frozenset([release_in_view]), frozenset([group_in_view]),
                                         frozenset([test_in_view]))
    assert result["tiles"]["spend"] == pytest.approx(7.0)
    with pytest.raises(DataValidationError):
        await explorer.query_for_view(uuid.uuid4(), start=START, end=END)
