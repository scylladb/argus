import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from cassandra.concurrent import execute_concurrent_with_args

from argus.backend.db import ScyllaCluster
from argus.backend.error_handlers import DataValidationError
from argus.backend.models.run_config import (
    EMPTY_PARAM_VALUES,
    NAME_BUCKET,
    RunConfigParam,
    RunConfigParamByRun,
    RunConfigParamName,
    RunConfigParamValueIndex,
)
from argus.backend.util.common import chunk

LOGGER = logging.getLogger(__name__)

CONCURRENCY = 50
SEARCH_LIMIT = 100


@dataclass(frozen=True, slots=True)
class ConfigParamFilter:
    name: str
    value: str | None


def parse_filters(raw: Any) -> list[ConfigParamFilter]:
    if not raw:
        return []
    if not isinstance(raw, list):
        raise DataValidationError("configParamFilters must be a list of {name, value} mappings")

    filters: list[ConfigParamFilter] = []
    seen: set[str] = set()
    for row in raw:
        if not isinstance(row, dict):
            raise DataValidationError("Every config parameter filter must be a {name, value} mapping")
        name = row.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        name = name.strip()
        if name in seen:
            raise DataValidationError(f"Duplicate config parameter filter for {name}")
        seen.add(name)
        value = row.get("value")
        if value is not None:
            value = str(value)
        filters.append(ConfigParamFilter(name=name, value=value or None))
    return filters


class RunConfigParamService:
    def __init__(self) -> None:
        self.database = ScyllaCluster.get()

    def search_names(self, query: str = "", limit: int = SEARCH_LIMIT) -> list[str]:
        needle = (query or "").strip().casefold()
        names: list[str] = []
        for row in RunConfigParamName.find(bucket=NAME_BUCKET).all():
            if needle and needle not in row.name.casefold():
                continue
            names.append(row.name)
            if len(names) >= limit:
                break
        return names

    def search_values(self, name: str, query: str = "", limit: int = SEARCH_LIMIT) -> list[str]:
        if not name or not name.strip():
            raise DataValidationError("A parameter name is required to search its values")

        finder = RunConfigParamValueIndex.find(name=name.strip())
        prefix = (query or "").strip()
        if prefix:
            finder = finder.filter(value__gte=prefix, value__lt=prefix + "￿")
        return [row.value for row in finder.limit(limit).all()]

    def narrow_run_ids(self, run_ids: Iterable[UUID], filters: Sequence[ConfigParamFilter]) -> set[UUID]:
        candidates = set(run_ids)
        if not filters:
            return candidates
        if not candidates:
            return set()

        for param in (f for f in filters if f.value is not None):
            candidates = self._narrow_by_value(candidates, param)
            if not candidates:
                return set()

        presence = [f for f in filters if f.value is None]
        if presence:
            candidates = self._narrow_by_presence(candidates, presence)
        return candidates

    @staticmethod
    def _narrow_by_value(candidates: set[UUID], param: ConfigParamFilter) -> set[UUID]:
        """One partition read of run_config_param, narrowed to the candidates on the clustering key."""
        by_str = {str(run_id): run_id for run_id in candidates}
        matched: set[UUID] = set()
        for slice_ in chunk(by_str.keys()):
            rows = RunConfigParam.find(name=param.name, value=param.value, run_id__in=list(slice_)).all()
            matched.update(by_str[row.run_id] for row in rows if row.run_id in by_str)
        return matched

    def _narrow_by_presence(self, candidates: set[UUID], filters: Sequence[ConfigParamFilter]) -> set[UUID]:
        """One point read per candidate run; the only shape the by-run table can answer."""
        ordered = list(candidates)
        names = sorted({param.name for param in filters})
        query = self.database.prepare(
            f"SELECT name, value FROM {RunConfigParamByRun.table_name()} WHERE run_id = ? AND name IN ?"
        )
        results = execute_concurrent_with_args(
            self.database.session, query, [(run_id, names) for run_id in ordered],
            concurrency=CONCURRENCY, raise_on_first_error=False,
        )

        matched: set[UUID] = set()
        for run_id, (success, rows) in zip(ordered, results):
            if not success:
                LOGGER.warning("Config parameter lookup failed for run %s: %s", run_id, rows)
                continue
            stored = {row["name"]: row["value"] for row in rows}
            if all(_matches(stored, param) for param in filters):
                matched.add(run_id)
        return matched


def _matches(stored: dict[str, str | None], param: ConfigParamFilter) -> bool:
    if param.name not in stored:
        return False
    value = stored[param.name]
    if param.value is None:
        return (value or "") not in EMPTY_PARAM_VALUES
    return value == param.value
