from flask import Blueprint

from argus.backend.plugins.sct.testrun import SCTEvent, SCTJunitReports, SCTTestRun, SCTUnprocessedEvent
from argus.backend.plugins.sct.controller import bp as sct_bp
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
    PerformanceHDRHistogram,
)


class PluginInfo(PluginInfoBase):
    name: str = "scylla-cluster-tests"
    model: PluginModelBase = SCTTestRun
    controller: Blueprint = sct_bp
    all_models = [
        SCTTestRun,
        SCTJunitReports,
        SCTEvent,
        SCTUnprocessedEvent,
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
