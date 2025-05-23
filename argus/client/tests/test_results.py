import pytest

from argus.client.generic_result import (
    StaticGenericResultTable,
    Status,
    ColumnMetadata,
    ResultType,
    ValidationRule,
    GenericResultTable,
)


class TestStaticResults(StaticGenericResultTable):
    """
    Testing Results, which contain all the information in Meta class
    """

    class Meta:
        name = "Important Static Results"
        description = "This is a test for important static results."
        columns = [
            ColumnMetadata(name="column1", unit="unit1", type=ResultType.INTEGER, higher_is_better=True),
        ]
        validation_rules = {"column1": ValidationRule(best_pct=10, best_abs=20, fixed_limit=30)}


class TestDynamicResults(GenericResultTable):
    """
    Testing Results, which pass all the information in the constructor
    """

    def __init__(self, operation):
        super().__init__(
            name=f"{operation} - Dynamic Results",
            description=f"Dynamic results for {operation}",
            columns=[
                ColumnMetadata(name="column1", unit="unit1", type=ResultType.INTEGER, higher_is_better=True),
                ColumnMetadata(name="column2", unit="unit2", type=ResultType.FLOAT, higher_is_better=False),
            ],
            validation_rules={"column1": ValidationRule(best_pct=10, best_abs=20, fixed_limit=30)},
        )


class TestMixedResults(StaticGenericResultTable):
    """
    Testing Results, which combine Meta class with some dynamic information
    """

    def __init__(self, operation):
        super().__init__(name=f"{operation} - Dynamic Results")

    class Meta:
        description = "This is a test for mixed results."
        columns = [
            ColumnMetadata(name="column1", unit="unit1", type=ResultType.INTEGER, higher_is_better=True),
            ColumnMetadata(name="column2", unit="unit2", type=ResultType.FLOAT, higher_is_better=False),
        ]
        validation_rules = {"column1": ValidationRule(best_pct=10, best_abs=20, fixed_limit=30)}


def test_static_results():
    """
    Tests that you can create Results with all the information in the Meta class
    """
    results = TestStaticResults()
    serialized = results.as_dict()
    assert serialized["meta"]["name"] == TestStaticResults.Meta.name
    assert serialized["meta"]["description"] == TestStaticResults.Meta.description
    assert len(serialized["meta"]["rows_meta"]) == 0
    assert len(serialized["meta"]["columns_meta"]) == 1
    assert len(serialized["meta"]["validation_rules"]) == 1
    assert len(serialized["results"]) == 0


def test_dynamic_results():
    """
    Tests that you can create Results with all the information in the constructor
    """
    results = TestDynamicResults("Write")
    serialized = results.as_dict()
    assert serialized["meta"]["name"] == "Write - Dynamic Results"
    assert serialized["meta"]["description"] == "Dynamic results for Write"
    assert len(serialized["meta"]["rows_meta"]) == 0
    assert len(serialized["meta"]["columns_meta"]) == 2
    assert len(serialized["meta"]["validation_rules"]) == 1
    assert len(serialized["results"]) == 0


def test_mixed_results():
    """
    Tests that you can create Results, which combine Meta class with some dynamic information
    """
    results = TestMixedResults("Write")
    serialized = results.as_dict()
    assert serialized["meta"]["name"] == "Write - Dynamic Results"
    assert serialized["meta"]["description"] == "This is a test for mixed results."

    assert len(serialized["meta"]["rows_meta"]) == 0
    assert len(serialized["meta"]["columns_meta"]) == 2
    assert len(serialized["meta"]["validation_rules"]) == 1
    assert len(serialized["results"]) == 0


def test_add_results():
    """Tests add results method"""
    results = TestStaticResults()
    results.add_result(column="column1", row="row1", value=10, status=Status.UNSET)
    results.add_result(column="column1", row="row2", value=20, status=Status.UNSET)
    serialized = results.as_dict()

    assert len(serialized["meta"]["rows_meta"]) == 2
    assert len(serialized["results"]) == 2


def test_no_column():
    """Tests validation for validation rule with nonexistent column"""

    class NoColumnRule(StaticGenericResultTable):
        class Meta:
            name = "Testing results"
            description = ""
            columns = [
                ColumnMetadata(name="column1", unit="unit1", type=ResultType.INTEGER, higher_is_better=True),
            ]
            validation_rules = {"nonexistent": ValidationRule(best_pct=10, best_abs=20, fixed_limit=30)}

    with pytest.raises(ValueError, match="not found"):
        NoColumnRule()


def test_different_type():
    """Tests validation of validation rule type"""

    class BadType(StaticGenericResultTable):
        class Meta:
            name = "Testing results"
            description = ""
            columns = [
                ColumnMetadata(name="column1", unit="unit1", type=ResultType.INTEGER, higher_is_better=True),
            ]
            validation_rules = {"nonexistent": "test"}

    with pytest.raises(ValueError, match="ValidationRule"):
        BadType()


def test_text_rule():
    """Test validation of rules for TEXT types"""

    class TextType(StaticGenericResultTable):
        class Meta:
            name = "Testing results"
            description = ""
            columns = [
                ColumnMetadata(name="column1", unit="unit1", type=ResultType.TEXT, higher_is_better=True),
            ]
            validation_rules = {"column1": ValidationRule(best_pct=10, best_abs=20, fixed_limit=30)}

    with pytest.raises(ValueError, match="TEXT"):
        TextType()
