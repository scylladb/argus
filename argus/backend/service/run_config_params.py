import asyncio
import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from cassandra import DriverException

from argus.backend.error_handlers import DataValidationError
from argus.backend.models.run_config import (
    EMPTY_PARAM_VALUES,
    NAME_BUCKET,
    RunConfigParam,
    RunConfigParamByRun,
    RunConfigParamName,
    RunConfigParamValueIndex,
)
from argus.backend.util.common import chunk, gather_limited

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
    async def search_names(self, query: str = "", limit: int = SEARCH_LIMIT) -> list[str]:
        needle = (query or "").strip().casefold()
        names: list[str] = []
        for row in await RunConfigParamName.find(bucket=NAME_BUCKET).all():
            if needle and needle not in row.name.casefold():
                continue
            names.append(row.name)
            if len(names) >= limit:
                break
        return names

    async def search_values(self, name: str, query: str = "", limit: int = SEARCH_LIMIT) -> list[str]:
        if not name or not name.strip():
            raise DataValidationError("A parameter name is required to search its values")

        finder = RunConfigParamValueIndex.find(name=name.strip())
        prefix = (query or "").strip()
        if prefix:
            finder = finder.filter(value__gte=prefix, value__lt=prefix + "￿")
        return [row.value for row in await finder.limit(limit).all()]

    async def narrow_run_ids(self, run_ids: Iterable[UUID], filters: Sequence[ConfigParamFilter]) -> set[UUID]:
        candidates = set(run_ids)
        if not filters:
            return candidates
        if not candidates:
            return set()

        for param in (f for f in filters if f.value is not None):
            candidates = await self._narrow_by_value(candidates, param)
            if not candidates:
                return set()

        presence = [f for f in filters if f.value is None]
        if presence:
            candidates = await self._narrow_by_presence(candidates, presence)
        return candidates

    @staticmethod
    async def _narrow_by_value(candidates: set[UUID], param: ConfigParamFilter) -> set[UUID]:
        """One partition read of run_config_param, narrowed to the candidates on the clustering key."""
        by_str = {str(run_id): run_id for run_id in candidates}
        queries = [
            RunConfigParam.find(name=param.name, value=param.value, run_id__in=list(slice_)).all()
            for slice_ in chunk(by_str.keys())
        ]
        matched: set[UUID] = set()
        for rows in await asyncio.gather(*queries):
            matched.update(by_str[row.run_id] for row in rows if row.run_id in by_str)
        return matched

    @staticmethod
    async def _narrow_by_presence(candidates: set[UUID], filters: Sequence[ConfigParamFilter]) -> set[UUID]:
        """One partition read per candidate run; the only shape the by-run table can answer."""
        ordered = list(candidates)
        names = sorted({param.name for param in filters})

        async def stored_params(run_id: UUID) -> dict[str, str | None] | None:
            try:
                rows = await RunConfigParamByRun.find(run_id=run_id, name__in=names) \
                    .only("name", "value").values_list("name", "value").all()
            except DriverException as exc:
                LOGGER.warning("Config parameter lookup failed for run %s: %s", run_id, exc)
                return None
            return dict(rows)

        matched: set[UUID] = set()
        results = await gather_limited((stored_params(run_id) for run_id in ordered), limit=CONCURRENCY)
        for run_id, stored in zip(ordered, results):
            if stored is None:
                continue
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
