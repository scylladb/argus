from flask import Blueprint

from argus.backend.plugins.sct.testrun import SCTTestRun
from argus.backend.plugins.sct.controller import bp as sct_bp
from argus.backend.plugins.core import PluginInfoBase, PluginModelBase


class PluginInfo(PluginInfoBase):
    name: str = "scylla-cluster-tests"
    model: PluginModelBase = SCTTestRun
    controller: Blueprint = sct_bp
