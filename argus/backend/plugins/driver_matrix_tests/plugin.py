from flask import Blueprint

from argus.backend.plugins.core import PluginInfoBase, PluginModelBase
from argus.backend.plugins.driver_matrix_tests.model import DriverTestRun
from argus.backend.plugins.driver_matrix_tests.udt import TestCollection, EnvironmentInfo, TestCase, TestSuite


class PluginInfo(PluginInfoBase):
    # pylint: disable=too-few-public-methods
    name: str = "driver-matrix-tests"
    model: PluginModelBase = DriverTestRun
    controller: Blueprint = None
    all_models = [
        DriverTestRun,
    ]
    all_types = [
        TestCollection,
        TestSuite,
        TestCase,
        EnvironmentInfo
    ]
