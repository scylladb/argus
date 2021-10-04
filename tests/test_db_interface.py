import json
from uuid import UUID, uuid4

import pytest
import logging
from mocks.mock_cluster import MockCluster, MockSession
from argus.db.config import Config
from argus.db.interface import ArgusDatabase, ArgusInterfaceSingletonError, ArgusInterfaceNameError, \
    ArgusInterfaceSchemaError

LOGGER = logging.getLogger(__name__)


def test_interface_connection(mock_cluster):
    db = ArgusDatabase.get()
    assert not db.session.is_shutdown
    ArgusDatabase.destroy()
    assert db.session.is_shutdown


def test_interface_from_config(mock_cluster):
    db = ArgusDatabase.from_config(
        config=Config(username="a", password="a", contact_points=["127.0.0.1", "127.0.0.2", "127.0.0.3"],
                      keyspace_name="example"))
    db.destroy()

    assert MockSession.MOCK_CURRENT_KEYSPACE == "example"


def test_interface_unable_to_init_from_config_twice(mock_cluster):
    db = ArgusDatabase.get()

    with pytest.raises(ArgusInterfaceSingletonError):
        db = ArgusDatabase.from_config(
            config=Config(username="a", password="a", contact_points=["127.0.0.1", "127.0.0.2", "127.0.0.3"],
                          keyspace_name="example"))
    db.destroy()


def test_interface_is_singleton(mock_cluster):
    db = ArgusDatabase.get()

    db2 = ArgusDatabase.get()

    assert id(db) == id(db2)


def test_inteface_supported_types(mock_cluster):
    db = ArgusDatabase.get()

    for typecls in [int, float, str, UUID]:
        assert db.is_native_type(typecls)
    db.destroy()


def test_interface_schema_init(mock_cluster, preset_test_details_schema, simple_primary_key):
    db = ArgusDatabase.get()

    schema = {
        **simple_primary_key,
        **preset_test_details_schema,
    }

    db.init_table("test_table", schema)
    assert MockSession.MOCK_LAST_QUERY[0] == "CREATE TABLE IF NOT EXISTS test_table" \
                                             "(name varchar , scm_revision_id varchar , started_by varchar , " \
                                             "build_job_name varchar , build_job_url varchar , start_time varint ," \
                                             " yaml_test_duration varint , config_files list<varchar> , " \
                                             "packages list<frozen<PackageVersion>> , end_time varint , " \
                                             "PRIMARY KEY (id, ))"
    db.destroy()


def test_interface_init_table_twice(mock_cluster, preset_test_details_schema, simple_primary_key):
    db = ArgusDatabase.get()

    schema = {
        **simple_primary_key,
        **preset_test_details_schema,
    }

    db.init_table("test_table", schema)

    second_result = db.init_table("test_table", schema)

    db.destroy()
    assert second_result[1] == "Table test_table already initialized"


def test_interface_prepare_cache(mock_cluster):
    db = ArgusDatabase.get()

    statement = db.prepare_query_for_table("example", "test", "SELECT * FROM example")

    cached_statement = db.prepared_statements.get("example_test")

    db.destroy()

    assert id(statement) == id(cached_statement)


def test_interface_keyspace_naming(mock_cluster):
    with pytest.raises(ArgusInterfaceNameError):
        db = ArgusDatabase.from_config(
            Config(username="a", password="b", contact_points=["127.0.0.1"], keyspace_name="has.a.dot"))


def test_interface_fetch(monkeypatch, mock_cluster):
    db = ArgusDatabase.get()

    class ResultSet:
        @staticmethod
        def one():
            return True

    monkeypatch.setattr(MockSession, "MOCK_RESULT_SET", ResultSet())

    result = db.fetch("example", uuid4())
    db.destroy()

    assert result


def test_interface_fetch_non_existing(monkeypatch, mock_cluster):
    db = ArgusDatabase.get()

    class ResultSet:
        @staticmethod
        def one():
            return None

    monkeypatch.setattr(MockSession, "MOCK_RESULT_SET", ResultSet())

    result = db.fetch("example", uuid4())
    db.destroy()

    assert not result


def test_interface_insert(mock_cluster):
    db = ArgusDatabase.get()
    data = {
        "id": str(uuid4()),
        "column": "value",
        "number": 30,
        "float": 1.5,
        "list": [1, 2, 3],
    }
    db.insert("example", data)

    parameters = MockSession.MOCK_LAST_QUERY[1][0]

    db.destroy()

    assert json.loads(parameters) == data


def test_interface_update(mock_cluster, simple_primary_key, preset_test_details_schema, preset_test_details_serialized):
    db = ArgusDatabase.get()

    schema = {
        **simple_primary_key,
        **preset_test_details_schema,
    }

    db.init_table("test_table", schema)
    test_id = str(uuid4())
    data = {
        "id": test_id,
        **preset_test_details_serialized
    }

    db.update("test_table", data)
    db.destroy()

    assert str(MockSession.MOCK_LAST_QUERY[1][-1:][0]) == test_id


def test_interface_update_uninitialized_table(mock_cluster, simple_primary_key, preset_test_details_schema,
                                              preset_test_details_serialized):
    db = ArgusDatabase.get()
    with pytest.raises(ArgusInterfaceSchemaError):
        db.update("test_table", {})

    db.destroy()


def test_interface_update_missing_primary_keys(mock_cluster, simple_primary_key, preset_test_details_schema,
                                               preset_test_details_serialized):
    db = ArgusDatabase.get()

    schema = {
        **simple_primary_key,
        **preset_test_details_schema,
    }

    db.init_table("test_table", schema)
    data = {
        **preset_test_details_serialized
    }
    with pytest.raises(ArgusInterfaceSchemaError):
        db.update("test_table", data)
    db.destroy()
