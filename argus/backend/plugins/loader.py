from pathlib import Path
import typing
from argus.backend.plugins.core import PluginInfoBase


class PluginModule(typing.Protocol):
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
