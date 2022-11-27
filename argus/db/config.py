from abc import ABC
from typing import Hashable, Any
from pathlib import Path
from os import getenv
import logging
import yaml

LOGGER = logging.getLogger(__name__)


class ConfigLocationError(Exception):
    pass


class BaseConfig(ABC):
    def __init__(self):
        pass

    @property
    def as_dict(self) -> dict[Hashable, Any]:
        raise NotImplementedError()

    @property
    def username(self) -> str:
        raise NotImplementedError()

    @property
    def password(self) -> str:
        raise NotImplementedError()

    @property
    def contact_points(self) -> list[str]:
        raise NotImplementedError()

    @property
    def keyspace_name(self) -> str:
        raise NotImplementedError()

    @property
    def address_mapping(self) -> dict:
        return NotImplementedError()


class FileConfig(BaseConfig):
    @property
    def username(self):
        return self.as_dict.get("username")

    @property
    def password(self) -> str:
        return self.as_dict.get("password")

    @property
    def contact_points(self) -> list[str]:
        return self.as_dict.get("contact_points")

    @property
    def keyspace_name(self) -> str:
        return self.as_dict.get("keyspace_name")

    @property
    def address_mapping(self) -> dict:
        return self.as_dict.get("address_mapping")

    DEFAULT_CONFIG_PATHS = (
        "./config/argus.local.yaml",
        "argus.local.yaml",
        "argus.yaml",
        getenv("HOME") + "/.argus.yaml"
    )

    def __init__(self, filepath: str = None):
        super().__init__()
        if not filepath:
            for file in self.DEFAULT_CONFIG_PATHS:
                LOGGER.info("Trying %s", file)
                if Path(file).exists():
                    filepath = file
                    break

        if not filepath:
            LOGGER.error("All config locations were tried and no config file found")
            raise ConfigLocationError("No config file supplied and no config exists at default location")

        self.filepath = filepath
        self._credentials = None

    @property
    def as_dict(self) -> dict[Hashable, Any]:
        if self._credentials:
            return self._credentials
        path = Path(self.filepath)
        if not path.exists():
            raise ConfigLocationError(f"File not found: {self.filepath}")

        with open(path.absolute(), "rt", encoding="utf-8") as file:
            self._credentials = yaml.safe_load(file)

        return self._credentials


class Config(BaseConfig):
    @property
    def username(self) -> str:
        return self.as_dict.get("username")

    @property
    def password(self) -> str:
        return self.as_dict.get("password")

    @property
    def contact_points(self) -> list[str]:
        return self.as_dict.get("contact_points")

    @property
    def keyspace_name(self) -> str:
        return self.as_dict.get("keyspace_name")

    @property
    def address_mapping(self) -> dict:
        return self.as_dict.get("address_mapping")

    def __init__(self, username: str, password: str, contact_points: list[str], keyspace_name: str, address_mapping: dict | None = None):
        super().__init__()
        self._config = {
            "username": username,
            "password": password,
            "contact_points": contact_points,
            "keyspace_name": keyspace_name,
            "address_mapping": address_mapping,
        }

    @property
    def as_dict(self) -> dict[Hashable, Any]:
        return self._config
