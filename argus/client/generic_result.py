from dataclasses import dataclass, field
from enum import Enum, auto
from functools import cached_property
from typing import Union


class Status(Enum):
    PASS = auto()
    WARNING = auto()
    ERROR = auto()
    UNSET = auto()

    def __str__(self):
        return self.name


class ResultType(Enum):
    INTEGER = auto()
    FLOAT = auto()
    DURATION = auto()
    TEXT = auto()

    def __str__(self):
        return self.name


@dataclass
class ColumnMetadata:
    name: str
    unit: str
    type: ResultType
    higher_is_better: bool = None

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "unit": self.unit,
            "type": str(self.type),
            "higher_is_better": self.higher_is_better,
        }


@dataclass
class ValidationRule:
    best_pct: float | None = None  # max value limit relative to best result in percent unit
    best_abs: float | None = None  # max value limit relative to best result in absolute unit
    fixed_limit: float | None = None

    def as_dict(self) -> dict:
        return {"best_pct": self.best_pct, "best_abs": self.best_abs, "fixed_limit": self.fixed_limit}


@dataclass
class Cell:
    column: str
    row: str
    value: Union[int, float, str]
    status: Status

    def as_dict(self) -> dict:
        cell = {"value_text": self.value} if isinstance(self.value, str) else {"value": self.value}
        cell.update({"column": self.column, "row": self.row, "status": str(self.status)})
        return cell


@dataclass
class GenericResultTable:
    """
    Base class for all Generic Result Tables in Argus. Use it as a base class for your result table.
    """

    name: str = ""
    description: str = ""
    columns: list[ColumnMetadata] = field(default_factory=list)
    # automatic timestamp based on SUT version. Works only with SCT and refers to Scylla version.
    sut_timestamp: int = 0
    sut_package_name: str = ""
    results: list[Cell] = field(default_factory=list)
    validation_rules: dict[str, ValidationRule] = field(default_factory=dict)

    @cached_property
    def column_types(self):
        """Return columns types as a dictionary."""
        return {column.name: column.type for column in self.columns}

    def __post_init__(self):
        """Validate validation rules."""
        for col_name, rule in self.validation_rules.items():
            if col_name not in self.column_types:
                raise ValueError(f"ValidationRule column {col_name} not found in the table")
            if self.column_types[col_name] == ResultType.TEXT:
                raise ValueError(f"Validation rules don't apply to TEXT columns")
            if not isinstance(rule, ValidationRule):
                raise ValueError(f"Validation rule for column {col_name} is not of type ValidationRule")

    def as_dict(self) -> dict:
        rows = []
        for result in self.results:
            if result.row not in rows:
                rows.append(result.row)

        meta_info = {
            "name": self.name,
            "description": self.description,
            "columns_meta": [column.as_dict() for column in self.columns],
            "rows_meta": rows,
            "validation_rules": {k: v.as_dict() for k, v in self.validation_rules.items()},
            "sut_package_name": self.sut_package_name,
        }
        return {
            "meta": meta_info,
            "sut_timestamp": self.sut_timestamp,
            "results": [result.as_dict() for result in self.results],
        }

    def add_result(self, column: str, row: str, value: Union[int, float, str], status: Status):
        if column not in self.column_types:
            raise ValueError(f"Column {column} not found in the table")
        if isinstance(value, str) and self.column_types[column] != ResultType.TEXT:
            raise ValueError(f"Column {column} is not of type TEXT")
        self.results.append(Cell(column=column, row=row, value=value, status=status))


class StaticGenericResultTable(GenericResultTable):
    """Results class for static results metainformation, defined in Meta class."""

    def __init__(
        self, name=None, description=None, columns=None, sut_package_name=None, validation_rules=None
    ):
        meta = getattr(self.__class__, "Meta")
        super().__init__(
            name=name or meta.name,
            description=description or meta.description,
            columns=columns or getattr(meta, "Columns", getattr(meta, "columns", None)),
            sut_package_name=sut_package_name or getattr(meta, "sut_package_name", ""),
            validation_rules=validation_rules or getattr(meta, "ValidationRules", getattr(meta, "validation_rules", {})),
        )
