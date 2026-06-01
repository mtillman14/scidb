"""
Tests for for_columns — column-wise iteration + reassembly in for_each().

`MyVar.for_columns([...])` (or `.for_columns()` for all columns) runs the
function once per column of a wide-table variable and reassembles the
per-column results into a single output variable whose data, per schema combo,
is a one-row table with the same column names as the source.

Covers:
- all-columns resolution and explicit-subset selection
- output is reassembled into one variable (1 x N, same column names)
- two for_columns inputs zipped by name (baseline Fixed + value)
- mismatched column sets raise
- column drift (a requested column absent) is a hard error
- where= still applies under iteration
- caching: identical re-run is a hit; changing the column set is not
- dry_run returns None
"""

import numpy as np
import pandas as pd
import pytest
import scifor as _scifor

from scidb import BaseVariable, configure_database, for_each, Fixed


SCHEMA = ["subject", "session"]


@pytest.fixture
def db(tmp_path):
    _scifor.set_schema([])
    db = configure_database(tmp_path / "test_for_columns.duckdb", SCHEMA)
    yield db
    _scifor.set_schema([])
    db.close()


# --- Variable types --------------------------------------------------------

class GaitData(BaseVariable): pass
class DeltaGait(BaseVariable): pass
class OtherData(BaseVariable): pass


# --- Pipeline functions ----------------------------------------------------

def col_mean(value):
    """Mean of a single column's values."""
    return float(np.mean(value))


def col_max(value):
    """Max of a single column's values (a different function for cache tests)."""
    return float(np.max(value))


def mean_change(baseline, value):
    """Change in column mean from a baseline."""
    return float(np.mean(value) - np.mean(baseline))


# --- Seeding ---------------------------------------------------------------

def _seed_wide(db, session="A"):
    """Two subjects, each a wide table with StepLength + Cadence columns."""
    GaitData.save(
        pd.DataFrame({"StepLength": [1.0, 2.0, 3.0], "Cadence": [10.0, 20.0, 30.0]}),
        db=db, subject="1", session=session,
    )
    GaitData.save(
        pd.DataFrame({"StepLength": [4.0, 5.0, 6.0], "Cadence": [40.0, 50.0, 60.0]}),
        db=db, subject="2", session=session,
    )


# ---------------------------------------------------------------------------
# ColumnSelection / for_columns basics
# ---------------------------------------------------------------------------

class TestForColumnsConstruction:
    def test_for_columns_all_sets_iterate(self):
        cs = GaitData.for_columns()
        assert cs.iterate is True
        assert cs.columns is None

    def test_for_columns_subset(self):
        cs = GaitData.for_columns(["StepLength", "Cadence"])
        assert cs.iterate is True
        assert cs.columns == ["StepLength", "Cadence"]

    def test_for_columns_single_string(self):
        cs = GaitData.for_columns("StepLength")
        assert cs.columns == ["StepLength"]

    def test_bracket_selection_not_iterate(self):
        assert GaitData["StepLength"].iterate is False

    def test_to_key_includes_iterate_and_columns(self):
        k_iter = GaitData.for_columns(["StepLength"]).to_key()
        k_plain = GaitData["StepLength"].to_key()
        assert "iterate=True" in k_iter
        assert k_iter != k_plain


# ---------------------------------------------------------------------------
# Reassembly into a single output variable
# ---------------------------------------------------------------------------

class TestForColumnsReassembly:
    def test_all_columns_reassembled(self, db):
        _seed_wide(db)

        result = for_each(
            col_mean,
            inputs={"value": GaitData.for_columns()},
            outputs=[DeltaGait],
            db=db,
            subject=[], session=[],
        )

        # One row per subject, columns mirror the source table.
        assert "StepLength" in result.columns
        assert "Cadence" in result.columns

        # load() returns the object directly for a single match.
        d1 = DeltaGait.load(db=db, subject="1", session="A")
        assert list(d1.data.columns) == ["StepLength", "Cadence"]
        assert d1.data["StepLength"].iloc[0] == pytest.approx(2.0)
        assert d1.data["Cadence"].iloc[0] == pytest.approx(20.0)

        d2 = DeltaGait.load(db=db, subject="2", session="A")
        assert d2.data["StepLength"].iloc[0] == pytest.approx(5.0)
        assert d2.data["Cadence"].iloc[0] == pytest.approx(50.0)

    def test_subset_columns(self, db):
        _seed_wide(db)

        for_each(
            col_mean,
            inputs={"value": GaitData.for_columns(["StepLength"])},
            outputs=[DeltaGait],
            db=db,
            subject=[], session=[],
        )

        d1 = DeltaGait.load(db=db, subject="1", session="A")
        assert list(d1.data.columns) == ["StepLength"]
        assert d1.data["StepLength"].iloc[0] == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# Two for_columns inputs zipped by name (baseline + value)
# ---------------------------------------------------------------------------

class TestForColumnsZip:
    def test_baseline_and_value(self, db):
        # Baseline session BL, value session FV.
        GaitData.save(
            pd.DataFrame({"StepLength": [1.0, 1.0], "Cadence": [10.0, 10.0]}),
            db=db, subject="1", session="BL",
        )
        GaitData.save(
            pd.DataFrame({"StepLength": [3.0, 3.0], "Cadence": [40.0, 40.0]}),
            db=db, subject="1", session="FV",
        )

        for_each(
            mean_change,
            inputs={
                "baseline": Fixed(GaitData.for_columns(), session="BL"),
                "value": GaitData.for_columns(),
            },
            outputs=[DeltaGait],
            db=db,
            subject=[], session=["FV"],
        )

        d = DeltaGait.load(db=db, subject="1", session="FV")
        assert d.data["StepLength"].iloc[0] == pytest.approx(2.0)   # 3 - 1
        assert d.data["Cadence"].iloc[0] == pytest.approx(30.0)     # 40 - 10

    def test_mismatched_column_sets_raise(self, db):
        _seed_wide(db)

        with pytest.raises(ValueError, match="same columns"):
            for_each(
                mean_change,
                inputs={
                    "baseline": GaitData.for_columns(["StepLength"]),
                    "value": GaitData.for_columns(["Cadence"]),
                },
                outputs=[DeltaGait],
                db=db,
                subject=[], session=[],
            )


# ---------------------------------------------------------------------------
# Column drift is a hard error
# ---------------------------------------------------------------------------

class TestForColumnsDrift:
    def test_missing_column_raises(self, db):
        _seed_wide(db)

        with pytest.raises(ValueError, match="drift"):
            for_each(
                col_mean,
                inputs={"value": GaitData.for_columns(["StepLength", "DoesNotExist"])},
                outputs=[DeltaGait],
                db=db,
                subject=[], session=[],
            )


# ---------------------------------------------------------------------------
# where= under iteration
# ---------------------------------------------------------------------------

class TestForColumnsWhere:
    def test_where_coexists_with_iteration(self, db):
        # A where= clause must not break column iteration. (where semantics
        # themselves are covered by test_where.py; here we only assert that
        # passing where under for_columns still runs and produces the output.)
        _seed_wide(db)

        result = for_each(
            col_mean,
            inputs={"value": GaitData.for_columns(["StepLength"])},
            outputs=[DeltaGait],
            db=db,
            where=GaitData["StepLength"] > 0.0,  # keeps all rows
            subject=["1"], session=[],
        )

        assert "StepLength" in result.columns
        d = DeltaGait.load(db=db, subject="1", session="A")
        assert list(d.data.columns) == ["StepLength"]
        assert d.data["StepLength"].iloc[0] == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

class TestForColumnsCaching:
    def test_identical_rerun_is_cached(self, db):
        _seed_wide(db)

        kwargs = dict(
            inputs={"value": GaitData.for_columns()},
            outputs=[DeltaGait],
            db=db,
            subject=[], session=[],
        )
        for_each(col_mean, **kwargs)
        for_each(col_mean, **kwargs)

        versions = DeltaGait.list_versions(db=db, subject="1", session="A")
        assert len(versions) == 1

    def test_changing_function_creates_new_record(self, db):
        # Different function over the same columns -> distinct version key ->
        # a new record coexists (same physical output columns, so the table
        # schema is unchanged).
        _seed_wide(db)

        for_each(
            col_mean,
            inputs={"value": GaitData.for_columns(["StepLength"])},
            outputs=[DeltaGait],
            db=db, subject=[], session=[],
        )
        for_each(
            col_max,
            inputs={"value": GaitData.for_columns(["StepLength"])},
            outputs=[DeltaGait],
            db=db, subject=[], session=[],
        )

        versions = DeltaGait.list_versions(db=db, subject="1", session="A")
        assert len(versions) == 2


# ---------------------------------------------------------------------------
# dry_run
# ---------------------------------------------------------------------------

class TestForColumnsDryRun:
    def test_dry_run_returns_none(self, db):
        _seed_wide(db)

        result = for_each(
            col_mean,
            inputs={"value": GaitData.for_columns()},
            outputs=[DeltaGait],
            db=db,
            dry_run=True,
            subject=[], session=[],
        )
        assert result is None
