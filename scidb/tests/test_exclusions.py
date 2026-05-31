"""Tests for schema-based exclusions (exclude_schema / include_schema / list_exclusions)."""

import sys
from pathlib import Path

import numpy as np
import pytest

_root = Path(__file__).parent.parent
sys.path.insert(0, str(_root / "src"))
sys.path.insert(0, str(_root / "sciduck" / "src"))
sys.path.insert(0, str(_root / "scifor" / "src"))
sys.path.insert(0, str(_root / "scilineage" / "src"))
sys.path.insert(0, str(_root / "path-gen" / "src"))
sys.path.insert(0, str(_root / "canonical-hash" / "src"))

import scidb
from scidb import configure_database, exclude_schema, include_schema, list_exclusions, for_each, BaseVariable
from scidb.exclusions import (
    get_schema_overrides_hash,
    filter_excluded_combos,
    _TABLE,
    _current_status,
)
from scidb.database import _local


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_db_state():
    if hasattr(_local, "database"):
        delattr(_local, "database")
    yield
    if hasattr(_local, "database"):
        delattr(_local, "database")


@pytest.fixture
def db(tmp_path):
    d = configure_database(tmp_path / "test.duckdb", ["subject", "trial"])
    yield d
    d.close()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _count_rows(db, **filters) -> int:
    """Count rows in __scidb_schema_overrides matching optional filters."""
    where_parts = []
    params = []
    for k, v in filters.items():
        where_parts.append(f'"{k}" = ?')
        params.append(str(v))
    where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    rows = db._duck._fetchall(
        f"SELECT COUNT(*) FROM {_TABLE} {where_clause}", params or None
    )
    return rows[0][0]


# ===========================================================================
# Basic exclude / include
# ===========================================================================

class TestExcludeSchema:
    def test_basic_exclude(self, db):
        exclude_schema(subject=1, trial=2, reason="bad trial", db=db)
        assert _count_rows(db) == 1

    def test_exclude_writes_status_false(self, db):
        exclude_schema(subject=1, trial=2, reason="bad", db=db)
        status = _current_status(db, {"subject": 1, "trial": 2})
        assert status is False

    def test_exclude_no_keys_raises(self, db):
        with pytest.raises(ValueError, match="At least one schema key"):
            exclude_schema(reason="bad", db=db)

    def test_exclude_unknown_key_raises(self, db):
        with pytest.raises(ValueError, match="Unknown schema key"):
            exclude_schema(subject=1, session=99, reason="bad", db=db)

    def test_exclude_already_excluded_raises(self, db):
        exclude_schema(subject=1, trial=2, reason="first", db=db)
        with pytest.raises(ValueError, match="already excluded"):
            exclude_schema(subject=1, trial=2, reason="second", db=db)

    def test_exclude_partial_keys_wildcard(self, db):
        # Exclude entire subject (trial is NULL = wildcard)
        exclude_schema(subject=3, reason="whole subject excluded", db=db)
        status = _current_status(db, {"subject": 3})
        assert status is False

    def test_exclude_uses_global_db(self, db):
        exclude_schema(subject=1, trial=2, reason="bad")
        assert _count_rows(db) == 1


class TestIncludeSchema:
    def test_include_after_exclude(self, db):
        exclude_schema(subject=1, trial=2, reason="bad", db=db)
        include_schema(subject=1, trial=2, reason="re-reviewed", db=db)
        status = _current_status(db, {"subject": 1, "trial": 2})
        assert status is True

    def test_include_without_prior_exclude_raises(self, db):
        with pytest.raises(ValueError, match="no exclusion record"):
            include_schema(subject=1, trial=2, reason="oops", db=db)

    def test_include_already_included_raises(self, db):
        exclude_schema(subject=1, trial=2, reason="bad", db=db)
        include_schema(subject=1, trial=2, reason="ok now", db=db)
        with pytest.raises(ValueError, match="already included"):
            include_schema(subject=1, trial=2, reason="again", db=db)

    def test_include_preserves_history(self, db):
        """The original exclusion row must remain (audit trail)."""
        exclude_schema(subject=1, trial=2, reason="bad", db=db)
        include_schema(subject=1, trial=2, reason="ok", db=db)
        assert _count_rows(db) == 2

    def test_include_no_keys_raises(self, db):
        with pytest.raises(ValueError, match="At least one schema key"):
            include_schema(reason="oops", db=db)


# ===========================================================================
# list_exclusions
# ===========================================================================

class TestListExclusions:
    def test_returns_empty_when_none(self, db):
        df = list_exclusions(db=db)
        assert len(df) == 0

    def test_returns_excluded_rows(self, db):
        exclude_schema(subject=1, trial=2, reason="bad", db=db)
        exclude_schema(subject=3, reason="whole subject", db=db)
        df = list_exclusions(db=db)
        assert len(df) == 2

    def test_does_not_return_re_included(self, db):
        exclude_schema(subject=1, trial=2, reason="bad", db=db)
        include_schema(subject=1, trial=2, reason="ok", db=db)
        df = list_exclusions(db=db)
        assert len(df) == 0

    def test_shows_only_current_excluded(self, db):
        exclude_schema(subject=1, trial=1, reason="bad1", db=db)
        exclude_schema(subject=1, trial=2, reason="bad2", db=db)
        include_schema(subject=1, trial=1, reason="ok", db=db)
        df = list_exclusions(db=db)
        assert len(df) == 1
        assert str(df.iloc[0]["trial"]) == "2"


# ===========================================================================
# No-op guard — exact-keyset semantics
# ===========================================================================

class TestNoOpGuard:
    def test_specific_can_be_added_even_if_wildcard_already_excluded(self, db):
        # Wildcard row: subject=3, trial=NULL
        exclude_schema(subject=3, reason="whole subject excluded", db=db)
        # Specific row: subject=3, trial=2 (different keyset — allowed)
        exclude_schema(subject=3, trial=2, reason="trial 2 also explicitly bad", db=db)
        assert _count_rows(db) == 2

    def test_most_specific_wins_over_wildcard(self, db):
        exclude_schema(subject=3, reason="whole subject excluded", db=db)
        # Re-include just trial 2 at the more specific level
        # First need to add the specific keyset before including it
        exclude_schema(subject=3, trial=2, reason="also excluded", db=db)
        include_schema(subject=3, trial=2, reason="trial 2 is actually fine", db=db)
        # Subject=3 wildcard is still excluded
        assert _current_status(db, {"subject": 3}) is False
        # But trial 2 specifically is now included (most specific wins)
        assert _current_status(db, {"subject": 3, "trial": 2}) is True


# ===========================================================================
# filter_excluded_combos
# ===========================================================================

class TestFilterExcludedCombos:
    def test_no_overrides_returns_all(self, db):
        combos = [{"subject": "1", "trial": "1"}, {"subject": "1", "trial": "2"}]
        result = filter_excluded_combos(combos, ["subject", "trial"], db)
        assert result == combos

    def test_exact_match_excluded(self, db):
        exclude_schema(subject=1, trial=2, reason="bad", db=db)
        combos = [{"subject": "1", "trial": "1"}, {"subject": "1", "trial": "2"}]
        result = filter_excluded_combos(combos, ["subject", "trial"], db)
        assert len(result) == 1
        assert result[0]["trial"] == "1"

    def test_wildcard_excludes_all_trials(self, db):
        exclude_schema(subject=3, reason="whole subject", db=db)
        combos = [
            {"subject": "3", "trial": "1"},
            {"subject": "3", "trial": "2"},
            {"subject": "1", "trial": "1"},
        ]
        result = filter_excluded_combos(combos, ["subject", "trial"], db)
        assert len(result) == 1
        assert result[0]["subject"] == "1"

    def test_specific_include_overrides_wildcard_exclude(self, db):
        exclude_schema(subject=3, reason="whole subject", db=db)
        exclude_schema(subject=3, trial=2, reason="also excluded", db=db)
        include_schema(subject=3, trial=2, reason="trial 2 ok after all", db=db)
        combos = [
            {"subject": "3", "trial": "1"},
            {"subject": "3", "trial": "2"},
        ]
        result = filter_excluded_combos(combos, ["subject", "trial"], db)
        assert len(result) == 1
        assert result[0]["trial"] == "2"

    def test_re_included_combo_survives(self, db):
        exclude_schema(subject=1, trial=2, reason="bad", db=db)
        include_schema(subject=1, trial=2, reason="ok", db=db)
        combos = [{"subject": "1", "trial": "2"}]
        result = filter_excluded_combos(combos, ["subject", "trial"], db)
        assert len(result) == 1


# ===========================================================================
# get_schema_overrides_hash
# ===========================================================================

class TestSchemaOverridesHash:
    def test_empty_table_returns_stable_hash(self, db):
        h1 = get_schema_overrides_hash(db)
        h2 = get_schema_overrides_hash(db)
        assert h1 == h2

    def test_hash_changes_on_exclude(self, db):
        h_before = get_schema_overrides_hash(db)
        exclude_schema(subject=1, trial=2, reason="bad", db=db)
        h_after = get_schema_overrides_hash(db)
        assert h_before != h_after

    def test_hash_changes_on_include(self, db):
        exclude_schema(subject=1, trial=2, reason="bad", db=db)
        h_before = get_schema_overrides_hash(db)
        include_schema(subject=1, trial=2, reason="ok", db=db)
        h_after = get_schema_overrides_hash(db)
        assert h_before != h_after


# ===========================================================================
# Backends without a DuckDB layer (no _duck) — exclusions degrade gracefully
# ===========================================================================

class _NoDuckDB:
    """Database double that doesn't expose a DuckDB backend.

    Mirrors backends (remote/net) and the lightweight test doubles used by
    scihist's for_each tests, which implement the public Database surface but
    have no ``_duck``.  Regression guard for the AttributeError that crashed
    for_each Step 9.5 when it reached straight into ``db._duck``.
    """

    dataset_schema_keys = ["subject", "trial"]


class TestExclusionsWithoutDuckBackend:
    def test_overrides_hash_returns_empty_payload_hash(self):
        import hashlib
        import json
        # Same value an empty overrides table would produce, not a crash.
        empty_payload_hash = hashlib.sha256(
            json.dumps([], sort_keys=True).encode()
        ).hexdigest()[:16]
        assert get_schema_overrides_hash(_NoDuckDB()) == empty_payload_hash

    def test_overrides_hash_is_stable_without_backend(self):
        assert get_schema_overrides_hash(_NoDuckDB()) == get_schema_overrides_hash(_NoDuckDB())

    def test_filter_returns_combos_unchanged_without_backend(self):
        combos = [{"subject": "1", "trial": "1"}, {"subject": "1", "trial": "2"}]
        result = filter_excluded_combos(combos, ["subject", "trial"], _NoDuckDB())
        assert result == combos


# ===========================================================================
# Integration with for_each
# ===========================================================================

class ScalarOutput(BaseVariable):
    schema_version = 1


class TestForEachIntegration:
    """for_each must skip excluded combos and encode override hash in version_keys."""

    def _setup(self, db):
        ScalarOutput.save(10.0, subject=1, trial=1)
        ScalarOutput.save(20.0, subject=1, trial=2)
        ScalarOutput.save(30.0, subject=2, trial=1)

    def test_excluded_combo_skipped(self, db, tmp_path):
        self._setup(db)
        exclude_schema(subject=1, trial=2, reason="bad", db=db)

        class DoubledOutput(BaseVariable):
            schema_version = 1

        processed = []

        def double(x):
            processed.append(x)
            return x * 2

        for_each(
            double,
            inputs={"x": ScalarOutput},
            outputs=[DoubledOutput],
            subject=[],
            trial=[],
        )

        # (subject=1, trial=2) should have been skipped
        assert len(processed) == 2
        assert 20.0 not in processed

    def test_override_hash_in_version_keys(self, db, tmp_path):
        self._setup(db)

        class TaggedOutput(BaseVariable):
            schema_version = 1

        def identity(x):
            return x

        for_each(
            identity,
            inputs={"x": ScalarOutput},
            outputs=[TaggedOutput],
            subject=[],
            trial=[],
        )

        # Check that __schema_overrides_hash appears in version_keys
        rows = db._duck._fetchall(
            "SELECT version_keys FROM _record_metadata WHERE variable_name = 'TaggedOutput'"
        )
        import json
        found = any(
            "__schema_overrides_hash" in json.loads(r[0] or "{}")
            for r in rows
        )
        assert found, "Expected __schema_overrides_hash in version_keys"

    def test_cache_invalidated_when_override_changes(self, db, tmp_path):
        """Records written before and after an exclusion must have different version_keys."""
        self._setup(db)

        class VersionedOutput(BaseVariable):
            schema_version = 1

        def identity(x):
            return x

        for_each(
            identity,
            inputs={"x": ScalarOutput},
            outputs=[VersionedOutput],
            subject=[],
            trial=[],
        )

        import json
        rows_before = db._duck._fetchall(
            "SELECT version_keys FROM _record_metadata WHERE variable_name = 'VersionedOutput'"
        )
        hashes_before = {
            json.loads(r[0] or "{}").get("__schema_overrides_hash") for r in rows_before
        }

        exclude_schema(subject=1, trial=2, reason="bad", db=db)

        for_each(
            identity,
            inputs={"x": ScalarOutput},
            outputs=[VersionedOutput],
            subject=[],
            trial=[],
        )

        rows_after = db._duck._fetchall(
            "SELECT version_keys FROM _record_metadata WHERE variable_name = 'VersionedOutput'"
        )
        hashes_after = {
            json.loads(r[0] or "{}").get("__schema_overrides_hash") for r in rows_after
        }

        # The hash from the second run must differ from the first run
        assert hashes_before != hashes_after or len(hashes_before) < len(hashes_after)
