import uuid
from datetime import datetime, timezone
from unittest.mock import patch
from argus.backend.models.result import ArgusGenericResultMetadata


def generate_random_test_id():
    return str(uuid.uuid4())


def test_initialization(argus_db):
    metadata = ArgusGenericResultMetadata(
        test_id=generate_random_test_id(),
        name="Test Metadata",
        description="A test description",
        columns_meta=[{"name": "col1", "unit": "ms", "type": "float", "higher_is_better": True}],
        validation_rules={"col1": [{"valid_from": datetime.now(
            timezone.utc), "best_pct": 90.0, "best_abs": 100.0, "fixed_limit": 50.0}]},
        rows_meta=["row1", "row2"]
    )
    assert metadata.name == "Test Metadata"
    assert len(metadata.columns_meta) == 1
    assert len(metadata.validation_rules) == 1
    assert len(metadata.rows_meta) == 2


def test_update_validation_rules():
    metadata = ArgusGenericResultMetadata(
        test_id=generate_random_test_id(),
        name="Test Metadata",
        columns_meta=[{"name": "col1", "unit": "ms", "type": "float", "higher_is_better": True}],
        validation_rules={"col1": [{"valid_from": datetime.now(
            timezone.utc), "best_pct": 90.0, "best_abs": 100.0, "fixed_limit": 50.0}]},
        rows_meta=["row1", "row2"]
    )
    new_rules = {"col1": {"best_pct": 95.0, "best_abs": 105.0, "fixed_limit": 55.0}}
    updated = metadata.update_validation_rules(new_rules)
    assert updated
    assert len(metadata.validation_rules["col1"]) == 2
    assert metadata.validation_rules["col1"][-1].best_pct == 95.0


def test_update_if_changed():
    metadata = ArgusGenericResultMetadata(
        test_id=generate_random_test_id(),
        name="Test Metadata",
        columns_meta=[{"name": "col1", "unit": "ms", "type": "float", "higher_is_better": True}],
        validation_rules={"col1": [{"valid_from": datetime.now(
            timezone.utc), "best_pct": 90.0, "best_abs": 100.0, "fixed_limit": 50.0}]},
        rows_meta=["row1", "row2"]
    )
    new_data = {
        "name": "Updated Metadata",
        "columns_meta": [{"name": "col1", "unit": "ms", "type": "float", "higher_is_better": True}],
        "validation_rules": {"col1": {"best_pct": 95.0, "best_abs": 105.0, "fixed_limit": 50.0}},
        "rows_meta": ["row1"],
        "sut_package_name": "new_package",
    }
    updated_metadata = metadata.update_if_changed(new_data)
    assert updated_metadata.name == "Updated Metadata"
    assert updated_metadata.sut_package_name == "new_package"
    assert len(updated_metadata.columns_meta) == 1
    assert len(updated_metadata.rows_meta) == 2  # should not remove rows from other runs
    assert len(updated_metadata.validation_rules["col1"]) == 2  # keep also the old rule


def test_no_update_on_same_data():
    metadata = ArgusGenericResultMetadata(
        test_id=generate_random_test_id(),
        name="Test Metadata",
        columns_meta=[{"name": "col1", "unit": "ms", "type": "float", "higher_is_better": True}],
        validation_rules={"col1": [{"valid_from": datetime.now(
            timezone.utc), "best_pct": 90.0, "best_abs": 100.0, "fixed_limit": 50.0}]},
        rows_meta=["row1", "row2"]
    )
    new_data = {
        "name": "Test Metadata",
        "columns_meta": [{"name": "col1", "unit": "ms", "type": "float", "higher_is_better": True}],
        "validation_rules": {"col1": {"valid_from": datetime.now(timezone.utc), "best_pct": 90.0, "best_abs": 100.0, "fixed_limit": 50.0}},
        "rows_meta": ["row1", "row2"]
    }
    with patch.object(metadata, 'save', wraps=metadata.save) as mock_save:
        metadata.update_if_changed(new_data)
        assert not mock_save.called


def test_adding_new_rows():
    metadata = ArgusGenericResultMetadata(
        test_id=generate_random_test_id(),
        name="Test Metadata",
        columns_meta=[{"name": "col1", "unit": "ms", "type": "float", "higher_is_better": True}],
        validation_rules={"col1": [{"valid_from": datetime.now(
            timezone.utc), "best_pct": 90.0, "best_abs": 100.0, "fixed_limit": 50.0}]},
        rows_meta=["row1"]
    )
    new_data = {"rows_meta": ["row2", "row3"]}
    updated_metadata = metadata.update_if_changed(new_data)
    assert len(updated_metadata.rows_meta) == 3
    assert "row2" in updated_metadata.rows_meta
    assert "row3" in updated_metadata.rows_meta
