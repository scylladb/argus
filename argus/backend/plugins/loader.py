from pathlib import Path
import typing
from argus.backend.plugins.core import PluginInfoBase
from argus.backend.plugins.core import PluginModelBase


class PluginModule(typing.Protocol):
    # pylint: disable=too-few-public-methods
    PluginInfo: PluginInfoBase


def plugin_loader() -> dict[str, PluginInfoBase]:
    loader_path = Path(__file__).parent
    plugin_dirs = [p for p in loader_path.glob("*") if p.is_dir()]
    modules = {}
    parent_module = ".".join(__name__.split(".")[:-1])
    for directory in plugin_dirs:
        if (plugin_path := directory / "plugin.py").exists():
            rel_path = str(plugin_path.relative_to(loader_path))
            module_path = rel_path.replace("/", ".").replace(".py", "")
            module: PluginModule = __import__(
                f"{parent_module}.{module_path}",
                globals=globals(),
                fromlist=("PluginInfo",)
            )
            plugin = module.PluginInfo
            modules[plugin.name] = plugin

    return modules


AVAILABLE_PLUGINS = plugin_loader()


def all_plugin_models(include_all=False) -> list[PluginModelBase]:
    return [model for plugin in AVAILABLE_PLUGINS.values() for model in plugin.all_models if issubclass(model, PluginModelBase) or include_all]


def all_plugin_types():
    return [user_type for plugin in AVAILABLE_PLUGINS.values() for user_type in plugin.all_types]
