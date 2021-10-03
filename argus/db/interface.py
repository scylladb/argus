from typing import KeysView, Union, Any, get_args as get_type_args, get_origin as get_type_origin
from types import GenericAlias
import cassandra.cluster
from cassandra.auth import PlainTextAuthProvider
from cassandra.cqltypes import UUIDType, IntegerType, VarcharType, FloatType
from argus.db.config import BaseConfig, FileConfig
from argus.db.db_types import ColumnInfo, CollectionHint, ArgusUDTBase
from uuid import UUID
from hashlib import sha1
from dataclasses import fields as dataclass_fields
import re
import logging
import json


class ArgusInterfaceSingletonError(Exception):
    pass


class ArgusInterfaceDatabaseConnectionError(Exception):
    pass


class ArgusInterfaceSchemaError(Exception):
    pass


class ArgusInterfaceNameError(Exception):
    pass


class ArgusDatabase:
    PYTHON_SCYLLA_TYPE_MAPPING = {
        int: IntegerType.typename,
        float: FloatType.typename,
        str: VarcharType.typename,
        UUID: UUIDType.typename,
    }

    log = logging.getLogger(__name__)
    _INSTANCE: Union['ArgusDatabase', Any] = None

    def __init__(self, config: BaseConfig = None):
        if not config:
            config = FileConfig()
        self.config = config.get_config()
        self.cluster = cassandra.cluster.Cluster(contact_points=self.config.get("contact_points", []),
                                                 auth_provider=PlainTextAuthProvider(
                                                     username=self.config.get("username"),
                                                     password=self.config.get("password")))

        self.session = self.cluster.connect()
        self._keyspace_initialized = False
        self.prepared_statements = dict()
        self.initialized_tables = dict()
        self._table_keys = dict()
        self._mapped_udts = dict()
        self._current_keyspace = self.init_keyspace(name=self.config.get("keyspace_name"))

    @classmethod
    def get(cls):
        if cls._INSTANCE:
            cls.log.debug("Found valid db session.")
            return cls._INSTANCE

        cls.log.debug("Initializing db session from default config")
        cls._INSTANCE = cls.from_config()
        return cls._INSTANCE

    @classmethod
    def destroy(cls):
        if not cls._INSTANCE:
            cls.log.warning("ArgusDatabase::destroy called with no valid session.")
            return False

        cls.log.info("Shutting down the cluster connection.")
        cls._INSTANCE.cluster.shutdown()
        cls._INSTANCE = None
        return True

    @classmethod
    def from_config(cls, config: BaseConfig = None):
        if not config:
            config = FileConfig()
        if cls._INSTANCE:
            raise ArgusInterfaceSingletonError("Attempt to call ArgusDatabase::from_config twice")

        cls._INSTANCE = cls(config=config)
        return cls._INSTANCE

    def prepare_query_for_table(self, table_name, query_type, query):
        prepared_statement = self.session.prepare(query=query)
        self.prepared_statements[f"{table_name}_{query_type}"] = prepared_statement

        return prepared_statement

    @staticmethod
    def _verify_keyspace_name(name: str):
        incorrect_keyspace_name_re = r"\."
        if match := re.match(incorrect_keyspace_name_re, name):
            raise ArgusInterfaceNameError("Keyspace name does not conform to the "
                                          "keyspace naming rules: %s (pos: %s)" % (name, match.pos))
        return name

    @staticmethod
    def _get_hash_from_keys(keys: Union[list[str], KeysView]):
        key_string = ".".join(keys).encode(encoding="utf-8")
        return sha1(key_string).hexdigest()

    def init_keyspace(self, name="argus", prefix="", suffix=""):
        keyspace_name = self._verify_keyspace_name(f"{prefix}{name}{suffix}")
        query = f"CREATE KEYSPACE IF NOT EXISTS {keyspace_name} " \
                "WITH replication={'class': 'SimpleStrategy', 'replication_factor' : 3}"
        self.log.debug("Running query: %s", query)
        self.session.execute(query=query)
        self.session.set_keyspace(keyspace_name)
        self._keyspace_initialized = True
        return keyspace_name

    def is_native_type(self, object_type):
        return self.PYTHON_SCYLLA_TYPE_MAPPING.get(object_type, False)

    def init_table(self, table_name: str, column_info: dict[str, ColumnInfo]):
        if not self._keyspace_initialized:
            raise ArgusInterfaceDatabaseConnectionError("Uninitialized keyspace, cannot continue")

        if self.initialized_tables.get(table_name):
            return True, f"Table {table_name} already initialized"

        primary_keys_info: dict = column_info.pop("$tablekeys$")
        partition_keys = [key for key, (cls, pk_type) in primary_keys_info.items() if pk_type == "partition"]
        partition_key_def = partition_keys[0] if len(partition_keys) == 1 else "(%s)" % (", ".join(partition_keys))
        clustering_columns = [key for key, (cls, pk_type) in primary_keys_info.items() if pk_type == "clustering"]
        clustering_column_def = ", ".join(clustering_columns)

        self._table_keys[table_name] = primary_keys_info

        query = "CREATE TABLE IF NOT EXISTS {table_name}({columns}, PRIMARY KEY ({partition_key}, {clustering_cols}))"
        columns_query = []
        for column in column_info.values():
            if mapped_type := self.is_native_type(column.type):
                column_type = mapped_type
            elif column.type is CollectionHint:
                column_type = self.create_collection_declaration(column.value.stored_type)
            else:
                # UDT
                column_type = "frozen<%s>" % (self._init_user_data_type(column.type),)

            constraints = " ".join(column.constraints)
            column_query = f"{column.name} {column_type} {constraints}"
            columns_query.append(column_query)

        columns_query = ", ".join(columns_query)
        completed_query = query.format(table_name=table_name, columns=columns_query, partition_key=partition_key_def,
                                       clustering_cols=clustering_column_def)
        self.log.debug("About to execute: \"%s\"", completed_query)
        self.session.execute(query=completed_query)
        self.initialized_tables[table_name] = True
        return True, "Initialization complete"

    def create_collection_declaration(self, hint: GenericAlias):
        collection_type = get_type_origin(hint)
        collection_types = get_type_args(hint)

        declaration_type = collection_type.__name__

        declared_types = []
        for inner_hint in collection_types:
            type_class = get_type_origin(inner_hint) if type(inner_hint) is GenericAlias else inner_hint

            if type_class is tuple or type_class is list:
                declaration = "frozen<%s>" % (self.create_collection_declaration(inner_hint),)
            elif matched_type := self.PYTHON_SCYLLA_TYPE_MAPPING.get(type_class):
                declaration = matched_type
            else:
                declaration = "frozen<%s>" % (self._init_user_data_type(type_class),)

            declared_types.append(declaration)

        declaration_query = ", ".join(declared_types) if collection_type is tuple else str(declared_types[0])

        return f"{declaration_type}<{declaration_query}>"

    def _init_user_data_type(self, cls: ArgusUDTBase):
        if not self._keyspace_initialized:
            raise ArgusInterfaceDatabaseConnectionError("Uninitialized keyspace, cannot continue")

        udt_name = cls.__name__ if not cls._typename else cls._typename

        if cls in self._mapped_udts.get(self._current_keyspace, []):
            return udt_name

        query = "CREATE TYPE IF NOT EXISTS {name} ({fields})"
        fields = []
        for field in dataclass_fields(cls):
            name = field.name
            field_type = get_type_origin(field.type) if type(field.type) is GenericAlias else field.type
            if field_type is list or field_type is tuple:
                field_declaration = self.create_collection_declaration(field.type)
            elif matched_type := self.PYTHON_SCYLLA_TYPE_MAPPING.get(field_type):
                field_declaration = matched_type
            else:
                field_declaration = "frozen<%s>" % (self._init_user_data_type(field.type),)
            fields.append(f"{name} {field_declaration}")

        joined_fields = ", ".join(fields)

        completed_query = query.format(name=udt_name, fields=joined_fields)
        self.log.debug("About to execute: \"%s\"", completed_query)
        self.session.execute(query=completed_query)

        existing_udts = self._mapped_udts.get(self._current_keyspace, [])
        existing_udts.append(cls)
        self._mapped_udts[self._current_keyspace] = existing_udts

        return udt_name

    def fetch(self, table_name: str, run_id: UUID):
        if not self._keyspace_initialized:
            raise ArgusInterfaceDatabaseConnectionError("Uninitialized keyspace, cannot continue")

        query = self.prepared_statements.get(f"{table_name}_select",
                                             self.prepare_query_for_table(table_name=table_name, query_type="insert",
                                                                          query=f"SELECT * FROM {table_name} "
                                                                                "WHERE id = ?"))

        cursor = self.session.execute(query=query, parameters=(run_id,))

        return cursor.one()

    def insert(self, table_name: str, run_data: dict):
        if not self._keyspace_initialized:
            raise ArgusInterfaceDatabaseConnectionError("Uninitialized keyspace, cannot continue")

        query = self.prepared_statements.get(f"{table_name}_insert",
                                             self.prepare_query_for_table(table_name=table_name, query_type="insert",
                                                                          query=f"INSERT INTO {table_name} JSON ?"))

        self.session.execute(query=query, parameters=(json.dumps(run_data),))

    def update(self, table_name: str, run_data: dict):
        def _convert_data_to_sequence(data: dict) -> list:
            data_list = list(data.values())
            for idx, value in enumerate(data_list):
                if type(value) is dict:
                    data_list[idx] = _convert_data_to_sequence(value)
                elif type(value) is list and len(value) > 0 and type(value[0]) is dict:
                    data_list[idx] = [_convert_data_to_sequence(d) for d in value]
            return data_list

        primary_keys: dict = self._table_keys[table_name]
        self.log.debug("Primary keys for table %s: %s", table_name, primary_keys)
        where_clause = []
        where_params = []
        for key, (ctor, key_type) in primary_keys.items():
            self.log.debug("Ejecting %s from update set as it is a part of the primary key", key)
            try:
                data_value = run_data.pop(key)
            except KeyError:
                raise ArgusInterfaceSchemaError("Missing key from update set", key)
            field = f"{key} = ?"
            where_clause.append(field)
            where_params.append(ctor(data_value))

        where_clause_joined = " AND ".join(where_clause)

        if not (prepared_statement := self.prepared_statements.get(f"update_{table_name}")):
            field_parameters = [f"\"{field_name}\" = ?" for field_name in run_data.keys()]
            fields_joined = ", ".join(field_parameters)

            query = f"UPDATE {table_name} SET {fields_joined} WHERE {where_clause_joined}"
            self.log.debug("Formatted query: %s", query)
            prepared_statement = self.session.prepare(query=query)
            self.prepared_statements[f"update_{table_name}"] = prepared_statement

        self.log.debug("Bound query for update: %s", prepared_statement.query_string)
        query_parameters = _convert_data_to_sequence(run_data)
        parameters = [*query_parameters, *where_params]
        self.log.debug("Parameters: %s", parameters)
        self.session.execute(prepared_statement, parameters=parameters)
