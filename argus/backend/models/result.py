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
    validation_rules = columns.Map(key_type=columns.Ascii(
    ), value_type=columns.List(columns.UserDefinedType(ValidationRules)))
    rows_meta = columns.List(value_type=columns.Ascii())
    sut_package_name = columns.Ascii()

    def __init__(self, **kwargs):
        kwargs["columns_meta"] = [ColumnMetadata(**col) for col in kwargs.pop('columns_meta', [])]
        validation_rules = kwargs.pop('validation_rules', {})

        if validation_rules:
            for column, rule in validation_rules.items():
                if not isinstance(rule, list):
                    rule['valid_from'] = datetime.now(timezone.utc)
                    validation_rules[column] = [rule]
            kwargs["validation_rules"] = {k: [ValidationRules(**rules)
                                              for rules in v] for k, v in validation_rules.items()}
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

            fields_to_compare = [field for field in ValidationRules._fields if field != 'valid_from']
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

            fields_to_compare = [field for field in ValidationRules._fields if field != 'valid_from']
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
    __table_name__ = "generic_result_best_v2"
    test_id = columns.UUID(partition_key=True)
    name = columns.Text(partition_key=True)
    result_date = columns.DateTime(primary_key=True, clustering_order="DESC")
    key = columns.Ascii(primary_key=True)  # represents pair column:row
    value = columns.Double()
    run_id = columns.UUID()


class ArgusGraphView(Model):
    __table_name__ = "graph_view_v1"
    test_id = columns.UUID(partition_key=True)
    id = columns.UUID(primary_key=True)
    name = columns.Text()
    description = columns.Text()
    # key: graph name, value: graph properties (e.g. size)
    graphs = columns.Map(key_type=columns.Text(), value_type=columns.Ascii())
