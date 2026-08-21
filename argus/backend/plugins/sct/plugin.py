from fastapi import APIRouter

from argus.backend.plugins.sct.testrun import SCTEvent, SCTJunitReports, SCTResource, SCTNemesis, SCTTestRun, SCTUnprocessedEvent, StressCommand
from argus.backend.plugins.sct.controller import router as sct_router
from argus.backend.plugins.core import PluginInfoBase, PluginModelBase
from argus.backend.plugins.sct.udt import (
    CloudInstanceDetails,
    CloudNodesInfo,
    CloudResource,
    CloudSetupDetails,
    EventsBySeverity,
    NemesisRunInfo,
    NodeDescription,
    PackageVersion,
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
        SCTEvent,
        SCTUnprocessedEvent,
        StressCommand,
        SCTResource,
    ]
    all_types = [
        NemesisRunInfo,
        NodeDescription,
        EventsBySeverity,
        CloudResource,
        CloudSetupDetails,
        CloudNodesInfo,
        CloudInstanceDetails,
        PackageVersion,
        PerformanceHDRHistogram,
    ]
