import asyncio
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

from coodie.exceptions import DocumentNotFound

from argus.backend.error_handlers import DataValidationError
from argus.backend.models.run_cost_rollup import UNASSIGNED_RELEASE, RunCostReleaseSpan, RunCostRollup
from argus.backend.models.web import ArgusGroup, ArgusRelease, ArgusTest, ArgusUserView
from argus.backend.service.cost_rollup_service import ON_DEMAND, SPOT, as_utc
from argus.backend.util.common import chunk, gather_limited
from argus.common.enums import TestStatus

MAX_WINDOW_DAYS = 366
TOP_RUNS = 20
TIERS = (SPOT, ON_DEMAND)
BREAKDOWNS = ("group", "test")
GRANULARITIES = ("day", "week", "month")
ERRORED_STATUSES = {TestStatus.TEST_ERROR.value, TestStatus.ABORTED.value}
UNASSIGNED_NAME = "Unassigned"
UNKNOWN_BACKEND = "unknown"


@dataclass(frozen=True)
class CostScope:
    release_ids: frozenset[UUID] = frozenset()
    group_ids: frozenset[UUID] = frozenset()
    test_ids: frozenset[UUID] = frozenset()

    def matches(self, row: RunCostRollup) -> bool:
        return row.release_id in self.release_ids or row.group_id in self.group_ids or row.test_id in self.test_ids


@dataclass
class CostQuery:
    start: datetime
    end: datetime
    release_ids: frozenset[UUID] = frozenset()
    group_ids: frozenset[UUID] = frozenset()
    test_ids: frozenset[UUID] = frozenset()
    scope: CostScope | None = None
    backends: frozenset[str] = frozenset()
    plugins: frozenset[str] = frozenset()
    statuses: frozenset[str] = frozenset()
    tiers: frozenset[str] = frozenset()
    breakdown: str = "group"
    granularity: str = "week"

    def matches(self, row: RunCostRollup) -> bool:
        return ((not self.release_ids or row.release_id in self.release_ids)
                and (not self.group_ids or row.group_id in self.group_ids)
                and (not self.test_ids or row.test_id in self.test_ids)
                and (self.scope is None or self.scope.matches(row))
                and (not self.backends or row.backend in self.backends)
                and (not self.plugins or row.plugin_name in self.plugins)
                and (not self.statuses or row.status in self.statuses))


@dataclass
class _Bucket:
    runs: int = 0
    priced_runs: int = 0
    spend: float = 0.0


class CostExplorerService:
    @staticmethod
    async def release_ids_for(names: list[str]) -> frozenset[UUID]:
        async def resolve(name: str) -> UUID:
            try:
                return (await ArgusRelease.get(name=name)).id
            except DocumentNotFound as exc:
                raise DataValidationError(f"Release {name} does not exist") from exc
        return frozenset(await gather_limited(resolve(name) for name in names))

    async def query_for_view(self, view_id: UUID, **window) -> CostQuery:
        try:
            view = await ArgusUserView.get(id=view_id)
        except DocumentNotFound as exc:
            raise DataValidationError(f"View {view_id} does not exist") from exc
        scope = CostScope(frozenset(view.release_ids), frozenset(view.group_ids), frozenset(view.tests))
        return CostQuery(scope=scope, **window)

    async def explore(self, query: CostQuery) -> dict:
        self._validate(query)
        start = as_utc(query.start)
        end = as_utc(query.end)
        previous_start = start - (end - start)
        rows = await self._read(self.months_between(previous_start, end), self._release_restriction(query))
        current, previous = await asyncio.to_thread(self._select, rows, query, previous_start, start, end)
        names = await self._names(current)
        selected_releases = query.release_ids or (query.scope.release_ids if query.scope else frozenset())
        span = await self._span(selected_releases)
        panels = await asyncio.to_thread(self._fold, current, previous, query, names, start, end)
        return {
            "span": span,
            "window": {"from": start, "to": end, "granularity": query.granularity,
                       "breakdown": query.breakdown, "tiers": sorted(query.tiers)},
            **panels,
        }

    @staticmethod
    def _select(rows: list[RunCostRollup], query: CostQuery, previous_start: datetime, start: datetime,
                end: datetime) -> tuple[list[RunCostRollup], list[RunCostRollup]]:
        current = [row for row in rows if start <= as_utc(row.start_time) < end and query.matches(row)]
        previous = [row for row in rows if previous_start <= as_utc(row.start_time) < start and query.matches(row)]
        return current, previous

    def _fold(self, current, previous, query: CostQuery, names: dict, start: datetime, end: datetime) -> dict:
        return {
            "tiles": self._tiles(current, previous, query, start, end),
            "series": self._series(current, query, start, end),
            "releases": self._releases(current, query, names),
            "top_runs": self._top_runs(current, query, names),
            "coverage": self._coverage(current),
            "tiers": self._tiers(current),
            "spot_terminations": self._spot_terminations(current, query),
        }

    @staticmethod
    def _validate(query: CostQuery) -> None:
        if query.end <= query.start:
            raise DataValidationError("The window must end after it starts")
        if query.end - query.start > timedelta(days=MAX_WINDOW_DAYS):
            raise DataValidationError(f"The window must not exceed {MAX_WINDOW_DAYS} days")
        if not query.tiers <= set(TIERS):
            raise DataValidationError(f"tiers must be among {', '.join(TIERS)}")
        if query.breakdown not in BREAKDOWNS:
            raise DataValidationError(f"breakdown must be one of {', '.join(BREAKDOWNS)}")
        if query.granularity not in GRANULARITIES:
            raise DataValidationError(f"granularity must be one of {', '.join(GRANULARITIES)}")

    @staticmethod
    def _release_restriction(query: CostQuery) -> set[UUID] | None:
        if query.release_ids:
            return set(query.release_ids)
        if query.scope and query.scope.release_ids and not (query.scope.group_ids or query.scope.test_ids):
            return set(query.scope.release_ids)
        return None

    @staticmethod
    def months_between(start: datetime, end: datetime) -> list[str]:
        months = []
        cursor = as_utc(start).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last = as_utc(end) - timedelta(microseconds=1)
        while cursor <= last:
            months.append(cursor.strftime("%Y-%m"))
            cursor = (cursor + timedelta(days=32)).replace(day=1)
        return months

    @staticmethod
    async def _read(months: list[str], release_ids: set[UUID] | None) -> list[RunCostRollup]:
        if release_ids:
            queries = [RunCostRollup.find(month=month, release_id=release_id).all()
                       for month in months for release_id in sorted(release_ids)]
        else:
            queries = [RunCostRollup.find(month=month).all() for month in months]
        return [row for rows in await gather_limited(queries) for row in rows]

    @staticmethod
    def bucket_key(moment: datetime, granularity: str) -> str:
        day = as_utc(moment).date()
        if granularity == "week":
            day = day - timedelta(days=day.weekday())
        elif granularity == "month":
            day = day.replace(day=1)
        return day.isoformat()

    @classmethod
    def bucket_keys(cls, start: datetime, end: datetime, granularity: str) -> list[str]:
        keys = []
        cursor = datetime.fromisoformat(cls.bucket_key(start, granularity)).replace(tzinfo=UTC)
        end = as_utc(end)
        while cursor < end:
            keys.append(cursor.date().isoformat())
            if granularity == "day":
                cursor += timedelta(days=1)
            elif granularity == "week":
                cursor += timedelta(days=7)
            else:
                cursor = (cursor + timedelta(days=32)).replace(day=1)
        return keys

    @staticmethod
    def priced(row: RunCostRollup) -> bool:
        return bool(row.item_count) and row.actual_cost is not None

    @classmethod
    def spend_of(cls, row: RunCostRollup, tiers: frozenset[str]) -> float | None:
        if not cls.priced(row):
            return None
        if not tiers:
            return row.actual_cost
        return math.fsum(row.spot_cost if tier == SPOT else row.on_demand_cost for tier in tiers)

    @classmethod
    def _spend(cls, rows: list[RunCostRollup], tiers: frozenset[str]) -> float:
        return math.fsum(spend for row in rows if (spend := cls.spend_of(row, tiers)) is not None)

    def _tiles(self, current, previous, query: CostQuery, start: datetime, end: datetime) -> dict:
        spend = self._spend(current, query.tiers)
        window_days = (end - start).total_seconds() / 86400
        return {
            "spend": spend,
            "previous_spend": self._spend(previous, query.tiers),
            "weekly_run_rate": spend / (window_days / 7) if window_days else 0.0,
            "errored_spend": self._spend([row for row in current if row.status in ERRORED_STATUSES], query.tiers),
            "leaked_spend": math.fsum(row.leaked_cost for row in current),
            "leaked_count": sum(row.leaked_count for row in current),
            "runs": len(current),
            "priced_runs": sum(1 for row in current if self.priced(row)),
        }

    def _series(self, current, query: CostQuery, start: datetime, end: datetime) -> dict:
        keys = self.bucket_keys(start, end, query.granularity)
        index = {key: position for position, key in enumerate(keys)}
        backends: dict[str, list[float]] = {}
        for row in current:
            spend = self.spend_of(row, query.tiers)
            position = index.get(self.bucket_key(row.start_time, query.granularity))
            if spend is None or position is None:
                continue
            backends.setdefault(row.backend or UNKNOWN_BACKEND, [0.0] * len(keys))[position] += spend
        return {"buckets": keys, "backends": dict(sorted(backends.items()))}

    def _releases(self, current, query: CostQuery, names: dict) -> list[dict]:
        by_release: dict[UUID, dict[UUID | None, _Bucket]] = defaultdict(lambda: defaultdict(_Bucket))
        for row in current:
            key = row.group_id if query.breakdown == "group" else row.test_id
            bucket = by_release[row.release_id][key]
            bucket.runs += 1
            spend = self.spend_of(row, query.tiers)
            if spend is not None:
                bucket.priced_runs += 1
                bucket.spend += spend
        name_map = names["groups"] if query.breakdown == "group" else names["tests"]
        releases = []
        for release_id, buckets in by_release.items():
            rows = [{
                "id": key, "name": name_map.get(key, UNASSIGNED_NAME), "runs": bucket.runs,
                "priced_runs": bucket.priced_runs, "spend": bucket.spend,
                "cost_per_run": bucket.spend / bucket.priced_runs if bucket.priced_runs else None,
            } for key, bucket in buckets.items()]
            rows.sort(key=lambda item: item["spend"], reverse=True)
            releases.append({
                "id": release_id,
                "name": names["releases"].get(release_id, UNASSIGNED_NAME),
                "runs": sum(item["runs"] for item in rows),
                "priced_runs": sum(item["priced_runs"] for item in rows),
                "spend": math.fsum(item["spend"] for item in rows),
                "rows": rows,
            })
        releases.sort(key=lambda item: item["spend"], reverse=True)
        return releases

    def _top_runs(self, current, query: CostQuery, names: dict) -> list[dict]:
        priced = [(spend, row) for row in current if (spend := self.spend_of(row, query.tiers)) is not None]
        priced.sort(key=lambda item: item[0], reverse=True)
        return [{
            "run_id": row.run_id, "build_id": row.build_id, "build_number": row.build_number,
            "plugin_name": row.plugin_name,
            "release": names["releases"].get(row.release_id, UNASSIGNED_NAME),
            "group": names["groups"].get(row.group_id, UNASSIGNED_NAME),
            "test": names["tests"].get(row.test_id, UNASSIGNED_NAME),
            "status": row.status, "start_time": as_utc(row.start_time),
            "end_time": as_utc(row.end_time) if row.end_time else None,
            "backend": row.backend, "region": row.region, "spend": spend,
            "coverage": row.coverage, "spot_terminated": row.spot_terminated,
        } for spend, row in priced[:TOP_RUNS]]

    @classmethod
    def _coverage(cls, current) -> dict:
        counts = {"complete": 0, "partial": 0, "none": 0}
        for row in current:
            counts[row.coverage] = counts.get(row.coverage, 0) + 1
        estimated = [row for row in current if not cls.priced(row) and row.estimated_cost is not None]
        counts["estimate_only"] = {"count": len(estimated), "spend": math.fsum(row.estimated_cost for row in estimated)}
        return counts

    @staticmethod
    def _tiers(current) -> dict:
        return {
            "spot": {"spend": math.fsum(row.spot_cost for row in current),
                     "items": sum(row.spot_count for row in current)},
            "on_demand": {"spend": math.fsum(row.on_demand_cost for row in current),
                          "items": sum(row.on_demand_count for row in current)},
            "untiered": {"spend": math.fsum(row.untiered_cost for row in current),
                         "items": sum(row.untiered_count for row in current)},
        }

    def _spot_terminations(self, current, query: CostQuery) -> dict:
        terminated = [row for row in current if row.spot_terminated]
        spot_runs = sum(1 for row in current if row.spot_count or row.spot_terminated)
        by_location: dict[tuple[str | None, str | None], _Bucket] = defaultdict(_Bucket)
        for row in terminated:
            bucket = by_location[(row.backend, row.region)]
            bucket.runs += 1
            bucket.spend += self.spend_of(row, query.tiers) or 0.0
        locations = [{"backend": backend, "region": region, "count": bucket.runs, "spend": bucket.spend}
                     for (backend, region), bucket in by_location.items()]
        locations.sort(key=lambda item: (item["count"], item["spend"]), reverse=True)
        return {
            "count": len(terminated),
            "spot_runs": spot_runs,
            "rate": len(terminated) / spot_runs if spot_runs else 0.0,
            "spend": self._spend(terminated, query.tiers),
            "by_location": locations,
        }

    @staticmethod
    async def _span(release_ids: frozenset[UUID]) -> dict | None:
        if not release_ids:
            return None
        batches = await gather_limited(RunCostReleaseSpan.find(release_id__in=batch).all()
                                       for batch in chunk(sorted(release_ids)))
        spans = [span for rows in batches for span in rows]
        if not spans:
            return None
        return {"from": min(as_utc(span.first_start) for span in spans),
                "to": max(as_utc(span.last_start) for span in spans)}

    @staticmethod
    async def _names(current) -> dict[str, dict[UUID, str]]:
        async def resolve(model, ids: set[UUID]) -> dict[UUID, str]:
            batches = await gather_limited(model.find(id__in=batch).only("id", "name", "pretty_name").all()
                                           for batch in chunk(sorted(ids)))
            return {row.id: row.pretty_name or row.name for rows in batches for row in rows}

        release_ids = {row.release_id for row in current if row.release_id != UNASSIGNED_RELEASE}
        group_ids = {row.group_id for row in current if row.group_id}
        test_ids = {row.test_id for row in current if row.test_id}
        releases, groups, tests = await gather_limited([
            resolve(ArgusRelease, release_ids), resolve(ArgusGroup, group_ids), resolve(ArgusTest, test_ids),
        ])
        return {"releases": releases, "groups": groups, "tests": tests}
