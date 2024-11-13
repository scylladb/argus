import copy
import logging
import math
import operator
from collections import defaultdict
from datetime import datetime, timezone
from functools import partial, cache
from typing import List, Dict, Any
from uuid import UUID

from dataclasses import dataclass
from argus.backend.db import ScyllaCluster
from argus.backend.models.result import ArgusGenericResultMetadata, ArgusGenericResultData, ArgusBestResultData, ColumnMetadata
from argus.backend.plugins.sct.udt import PackageVersion
from argus.backend.service.testrun import TestRunService

LOGGER = logging.getLogger(__name__)

type RunId = str
type ReleasesMap = dict[str, list[RunId]]


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

    def update_cell_status_based_on_rules(self, table_metadata: ArgusGenericResultMetadata, best_results: dict[str, List[BestResult]],
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
            best_value = best_result[-1].value
            if (best_pct := rules.best_pct) is not None:
                multiplier = 1 - best_pct / 100 if higher_is_better else 1 + best_pct / 100
                limits.append(best_value * multiplier)
            if (best_abs := rules.best_abs) is not None:
                limits.append(best_value - best_abs if higher_is_better else best_value + best_abs)
        if all(is_better(limit) for limit in limits):
            self.status = "PASS"
        else:
            self.status = "ERROR"


@dataclass
class RunsDetails:
    ignored: list[RunId]
    packages: dict[RunId, list[PackageVersion]]


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
    'rgba(220, 53, 69, 1.0)',    # Soft Red
    'rgba(40, 167, 69, 1.0)',    # Soft Green
    'rgba(0, 123, 255, 1.0)',    # Soft Blue
    'rgba(23, 162, 184, 1.0)',   # Soft Cyan
    'rgba(108, 117, 125, 1.0)',  # Soft Magenta
    'rgba(255, 193, 7, 1.0)',    # Soft Yellow
    'rgba(255, 133, 27, 1.0)',   # Soft Orange
    'rgba(102, 16, 242, 1.0)',   # Soft Purple
    'rgba(111, 207, 151, 1.0)',  # Soft Lime
    'rgba(255, 182, 193, 1.0)',  # Soft Pink
    'rgba(32, 201, 151, 1.0)',   # Soft Teal
    'rgba(134, 83, 78, 1.0)',    # Soft Brown
    'rgba(0, 84, 153, 1.0)',     # Soft Navy
    'rgba(128, 128, 0, 1.0)',    # Soft Olive
    'rgba(255, 159, 80, 1.0)'    # Soft Coral
]
shapes = ["circle", "triangle", "rect", "star", "dash", "crossRot", "line"]


def get_sorted_data_for_column_and_row(data: List[ArgusGenericResultData], column: str, row: str,
                                       runs_details: RunsDetails, main_package: str) -> List[Dict[str, Any]]:
    points =  sorted([{"x": entry.sut_timestamp.strftime('%Y-%m-%dT%H:%M:%SZ'),
                    "y": entry.value,
                    "id": entry.run_id,
                    }
                   for entry in data if entry.column == column and entry.row == row],
                  key=lambda point: point["x"])
    if not points:
        return points
    packages = runs_details.packages
    prev_versions = {pkg.name: pkg.version + (f" ({pkg.date})" if pkg.date else "") for pkg in packages.get(points[0]["id"], [])}
    points[0]['changes'] = [f"{main_package}: {prev_versions.pop(main_package, None)}"]
    points[0]['dep_change'] = False
    for point in points[1:]:
        changes = []
        mark_dependency_change = False
        current_versions = {pkg.name: pkg.version + (f" ({pkg.date})" if pkg.date else "") for pkg in packages.get(point["id"], [])}
        main_package_version = current_versions.pop(main_package, None)
        for pkg_name in current_versions.keys() | prev_versions.keys():
            curr_ver = current_versions.get(pkg_name)
            prev_ver = prev_versions.get(pkg_name)
            if curr_ver != prev_ver:
                changes.append({'name': pkg_name, 'prev_version': prev_ver, 'curr_version': curr_ver})
                if pkg_name != main_package:
                    mark_dependency_change = True
        point['changes'] = [f"{main_package}: {main_package_version}"] + [
            f"{change['name']}: {change['prev_version']} -> {change['curr_version']}" for change in changes]
        point['dep_change'] = mark_dependency_change
        prev_versions = current_versions
    return points

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


def coerce_values_to_axis_boundaries(datasets: List[Dict[str, Any]], min_y: float, max_y: float) -> List[Dict[str, Any]]:
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


def calculate_limits(points: List[dict], best_results: List, validation_rules_list: List, higher_is_better: bool) -> List[dict]:
    """Calculate limits for points based on best results and validation rules"""
    for point in points:
        point_date = datetime.strptime(point["x"], '%Y-%m-%dT%H:%M:%SZ')
        validation_rule = next(
            (rule for rule in reversed(validation_rules_list) if rule.valid_from <= point_date),
            validation_rules_list[0]
        )
        best_result = next(
            (result for result in reversed(best_results) if result.result_date <= point_date),
            best_results[0]
        )
        limit_values = []
        if validation_rule.fixed_limit is not None:
            limit_values.append(validation_rule.fixed_limit)
        best_value = best_result.value
        if validation_rule.best_pct is not None:
            multiplier = 1 - validation_rule.best_pct / 100 if higher_is_better else 1 + validation_rule.best_pct / 100
            limit_values.append(best_value * multiplier)
        if validation_rule.best_abs is not None:
            limit_values.append(best_value - validation_rule.best_abs if higher_is_better else best_value + validation_rule.best_abs)
        if limit_values:
            limit_value = max(limit_values) if higher_is_better else min(limit_values)
            point['limit'] = limit_value

    return points


def create_datasets_for_column(table: ArgusGenericResultMetadata, data: list[ArgusGenericResultData],
                               best_results: dict[str, List[BestResult]], releases_map: ReleasesMap, column: ColumnMetadata,
                               runs_details: RunsDetails, main_package:str) -> List[Dict]:
    """
    Create datasets (series) for a specific column, splitting by version and showing limit lines.
    """
    datasets = []
    is_fixed_limit_drawn = False

    for idx, row in enumerate(table.rows_meta):
        line_color = colors[idx % len(colors)]
        points = get_sorted_data_for_column_and_row(data, column.name, row, runs_details, main_package)

        datasets.extend(create_release_datasets(points, row, releases_map, line_color))

        limit_dataset = create_limit_dataset(points, column, row, best_results, table, line_color, is_fixed_limit_drawn)
        if limit_dataset:
            datasets.append(limit_dataset)
            is_fixed_limit_drawn = True

    return datasets


def create_release_datasets(points: list[Dict], row: str, releases_map: ReleasesMap, line_color: str) -> List[Dict]:
    """
    Create datasets separately for each release.
    """
    release_datasets = []

    for v_idx, (release, run_ids) in enumerate(releases_map.items()):
        release_points = [point for point in points if point["id"] in run_ids]

        if release_points:
            release_datasets.append({
                "label": f"{release} - {row}",
                "borderColor": line_color,
                "borderWidth": 2,
                "pointRadius": 3,
                "showLine": True,
                "data": release_points,
                "pointStyle": shapes[v_idx % len(shapes)]
            })

    return release_datasets


def create_limit_dataset(points: list[Dict], column: ColumnMetadata, row: str, best_results: dict[str, List[BestResult]],
                         table: ArgusGenericResultMetadata, line_color: str, is_fixed_limit_drawn: bool) -> Dict | None:
    """
    Create a dataset for limit lines if applicable.
    """
    key = f"{column.name}:{row}"
    higher_is_better = column.higher_is_better

    if higher_is_better is None:
        return None

    best_result_list = best_results.get(key, [])
    validation_rules_list = table.validation_rules.get(column.name, [])

    if validation_rules_list and best_result_list:
        points = calculate_limits(points, best_result_list, validation_rules_list, higher_is_better)
        limit_points = [{"x": point["x"], "y": point["limit"]} for point in points if 'limit' in point]

        if limit_points and not is_fixed_limit_drawn:
            return {
                "label": "error threshold",
                "borderColor": line_color,
                "borderWidth": 2,
                "borderDash": [5, 5],
                "fill": False,
                "data": limit_points,
                "showLine": True,
                "pointRadius": 0,
                "pointHitRadius": 0,
            }

    return None


def create_chart_options(table: ArgusGenericResultMetadata, column: ColumnMetadata, min_y: float, max_y: float) -> Dict:
    """
    Create options for Chart.js, including title and y-axis configuration.
    """
    options = copy.deepcopy(default_options)
    options["plugins"]["title"]["text"] = f"{table.name} - {column.name}"
    options["scales"]["y"]["title"]["text"] = f"[{column.unit}]" if column.unit else ""
    options["scales"]["y"]["min"] = min_y
    options["scales"]["y"]["max"] = max_y

    return options


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
    if not max_x or not min_x:
        return {}  # no data
    return {"min": min_x[:10], "max": max_x[:10]}



def _identify_most_changed_package(packages_list: list[PackageVersion]) -> str:
    version_date_changes: dict[str, set[tuple[str, str]]] = defaultdict(set)

    for package_version in packages_list:
        version_date_changes[package_version.name].add((package_version.version, package_version.date))

    return max(version_date_changes, key=lambda k: len(version_date_changes[k]))


def _split_results_by_release(packages: dict[str, list[PackageVersion]], main_package: str) -> ReleasesMap:
    releases_map = defaultdict(list)
    for run_id, package_versions in packages.items():
        for package in package_versions:
            if package.name == main_package:
                if "dev" in package.version:
                    major_version = 'dev'
                else:
                    major_version = '.'.join(package.version.split('.')[:2])
                releases_map[major_version].append(run_id)
    return releases_map


def create_chartjs(table: ArgusGenericResultMetadata, data: list[ArgusGenericResultData], best_results: dict[str, List[BestResult]],
                   releases_map: ReleasesMap, runs_details: RunsDetails, main_package: str) -> List[Dict]:
    """
    Create Chart.js-compatible graph for each column in the table.
    """
    graphs = []
    columns = [column for column in table.columns_meta if column.type != "TEXT"]

    for column in columns:
        datasets = create_datasets_for_column(table, data, best_results, releases_map, column, runs_details, main_package)

        if datasets:
            min_y, max_y = get_min_max_y(datasets)
            datasets = coerce_values_to_axis_boundaries(datasets, min_y, max_y)
            options = create_chart_options(table, column, min_y, max_y)
            graphs.append({"options": options, "data": {"datasets": datasets}})

    return graphs


class ResultsService:

    def __init__(self):
        self.cluster = ScyllaCluster.get()

    @cache
    def _get_runs_details(self, test_id: UUID) -> RunsDetails:
        plugin_query = self.cluster.prepare("SELECT id, plugin_name FROM argus_test_v2 WHERE id = ?")
        plugin_name = self.cluster.session.execute(plugin_query, parameters=(test_id,)).one()['plugin_name']
        plugin = TestRunService().get_plugin(plugin_name)
        runs_details_query = self.cluster.prepare(
            f"SELECT id, investigation_status, packages FROM {plugin.model.table_name()} WHERE test_id = ?")
        rows = self.cluster.session.execute(runs_details_query, parameters=(test_id,)).all()
        ignored_runs = [row["id"] for row in rows if row["investigation_status"].lower() == "ignored"]
        packages = {row["id"]: row["packages"] for row in rows if row["packages"] and row["id"] not in ignored_runs}
        return RunsDetails(ignored=ignored_runs, packages=packages)

    def _get_tables_metadata(self, test_id: UUID) -> list[ArgusGenericResultMetadata]:
        query_fields = ["name", "description", "columns_meta", "rows_meta", "validation_rules"]
        raw_query = (f"SELECT {','.join(query_fields)}"
                     f" FROM generic_result_metadata_v1 WHERE test_id = ?")
        query = self.cluster.prepare(raw_query)
        tables_meta = self.cluster.session.execute(query=query, parameters=(test_id,))
        return [ArgusGenericResultMetadata(**table) for table in tables_meta]

    def _get_tables_data(self, test_id: UUID, table_name: str, ignored_runs: list[RunId],
                         start_date: datetime | None = None, end_date: datetime | None = None) -> list[ArgusGenericResultData]:
        query_fields = ["run_id", "column", "row", "value", "status", "sut_timestamp"]
        raw_query = (f"SELECT {','.join(query_fields)}"
                     f" FROM generic_result_data_v1 WHERE test_id = ? AND name = ?")

        parameters = [test_id, table_name]

        if start_date:
            raw_query += " AND sut_timestamp >= ?"
            parameters.append(start_date)
        if end_date:
            raw_query += " AND sut_timestamp <= ?"
            parameters.append(end_date)

        if start_date or end_date:
            raw_query += " ALLOW FILTERING"
        query = self.cluster.prepare(raw_query)
        data = self.cluster.session.execute(query=query, parameters=tuple(parameters))
        return [ArgusGenericResultData(**cell) for cell in data if cell["run_id"] not in ignored_runs]

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

    def get_test_graphs(self, test_id: UUID, start_date: datetime | None = None, end_date: datetime | None = None):
        runs_details = self._get_runs_details(test_id)
        tables_meta = self._get_tables_metadata(test_id=test_id)
        graphs = []
        releases_filters = set()
        for table in tables_meta:
            data = self._get_tables_data(test_id=test_id, table_name=table.name, ignored_runs=runs_details.ignored,
                                         start_date=start_date, end_date=end_date)
            if not data:
                continue
            best_results = self.get_best_results(test_id=test_id, name=table.name)
            main_package = _identify_most_changed_package([pkg for sublist in runs_details.packages.values() for pkg in sublist])
            releases_map = _split_results_by_release(runs_details.packages, main_package=main_package)
            graphs.extend(create_chartjs(table, data, best_results, releases_map=releases_map, runs_details=runs_details, main_package=main_package))
            releases_filters.update(releases_map.keys())
        ticks = calculate_graph_ticks(graphs)
        return graphs, ticks, list(releases_filters)

    def is_results_exist(self, test_id: UUID):
        """Verify if results for given test id exist at all."""
        return bool(ArgusGenericResultMetadata.objects(test_id=test_id).only(["name"]).limit(1))

    def get_best_results(self, test_id: UUID, name: str) -> dict[str, List[BestResult]]:
        runs_details = self._get_runs_details(test_id)
        query_fields = ["key", "value", "result_date", "run_id"]
        raw_query = (f"SELECT {','.join(query_fields)}"
                     f" FROM generic_result_best_v2 WHERE test_id = ? and name = ?")
        query = self.cluster.prepare(raw_query)
        best_results = [BestResult(**best) for best in self.cluster.session.execute(query=query, parameters=(test_id, name))
                        if best["run_id"] not in runs_details.ignored]
        best_results_map = defaultdict(list)
        for best in sorted(best_results, key=lambda x: x.result_date):
            best_results_map.setdefault(best.key, []).append(best)
        return best_results_map

    def update_best_results(self, test_id: UUID, table_name: str, cells: list[Cell],
                            table_metadata: ArgusGenericResultMetadata, run_id: str) -> dict[str, List[BestResult]]:
        """update best results for given test_id and table_name based on cells values - if any value is better than current best"""
        higher_is_better_map = {meta["name"]: meta.higher_is_better for meta in table_metadata.columns_meta}
        best_results = self.get_best_results(test_id=test_id, name=table_name)
        for cell in cells:
            if cell.value is None:
                # textual value, skip
                continue
            key = f"{cell.column}:{cell.row}"
            if higher_is_better_map[cell.column] is None:
                # skipping updating best value when higher_is_better is not set (not enabled by user)
                continue
            current_best = best_results.get(key)[-1] if key in best_results else None
            is_better = partial(operator.gt, cell.value) if higher_is_better_map[cell.column] \
                else partial(operator.lt, cell.value)
            if current_best is None or is_better(current_best.value):
                result_date = datetime.now(timezone.utc)
                best_results[key].append(BestResult(key=key, value=cell.value, result_date=result_date, run_id=run_id))
                ArgusBestResultData(test_id=test_id, name=table_name, key=key, value=cell.value, result_date=result_date,
                                    run_id=run_id).save()
        return best_results
