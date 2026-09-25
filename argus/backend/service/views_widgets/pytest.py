import asyncio
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from functools import reduce
from pprint import pformat
import re
import logging
from typing import TypedDict
from uuid import UUID
from time import sleep, time


from humanize import naturaltime
from cassandra.util import uuid_from_time, unix_time_from_uuid1
from argus.backend.models.pytest import PytestResultTable, PytestUserField
from argus.backend.models.web import ArgusTest, ArgusUserView
from argus.backend.plugins.generic.plugin import PluginInfo as GenericPluginInfo
from argus.backend.util.common import chunk
from argus.common.enums import PytestStatus

LOGGER = logging.getLogger(__name__)


class PytestResult(TypedDict):
    hits: list[PytestResultTable]
    barChart: dict
    pieChart: dict


class PytestViewService:
    @staticmethod
    def stringify_result(result: dict) -> str:
        try:
            markers = " ".join(f"{mark}" for mark in (result["markers"] or []))
            return f"{result['name']} {result['message'] or ''} {markers}".lower()
        except Exception as exc:
            LOGGER.error("%s", result, exc_info=True)
            raise exc

    async def get_user_fields_for_result(self, name: str, id: str):
        field_rows = await PytestUserField.find(
            name=name,  id=datetime.fromisoformat(id)).all()
        result = {row.field_name: row.field_value for row in field_rows}

        return result

    @staticmethod
    def do_user_field_filter(field: str, value: str, negated: bool, result: dict) -> bool:

        if not (field_value := (result["user_fields"] or {}).get(field)):
            return field not in (result["user_fields"] or {}) if negated else field in (result["user_fields"] or {})

        res = field_value == value

        if negated:
            return not res
        return res

    async def view_results(self, view_id: str | UUID, args):
        return await self.result_filter(args)

    async def release_results(self, release_id: str | UUID, args):
        return await self.result_filter(args)

    def prepare_pie_chart(self, hits: list[dict]) -> dict:
        def count_status(acc: dict, result: dict):
            acc[result["status"]] += 1
            return acc
        return reduce(count_status, hits, defaultdict(lambda: 0))

    def prepare_bar_chart(self, hits: list[dict], before: datetime, after: datetime) -> dict:
        start_date = None
        end_date = None
        # without hits there is no oldest result to open the window at —
        # fall back to today, producing an empty chart
        oldest_hit_date = date.fromtimestamp(hits[-1]["id"].timestamp()) if hits else date.today()
        if not before and not after:
            start_date = oldest_hit_date
            end_date = date.today()
        elif before and not after:
            start_date = oldest_hit_date
            end_date = date.fromtimestamp(before.timestamp())
        elif after and not before:
            start_date = date.fromtimestamp(after.timestamp())
            end_date = date.today()
        else:
            start_date = date.fromtimestamp(after.timestamp())
            end_date = date.fromtimestamp(before.timestamp())

        bucket_days = (end_date - start_date).days
        buckets = {date.today() - timedelta(days=d): defaultdict(lambda: 0)
                   for d in range(bucket_days)}
        for hit in hits:
            if hit["session_timestamp"]:
                key = date.fromtimestamp(hit["session_timestamp"].timestamp())
                bucket = buckets.get(key, defaultdict(lambda: 0))
                bucket[hit["status"]] += 1
                buckets[key] = bucket

        buckets = {k.strftime("%Y-%m-%d"): v for k,
                   v in reversed(buckets.items())}
        datasets = []
        for status in PytestStatus:
            datasets.append({
                "label": status.value,
                "data": [result.get(status.value, 0) for result in buckets.values()]
            })

        return {
            "labels": list(buckets.keys()),
            "datasets": datasets,
        }

    async def result_filter(self, args) -> PytestResult:
        test = args.get("test")

        unique_tests: list[str] = [
            name for (name,) in
            await PytestResultTable.find().distinct().only("name").values_list("name").timeout(60.0).all()
        ]

        if test:
            LOGGER.warning(test)
            unique_tests = [
                t for t in unique_tests if re.search(re.escape(test), t)]

        limit = int(args.get("limit", 500))
        before = args.get("before")
        after = args.get("after")
        enabled_statuses = args.getlist("status[]")
        query = args.get("query")
        filters = args.getlist("filters[]")
        markers = args.getlist("markers[]")

        columns = ("test_id", "id", "name", "run_id", "message", "session_timestamp", "status", "markers", "duration",
                   "test_type")
        query_filters = {}

        if before:
            before = datetime.fromtimestamp(int(before), tz=UTC)
            query_filters["id__lte"] = before

        if after:
            after = datetime.fromtimestamp(int(after), tz=UTC)
            query_filters["id__gte"] = after

        if isinstance(enabled_statuses, list) and len(enabled_statuses) > 0:
            query_filters["status__in"] = enabled_statuses

        results = []
        for sequential_batch in chunk(unique_tests, 1000):
            batches = await asyncio.gather(*(
                PytestResultTable.find(name__in=partition_chunk, **query_filters)
                .only(*columns).values_list(*columns).consistency("ONE").timeout(60.0).all()
                for partition_chunk in chunk(sequential_batch, 100)
            ))
            results.extend(dict(zip(columns, row)) for batch in batches for row in batch)

        if markers:
            for marker in markers:
                results = [result for result in results if marker in (
                    result["markers"] or [])]
        if query:
            pattern = re.compile(query.lower())
            results = [result for result in results if re.search(
                pattern, self.stringify_result(result))]
        user_fields = {}

        if filters:
            batches = await asyncio.gather(*(
                PytestUserField.find(name__in=[r["name"] for r in batch], id__in=[r["id"] for r in batch])
                .consistency("ONE").timeout(60.0).all()
                for batch in chunk(results)
            ))
            for row in (row for batch in batches for row in batch):
                key = (row.name, row.id)
                val = user_fields.get(key, {})
                val[row.field_name] = row.field_value
                user_fields[key] = val
            results = [{**result, "user_fields": user_fields.get(
                (result["name"], result["id"]), {})} for result in results]
            filters = [(f[0] == "!", f.lstrip("!").split("=", 1)[0],
                        f.lstrip("!").split("=", 1)[1]) for f in filters]
            for negated, field, value in filters:
                results = [result for result in results if self.do_user_field_filter(
                    field, value, negated, result)]

        results = sorted(results, key=lambda r: r["id"], reverse=True)
        return {
            "total": len(results),
            "barChart": self.prepare_bar_chart(results, before, after),
            "pieChart": self.prepare_pie_chart(results),
            "hits": results[:limit]
        }
