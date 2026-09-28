import json
from uuid import uuid4

from argus.backend.models.run_config import (
    NAME_BUCKET,
    RunConfigParamByRun,
    RunConfigParamName,
    RunConfigParamValueIndex,
)
from argus.backend.service.client_service import ClientService


def index_config(run_id, params: dict, config_name: str = "cfg") -> None:
    """Seed through the writer; the assertions below read the key shapes back."""
    ClientService.parse_config_values(config_name, json.dumps(params), str(run_id))


def test_by_run_rows_of_one_run_live_in_one_partition(argus_db):
    run_id = uuid4()
    index_config(run_id, {"backend": "aws", "region": "eu-west-1"})

    stored = {row.name: row.value for row in RunConfigParamByRun.find(run_id=run_id).all()}

    assert stored == {"cfg.backend": "aws", "cfg.region": "eu-west-1"}


def test_by_run_row_records_an_empty_value_as_null(argus_db):
    run_id = uuid4()
    index_config(run_id, {"empty": ""})

    assert RunConfigParamByRun.get(run_id=run_id, name="cfg.empty").value == "null"


def test_value_index_orders_values_inside_the_name_partition(argus_db):
    key = uuid4().hex
    for value in ("gce", "aws", "azure"):
        index_config(uuid4(), {key: value})

    found = RunConfigParamValueIndex.find(name=f"cfg.{key}").all()
    assert [row.value for row in found] == ["aws", "azure", "gce"]


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
    index_config(uuid4(), {unique: {"alpha": 1, "beta": 2}})

    names = [row.name for row in RunConfigParamName.find(bucket=NAME_BUCKET).all()]

    assert f"cfg.{unique}.alpha" in names
    assert f"cfg.{unique}.beta" in names
