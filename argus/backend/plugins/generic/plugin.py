from flask import Blueprint

from argus.backend.plugins.core import PluginInfoBase, PluginModelBase
from argus.backend.plugins.generic.model import GenericRun


class PluginInfo(PluginInfoBase):
    # pylint: disable=too-few-public-methods
    name: str = "generic"
    model: PluginModelBase = GenericRun
    controller: Blueprint = None
    all_models = [
        GenericRun
    ]
    all_types = [
    ]
