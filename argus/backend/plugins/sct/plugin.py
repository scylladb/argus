from fastapi import APIRouter
from flask import Blueprint

from argus.backend.plugins.sct.testrun import SCTEvent, SCTJunitReports, SCTResource, SCTNemesis, SCTTestRun, SCTUnprocessedEvent, StressCommand
from argus.backend.plugins.sct.controller import bp as sct_bp, router as sct_router
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
    controller_bp: Blueprint = sct_bp
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
