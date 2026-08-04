from datetime import datetime, time
from typing import Annotated, ClassVar, Optional

from coodie import Ascii, Double, PrimaryKey
from coodie.sync import Document


class RuntimeStore(Document):
    """
        This model provides a way for the application to store configuration
        data inside its database. Supports time, datetime, int, float, str, boolean values
        and will automatically manage which type is being used.

        Example:

        prop = RuntimeStore(key="my_property_value")
        prop.value = 0
        prop.save()

    """
    _type_map: ClassVar[dict[type, str]] = {
        float: "float",
        bool: "boolean",
        time: "time",
        int: "int",
        str: "text",
        datetime: "datetime",
    }
    key: Annotated[str, PrimaryKey()]
    value_type: Annotated[Optional[str], Ascii()] = None
    value_int: Optional[int] = None
    value_text: Optional[str] = None
    value_ts: Optional[time] = None
    value_date: Optional[datetime] = None
    value_float: Annotated[Optional[float], Double()] = None
    value_boolean: Optional[bool] = None

    class Settings:
        name = "runtime_store"

    @property
    def value(self) -> int | str | float | datetime:
        match self.value_type:
            case "float": return self.value_float
            case "time": return self.value_ts
            case "int": return self.value_int
            case "text": return self.value_text
            case "boolean": return self.value_boolean
            case "datetime": return self.value_date

    @value.setter
    def value(self, v):
        if not (type_name := self._type_map.get(type(v))):
            raise ValueError(f"Unsupported type: {type(v)}")
        match type_name:
            case "float": self.value_float = v
            case "time": self.value_ts = v
            case "int": self.value_int = v
            case "text": self.value_text = v
            case "boolean": self.value_boolean = v
            case "datetime": self.value_date = v
        self.value_type = type_name
