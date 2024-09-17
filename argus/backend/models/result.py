import math
from datetime import datetime, timezone

from cassandra.cqlengine import columns
from cassandra.cqlengine.models import Model
from cassandra.cqlengine.usertype import UserType

class ValidationRules(UserType):
    valid_from = columns.DateTime()
    best_pct = columns.Double()  # max value limit relative to best result in percent unit
    best_abs = columns.Double()  # max value limit relative to best result in absolute unit
    fixed_limit = columns.Double()  # fixed limit

class ColumnMetadata(UserType):
    name = columns.Ascii()
    unit = columns.Text()
    type = columns.Ascii()
    higher_is_better = columns.Boolean()  # used for tracking best results, if None - no tracking


class ArgusGenericResultMetadata(Model):
    __table_name__ = "generic_result_metadata_v1"
    test_id = columns.UUID(partition_key=True)
    name = columns.Text(required=True, primary_key=True)
    description = columns.Text()
    columns_meta = columns.List(value_type=columns.UserDefinedType(ColumnMetadata))
    validation_rules = columns.Map(key_type=columns.Ascii(), value_type=columns.List(columns.UserDefinedType(ValidationRules)))
    rows_meta = columns.List(value_type=columns.Ascii())

    def __init__(self, **kwargs):
        kwargs["columns_meta"] = [ColumnMetadata(**col) for col in kwargs.pop('columns_meta', [])]
        validation_rules = kwargs.pop('validation_rules', {})

        if validation_rules:
            for column, rule in validation_rules.items():
                if not isinstance(rule, list):
                    rule['valid_from'] = datetime.now(timezone.utc)
                    validation_rules[column] = [rule]
            kwargs["validation_rules"] = {k: [ValidationRules(**rules) for rules in v] for k, v in validation_rules.items()}
        super().__init__(**kwargs)

    def update_validation_rules(self, key: str, new_rule_dict: dict) -> bool:
        """
        Checks if the most recent ValidationRule for the given key matches the new_rule_dict.
        If not, adds the new rule to the list with the current timestamp.

        :param key: The key (column name) in the validation_rules map to update.
        :param new_rule_dict: A dictionary containing the new validation rule values.
        :return: True if a new rule was added, False if the existing rule matches.
        """
        rules_list = self.validation_rules.get(key, [])
        most_recent_rule = None

        if rules_list:
            most_recent_rule = rules_list[-1]

        fields_to_compare = [field for field in ValidationRules._fields if field != 'valid_from']
        rules_match = True
        if most_recent_rule:
            for field in fields_to_compare:
                db_value = getattr(most_recent_rule, field)
                new_value = new_rule_dict.get(field)
                if db_value is None and new_value is None:
                    continue
                if db_value is None or new_value is None:
                    rules_match = False
                    break
                if not math.isclose(db_value, new_value, rel_tol=1e-9, abs_tol=0.0):
                    rules_match = False
                    break
        else:
            rules_match = False

        if not rules_match:
            new_rule = ValidationRules(
                valid_from=datetime.now(timezone.utc),
                best_pct=new_rule_dict.get('best_pct'),
                best_abs=new_rule_dict.get('best_abs'),
                fixed_limit=new_rule_dict.get('fixed_limit')
            )
            rules_list.append(new_rule)
            self.validation_rules = self.validation_rules or {}
            self.validation_rules.update({key: rules_list})
            return True

        return False  # Existing rule matches

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
                if any([self.update_validation_rules(key, rules) for key, rules in value.items()]):
                    updated = True
            elif getattr(self, field) != value:
                setattr(self, field, value)
                updated = True

        if updated:
            self.save()
        return self

class ArgusGenericResultData(Model):
    __table_name__ = "generic_result_data_v1"
    test_id = columns.UUID(partition_key=True)
    name = columns.Text(partition_key=True)
    run_id = columns.UUID(primary_key=True)
    column = columns.Ascii(primary_key=True, index=True)
    row = columns.Ascii(primary_key=True, index=True)
    sut_timestamp = columns.DateTime()  # for sorting
    value = columns.Double()
    value_text = columns.Text()
    status = columns.Ascii()

class ArgusBestResultData(Model):
    __table_name__ = "generic_result_best_v1"
    test_id = columns.UUID(partition_key=True)
    name = columns.Text(partition_key=True)
    key = columns.Ascii(primary_key=True)  # represents pair column:row
    result_date = columns.DateTime(primary_key=True, clustering_order="DESC")
    value = columns.Double()
    run_id = columns.UUID()
