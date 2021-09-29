import pytest
from argus.db.db_types import NodeDescription, NemesisStatus, NemesisRunInfo
from pydantic import ValidationError
from dataclasses import asdict
from collections import namedtuple
from time import time


def test_node_description():
    node = NodeDescription(name="test", ip="1.1.1.1", shards=10)
    assert asdict(node) == {
        "name": "test",
        "ip": "1.1.1.1",
        "shards": 10,
    }


def test_node_description_invalid_ip_address():
    with pytest.raises(ValidationError):
        NodeDescription(name="test", ip="666.666.666.666", shards=10)


def test_node_description_recreate_from_udt_set():
    nodedescription = namedtuple("NodeDescription", ["name", "ip", "shards"])
    udt = nodedescription(name="test", ip="1.1.1.1", shards=10)
    node = NodeDescription.from_db_udt(udt)

    assert asdict(node) == udt._asdict()


def test_nemesis_run_info():
    start_time = int(time())
    nem_dict = {
        "class_name": "SisyphusMonkey",
        "nemesis_name": "disrupt_me",
        "duration": 400,
        "target_node": {
            "name": "test",
            "ip": "1.1.1.1",
            "shards": 10,
        },
        "status": "started",
        "start_time": start_time,
        "end_time": 0,
        "stack_trace": ""
    }
    node = NodeDescription(name="test", ip="1.1.1.1", shards=10)
    nem = NemesisRunInfo("SisyphusMonkey", "disrupt_me", 400, target_node=node, status=NemesisStatus.Started,
                         start_time=start_time)

    assert asdict(nem) == nem_dict


def test_nemesis_run_complete_success():
    start_time = int(time())
    node = NodeDescription(name="test", ip="1.1.1.1", shards=10)
    nem = NemesisRunInfo("SisyphusMonkey", "disrupt_me", 400, target_node=node, status=NemesisStatus.Started,
                         start_time=start_time)

    nem.complete()

    assert nem.nemesis_status == NemesisStatus.Succeeded


def test_nemesis_run_complete_failure():
    start_time = int(time())
    node = NodeDescription(name="test", ip="1.1.1.1", shards=10)
    nem = NemesisRunInfo("SisyphusMonkey", "disrupt_me", 400, target_node=node, status=NemesisStatus.Started,
                         start_time=start_time)
    traceback = "Traceback: something happened"
    nem.complete(traceback)

    assert nem.nemesis_status == NemesisStatus.Failed and nem.stack_trace == traceback


def test_nemesis_run_state_enumerated_only():
    start_time = int(time())
    node = NodeDescription(name="test", ip="1.1.1.1", shards=10)
    nem = NemesisRunInfo("SisyphusMonkey", "disrupt_me", 400, target_node=node, status=NemesisStatus.Started,
                         start_time=start_time)
    with pytest.raises(ValueError):
        nem.nemesis_status = "AGJKSDHGKJSG"


def test_nemesis_run_state_valid_enum_coercible():
    start_time = int(time())
    node = NodeDescription(name="test", ip="1.1.1.1", shards=10)
    nem = NemesisRunInfo("SisyphusMonkey", "disrupt_me", 400, target_node=node, status=NemesisStatus.Started,
                         start_time=start_time)

    nem.nemesis_status = "running"

    assert nem.nemesis_status == NemesisStatus.Running
