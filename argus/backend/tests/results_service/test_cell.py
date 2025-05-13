from argus.backend.service.results_service import Cell, ArgusGenericResultMetadata


def test_cell_initialization():
    cell = Cell(column="col1", row="row1", status="UNSET")
    assert cell.column == "col1"
    assert cell.row == "row1"
    assert cell.status == "UNSET"
    assert cell.value is None
    assert cell.value_text is None


def test_valid_rules_and_better_value_should_pass():
    cell = Cell(column="col1", row="row1", status="UNSET", value=10)
    table_metadata = ArgusGenericResultMetadata(
        validation_rules={"col1": [{"fixed_limit": 5}]},
        columns_meta=[{"name": "col1", "higher_is_better": True}]
    )
    best_results = {}
    cell.update_cell_status_based_on_rules(table_metadata, best_results)
    assert cell.status == "PASS"


def test_valid_rules_and_worse_value_should_fail():
    cell = Cell(column="col1", row="row1", status="UNSET", value=3)
    table_metadata = ArgusGenericResultMetadata(
        validation_rules={"col1": [{"fixed_limit": 5}]},
        columns_meta=[{"name": "col1", "higher_is_better": True}]
    )
    best_results = {}
    cell.update_cell_status_based_on_rules(table_metadata, best_results)
    assert cell.status == "ERROR"


def test_no_rules_should_keep_status_unset():
    cell = Cell(column="col1", row="row1", status="UNSET", value=10)
    table_metadata = ArgusGenericResultMetadata(
        validation_rules={},
        columns_meta=[{"name": "col1", "higher_is_better": True}]
    )
    best_results = {}
    cell.update_cell_status_based_on_rules(table_metadata, best_results)
    assert cell.status == "UNSET"


def test_not_unset_status_should_not_be_validated():
    cell = Cell(column="col1", row="row1", status="PASS", value=10)
    table_metadata = ArgusGenericResultMetadata(
        validation_rules={"col1": [{"fixed_limit": 5}]},
        columns_meta=[{"name": "col1", "higher_is_better": True}]
    )
    best_results = {}
    cell.update_cell_status_based_on_rules(table_metadata, best_results)
    assert cell.status == "PASS"


def test_higher_is_better_false_should_fail():
    cell = Cell(column="col1", row="row1", status="UNSET", value=10)
    table_metadata = ArgusGenericResultMetadata(
        validation_rules={"col1": [{"fixed_limit": 5}]},
        columns_meta=[{"name": "col1", "higher_is_better": False}]
    )
    best_results = {}
    cell.update_cell_status_based_on_rules(table_metadata, best_results)
    assert cell.status == "ERROR"
