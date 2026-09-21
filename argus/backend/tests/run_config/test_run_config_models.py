from uuid import uuid4

from argus.backend.models.run_config import (
    NAME_BUCKET,
    RunConfigParamByRun,
    RunConfigParamName,
    RunConfigParamValueIndex,
)


def test_by_run_rows_of_one_run_live_in_one_partition(argus_db):
    run_id = uuid4()
    for name, value in (("cfg.backend", "aws"), ("cfg.region", "eu-west-1")):
        row = RunConfigParamByRun.model_construct()
        row.run_id = run_id
        row.name = name
        row.value = value
        row.save()

    stored = {row.name: row.value for row in RunConfigParamByRun.find(run_id=run_id).all()}

    assert stored == {"cfg.backend": "aws", "cfg.region": "eu-west-1"}


def test_by_run_row_accepts_a_missing_value(argus_db):
    run_id = uuid4()
    row = RunConfigParamByRun.model_construct()
    row.run_id = run_id
    row.name = "cfg.empty"
    row.value = None
    row.save()

    assert RunConfigParamByRun.get(run_id=run_id, name="cfg.empty").value is None


def test_value_index_orders_values_inside_the_name_partition(argus_db):
    name = f"cfg.{uuid4().hex}"
    for value in ("gce", "aws", "azure"):
        row = RunConfigParamValueIndex.model_construct()
        row.name = name
        row.value = value
        row.save()

    assert [row.value for row in RunConfigParamValueIndex.find(name=name).all()] == ["aws", "azure", "gce"]


def test_value_index_supports_a_bounded_prefix_range(argus_db):
    name = f"cfg.{uuid4().hex}"
    for value in ("aws", "aws-eu", "gce"):
        row = RunConfigParamValueIndex.model_construct()
        row.name = name
        row.value = value
        row.save()

    found = RunConfigParamValueIndex.find(name=name, value__gte="aw", value__lt="aw" + "￿").all()

    assert [row.value for row in found] == ["aws", "aws-eu"]


def test_the_name_catalogue_is_one_partition(argus_db):
    unique = uuid4().hex
    for suffix in ("alpha", "beta"):
        row = RunConfigParamName.model_construct()
        row.bucket = NAME_BUCKET
        row.name = f"cfg.{unique}.{suffix}"
        row.save()

    names = [row.name for row in RunConfigParamName.find(bucket=NAME_BUCKET).all()]

    assert f"cfg.{unique}.alpha" in names
    assert f"cfg.{unique}.beta" in names
