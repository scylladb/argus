from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from functools import reduce
from pprint import pformat
import re
import logging
from typing import NamedTuple, TypedDict
from uuid import UUID
from time import sleep, time


from humanize import naturaltime
from flask import request
from cassandra.util import uuid_from_time, unix_time_from_uuid1
from argus.backend.db import ScyllaCluster
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
    def __init__(self) -> None:
        self.cluster = ScyllaCluster.get()

    @staticmethod
    def stringify_result(result: dict) -> str:
        try:
            return f"{result.name} {result.message or ''} {' '.join(f'{mark}' for mark in (result.markers or []))}".lower()
        except Exception as exc:
            LOGGER.error("%s", result, exc_info=True)
            raise exc

    def get_user_fields_for_result(self, name: str, id: str):
        field_rows = PytestUserField.filter(name=name,  id=datetime.fromisoformat(id)).all()
        result = { row["field_name"]: row["field_value"] for row in field_rows }

        return result

    @staticmethod
    def do_user_field_filter(field: str, value: str, negated: bool, result: dict) -> bool:

        if not (field_value := (result["user_fields"] or {}).get(field)):
            return field not in (result["user_fields"] or {}) if negated else field in (result["user_fields"]or {})

        res = field_value == value

        if negated:
            return not res
        return res

    def view_results(self, view_id: str | UUID):
        return self.result_filter()

    def release_results(self, release_id: str | UUID):
        return self.result_filter()

    def prepare_pie_chart(self, hits: list[dict]) -> dict:
        def count_status(acc: dict, result: dict):
            acc[result["status"]] += 1
            return acc
        return reduce(count_status, hits, defaultdict(lambda: 0))

    def prepare_bar_chart(self, hits: list[dict], before: datetime, after: datetime) -> dict:
        start_date = None
        end_date = None
        if not before and not after:
            start_date = date.fromtimestamp(hits[-1]["id"].timestamp())
            end_date = date.today()
        elif before and not after:
            start_date = date.fromtimestamp(hits[-1]["id"].timestamp())
            end_date = date.fromtimestamp(before.timestamp())
        elif after and not before:
            start_date = date.fromtimestamp(after.timestamp())
            end_date = date.today()
        else:
            start_date = date.fromtimestamp(after.timestamp())
            end_date = date.fromtimestamp(before.timestamp())

        bucket_days = (end_date - start_date).days
        buckets = {date.today() - timedelta(days=d): defaultdict(lambda: 0) for d in range(bucket_days)}
        for hit in hits:
            if hit["session_timestamp"]:
                key = date.fromtimestamp(hit["session_timestamp"].timestamp())
                bucket = buckets.get(key, defaultdict(lambda: 0))
                bucket[hit["status"]] += 1
                buckets[key] = bucket


        buckets = { k.strftime("%Y-%m-%d"): v for k, v in reversed(buckets.items())}
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

    def result_filter(self) -> PytestResult:
        db = ScyllaCluster.get()
        test = request.args.get("test")

        unique_tests: list[str] = []
        unique_tests.extend((row["name"] for row in db.session.execute(f"SELECT DISTINCT name FROM pytest_v2", timeout=60.0).all()))

        if test:
            LOGGER.warning(test)
            unique_tests = [t for t in unique_tests if re.search(re.escape(test), t)]

        limit = request.args.get("limit", 500)
        before = request.args.get("before")
        after = request.args.get("after")
        enabled_statuses = request.args.getlist("status[]")
        query = request.args.get("query")
        filters = request.args.getlist("filters[]")
        markers = request.args.getlist("markers[]")

        db_query = "SELECT test_id, id, name, run_id, message, session_timestamp, status, markers, duration, test_type FROM pytest_v2"
        query_filters = []

        if before:
            before = datetime.fromtimestamp(int(before), tz=UTC)
            query_filters.append(("id <= ?", before))

        if after:
            after = datetime.fromtimestamp(int(after), tz=UTC)
            query_filters.append(("id >= ?", after))

        prepared = db.prepare(db_query)
        results: list[NamedTuple] = []
        if isinstance(enabled_statuses, list) and len(enabled_statuses) > 0:
            query_filters.append(("status in ?", enabled_statuses))

        results = []
        for sequential_batch in chunk(unique_tests, 1000):
            futures = []
            for partition_chunk in chunk(sequential_batch, 100):
                parallel_filter = [*query_filters]
                parallel_query = db_query
                partition_filter = [("name IN ?", partition_chunk), *parallel_filter]
                parallel_query += " WHERE "
                parallel_query += " AND ".join([f for f, _ in partition_filter])
                prepared = db.prepare(parallel_query)
                future = db.session.execute_async(prepared, parameters=[p for _, p in partition_filter], timeout=60.0, execution_profile="read_fast_named_tuple")
                futures.append(future)
            results.extend([row for future in futures for row in future.result()])

        if markers:
            for marker in markers:
                results = [result for result in results if marker in (result.markers or [])]
        if query:
            pattern = re.compile(query.lower())
            results = [result for result in results if re.search(pattern, self.stringify_result(result))]
        user_fields = {}

        if filters:
            base_filter_query = db.prepare("SELECT * FROM pytest_user_field WHERE name IN ? AND id IN ?")
            futures = []
            for batch in chunk((r.name,  r.id) for r in results):
                future = db.session.execute_async(base_filter_query, parameters=[[b[0] for b in batch], [b[1] for b in batch]], timeout=60.0, execution_profile="read_fast")
                futures.append(future)
            filter_rows = [row for future in futures for row in future.result()]
            for row in filter_rows:
                key = (row["name"], row["id"])
                val = user_fields.get(key, {})
                val[row["field_name"]] = row["field_value"]
                user_fields[key] = val
            results = [{**result._asdict(), "user_fields": user_fields.get((result.name, result.id), {})} for result in results]
            filters = [(f[0] == "!", f.lstrip("!").split("=", 1)[0], f.lstrip("!").split("=", 1)[1]) for f in filters]
            for negated, field, value in filters:
                results = [result for result in results if self.do_user_field_filter(field, value, negated, result)]
        else:
            results = [result._asdict() for result in results]

        results = sorted(results, key=lambda r: r["id"], reverse=True)
        return {
            "total": len(results),
            "barChart": self.prepare_bar_chart(results, before, after),
            "pieChart": self.prepare_pie_chart(results),
            "hits": results[:limit]
        }
