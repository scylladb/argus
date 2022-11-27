# TODO: Deprecated, will be removed once REST API client is ready
from datetime import datetime
import re
import logging
import json
from uuid import UUID
from hashlib import sha1
from dataclasses import fields as dataclass_fields
from typing import KeysView, Union, Optional, Any, get_args as get_type_args, get_origin as get_type_origin
from types import GenericAlias

import cassandra.cluster
import cassandra.cqltypes
from cassandra import ConsistencyLevel
from cassandra.auth import PlainTextAuthProvider
from cassandra.query import named_tuple_factory
from cassandra.policies import WhiteListRoundRobinPolicy, AddressTranslator
from cassandra.cluster import ExecutionProfile, EXEC_PROFILE_DEFAULT
from cassandra.cqlengine import connection
from cassandra.cqlengine import models
from cassandra.cqlengine import management
from argus.db.argus_json import ArgusJSONEncoder

from argus.db.config import BaseConfig, FileConfig
from argus.db.db_types import ColumnInfo, CollectionHint, ArgusUDTBase
from argus.db.cloud_types import ResourceState
from argus.backend.models.web import ArgusSchedule, ArgusScheduleAssignee, \
    ArgusScheduleGroup, ArgusScheduleTest, ArgusRelease, ArgusGroup, ArgusTest

LOGGER = logging.getLogger(__name__)


class ArgusInterfaceSingletonError(Exception):
    pass


class ArgusInterfaceDatabaseConnectionError(Exception):
    pass


class ArgusInterfaceSchemaError(Exception):
    pass


class ArgusInterfaceNameError(Exception):
    pass


class PrivateToPublicAddressTranslator(AddressTranslator):
    def __init__(self, address_mapping):
        self.address_mapping = address_mapping

    def translate(self, addr):
        return self.address_mapping.get(addr, addr)


class ArgusDatabase:
    # pylint: disable=too-many-instance-attributes
    CQL_ENGINE_CONNECTION_NAME = 'argus_cql_engine_conn'
    ARGUS_EXECUTION_PROFILE = "argus_named_tuple"
    REQUIRED_CQL_ENGINE_MODELS = [
        ArgusSchedule,
        ArgusScheduleGroup,
        ArgusScheduleTest,
        ArgusScheduleAssignee,
        ArgusTest,
        ArgusGroup,
        ArgusRelease,
    ]
    PYTHON_SCYLLA_TYPE_MAPPING = {
        int: cassandra.cqltypes.IntegerType.typename,
        float: cassandra.cqltypes.FloatType.typename,
        str: cassandra.cqltypes.VarcharType.typename,
        UUID: cassandra.cqltypes.UUIDType.typename,
        datetime: cassandra.cqltypes.DateType.typename,
        ResourceState: cassandra.cqltypes.VarcharType.typename,
        Optional[str]: cassandra.cqltypes.VarcharType.typename,
        Optional[int]: cassandra.cqltypes.IntegerType.typename,
    }

    _INSTANCE: Union['ArgusDatabase', Any] = None

    def __init__(self, config: BaseConfig = None):
        if not config:
            config = FileConfig()
        self.config = config
        self.execution_profile = ExecutionProfile(
            load_balancing_policy=WhiteListRoundRobinPolicy(hosts=self.config.contact_points),
            consistency_level=ConsistencyLevel.QUORUM,
        )
        self.exec_profile_named_tuple = ExecutionProfile(
            load_balancing_policy=WhiteListRoundRobinPolicy(hosts=self.config.contact_points),
            consistency_level=ConsistencyLevel.QUORUM,
            row_factory=named_tuple_factory
        )
        address_translator = None
        if self.config.address_mapping:
            address_translator = PrivateToPublicAddressTranslator(self.config.address_mapping)

        self.cluster = cassandra.cluster.Cluster(contact_points=self.config.contact_points,
                                                 protocol_version=4,
                                                 auth_provider=PlainTextAuthProvider(
                                                     username=self.config.username,
                                                     password=self.config.password),
                                                 execution_profiles={
                                                     EXEC_PROFILE_DEFAULT: self.execution_profile,
                                                     self.ARGUS_EXECUTION_PROFILE: self.exec_profile_named_tuple
                                                 },
                                                 address_translator=address_translator,
                                                 )
        self.session = self.cluster.connect()
        self._keyspace_initialized = False
        self.prepared_statements = {}
        self.initialized_tables = {}
        self._table_keys = {}
        self._mapped_udts = {}
        self._current_keyspace = self.init_keyspace(name=self.config.keyspace_name)
        connection.register_connection(self.CQL_ENGINE_CONNECTION_NAME, session=self.session)
        for model in self.REQUIRED_CQL_ENGINE_MODELS:
            management.sync_table(model, keyspaces=(self._current_keyspace,),
                                  connections=(self.CQL_ENGINE_CONNECTION_NAME,))
        if not models.DEFAULT_KEYSPACE:
            models.DEFAULT_KEYSPACE = self._current_keyspace
        elif models.DEFAULT_KEYSPACE != self._current_keyspace:
            LOGGER.warning(
                "CQL Engine DEFAULT_KEYSPACE has been set already and differs from interface keyspace, this could cause issues")

    @classmethod
    def get(cls, config: BaseConfig = None):
        if cls._INSTANCE:
            LOGGER.debug("Found valid db session.")
            return cls._INSTANCE

        if not config:
            config = FileConfig()

        LOGGER.debug("Initializing db session from default config")
        cls._INSTANCE = cls(config=config)
        return cls._INSTANCE

    @classmethod
    def destroy(cls):
        if not cls._INSTANCE:
            LOGGER.warning("ArgusDatabase::destroy called with no valid session.")
            return False

        LOGGER.info("Shutting down the cluster connection.")
        cls._INSTANCE.cluster.shutdown()
        cls._INSTANCE = None
        return True

    @classmethod
    def from_config(cls, config: BaseConfig = None):
        return cls.get(config)

    def prepare_query_for_table(self, table_name, query_type, query):
        prepared_statement = self.session.prepare(query=query)
        self.prepared_statements[f"{table_name}_{query_type}"] = prepared_statement

        return prepared_statement

    @staticmethod
    def _verify_keyspace_name(name: str):
        incorrect_keyspace_name_re = r"\."
        if match := re.search(incorrect_keyspace_name_re, name):
            raise ArgusInterfaceNameError("Keyspace name does not conform to the "
                                          f"keyspace naming rules: {name} (pos: {match.pos})")
        return name

    @staticmethod
    def _get_hash_from_keys(keys: Union[list[str], KeysView]):
        key_string = ".".join(keys).encode(encoding="utf-8")
        return sha1(key_string).hexdigest()

    def init_keyspace(self, name="argus", prefix="", suffix="") -> str:
        keyspace_name = self._verify_keyspace_name(f"{prefix}{name}{suffix}")
        query = f"CREATE KEYSPACE IF NOT EXISTS {keyspace_name} " \
                "WITH replication={'class': 'SimpleStrategy', 'replication_factor' : 3}"
        LOGGER.debug("Running query: %s", query)
        self.session.execute(query=query, execution_profile=self.ARGUS_EXECUTION_PROFILE)
        self.session.set_keyspace(keyspace_name)
        self._keyspace_initialized = True
        return keyspace_name

    def is_native_type(self, object_type):
        return self.PYTHON_SCYLLA_TYPE_MAPPING.get(object_type, False)

    def init_table(self, table_name: str, column_info: dict[str, ColumnInfo]):
        # pylint: disable=too-many-locals
        if not self._keyspace_initialized:
            raise ArgusInterfaceDatabaseConnectionError("Uninitialized keyspace, cannot continue")

        if self.initialized_tables.get(table_name):
            return True, f"Table {table_name} already initialized"

        primary_keys_info: dict = column_info.pop("$tablekeys$")
        clustering_order_info: dict = column_info.pop("$clustering_order$")
        indices_info: dict = column_info.pop("$indices$")
        partition_keys = [key for key, (cls, pk_type) in primary_keys_info.items() if pk_type == "partition"]
        partition_key_def = partition_keys[0] if len(partition_keys) == 1 else f"({', '.join(partition_keys)})"
        clustering_columns = [key for key, (cls, pk_type) in primary_keys_info.items() if pk_type == "clustering"]
        clustering_column_def = ", ".join(clustering_columns)
        clustering_order = [f"{key} {clustering_order_info[key]}" for key in clustering_columns +
                            partition_keys if clustering_order_info.get(key)]
        clustering_order_def = ", ".join(clustering_order)
        clustering_statement = f"WITH CLUSTERING ORDER BY ({clustering_order_def})" if len(clustering_order) > 0 else ""

        self._table_keys[table_name] = primary_keys_info
        primary_key_def = f"{partition_key_def}, {clustering_column_def}" if len(
            clustering_column_def) > 0 else partition_key_def
        query = "CREATE TABLE IF NOT EXISTS {table_name}({columns}, PRIMARY KEY ({pk})) {cs}"
        columns_query = []
        for column in column_info.values():
            if mapped_type := self.is_native_type(column.type):
                column_type = mapped_type
            elif column.type is CollectionHint:
                column_type = self.create_collection_declaration(column.value.stored_type)
            else:
                # UDT
                column_type = f"frozen<{self._init_user_data_type(column.type)}>"

            constraints = " ".join(column.constraints)
            column_query = f"{column.name} {column_type} {constraints}"
            columns_query.append(column_query)

        columns_query = ", ".join(columns_query)
        completed_query = query.format(table_name=table_name, columns=columns_query,
                                       pk=primary_key_def, cs=clustering_statement)
        LOGGER.debug("About to execute: \"%s\"", completed_query)
        self.session.execute(query=completed_query, execution_profile=self.ARGUS_EXECUTION_PROFILE)
        self.create_indices(table_name, indices=indices_info)
        self.initialized_tables[table_name] = True
        return True, "Initialization complete"

    def create_indices(self, table_name, indices):
        for index in indices:
            self.session.execute(f"CREATE INDEX IF NOT EXISTS ON {table_name}({index})")
        return True

    def create_collection_declaration(self, hint: GenericAlias):
        collection_type = get_type_origin(hint)
        collection_types = get_type_args(hint)

        declaration_type = collection_type.__name__

        declared_types = []
        for inner_hint in collection_types:
            type_class = get_type_origin(inner_hint) if isinstance(inner_hint, GenericAlias) else inner_hint

            if type_class is tuple or type_class is list:
                declaration = f"frozen<{self.create_collection_declaration(inner_hint)}>"
            elif matched_type := self.PYTHON_SCYLLA_TYPE_MAPPING.get(type_class):
                declaration = matched_type
            else:
                declaration = f"frozen<{self._init_user_data_type(type_class)}>"

            declared_types.append(declaration)

        declaration_query = ", ".join(declared_types) if collection_type is tuple else str(declared_types[0])

        return f"{declaration_type}<{declaration_query}>"

    def _init_user_data_type(self, cls: ArgusUDTBase):
        if not self._keyspace_initialized:
            raise ArgusInterfaceDatabaseConnectionError("Uninitialized keyspace, cannot continue")

        udt_name = cls.basename()

        if cls in self._mapped_udts.get(self._current_keyspace, []):
            return udt_name

        query = "CREATE TYPE IF NOT EXISTS {name} ({fields})"
        fields = []
        for field in dataclass_fields(cls):
            name = field.name
            field_type = get_type_origin(field.type) if isinstance(field.type, GenericAlias) else field.type
            if field_type is list or field_type is tuple:
                field_declaration = self.create_collection_declaration(field.type)
            elif matched_type := self.PYTHON_SCYLLA_TYPE_MAPPING.get(field_type):
                field_declaration = matched_type
            else:
                field_declaration = f"frozen<{self._init_user_data_type(field.type)}>"
            fields.append(f"{name} {field_declaration}")

        joined_fields = ", ".join(fields)

        completed_query = query.format(name=udt_name, fields=joined_fields)
        LOGGER.debug("About to execute: \"%s\"", completed_query)
        self.session.execute(query=completed_query, execution_profile=self.ARGUS_EXECUTION_PROFILE)

        existing_udts = self._mapped_udts.get(self._current_keyspace, [])
        existing_udts.append(cls)
        self._mapped_udts[self._current_keyspace] = existing_udts

        return udt_name

    def fetch(self, table_name: str, run_id: UUID, where_clause="WHERE id = ?"):
        return self._fetch(table_name, (run_id,), where_clause)

    def _fetch(self, table_name: str, params: tuple | list, where_clause: str):
        if not self._keyspace_initialized:
            raise ArgusInterfaceDatabaseConnectionError("Uninitialized keyspace, cannot continue")

        query = self.prepared_statements.get(f"{table_name}_select_{where_clause.lower().replace(' ', '-')}",
                                             self.prepare_query_for_table(table_name=table_name, query_type="insert",
                                                                          query=f"SELECT * FROM {table_name} "
                                                                                f"{where_clause}"))

        cursor = self.session.execute(query=query, parameters=params, execution_profile=self.ARGUS_EXECUTION_PROFILE)

        return cursor.one()

    def fetch_generic(self, table_name: str, params: tuple | list, where_clause: str):
        return self._fetch(table_name, params, where_clause)

    def insert(self, table_name: str, run_data: dict):
        if not self._keyspace_initialized:
            raise ArgusInterfaceDatabaseConnectionError("Uninitialized keyspace, cannot continue")

        query = self.prepared_statements.get(f"{table_name}_insert",
                                             self.prepare_query_for_table(table_name=table_name, query_type="insert",
                                                                          query=f"INSERT INTO {table_name} JSON ?"))

        self.session.execute(query=query, parameters=(json.dumps(run_data, cls=ArgusJSONEncoder),),
                             execution_profile=self.ARGUS_EXECUTION_PROFILE)

    def update(self, table_name: str, run_data: dict):
        # pylint: disable=too-many-locals
        def _convert_data_to_sequence(data: dict) -> list:
            data_list = list(data.values())
            for idx, value in enumerate(data_list):
                if isinstance(value, dict):
                    data_list[idx] = _convert_data_to_sequence(value)
                elif isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict):
                    data_list[idx] = [_convert_data_to_sequence(d) for d in value]
            return data_list

        primary_keys: dict = self._table_keys.get(table_name)
        if not primary_keys:
            raise ArgusInterfaceSchemaError(f"Table \"{table_name}\" is not initialized!")

        LOGGER.debug("Primary keys for table %s: %s", table_name, primary_keys)
        where_clause = []
        where_params = []
        for key, (_, _) in primary_keys.items():
            LOGGER.debug("Ejecting %s from update set as it is a part of the primary key", key)
            try:
                data_value = run_data.pop(key)
            except KeyError as exc:
                raise ArgusInterfaceSchemaError("Missing key from update set", key) from exc
            field = f"{key} = ?"
            where_clause.append(field)
            where_params.append(data_value)

        where_clause_joined = " AND ".join(where_clause)

        if not (prepared_statement := self.prepared_statements.get(f"update_{table_name}")):
            field_parameters = [f"\"{field_name}\" = ?" for field_name in run_data.keys()]
            fields_joined = ", ".join(field_parameters)

            query = f"UPDATE {table_name} SET {fields_joined} WHERE {where_clause_joined}"
            LOGGER.debug("Formatted query: %s", query)
            prepared_statement = self.session.prepare(query=query)
            self.prepared_statements[f"update_{table_name}"] = prepared_statement

        LOGGER.debug("Bound query for update: %s", prepared_statement.query_string)
        query_parameters = _convert_data_to_sequence(run_data)
        parameters = [*query_parameters, *where_params]
        LOGGER.debug("Parameters: %s", parameters)
        self.session.execute(prepared_statement, parameters=parameters, execution_profile=self.ARGUS_EXECUTION_PROFILE)
