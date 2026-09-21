import pytest

from argus.backend.plugins.core import DEFAULT_STATS_PER_PARTITION_LIMIT
from argus.backend.plugins.driver_matrix_tests.model import DriverTestRun
from argus.backend.plugins.generic.model import GenericRun
from argus.backend.plugins.sct.testrun import SCTTestRun
from argus.backend.plugins.sirenada.model import SirenadaRun

PLUGIN_MODELS = [SCTTestRun, GenericRun, SirenadaRun, DriverTestRun]


@pytest.mark.parametrize("model", PLUGIN_MODELS, ids=lambda m: m.__name__)
def test_the_default_run_window_is_unchanged(model):
    assert f"PER PARTITION LIMIT {DEFAULT_STATS_PER_PARTITION_LIMIT}" in model._stats_query()


@pytest.mark.parametrize("model", PLUGIN_MODELS, ids=lambda m: m.__name__)
def test_a_wider_run_window_reaches_the_cql(model):
    assert "PER PARTITION LIMIT 50" in model._stats_query(50)
