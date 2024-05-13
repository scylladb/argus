from flask import Blueprint

from argus.backend.plugins.sct.testrun import SCTJunitReports, SCTTestRun
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
    # pylint: disable=too-few-public-methods
    name: str = "scylla-cluster-tests"
    model: PluginModelBase = SCTTestRun
    controller: Blueprint = sct_bp
    all_models = [
        SCTTestRun,
        SCTJunitReports,
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
