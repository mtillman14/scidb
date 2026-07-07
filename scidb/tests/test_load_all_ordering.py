"""
Regression test to verify that load_all() returns data ordered by schema keys.

This test ensures that bulk loading operations return data sorted by schema keys
in the order they appear in the dataset schema, with alphanumeric sorting within
each key. This guarantees predictable ordering for downstream processing.
"""

import numpy as np
import pandas as pd
import pytest
import scifor as _scifor

from scidb import BaseVariable, configure_database


SCHEMA = ["subject", "trial"]


@pytest.fixture
def db(tmp_path):
    """Fresh database for each test."""
    _scifor.set_schema([])
    db = configure_database(tmp_path / "test_ordering.duckdb", SCHEMA)
    yield db
    _scifor.set_schema([])
    db.close()


class TestData(BaseVariable):
    __test__ = False  # fixture data type, not a test class (silences pytest collection warning)


class TestLoadAllOrdering:
    """Verify load_all() returns data ordered by schema keys."""

    def test_load_all_orders_by_schema_keys(self, db):
        """load_all() should return data ordered by schema keys in dataset order."""
        # Save data in non-alphabetical order to verify ordering is enforced
        TestData.save(np.array([1.0]), subject="S03", trial="T02")
        TestData.save(np.array([2.0]), subject="S01", trial="T01")
        TestData.save(np.array([3.0]), subject="S02", trial="T03")
        TestData.save(np.array([4.0]), subject="S01", trial="T02")
        TestData.save(np.array([5.0]), subject="S03", trial="T01")
        TestData.save(np.array([6.0]), subject="S02", trial="T01")

        # Load all data
        results = TestData.load(version="all")

        # Extract schema keys in the order they were loaded (convert to strings)
        loaded_order = [(str(v.metadata["subject"]), str(v.metadata["trial"])) for v in results]

        # Expected order: sorted by subject, then by trial within each subject
        expected_order = [
            ("S01", "T01"),
            ("S01", "T02"),
            ("S02", "T01"),
            ("S02", "T03"),
            ("S03", "T01"),
            ("S03", "T02"),
        ]

        assert loaded_order == expected_order, (
            f"Data not ordered by schema keys.\n"
            f"Expected: {expected_order}\n"
            f"Got:      {loaded_order}"
        )

    def test_load_all_with_dataframe_data_orders_rows(self, db):
        """load_all() should maintain schema ordering for DataFrame variables."""
        # Save DataFrames with multiple rows per schema location
        TestData.save(
            pd.DataFrame({"value": [30, 31]}),
            subject="S03", trial="T01"
        )
        TestData.save(
            pd.DataFrame({"value": [10, 11]}),
            subject="S01", trial="T01"
        )
        TestData.save(
            pd.DataFrame({"value": [20, 21]}),
            subject="S02", trial="T01"
        )

        # Load all data
        results = TestData.load(version="all")

        # Verify schema key ordering (convert to strings)
        loaded_subjects = [str(v.metadata["subject"]) for v in results]
        assert loaded_subjects == ["S01", "S02", "S03"], (
            f"DataFrame variables not ordered by schema keys: {loaded_subjects}"
        )

        # Verify data values are correct
        assert results[0].data["value"].tolist() == [10, 11]
        assert results[1].data["value"].tolist() == [20, 21]
        assert results[2].data["value"].tolist() == [30, 31]

    def test_load_all_numeric_schema_keys_sorted_numerically(self, db):
        """Schema keys with all-numeric values should be sorted numerically."""
        # Save with numeric-looking string values
        TestData.save(np.array([1.0]), subject="10", trial="1")
        TestData.save(np.array([2.0]), subject="2", trial="1")
        TestData.save(np.array([3.0]), subject="100", trial="1")
        TestData.save(np.array([4.0]), subject="20", trial="1")

        results = TestData.load(version="all")
        # Convert to strings for comparison (schema keys may be returned as native types)
        loaded_subjects = [str(v.metadata["subject"]) for v in results]

        # All values are numeric, so sort numerically: "2", "10", "20", "100"
        expected_subjects = ["2", "10", "20", "100"]
        assert loaded_subjects == expected_subjects, (
            f"All-numeric schema keys not sorted numerically.\n"
            f"Expected: {expected_subjects}\n"
            f"Got:      {loaded_subjects}"
        )

    def test_load_all_mixed_alphanumeric_sorted_alphabetically(self, db):
        """Schema keys with any non-numeric values should be sorted alphabetically."""
        # Save with mixed numeric and alphanumeric values
        TestData.save(np.array([1.0]), subject="10", trial="1")
        TestData.save(np.array([2.0]), subject="2", trial="1")
        TestData.save(np.array([3.0]), subject="S01", trial="1")  # Has letter
        TestData.save(np.array([4.0]), subject="20", trial="1")
        TestData.save(np.array([5.0]), subject="100", trial="1")

        results = TestData.load(version="all")
        # Convert to strings for comparison (schema keys may be returned as native types)
        loaded_subjects = [str(v.metadata["subject"]) for v in results]

        # Mixed values → alphabetical sort: "10", "100", "2", "20", "S01"
        expected_subjects = ["10", "100", "2", "20", "S01"]
        assert loaded_subjects == expected_subjects, (
            f"Mixed alphanumeric schema keys not sorted alphabetically.\n"
            f"Expected: {expected_subjects}\n"
            f"Got:      {loaded_subjects}"
        )

    def test_load_all_with_metadata_filter_preserves_ordering(self, db):
        """load_all() with metadata filters should still return ordered results."""
        # Create data across multiple subjects
        for subj in ["S03", "S01", "S02"]:
            for trial in ["T02", "T01"]:
                TestData.save(np.array([1.0]), subject=subj, trial=trial)

        # Load with filter (only S01 and S03)
        results = TestData.load(version="all", subject=["S01", "S03"])

        # Should still be ordered by schema keys (convert to strings)
        loaded_order = [(str(v.metadata["subject"]), str(v.metadata["trial"])) for v in results]
        expected_order = [
            ("S01", "T01"),
            ("S01", "T02"),
            ("S03", "T01"),
            ("S03", "T02"),
        ]

        assert loaded_order == expected_order, (
            f"Filtered load_all() not ordered by schema keys.\n"
            f"Expected: {expected_order}\n"
            f"Got:      {loaded_order}"
        )

    def test_load_all_with_three_level_schema(self, tmp_path):
        """Verify ordering works with deeper schema hierarchies."""
        # Create database with 3-level schema
        _scifor.set_schema([])
        db = configure_database(
            tmp_path / "test_three_level.duckdb",
            ["subject", "session", "trial"]
        )

        class MultiLevelData(BaseVariable):
            pass

        # Save in random order
        MultiLevelData.save(np.array([1.0]), subject="S02", session="A", trial="T01")
        MultiLevelData.save(np.array([2.0]), subject="S01", session="B", trial="T02")
        MultiLevelData.save(np.array([3.0]), subject="S02", session="A", trial="T02")
        MultiLevelData.save(np.array([4.0]), subject="S01", session="A", trial="T01")
        MultiLevelData.save(np.array([5.0]), subject="S01", session="B", trial="T01")

        # Load and verify ordering (convert to strings)
        results = MultiLevelData.load(version="all")
        loaded_order = [
            (str(v.metadata["subject"]), str(v.metadata["session"]), str(v.metadata["trial"]))
            for v in results
        ]

        expected_order = [
            ("S01", "A", "T01"),
            ("S01", "B", "T01"),
            ("S01", "B", "T02"),
            ("S02", "A", "T01"),
            ("S02", "A", "T02"),
        ]

        assert loaded_order == expected_order, (
            f"3-level schema not ordered correctly.\n"
            f"Expected: {expected_order}\n"
            f"Got:      {loaded_order}"
        )

        db.close()
        _scifor.set_schema([])
