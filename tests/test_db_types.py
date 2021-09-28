import pytest
from argus.db.db_types import NodeDescription
from pydantic import ValidationError
from dataclasses import asdict


class UdtResult:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


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
    udt = UdtResult(name="test", ip="1.1.1.1", shards=10)
    node = NodeDescription.from_db_udt(udt)

    assert asdict(node) == udt.__dict__
