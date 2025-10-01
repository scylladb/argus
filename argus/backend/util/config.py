import logging
from pathlib import Path

import yaml


LOGGER = logging.getLogger(__name__)


class Config:
    CONFIG = None
    CONFIG_PATHS = [
        Path(__file__).parents[3] / "config" / "argus_web.yaml",
        Path("argus_web.yaml"),
        Path("../config/argus_web.yaml"),

    ]

    @classmethod
    def locate_argus_web_config(cls) -> Path:
        for config in cls.CONFIG_PATHS:
            if config.exists():
                return config
            else:
                LOGGER.debug("Tried %s as config, not found.", config)

        raise Exception("Failed to locate web application config file!")

    @classmethod
    def load_yaml_config(cls, force: bool = False) -> dict:
        if cls.CONFIG and not force:
            return cls.CONFIG
        path = cls.locate_argus_web_config()
        with open(path, "rt", encoding="utf-8") as file:
            config = yaml.safe_load(file)

        cls.CONFIG = config
        return config
