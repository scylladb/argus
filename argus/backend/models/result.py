from cassandra.cqlengine import columns
from cassandra.cqlengine.models import Model
from cassandra.cqlengine.usertype import UserType
from enum import Enum


class Status(Enum):
    PASS = 0
    WARNING = 1
    ERROR = 2


class ColumnMetadata(UserType):
    name = columns.Ascii()
    unit = columns.Text()
    type = columns.Ascii()


class ArgusGenericResultMetadata(Model):
    __table_name__ = "generic_result_metadata_v1"
    test_id = columns.UUID(partition_key=True)
    name = columns.Text(required=True, primary_key=True)
    description = columns.Text()
    columns_meta = columns.List(value_type=columns.UserDefinedType(ColumnMetadata))
    rows_meta = columns.List(value_type=columns.Ascii())

    def __init__(self, **kwargs):
        kwargs["columns_meta"] = [ColumnMetadata(**col) for col in kwargs.pop('columns_meta', [])]
        super().__init__(**kwargs)


class ArgusGenericResultData(Model):
    __table_name__ = "generic_result_data_v1"
    test_id = columns.UUID(partition_key=True)
    name = columns.Text(partition_key=True)
    run_id = columns.UUID(primary_key=True)
    column = columns.Ascii(primary_key=True, index=True)
    row = columns.Ascii(primary_key=True, index=True)
    sut_timestamp = columns.DateTime()  # for sorting
    value = columns.Double()
    status = columns.Ascii()
