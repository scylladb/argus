import json
from uuid import uuid4

import pytest

from argus.backend.error_handlers import DataValidationError
from argus.backend.models.run_config import NAME_BUCKET, RunConfigParamName, RunConfigParamValueIndex
from argus.backend.service.client_service import ClientService
from argus.backend.models.run_config import EMPTY_PARAM_VALUES
from argus.backend.service.run_config_params import (
    ConfigParamFilter,
    RunConfigParamService,
    _matches,
    parse_filters,
)


async def store_params(run_id, params: dict) -> None:
    """Index a run's parameters through the writer, under the ``cfg.`` prefix."""
    await ClientService.parse_config_values("cfg", json.dumps(params), str(run_id))


def test_parse_filters_reads_a_concrete_value_and_an_any_value_row():
    filters = parse_filters([
        {"name": "sct_config.backend", "value": "aws"},
        {"name": "sct_config.unified_package", "value": None},
    ])

    assert filters == [
        ConfigParamFilter(name="sct_config.backend", value="aws"),
        ConfigParamFilter(name="sct_config.unified_package", value=None),
    ]


def test_parse_filters_drops_a_blank_row():
    assert parse_filters([{"name": "", "value": "aws"}, {"name": "   ", "value": None}]) == []


def test_parse_filters_coerces_a_non_string_value():
    assert parse_filters([{"name": "cfg.count", "value": 10}]) == [ConfigParamFilter(name="cfg.count", value="10")]


def test_parse_filters_reads_an_empty_value_as_any_value():
    """The editor stores "" when a row leaves Any unticked without a value picked."""
    assert parse_filters([{"name": "cfg.a", "value": ""}]) == [ConfigParamFilter(name="cfg.a", value=None)]


def test_parse_filters_accepts_nothing():
    assert parse_filters(None) == []
    assert parse_filters([]) == []


def test_parse_filters_rejects_a_duplicate_name():
    with pytest.raises(DataValidationError):
        parse_filters([{"name": "cfg.backend", "value": "aws"}, {"name": "cfg.backend", "value": "gce"}])


def test_parse_filters_rejects_garbage():
    with pytest.raises(DataValidationError):
        parse_filters({"name": "cfg.backend"})
    with pytest.raises(DataValidationError):
        parse_filters(["cfg.backend"])


async def test_an_empty_filter_list_passes_every_run_through(argus_db):
    run_ids = {uuid4(), uuid4()}

    assert await RunConfigParamService().narrow_run_ids(run_ids, []) == run_ids


async def test_no_candidates_yields_nothing(argus_db):
    filters = [ConfigParamFilter(name="cfg.backend", value="aws")]

    assert await RunConfigParamService().narrow_run_ids([], filters) == set()


async def test_a_concrete_value_keeps_only_the_matching_run(argus_db):
    matching, other = uuid4(), uuid4()
    await store_params(matching, {"backend": "aws"})
    await store_params(other, {"backend": "gce"})

    found = await RunConfigParamService().narrow_run_ids(
        [matching, other], [ConfigParamFilter(name="cfg.backend", value="aws")]
    )

    assert found == {matching}


async def test_a_run_absent_from_the_table_is_excluded(argus_db):
    known, unknown = uuid4(), uuid4()
    await store_params(known, {"backend": "aws"})

    found = await RunConfigParamService().narrow_run_ids(
        [known, unknown], [ConfigParamFilter(name="cfg.backend", value="aws")]
    )

    assert found == {known}


@pytest.mark.parametrize("stored", ["", None])
async def test_any_value_rejects_the_empty_encodings(argus_db, stored):
    """parse_config_values turns "" into "null" and None into "None"."""
    run_id = uuid4()
    await store_params(run_id, {"unified_package": stored})

    found = await RunConfigParamService().narrow_run_ids(
        [run_id], [ConfigParamFilter(name="cfg.unified_package", value=None)]
    )

    assert found == set()


async def test_any_value_accepts_a_real_value(argus_db):
    run_id = uuid4()
    await store_params(run_id, {"unified_package": "http://example.invalid/pkg.tar.gz"})

    found = await RunConfigParamService().narrow_run_ids(
        [run_id], [ConfigParamFilter(name="cfg.unified_package", value=None)]
    )

    assert found == {run_id}


async def test_two_rows_and_together(argus_db):
    both, one = uuid4(), uuid4()
    await store_params(both, {"backend": "aws", "unified_package": "pkg"})
    await store_params(one, {"backend": "aws", "unified_package": ""})

    found = await RunConfigParamService().narrow_run_ids(
        [both, one],
        [
            ConfigParamFilter(name="cfg.backend", value="aws"),
            ConfigParamFilter(name="cfg.unified_package", value=None),
        ],
    )

    assert found == {both}


async def test_search_names_matches_a_substring_case_insensitively(argus_db):
    unique = uuid4().hex
    for suffix in ("Unified_Package", "backend"):
        row = RunConfigParamName.model_construct()
        row.bucket = NAME_BUCKET
        row.name = f"cfg.{unique}.{suffix}"
        await row.save()

    found = await RunConfigParamService().search_names(f"{unique}.unified")

    assert found == [f"cfg.{unique}.Unified_Package"]


async def test_search_names_honours_the_limit(argus_db):
    assert len(await RunConfigParamService().search_names("", limit=2)) <= 2


async def test_search_values_matches_by_prefix_and_honours_the_limit(argus_db):
    name = f"cfg.{uuid4().hex}"
    for value in ("aws", "aws-eu", "gce"):
        row = RunConfigParamValueIndex.model_construct()
        row.name = name
        row.value = value
        await row.save()

    service = RunConfigParamService()

    assert await service.search_values(name, "aws") == ["aws", "aws-eu"]
    assert await service.search_values(name) == ["aws", "aws-eu", "gce"]
    assert await service.search_values(name, limit=1) == ["aws"]


async def test_search_values_requires_a_name(argus_db):
    with pytest.raises(DataValidationError):
        await RunConfigParamService().search_values("")


@pytest.mark.parametrize("stored", sorted(EMPTY_PARAM_VALUES))
def test_the_empty_encodings_never_satisfy_an_is_set_row(stored):
    """Covers "", which the writer cannot produce but the model tolerates."""
    assert _matches({"cfg.a": stored}, ConfigParamFilter(name="cfg.a", value=None)) is False


def test_a_present_value_satisfies_an_is_set_row():
    assert _matches({"cfg.a": "aws"}, ConfigParamFilter(name="cfg.a", value=None)) is True
