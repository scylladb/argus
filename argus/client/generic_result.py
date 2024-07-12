from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Union


class Status(Enum):
    PASS = auto()
    WARNING = auto()
    ERROR = auto()

    def __str__(self):
        return self.name


class ResultType(Enum):
    INTEGER = auto()
    FLOAT = auto()
    DURATION = auto()

    def __str__(self):
        return self.name


@dataclass
class ColumnMetadata:
    name: str
    unit: str
    type: ResultType

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "unit": self.unit,
            "type": str(self.type)
        }


class ResultTableMeta(type):
    def __new__(cls, name, bases, dct):
        cls_instance = super().__new__(cls, name, bases, dct)
        meta = dct.get('Meta')

        if meta:
            cls_instance.name = meta.name
            cls_instance.description = meta.description
            cls_instance.columns = meta.Columns
            cls_instance.column_names = {column.name for column in cls_instance.columns}
            cls_instance.rows = []
        return cls_instance


@dataclass
class Cell:
    column: str
    row: str
    value: Union[int, float, str]
    status: Status

    def as_dict(self) -> dict:
        return {
            "column": self.column,
            "row": self.row,
            "value": self.value,
            "status": str(self.status)
        }


@dataclass
class GenericResultTable(metaclass=ResultTableMeta):
    """
    Base class for all Generic Result Tables in Argus. Use it as a base class for your result table.
    """
    sut_timestamp: int = 0  # automatic timestamp based on SUT version. Works only with SCT and refers to Scylla version.
    sut_details: str = ""
    results: list[Cell] = field(default_factory=list)

    def as_dict(self) -> dict:
        rows = []
        for result in self.results:
            if result.row not in rows:
                rows.append(result.row)

        meta_info = {
            "name": self.name,
            "description": self.description,
            "columns_meta": [column.as_dict() for column in self.columns],
            "rows_meta": rows
        }
        return {
            "meta": meta_info,
            "sut_timestamp": self.sut_timestamp,
            "sut_details": self.sut_details,
            "results": [result.as_dict() for result in self.results]
        }

    def add_result(self, column: str, row: str, value: Union[int, float, str], status: Status):
        if column not in self.column_names:
            raise ValueError(f"Column {column} not found in the table")
        self.results.append(Cell(column=column, row=row, value=value, status=status))
