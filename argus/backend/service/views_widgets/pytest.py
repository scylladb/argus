from collections import defaultdict
from datetime import datetime
from functools import reduce
import re
import logging
from typing import TypedDict
from uuid import UUID

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
    def stringify_result(result: PytestResultTable) -> str:
        return f"{result.name} {result.message or ''} {' '.join(f'{key} {val}' for key, val, in result.user_fields.items())} {' '.join(f'{mark}' for mark in result.markers)}".lower()

    @staticmethod
    def do_user_field_filter(field: str, negated: bool, result: PytestResultTable) -> bool:
        if negated:
            return field not in result.user_fields
        return field in result.user_fields

    def view_results(self, view_id: str | UUID):
        view: ArgusUserView = ArgusUserView.get(id=view_id)
        tests = [test for batch in chunk(view.tests) for test in ArgusTest.filter(id__in=batch).all()]
        return self.result_filter([test for test in tests if test.plugin_name == GenericPluginInfo.name])

    def release_results(self, release_id: str | UUID):
        tests = list(ArgusTest.filter(release_id=release_id).all())
        return self.result_filter([test for test in tests if test.plugin_name == GenericPluginInfo.name])

    def prepare_pie_chart(self, hits: list[PytestResultTable]) -> dict:
        def count_status(acc: dict, result: PytestResultTable):
            acc[result.status] += 1
            return acc
        return reduce(count_status, hits, defaultdict(lambda: 0))

    def prepare_bar_chart(self, hits: list[PytestResultTable]) -> dict:
        result = {}
        for hit in hits:
            if hit.session_timestamp:
                key = hit.session_timestamp.strftime("%Y-%m-%d %H:%M:%S")
                bucket = result.get(key, defaultdict(lambda: 0))
                bucket[hit.status] += 1
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
        limit = request.args.get("limit", 500)
        before = request.args.get("before")
        after = request.args.get("after")
        enabled_statuses = request.args.getlist("status[]")
        query = request.args.get("query")
        filters = request.args.getlist("filters[]")
        markers = request.args.getlist("markers[]")

        dml = PytestResultTable.filter().allow_filtering()

        if before:
            dml = dml.filter(id__lt=uuid_from_time(float(before)))

        if after:
            dml = dml.filter(id__gt=uuid_from_time(float(after)))

        results: list[PytestResultTable] = [result for batch in chunk(test.id for test in tests) for result in dml.filter(test_id__in=batch).all()]

        if markers:
            for marker in markers:
                results = [result for result in results if marker in result.markers]

        if query:
            pattern = re.compile(query.lower())
            results = [result for result in results if re.search(pattern, self.stringify_result(result))]

        if filters:
            filters = [(f[0] == "!", f.lstrip("!")) for f in filters]
            for negated, field in filters:
                results = [result for result in results if self.do_user_field_filter(field, negated, result)]

        if isinstance(enabled_statuses, list):
            results = [result for result in results if result.status in enabled_statuses]

        results = sorted(results, key=lambda r: unix_time_from_uuid1(r.id), reverse=True)

        return {
            "total": len(results),
            "barChart": self.prepare_bar_chart(results),
            "pieChart": self.prepare_pie_chart(results),
            "hits": results[:limit]
        }
