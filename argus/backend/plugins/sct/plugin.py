from fastapi import APIRouter

from argus.backend.plugins.sct.testrun import (
    SCTEvent,
    SCTJunitReports,
    SCTNemesis,
    SCTNemesisDescription,
    SCTPackage,
    SCTResource,
    SCTTestRun,
    SCTUnprocessedEvent,
    StressCommand,
)
from argus.backend.plugins.sct.controller import router as sct_router
from argus.backend.plugins.core import PluginInfoBase, PluginModelBase
from argus.backend.plugins.sct.udt import (
    CloudInstanceDetails,
    CloudNodesInfo,
    CloudSetupDetails,
    NodeDescription,
    PerformanceHDRHistogram
)


class PluginInfo(PluginInfoBase):
    name: str = "scylla-cluster-tests"
    model: PluginModelBase = SCTTestRun
    controller: APIRouter = sct_router
    all_models = [
        SCTTestRun,
        SCTJunitReports,
        SCTNemesis,
        SCTNemesisDescription,
        SCTEvent,
        SCTUnprocessedEvent,
        StressCommand,
        SCTResource,
        SCTPackage,
    ]
    all_types = [
        NodeDescription,
        CloudSetupDetails,
        CloudNodesInfo,
        CloudInstanceDetails,
        PerformanceHDRHistogram,
    ]
