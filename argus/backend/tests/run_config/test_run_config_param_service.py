from uuid import uuid4

import pytest

from argus.backend.error_handlers import DataValidationError
from argus.backend.models.run_config import (
    NAME_BUCKET,
    RunConfigParam,
    RunConfigParamByRun,
    RunConfigParamName,
    RunConfigParamValueIndex,
)
from argus.backend.service.run_config_params import (
    ConfigParamFilter,
    RunConfigParamService,
    parse_filters,
)


def store_params(run_id, params: dict[str, str | None]) -> None:
    """Write the same rows parse_config_values does, so both read paths are covered."""
    for name, value in params.items():
        by_run = RunConfigParamByRun.model_construct()
        by_run.run_id = run_id
        by_run.name = name
        by_run.value = value
        by_run.save()

        legacy = RunConfigParam.model_construct()
        legacy.name = name
        legacy.value = value if value is not None else "null"
        legacy.run_id = str(run_id)
        legacy.save()


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


def test_an_empty_filter_list_passes_every_run_through(argus_db):
    run_ids = {uuid4(), uuid4()}

    assert RunConfigParamService().narrow_run_ids(run_ids, []) == run_ids


def test_no_candidates_yields_nothing(argus_db):
    filters = [ConfigParamFilter(name="cfg.backend", value="aws")]

    assert RunConfigParamService().narrow_run_ids([], filters) == set()


def test_a_concrete_value_keeps_only_the_matching_run(argus_db):
    matching, other = uuid4(), uuid4()
    store_params(matching, {"cfg.backend": "aws"})
    store_params(other, {"cfg.backend": "gce"})

    found = RunConfigParamService().narrow_run_ids(
        [matching, other], [ConfigParamFilter(name="cfg.backend", value="aws")]
    )

    assert found == {matching}


def test_a_run_absent_from_the_table_is_excluded(argus_db):
    known, unknown = uuid4(), uuid4()
    store_params(known, {"cfg.backend": "aws"})

    found = RunConfigParamService().narrow_run_ids(
        [known, unknown], [ConfigParamFilter(name="cfg.backend", value="aws")]
    )

    assert found == {known}


@pytest.mark.parametrize("stored", ["", "null", "None"])
def test_any_value_rejects_the_empty_encodings(argus_db, stored):
    run_id = uuid4()
    store_params(run_id, {"cfg.unified_package": stored})

    found = RunConfigParamService().narrow_run_ids(
        [run_id], [ConfigParamFilter(name="cfg.unified_package", value=None)]
    )

    assert found == set()


def test_any_value_accepts_a_real_value(argus_db):
    run_id = uuid4()
    store_params(run_id, {"cfg.unified_package": "http://example.invalid/pkg.tar.gz"})

    found = RunConfigParamService().narrow_run_ids(
        [run_id], [ConfigParamFilter(name="cfg.unified_package", value=None)]
    )

    assert found == {run_id}


def test_two_rows_and_together(argus_db):
    both, one = uuid4(), uuid4()
    store_params(both, {"cfg.backend": "aws", "cfg.unified_package": "pkg"})
    store_params(one, {"cfg.backend": "aws", "cfg.unified_package": "null"})

    found = RunConfigParamService().narrow_run_ids(
        [both, one],
        [
            ConfigParamFilter(name="cfg.backend", value="aws"),
            ConfigParamFilter(name="cfg.unified_package", value=None),
        ],
    )

    assert found == {both}


def test_search_names_matches_a_substring_case_insensitively(argus_db):
    unique = uuid4().hex
    for suffix in ("Unified_Package", "backend"):
        row = RunConfigParamName.model_construct()
        row.bucket = NAME_BUCKET
        row.name = f"cfg.{unique}.{suffix}"
        row.save()

    found = RunConfigParamService().search_names(f"{unique}.unified")

    assert found == [f"cfg.{unique}.Unified_Package"]


def test_search_names_honours_the_limit(argus_db):
    assert len(RunConfigParamService().search_names("", limit=2)) <= 2


def test_search_values_matches_by_prefix_and_honours_the_limit(argus_db):
    name = f"cfg.{uuid4().hex}"
    for value in ("aws", "aws-eu", "gce"):
        row = RunConfigParamValueIndex.model_construct()
        row.name = name
        row.value = value
        row.save()

    service = RunConfigParamService()

    assert service.search_values(name, "aws") == ["aws", "aws-eu"]
    assert service.search_values(name) == ["aws", "aws-eu", "gce"]
    assert service.search_values(name, limit=1) == ["aws"]


def test_search_values_requires_a_name(argus_db):
    with pytest.raises(DataValidationError):
        RunConfigParamService().search_values("")
