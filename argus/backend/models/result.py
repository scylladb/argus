from datetime import datetime, timezone
from typing import Annotated, Optional
from uuid import UUID

from pydantic import Field
from coodie import Ascii, ClusteringKey, Double, Frozen, Indexed, PrimaryKey
from coodie.sync import Document
from coodie.usertype import UserType


class ValidationRules(UserType):
    valid_from: Optional[datetime] = None
    best_pct: Annotated[Optional[float], Double()] = None  # max value limit relative to best result in percent unit
    best_abs: Annotated[Optional[float], Double()] = None  # max value limit relative to best result in absolute unit
    fixed_limit: Annotated[Optional[float], Double()] = None  # fixed limit


class ColumnMetadata(UserType):
    name: Annotated[Optional[str], Ascii()] = None
    unit: Optional[str] = None
    type: Annotated[Optional[str], Ascii()] = None
    higher_is_better: Optional[bool] = None  # used for tracking best results, if None - no tracking
    visible: Optional[bool] = True  # controls visibility in UI, True by default


class ArgusGenericResultMetadata(Document):
    test_id: Annotated[Optional[UUID], PrimaryKey()] = None
    name: Annotated[Optional[str], ClusteringKey()] = None
    description: Optional[str] = None
    columns_meta: list[ColumnMetadata] = Field(default_factory=list)
    validation_rules: dict[Annotated[str, Ascii()], Annotated[list[ValidationRules], Frozen()]] = Field(
        default_factory=dict)
    rows_meta: list[Annotated[str, Ascii()]] = Field(default_factory=list)
    sut_package_name: Annotated[Optional[str], Ascii()] = None

    class Settings:
        name = "generic_result_metadata_v1"

    def __init__(self, **kwargs):
        # raw driver rows carry NULL collections as None; let defaults apply
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        validation_rules = kwargs.get("validation_rules") or {}
        for column, rule in list(validation_rules.items()):
            if not isinstance(rule, list):
                rule["valid_from"] = datetime.now(timezone.utc)
                validation_rules[column] = [rule]
        super().__init__(**kwargs)

    def update_validation_rules(self, new_rules: dict) -> "ArgusGenericResultMetadata":
        """
        Updates the validation rules based on the new input data.

        For each key in new_rules:
            - If the key exists in self.validation_rules, compare the new rule with the most recent one.
                - If they differ, append the new rule.
            - If the key does not exist in self.validation_rules, add the key with the new rule.

        For keys in self.validation_rules but not in new_rules:
            - If the most recent rule does not have all fields set to None, append a new rule with fields set to None.

        :param new_rules: A dictionary where each key maps to a new rule dict.
        :return: True if any rules were updated, False otherwise.
        """
        updated = False
        input_data_keys = set(new_rules.keys())
        existing_keys = set(self.validation_rules.keys())

        # Handle existing keys in new input data
        for key, new_rule_dict in new_rules.items():
            rules_list = self.validation_rules.get(key, [])
            most_recent_rule = rules_list[-1] if rules_list else None

            fields_to_compare = [field for field in ValidationRules.model_fields if field != 'valid_from']
            rules_match = True

            if most_recent_rule:
                for field in fields_to_compare:
                    db_value = getattr(most_recent_rule, field)
                    new_value = new_rule_dict.get(field)
                    if db_value != new_value:
                        rules_match = False
                        break
            else:
                rules_match = False  # No existing rule, need to add one

            if not rules_match:
                new_rule = ValidationRules(
                    valid_from=datetime.now(timezone.utc),
                    best_pct=new_rule_dict.get('best_pct'),
                    best_abs=new_rule_dict.get('best_abs'),
                    fixed_limit=new_rule_dict.get('fixed_limit')
                )
                rules_list.append(new_rule)
                self.validation_rules[key] = rules_list
                updated = True

        # Handle keys missing in new input data
        missing_keys = existing_keys - input_data_keys
        for key in missing_keys:
            rules_list = self.validation_rules.get(key, [])
            most_recent_rule = rules_list[-1] if rules_list else None

            fields_to_compare = [field for field in ValidationRules.model_fields if field != 'valid_from']
            all_fields_none = True

            if most_recent_rule:
                for field in fields_to_compare:
                    if getattr(most_recent_rule, field) is not None:
                        all_fields_none = False
                        break
            else:
                all_fields_none = False

            if not all_fields_none:
                new_rule = ValidationRules(
                    valid_from=datetime.now(timezone.utc),
                    best_pct=None,
                    best_abs=None,
                    fixed_limit=None
                )
                rules_list.append(new_rule)
                self.validation_rules[key] = rules_list
                updated = True

        return updated

    def update_if_changed(self, new_data: dict) -> "ArgusGenericResultMetadata":
        """
        Updates table metadata if changed column/description or new rows were added.
        See that rows can only be added, not removed once was sent.
        Columns may be removed, but data in results table persists.
        """
        updated = False
        for field, value in new_data.items():
            if field == "columns_meta":
                value = [ColumnMetadata(**col) for col in value]
                if self.columns_meta != value:
                    self.columns_meta = value
                    updated = True
            elif field == "rows_meta":
                added_rows = []
                for row in value:
                    if row not in self.rows_meta:
                        added_rows.append(row)
                        updated = True
                self.rows_meta += added_rows
            elif field == "validation_rules":
                if self.update_validation_rules(value):
                    updated = True
            elif getattr(self, field) != value:
                setattr(self, field, value)
                updated = True

        if updated:
            self.save()
        return self


class ArgusGenericResultData(Document):
    test_id: Annotated[Optional[UUID], PrimaryKey(partition_key_index=0)] = None
    name: Annotated[Optional[str], PrimaryKey(partition_key_index=1)] = None
    run_id: Annotated[Optional[UUID], ClusteringKey(clustering_key_index=0)] = None
    column: Annotated[Optional[str], Ascii(), ClusteringKey(clustering_key_index=1), Indexed()] = None
    row: Annotated[Optional[str], Ascii(), ClusteringKey(clustering_key_index=2), Indexed()] = None
    sut_timestamp: Optional[datetime] = None  # for sorting
    value: Annotated[Optional[float], Double()] = None
    value_text: Optional[str] = None
    status: Annotated[Optional[str], Ascii()] = None

    class Settings:
        name = "generic_result_data_v1"


class ArgusBestResultData(Document):
    test_id: Annotated[Optional[UUID], PrimaryKey(partition_key_index=0)] = None
    name: Annotated[Optional[str], PrimaryKey(partition_key_index=1)] = None
    result_date: Annotated[Optional[datetime], ClusteringKey(order="DESC", clustering_key_index=0)] = None
    key: Annotated[Optional[str], Ascii(), ClusteringKey(clustering_key_index=1)] = None  # represents pair column:row
    value: Annotated[Optional[float], Double()] = None
    run_id: Optional[UUID] = None

    class Settings:
        name = "generic_result_best_v2"


class ArgusGraphView(Document):
    test_id: Annotated[Optional[UUID], PrimaryKey()] = None
    id: Annotated[Optional[UUID], ClusteringKey()] = None
    name: Optional[str] = None
    description: Optional[str] = None
    # key: graph name, value: graph properties (e.g. size)
    graphs: dict[str, Annotated[str, Ascii()]] = Field(default_factory=dict)

    class Settings:
        name = "graph_view_v1"
