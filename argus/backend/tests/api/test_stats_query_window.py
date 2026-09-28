import pytest

from argus.backend.plugins.core import DEFAULT_STATS_PER_PARTITION_LIMIT
from argus.backend.plugins.driver_matrix_tests.model import DriverTestRun
from argus.backend.plugins.generic.model import GenericRun
from argus.backend.plugins.sct.testrun import SCTTestRun
from argus.backend.plugins.sirenada.model import SirenadaRun

PLUGIN_MODELS = [SCTTestRun, GenericRun, SirenadaRun, DriverTestRun]


class RecordingQuery:
    """Stands in for the coodie query chain and records the per-partition window it was given."""

    def __init__(self, recorded: list[int]):
        self.recorded = recorded

    def per_partition_limit(self, limit: int) -> "RecordingQuery":
        self.recorded.append(limit)
        return self

    def only(self, *columns) -> "RecordingQuery":
        return self

    def values_list(self, *columns) -> "RecordingQuery":
        return self

    def consistency(self, level: str) -> "RecordingQuery":
        return self

    async def all(self) -> list:
        return []


def test_the_default_run_window_is_fifteen_runs_per_test():
    assert DEFAULT_STATS_PER_PARTITION_LIMIT == 15


@pytest.mark.parametrize("model", PLUGIN_MODELS, ids=lambda m: m.__name__)
def test_the_stats_read_carries_the_columns_the_dashboard_needs(model):
    columns = model._stats_columns()

    assert {"build_id", "build_number", "scylla_version"} <= set(columns)


@pytest.mark.parametrize("model", PLUGIN_MODELS, ids=lambda m: m.__name__)
async def test_the_stats_read_uses_the_default_run_window(model, monkeypatch):
    recorded = []
    monkeypatch.setattr(model, "find", classmethod(lambda cls, **kwargs: RecordingQuery(recorded)))

    await model.get_stats_for_release(release=None, build_ids=["b1"])

    assert recorded == [DEFAULT_STATS_PER_PARTITION_LIMIT]


@pytest.mark.parametrize("model", PLUGIN_MODELS, ids=lambda m: m.__name__)
async def test_a_wider_run_window_reaches_the_query(model, monkeypatch):
    recorded = []
    monkeypatch.setattr(model, "find", classmethod(lambda cls, **kwargs: RecordingQuery(recorded)))

    await model.get_stats_for_release(release=None, build_ids=["b1"], per_partition_limit=50)

    assert recorded == [50]
