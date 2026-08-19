from fastapi import APIRouter
from flask import Blueprint

from argus.backend.plugins.core import PluginInfoBase, PluginModelBase
from argus.backend.plugins.generic.model import GenericRun


class PluginInfo(PluginInfoBase):
    name: str = "generic"
    model: PluginModelBase = GenericRun
    controller: APIRouter | None = None
    controller_bp: Blueprint | None = None
    all_models = [
        GenericRun
    ]
    all_types = [
    ]
