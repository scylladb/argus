from flask import Blueprint

from argus.backend.plugins.core import PluginInfoBase, PluginModelBase
from argus.backend.plugins.sirenada.model import SirenadaRun, SirenadaTest


class PluginInfo(PluginInfoBase):
    # pylint: disable=too-few-public-methods
    name: str = "sirenada"
    model: PluginModelBase = SirenadaRun
    controller: Blueprint = None
    all_models = [
        SirenadaRun
    ]
    all_types = [
        SirenadaTest
    ]
