"""Integration tests for SchemaKey filter types.

Tests verify that schema-key-based filters correctly restrict which records
are returned from load(), covering:
- String key isin (session IN [...])
- Numeric key isin (subject IN [...])
- Equality and inequality on string keys
- Ordering operators (<, <=, >, >=) on numeric keys stored as VARCHAR
- AND/OR combinations of schema key filters
- Combined schema key + variable filters
- Error cases (unknown key)
"""

import pytest

import sys
from pathlib import Path
_root = Path(__file__).parent.parent
sys.path.insert(0, str(_root / "src"))

from scidb import BaseVariable, configure_database, schema_key
from scidb.exceptions import NotFoundError
from scidb.filters import SchemaKeyCompareFilter, SchemaKeyInFilter


# ===========================================================================
# Variable classes
# ===========================================================================

class Measurement(BaseVariable):
    """Scalar measurement used across all schema key filter tests."""
    schema_version = 1


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def session_db(tmp_path):
    """DB with schema keys [subject, session].

    Data layout (all for Measurement):
      subject=1, session="BL"    → 1.0
      subject=1, session="POST"  → 2.0
      subject=1, session="FOL"   → 3.0
      subject=2, session="BL"    → 4.0
      subject=2, session="POST"  → 5.0
    """
    db = configure_database(tmp_path / "test.duckdb", ["subject", "session"])
    Measurement.save(1.0, subject=1, session="BL")
    Measurement.save(2.0, subject=1, session="POST")
    Measurement.save(3.0, subject=1, session="FOL")
    Measurement.save(4.0, subject=2, session="BL")
    Measurement.save(5.0, subject=2, session="POST")
    yield db
    db.close()


@pytest.fixture
def numeric_db(tmp_path):
    """DB with schema key [subject] and subjects 1–5."""
    db = configure_database(tmp_path / "test.duckdb", ["subject"])
    for i in range(1, 6):
        Measurement.save(float(i * 10), subject=i)
    yield db
    db.close()


# ===========================================================================
# isin — string schema key
# ===========================================================================

class TestSchemaKeyIsin:

    def test_isin_two_of_three_sessions(self, session_db):
        results = Measurement.load(where=schema_key("session").isin(["BL", "POST"]))
        assert len(results) == 4  # subjects 1+2, sessions BL+POST

    def test_isin_single_session(self, session_db):
        results = Measurement.load(where=schema_key("session").isin(["BL"]))
        assert len(results) == 2

    def test_isin_empty_returns_nothing(self, session_db):
        with pytest.raises(NotFoundError):
            Measurement.load(where=schema_key("session").isin([]))

    def test_isin_no_match_raises(self, session_db):
        with pytest.raises(NotFoundError):
            Measurement.load(where=schema_key("session").isin(["NONEXISTENT"]))

    def test_isin_with_metadata_narrows_further(self, session_db):
        result = Measurement.load(
            subject=1,
            where=schema_key("session").isin(["BL", "POST"]),
        )
        # subject=1 has BL and POST → 2 records, but single subject+session → array
        assert len(result) == 2

    def test_isin_all_sessions_returns_all(self, session_db):
        results = Measurement.load(
            where=schema_key("session").isin(["BL", "POST", "FOL"])
        )
        assert len(results) == 5


# ===========================================================================
# isin — numeric schema key
# ===========================================================================

class TestSchemaKeyIsinNumeric:

    def test_isin_numeric_subjects(self, numeric_db):
        results = Measurement.load(where=schema_key("subject").isin([1, 2]))
        assert len(results) == 2

    def test_isin_numeric_single(self, numeric_db):
        result = Measurement.load(where=schema_key("subject").isin([3]))
        # Single result may come back as a single BaseVariable, not a list
        if hasattr(result, '__len__'):
            assert len(result) == 1
        else:
            assert result.metadata["subject"] in ("3", 3)

    def test_isin_float_whole_numbers(self, numeric_db):
        # 1.0 and 2.0 should match subjects 1 and 2 (stored as "1", "2")
        results = Measurement.load(where=schema_key("subject").isin([1.0, 2.0]))
        assert len(results) == 2


# ===========================================================================
# Equality and inequality — string key
# ===========================================================================

class TestSchemaKeyEquality:

    def test_eq_string_key(self, session_db):
        results = Measurement.load(where=schema_key("session") == "BL")
        assert len(results) == 2

    def test_ne_string_key(self, session_db):
        # All except BL → POST + FOL = 3 records
        results = Measurement.load(where=schema_key("session") != "BL")
        assert len(results) == 3

    def test_eq_numeric_key(self, numeric_db):
        result = Measurement.load(where=schema_key("subject") == 3)
        # Single record
        if hasattr(result, '__len__'):
            assert len(result) == 1
        else:
            assert result.metadata["subject"] in ("3", 3)


# ===========================================================================
# Ordering operators — numeric key stored as VARCHAR
# ===========================================================================

class TestSchemaKeyOrdering:

    def test_gt(self, numeric_db):
        results = Measurement.load(where=schema_key("subject") > 3)
        assert len(results) == 2  # subjects 4, 5

    def test_ge(self, numeric_db):
        results = Measurement.load(where=schema_key("subject") >= 3)
        assert len(results) == 3  # subjects 3, 4, 5

    def test_lt(self, numeric_db):
        results = Measurement.load(where=schema_key("subject") < 3)
        assert len(results) == 2  # subjects 1, 2

    def test_le(self, numeric_db):
        results = Measurement.load(where=schema_key("subject") <= 3)
        assert len(results) == 3  # subjects 1, 2, 3

    def test_gt_excludes_boundary(self, numeric_db):
        """Verify > 5 returns nothing (subjects only go up to 5)."""
        with pytest.raises(NotFoundError):
            Measurement.load(where=schema_key("subject") > 5)

    def test_ordering_correct_for_multi_digit(self, tmp_path):
        """Lexicographic ordering would give wrong results (10 < 2 as string).
        Numeric cast must be used so 10 > 9."""
        db = configure_database(tmp_path / "test.duckdb", ["subject"])
        try:
            for i in [1, 2, 9, 10, 11]:
                Measurement.save(float(i), subject=i)
            results = Measurement.load(where=schema_key("subject") > 9)
            assert len(results) == 2  # subjects 10, 11 — would be 0 with lexicographic sort
        finally:
            db.close()


# ===========================================================================
# Compound combinations
# ===========================================================================

class TestSchemaKeyCompound:

    def test_and_two_schema_key_filters(self, numeric_db):
        f = (schema_key("subject") >= 2) & (schema_key("subject") <= 4)
        results = Measurement.load(where=f)
        assert len(results) == 3  # subjects 2, 3, 4

    def test_or_two_schema_key_filters(self, session_db):
        f = (schema_key("session") == "BL") | (schema_key("session") == "FOL")
        results = Measurement.load(where=f)
        assert len(results) == 3  # subject 1+2 BL, subject 1 FOL

    def test_not_schema_key_filter(self, session_db):
        f = ~schema_key("session").isin(["BL"])
        results = Measurement.load(where=f)
        assert len(results) == 3  # POST×2 + FOL×1


# ===========================================================================
# Error handling
# ===========================================================================

class TestSchemaKeyFilterErrors:

    def test_unknown_key_raises(self, session_db):
        with pytest.raises(ValueError, match="Unknown schema key"):
            Measurement.load(where=schema_key("nonexistent") == "BL")

    def test_unknown_key_isin_raises(self, session_db):
        with pytest.raises(ValueError, match="Unknown schema key"):
            Measurement.load(where=schema_key("nonexistent").isin(["BL"]))
