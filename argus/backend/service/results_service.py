import copy
import logging
import math
import operator
from datetime import datetime, timezone
from functools import partial
from typing import List, Dict, Any
from uuid import UUID

from dataclasses import dataclass
from argus.backend.db import ScyllaCluster
from argus.backend.models.result import ArgusGenericResultMetadata, ArgusGenericResultData, ArgusBestResultData

LOGGER = logging.getLogger(__name__)


@dataclass
class BestResult:
    key: str
    value: float
    result_date: datetime
    run_id: str


@dataclass
class Cell:
    column: str
    row: str
    status: str
    value: Any | None = None
    value_text: str | None = None

    def update_cell_status_based_on_rules(self, table_metadata: ArgusGenericResultMetadata, best_results: dict[str, BestResult],
                                          ) -> None:
        column_validation_rules = table_metadata.validation_rules.get(self.column)
        rules = column_validation_rules[-1] if column_validation_rules else {}
        higher_is_better = next((col.higher_is_better for col in table_metadata.columns_meta if col.name == self.column), None)
        if not rules or self.status != "UNSET" or higher_is_better is None:
            return
        is_better = partial(operator.gt, self.value) if higher_is_better else partial(operator.lt, self.value)
        key = f"{self.column}:{self.row}"
        limits = []
        if rules.fixed_limit is not None:
            limits.append(rules.fixed_limit)

        if best_result := best_results.get(key):
            best_value = best_result.value
            if (best_pct := rules.best_pct) is not None:
                multiplier = 1 - best_pct / 100 if higher_is_better else 1 + best_pct / 100
                limits.append(best_value * multiplier)
            if (best_abs := rules.best_abs) is not None:
                limits.append(best_value - best_abs if higher_is_better else best_value + best_abs)
        if all(is_better(limit) for limit in limits):
            self.status = "PASS"
        else:
            self.status = "ERROR"


default_options = {
    "scales": {
        "y": {
            "beginAtZero": True,
            "title": {
                "display": True,
                "text": ''
            }
        },
        "x": {
            "type": "time",
            "time": {
                "unit": "day",
                "displayFormats": {
                    "day": "yyyy-MM-dd",
                },
            },
            "title": {
                "display": True,
                "text": 'SUT Date'
            }
        },
    },
    "elements": {
        "line": {
            "tension": .1,
        }
    },
    "plugins": {
        "legend": {
            "position": 'top',
        },
        "title": {
            "display": True,
            "text": ''
        }
    }
}

colors = [
    'rgba(255, 0, 0, 1.0)',  # Red
    'rgba(0, 255, 0, 1.0)',  # Green
    'rgba(0, 0, 255, 1.0)',  # Blue
    'rgba(0, 255, 255, 1.0)',  # Cyan
    'rgba(255, 0, 255, 1.0)',  # Magenta
    'rgba(255, 255, 0, 1.0)',  # Yellow
    'rgba(255, 165, 0, 1.0)',  # Orange
    'rgba(128, 0, 128, 1.0)',  # Purple
    'rgba(50, 205, 50, 1.0)',  # Lime
    'rgba(255, 192, 203, 1.0)',  # Pink
    'rgba(0, 128, 128, 1.0)',  # Teal
    'rgba(165, 42, 42, 1.0)',  # Brown
    'rgba(0, 0, 128, 1.0)',  # Navy
    'rgba(128, 128, 0, 1.0)',  # Olive
    'rgba(255, 127, 80, 1.0)'  # Coral
]


def get_sorted_data_for_column_and_row(data: List[ArgusGenericResultData], column: str, row: str) -> List[Dict[str, Any]]:
    return sorted([{"x": entry.sut_timestamp.strftime('%Y-%m-%dT%H:%M:%SZ'),
                    "y": entry.value,
                    "id": entry.run_id}
                   for entry in data if entry.column == column and entry.row == row],
                  key=lambda point: point["x"])


def get_min_max_y(datasets: List[Dict[str, Any]]) -> (float, float):
    """0.5 - 1.5 of min/max of 50% results"""
    y = [entry['y'] for dataset in datasets for entry in dataset['data']]
    if not y:
        return 0, 0
    sorted_y = sorted(y)
    lower_percentile_index = int(0.25 * len(sorted_y))
    upper_percentile_index = int(0.75 * len(sorted_y)) - 1
    y_min = sorted_y[lower_percentile_index]
    y_max = sorted_y[upper_percentile_index]
    return math.floor(0.5 * y_min), math.ceil(1.5 * y_max)


def round_datasets_to_min_max(datasets: List[Dict[str, Any]], min_y: float, max_y: float) -> List[Dict[str, Any]]:
    """Round values to min/max and provide original value for tooltip"""
    for dataset in datasets:
        for entry in dataset['data']:
            val = entry['y']
            if val > max_y:
                entry['y'] = max_y
                entry['ori'] = val
            elif val < min_y:
                entry['y'] = min_y
                entry['ori'] = val
    return datasets


def create_chartjs(table, data):
    graphs = []
    for column in table.columns_meta:
        if column.type == "TEXT":
            # skip text columns
            continue
        datasets = [
            {"label": row,
             "borderColor": colors[idx % len(colors)],
             "borderWidth": 3,
             "showLine": True,
             "data": get_sorted_data_for_column_and_row(data, column.name, row)} for idx, row in enumerate(table.rows_meta)]
        min_y, max_y = get_min_max_y(datasets)
        datasets = round_datasets_to_min_max(datasets, min_y, max_y)
        if not min_y + max_y:
            # filter out those without data
            continue
        options = copy.deepcopy(default_options)
        options["plugins"]["title"]["text"] = f"{table.name} - {column.name}"
        options["scales"]["y"]["title"]["text"] = f"[{column.unit}]" if column.unit else ""
        options["scales"]["y"]["min"] = min_y
        options["scales"]["y"]["max"] = max_y
        graphs.append({"options": options, "data":
            {"datasets": datasets}})
    return graphs


def calculate_graph_ticks(graphs: List[Dict]) -> dict[str, str]:
    min_x, max_x = None, None

    for graph in graphs:
        for dataset in graph["data"]["datasets"]:
            if not dataset["data"]:
                continue
            first_x = dataset["data"][0]["x"]
            last_x = dataset["data"][-1]["x"]
            if min_x is None or first_x < min_x:
                min_x = first_x
            if max_x is None or last_x > max_x:
                max_x = last_x
    return {"min": min_x[:10], "max": max_x[:10]}


class ResultsService:

    def __init__(self):
        self.cluster = ScyllaCluster.get()

    def _get_tables_metadata(self, test_id: UUID) -> list[ArgusGenericResultMetadata]:
        query_fields = ["name", "description", "columns_meta", "rows_meta"]
        raw_query = (f"SELECT {','.join(query_fields)}"
                     f" FROM generic_result_metadata_v1 WHERE test_id = ?")
        query = self.cluster.prepare(raw_query)
        tables_meta = self.cluster.session.execute(query=query, parameters=(test_id,))
        return [ArgusGenericResultMetadata(**table) for table in tables_meta]

    def get_table_metadata(self, test_id: UUID, table_name: str) -> ArgusGenericResultMetadata:
        raw_query = ("SELECT * FROM generic_result_metadata_v1 WHERE test_id = ? AND name = ?")
        query = self.cluster.prepare(raw_query)
        table_meta = self.cluster.session.execute(query=query, parameters=(test_id, table_name))
        return [ArgusGenericResultMetadata(**table) for table in table_meta][0] if table_meta else None

    def get_run_results(self, test_id: UUID, run_id: UUID) -> list[dict]:
        query_fields = ["column", "row", "value", "value_text", "status"]
        raw_query = (f"SELECT {','.join(query_fields)},WRITETIME(status) as ordering"
                     f" FROM generic_result_data_v1 WHERE test_id = ? AND run_id = ? AND name = ?")
        query = self.cluster.prepare(raw_query)
        tables_meta = self._get_tables_metadata(test_id=test_id)
        tables = []
        for table in tables_meta:
            cells = self.cluster.session.execute(query=query, parameters=(test_id, run_id, table.name))
            if not cells:
                continue
            cells = [dict(cell.items()) for cell in cells]
            tables.append({'meta': {
                'name': table.name,
                'description': table.description,
                'columns_meta': table.columns_meta,
                'rows_meta': table.rows_meta,
            },
                'cells': [{k: v for k, v in cell.items() if k in query_fields} for cell in cells],
                'order': min([cell['ordering'] for cell in cells] or [0])})
        return sorted(tables, key=lambda x: x['order'])

    def get_test_graphs(self, test_id: UUID):
        query_fields = ["run_id", "column", "row", "value", "status", "sut_timestamp"]
        raw_query = (f"SELECT {','.join(query_fields)}"
                     f" FROM generic_result_data_v1 WHERE test_id = ? AND name = ? LIMIT 2147483647")
        query = self.cluster.prepare(raw_query)
        tables_meta = self._get_tables_metadata(test_id=test_id)
        graphs = []
        for table in tables_meta:
            data = self.cluster.session.execute(query=query, parameters=(test_id, table.name))
            data = [ArgusGenericResultData(**cell) for cell in data]
            if not data:
                continue
            graphs.extend(create_chartjs(table, data))
        ticks = calculate_graph_ticks(graphs)
        return graphs, ticks

    def is_results_exist(self, test_id: UUID):
        """Verify if results for given test id exist at all."""
        return bool(ArgusGenericResultMetadata.objects(test_id=test_id).only(["name"]).limit(1))

    def get_best_results(self, test_id: UUID, name: str) -> List[BestResult]:
        query_fields = ["key", "value", "result_date", "run_id"]
        raw_query = (f"SELECT {','.join(query_fields)}"
                     f" FROM generic_result_best_v1 WHERE test_id = ? and name = ?")
        query = self.cluster.prepare(raw_query)
        best_results = self.cluster.session.execute(query=query, parameters=(test_id, name))
        return [BestResult(**best) for best in best_results]

    @staticmethod
    def _update_best_value(best_results: dict[str, list[dict]], higher_is_better_map: dict[str, bool | None], cells: list[dict],
                           sut_timestamp: float, run_id: str
                           ) -> dict[str, list[dict]]:

        for cell in cells:
            if "column" not in cell or "row" not in cell or "value" not in cell:
                continue
            column, row, value = cell["column"], cell["row"], cell["value"]
            key_name = f"{column}_{row}"
            if higher_is_better_map[column] is None:
                # skipping updating best value when higher_is_better is not set (not enabled by user)
                return best_results
            if key_name not in best_results:
                best_results[key_name] = []
                current_best = None
            else:
                current_best = best_results[key_name][-1]
                if current_best["sut_timestamp"].timestamp() > sut_timestamp:
                    # skip updating best value when testing older version than current best
                    # as would have to update all values between these dates to make cells statuses to be consistent
                    return best_results

            is_better = partial(operator.gt, value) if higher_is_better_map[column] else partial(operator.lt, value)
            if current_best is None or is_better(current_best["value"]):
                best_results[key_name].append({"sut_timestamp": sut_timestamp, "value": value, "run_id": run_id})
        return best_results

    def update_best_results(self, test_id: UUID, table_name: str, cells: list[Cell],
                            table_metadata: ArgusGenericResultMetadata, run_id: str) -> dict[str, BestResult]:
        """update best results for given test_id and table_name based on cells values - if any value is better than current best"""
        higher_is_better_map = {meta["name"]: meta.higher_is_better for meta in table_metadata.columns_meta}
        best_results = {}
        for best in self.get_best_results(test_id=test_id, name=table_name):
            if best.key not in best_results:
                best_results[best.key] = best

        for cell in cells:
            if cell.value is None:
                # textual value, skip
                continue
            key = f"{cell.column}:{cell.row}"
            if higher_is_better_map[cell.column] is None:
                # skipping updating best value when higher_is_better is not set (not enabled by user)
                continue
            current_best = best_results.get(key)
            is_better = partial(operator.gt, cell.value) if higher_is_better_map[cell.column] \
                else partial(operator.lt, cell.value)
            if current_best is None or is_better(current_best.value):
                result_date = datetime.now(timezone.utc)
                best_results[key] = BestResult(key=key, value=cell.value, result_date=result_date, run_id=run_id)
                ArgusBestResultData(test_id=test_id, name=table_name, key=key, value=cell.value, result_date=result_date,
                                    run_id=run_id).save()
        return best_results
