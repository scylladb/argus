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


class TestVisibilityResults(StaticGenericResultTable):
    """
    Testing Results with mixed visible and invisible columns
    """

    class Meta:
        name = "Visibility Test Results"
        description = "Testing column visibility feature"
        columns = [
            ColumnMetadata(name="visible_col", unit="unit1", type=ResultType.INTEGER, higher_is_better=True, visible=True),
            ColumnMetadata(name="invisible_col", unit="unit2", type=ResultType.FLOAT, higher_is_better=False, visible=False),
            ColumnMetadata(name="default_col", unit="unit3", type=ResultType.DURATION, higher_is_better=True),  # Should default to visible=True
        ]


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


def test_column_metadata_as_dict_includes_visibility():
    """Test that ColumnMetadata.as_dict() includes visibility field"""
    # Test explicitly visible column
    visible_col = ColumnMetadata(name="test", unit="unit", type=ResultType.INTEGER, visible=True)
    visible_dict = visible_col.as_dict()
    assert "visible" in visible_dict
    assert visible_dict["visible"] is True

    # Test explicitly invisible column
    invisible_col = ColumnMetadata(name="test", unit="unit", type=ResultType.INTEGER, visible=False)
    invisible_dict = invisible_col.as_dict()
    assert "visible" in invisible_dict
    assert invisible_dict["visible"] is False

    # Test default visibility
    default_col = ColumnMetadata(name="test", unit="unit", type=ResultType.INTEGER)
    default_dict = default_col.as_dict()
    assert "visible" in default_dict
    assert default_dict["visible"] is True


def test_mixed_visibility_dynamic_results():
    """Test dynamic results with mixed column visibility"""
    class TestDynamicVisibility(GenericResultTable):
        def __init__(self):
            super().__init__(
                name="Dynamic Visibility Test",
                description="Testing dynamic column visibility",
                columns=[
                    ColumnMetadata(name="visible1", unit="unit1", type=ResultType.INTEGER, visible=True),
                    ColumnMetadata(name="invisible1", unit="unit2", type=ResultType.FLOAT, visible=False),
                    ColumnMetadata(name="visible2", unit="unit3", type=ResultType.TEXT),  # Default visible
                ],
            )

    results = TestDynamicVisibility()
    serialized = results.as_dict()

    columns_meta = serialized["meta"]["columns_meta"]
    assert len(columns_meta) == 3

    visible_columns = [col for col in columns_meta if col["visible"]]
    invisible_columns = [col for col in columns_meta if not col["visible"]]

    assert len(visible_columns) == 2
    assert len(invisible_columns) == 1
    assert invisible_columns[0]["name"] == "invisible1"


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
