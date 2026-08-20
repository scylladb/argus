from fastapi import APIRouter

from argus.backend.plugins.core import PluginInfoBase, PluginModelBase
from argus.backend.plugins.sirenada.model import SirenadaRun, SirenadaTest


class PluginInfo(PluginInfoBase):
    name: str = "sirenada"
    model: PluginModelBase = SirenadaRun
    controller: APIRouter | None = None
    all_models = [
        SirenadaRun
    ]
    all_types = [
        SirenadaTest
    ]
