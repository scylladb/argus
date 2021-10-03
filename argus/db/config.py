from abc import ABC, abstractmethod
from typing import Hashable, Any
from pathlib import Path
from os import getenv
import yaml
import logging


class ConfigLocationError(Exception):
    pass


class BaseConfig(ABC):
    def __init__(self):
        self.log = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def get_config(self) -> dict[Hashable, Any]:
        raise NotImplementedError()


class FileConfig(BaseConfig):
    DEFAULT_CONFIG_PATHS = (
        "argus.local.yaml",
        "argus.yaml",
        getenv("HOME") + "/.argus.yaml"
    )

    def __init__(self, filepath: str = None):
        super().__init__()
        if not filepath:
            for file in self.DEFAULT_CONFIG_PATHS:
                self.log.info("Trying %s", file)
                if Path(file).exists():
                    filepath = file
                    break

        if not filepath:
            self.log.error("All config locations were tried and no config file found")
            raise ConfigLocationError("No config file supplied and no config exists at default location")

        self.filepath = filepath

    def get_config(self) -> dict[Hashable, Any]:
        path = Path(self.filepath)
        if not path.exists():
            raise ConfigLocationError("File not found: {}".format(self.filepath))

        with open(path.absolute()) as fd:
            credentials = yaml.safe_load(fd)

        return credentials


class Config(BaseConfig):
    def __init__(self, username: str, password: str, contact_points: list[str], keyspace_name: str):
        super().__init__()
        self.config = {
            "username": username,
            "password": password,
            "contact_points": contact_points,
            "keyspace_name": keyspace_name,
        }

    def get_config(self) -> dict[Hashable, Any]:
        return self.config
