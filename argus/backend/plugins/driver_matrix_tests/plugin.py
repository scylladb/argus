from fastapi import APIRouter

from argus.backend.plugins.core import PluginInfoBase, PluginModelBase
from argus.backend.plugins.driver_matrix_tests.model import DriverTestRun
from argus.backend.plugins.driver_matrix_tests.controller import router as driver_matrix_router
from argus.backend.plugins.driver_matrix_tests.udt import TestCollection, EnvironmentInfo, TestCase, TestSuite


class PluginInfo(PluginInfoBase):
    name: str = "driver-matrix-tests"
    model: PluginModelBase = DriverTestRun
    controller: APIRouter = driver_matrix_router
    all_models = [
        DriverTestRun,
    ]
    all_types = [
        TestCollection,
        TestSuite,
        TestCase,
        EnvironmentInfo
    ]
