import copy
import logging
import math
from typing import List, Dict, Any
from uuid import UUID

from argus.backend.db import ScyllaCluster
from argus.backend.models.result import ArgusGenericResultMetadata, ArgusGenericResultData

LOGGER = logging.getLogger(__name__)

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


def get_sorted_data_for_column_and_row(data: List[Dict[str, Any]], column: str, row: str) -> List[Dict[str, Any]]:
    return sorted([{"x": entry.sut_timestamp.strftime('%Y-%m-%dT%H:%M:%SZ'),
                    "y": entry.value,
                    "id": entry.run_id}
                   for entry in data if entry['column'] == column and entry['row'] == row],
                  key=lambda x: x['x'])


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
        options["scales"]["y"]["title"]["text"] = f"[{column.unit}]"
        options["scales"]["y"]["min"] = min_y
        options["scales"]["y"]["max"] = max_y
        graphs.append({"options": options, "data":
            {"datasets": datasets}})
    return graphs


class ResultsService:

    def __init__(self, database_session=None):
        self.session = database_session if database_session else ScyllaCluster.get_session()

    def get_results(self, test_id: UUID):
        graphs = []
        res = ArgusGenericResultMetadata.objects(test_id=test_id).all()
        for table in res:
            data = ArgusGenericResultData.objects(test_id=test_id, name=table.name).all()
            graphs.extend(create_chartjs(table, data))
        return graphs
