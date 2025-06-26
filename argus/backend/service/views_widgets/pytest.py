from collections import defaultdict
from datetime import datetime
from functools import reduce
import re
import logging
from typing import TypedDict
from uuid import UUID
from time import time


from humanize import naturaltime
from flask import request
from cassandra.util import uuid_from_time, unix_time_from_uuid1
from argus.backend.db import ScyllaCluster
from argus.backend.models.pytest import PytestResultTable
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
            return f"{result['name']} {result['message'] or ''} {' '.join(f'{key} {val}' for key, val, in result.get('user_fields', {}).items())} {' '.join(f'{mark}' for mark in (result.get('markers') or []))}".lower()
        except Exception as exc:
            LOGGER.error("%s", result, exc_info=True)
            raise exc

    @staticmethod
    def do_user_field_filter(field: str, value: str, negated: bool, result: dict) -> bool:

        if not (field_value := result.get("user_fields", {}).get(field)):
            return field not in result.get("user_fields", {}) if negated else field in result.get("user_fields", {})

        res = field_value == value

        if negated:
            return not res
        return res

    def view_results(self, view_id: str | UUID):
        view: ArgusUserView = ArgusUserView.get(id=view_id)
        tests = [test for batch in chunk(view.tests) for test in ArgusTest.filter(id__in=batch).all()]
        return self.result_filter([test for test in tests if test.plugin_name == GenericPluginInfo.name])

    def release_results(self, release_id: str | UUID):
        tests = list(ArgusTest.filter(release_id=release_id).all())
        return self.result_filter([test for test in tests if test.plugin_name == GenericPluginInfo.name])

    def prepare_pie_chart(self, hits: list[dict]) -> dict:
        def count_status(acc: dict, result: dict):
            acc[result["status"]] += 1
            return acc
        return reduce(count_status, hits, defaultdict(lambda: 0))

    def prepare_bar_chart(self, hits: list[dict]) -> dict:
        result = {}
        for hit in hits:
            if hit["session_timestamp"]:
                key = hit["session_timestamp"].strftime("%Y-%m-%d %H:%M:%S")
                bucket = result.get(key, defaultdict(lambda: 0))
                bucket[hit["status"]] += 1
                result[key] = bucket

        datasets = []
        for status in PytestStatus:
            datasets.append({
                "label": status.value,
                "data": [result.get(status.value, 0) for result in result.values()]
            })

        return {
            "labels": list(result.keys()),
            "datasets": datasets,
        }

    def result_filter(self, tests: list[ArgusTest]) -> PytestResult:
        ts_start = time()
        db = ScyllaCluster.get()

        partitions = {}
        for test in tests:
            result = db.session.execute(f"SELECT name FROM pytest_v2 WHERE test_id = {test.id}").all()
            partitions[test.id] = list({res["name"] for res in result})

        limit = request.args.get("limit", 500)
        before = request.args.get("before")
        after = request.args.get("after")
        enabled_statuses = request.args.getlist("status[]")
        query = request.args.get("query")
        filters = request.args.getlist("filters[]")
        markers = request.args.getlist("markers[]")

        db_query = "SELECT * FROM pytest_v2"
        query_filters = []

        if before:
            query_filters.append(("id <= ?", uuid_from_time(float(before))))

        if after:
            query_filters.append(("id >= ?", uuid_from_time(float(after))))

        LOGGER.warning("%s, %s", db_query, query_filters)
        prepared = db.prepare(db_query)
        ts_prepare = time()
        results: list[dict] = []
        for test in tests:
            parallel_filter = [("test_id = ?", test.id), *query_filters]
            for partition in partitions[test.id]:
                parallel_query = db_query
                partition_filter = [("name = ?", partition), *parallel_filter]
                parallel_query += " WHERE "
                parallel_query += " AND ".join([f for f, _ in partition_filter])
                LOGGER.warning("%s, %s", parallel_query, partition_filter)
                prepared = db.prepare(parallel_query)
                future = db.session.execute_async(prepared, parameters=[p for _, p in partition_filter], timeout=60.0)
                results.append(future)
        LOGGER.warning("Total queries in progress: %s", len(results))
        results = [row for future in results for row in future.result()]

        ts_data_fetch = time()

        if markers:
            for marker in markers:
                results = [result for result in results if marker in (result.get("markers") or [])]
        ts_marker_filter = time()
        if query:
            pattern = re.compile(query.lower())
            results = [result for result in results if re.search(pattern, self.stringify_result(result))]
        ts_text_filter = time()
        if filters:
            filters = [(f[0] == "!", f.lstrip("!").split("=", 1)[0], f.lstrip("!").split("=", 1)[1]) for f in filters]
            for negated, field, value in filters:
                results = [result for result in results if self.do_user_field_filter(field, value, negated, result)]
        ts_user_filter = time()
        if isinstance(enabled_statuses, list):
            results = [result for result in results if result["status"] in enabled_statuses]
        ts_status_filter = time()
        results = sorted(results, key=lambda r: unix_time_from_uuid1(r["id"]), reverse=True)
        ts_sort = time()
        LOGGER.warning("Stats\nParse: %s\nFetch: %s\nMarkers: %s\nText: %s\nFields: %s\nStatus: %s\nSort: %s",
                       naturaltime(ts_prepare - ts_start, minimum_unit="milliseconds"),
                       naturaltime(ts_data_fetch - ts_prepare, minimum_unit="milliseconds"),
                       naturaltime(ts_marker_filter - ts_data_fetch, minimum_unit="milliseconds"),
                       naturaltime(ts_text_filter - ts_marker_filter, minimum_unit="milliseconds"),
                       naturaltime(ts_user_filter - ts_text_filter, minimum_unit="milliseconds"),
                       naturaltime(ts_status_filter - ts_user_filter, minimum_unit="milliseconds"),
                       naturaltime(ts_sort - ts_status_filter, minimum_unit="milliseconds"),

                    )
        return {
            "total": len(results),
            "barChart": self.prepare_bar_chart(results),
            "pieChart": self.prepare_pie_chart(results),
            "hits": results[:limit]
        }
