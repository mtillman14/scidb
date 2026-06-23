"""Regression tests for non-existent-combo leakage with ColumnSelection inputs.

Bug: ``_for_each_prepare`` Step 11 detected input wrappers with a bare
``hasattr(data, 'data')`` check. Both ``_scifor.Fixed`` and
``_scifor.ColumnSelection`` expose a ``.data`` DataFrame, so a ColumnSelection
input (e.g. ``GaitData["StepLength"]``) was misclassified as Fixed and never had
its rid key registered. In full-iteration mode the rid-validity skip is the ONLY
thing that prunes Cartesian-product combos with no backing data, so disabling rid
tracking caused every non-existent schema location to be passed to the user's
function as an EMPTY table.

Observed symptom (MATLAB): iterating subject/session/speed/trial/cycle over a
sparse, ragged dataset produced runs of populated tables interleaved with runs of
0-row tables (the missing grid points), e.g. one 2x6 table, then four 0x6 tables,
then several 2x6 tables, etc.

These tests pin the fix: a ColumnSelection input must prune non-existent combos
exactly like a plain variable input does, and must never hand the function an
empty per-combo table for a location that has no data.
"""

import numpy as np
import pandas as pd
import pytest

import scifor as _scifor
from scidb import BaseVariable, configure_database, for_each


SCHEMA = ["subject", "session"]


@pytest.fixture
def db(tmp_path):
    _scifor.set_schema([])
    db = configure_database(tmp_path / "test_combo_pruning.duckdb", SCHEMA)
    yield db
    _scifor.set_schema([])
    db.close()


class GaitData(BaseVariable):
    pass


class OutVar(BaseVariable):
    pass


def _seed_sparse(db):
    """Populate a RAGGED grid: subject 1 has sessions A and B; subject 2 has
    only session A. The Cartesian product of distinct values therefore includes
    (subject=2, session=B), which does NOT exist in the data.
    """
    GaitData.save(
        pd.DataFrame({"StepLength": [1.0, 2.0], "Cadence": [10.0, 20.0]}),
        db=db, subject="1", session="A",
    )
    GaitData.save(
        pd.DataFrame({"StepLength": [3.0, 4.0], "Cadence": [30.0, 40.0]}),
        db=db, subject="1", session="B",
    )
    GaitData.save(
        pd.DataFrame({"StepLength": [5.0, 6.0], "Cadence": [50.0, 60.0]}),
        db=db, subject="2", session="A",
    )


# Populated locations (the only combos a correct run should visit).
POPULATED = {("1", "A"), ("1", "B"), ("2", "A")}
# The Cartesian product additionally contains this non-existent location.
NONEXISTENT = ("2", "B")


def _make_recorder():
    """Return (fn, calls) where fn records each per-combo call it receives.

    With as_table=True the per-combo DataFrame carries the schema columns, so a
    non-empty call reveals its own (subject, session). Empty calls are recorded
    with row count 0 (and would only happen for a leaked non-existent combo).
    """
    calls: list[dict] = []

    def record(value):
        rows = len(value)
        combos = (
            set(zip(value["subject"].tolist(), value["session"].tolist()))
            if rows
            else set()
        )
        calls.append({
            "rows": rows,
            "combos": combos,
            "columns": list(value.columns),
        })
        return float(rows)

    return record, calls


def _assert_no_internal_columns(calls):
    """The function must never see internal tracking columns (e.g. __rid_*)."""
    for c in calls:
        leaked = [col for col in c["columns"] if col.startswith("__")]
        assert leaked == [], f"internal column(s) leaked to fn: {leaked}"


def _visited_combos(calls):
    visited: set = set()
    for c in calls:
        visited |= c["combos"]
    return visited


class TestColumnSelectionComboPruning:
    def test_column_selection_does_not_leak_empty_combos(self, db):
        """A ColumnSelection input must never hand the function an empty table
        for a non-existent schema location."""
        _seed_sparse(db)
        record, calls = _make_recorder()

        for_each(
            record,
            {"value": GaitData["StepLength"]},
            [OutVar],
            subject=[], session=[],
            as_table=True, save=False,
        )

        empty_calls = [c for c in calls if c["rows"] == 0]
        assert empty_calls == [], (
            f"expected no empty per-combo calls, got {len(empty_calls)} "
            f"(non-existent combo {NONEXISTENT} leaked through as an empty table)"
        )
        assert _visited_combos(calls) == POPULATED
        assert NONEXISTENT not in _visited_combos(calls)
        # Exactly one call per populated location (no rid variants here).
        assert len(calls) == len(POPULATED)
        # The internal __rid_* discriminator must not leak into the as_table df.
        _assert_no_internal_columns(calls)

    def test_column_selection_matches_plain_input_combos(self, db):
        """ColumnSelection input must visit the SAME combos as a plain variable
        input (parity) — the column narrowing must not change which combos run."""
        _seed_sparse(db)

        rec_plain, calls_plain = _make_recorder()
        for_each(
            rec_plain,
            {"value": GaitData},
            [OutVar],
            subject=[], session=[],
            as_table=True, save=False,
        )

        rec_sel, calls_sel = _make_recorder()
        for_each(
            rec_sel,
            {"value": GaitData["StepLength"]},
            [OutVar],
            subject=[], session=[],
            as_table=True, save=False,
        )

        assert _visited_combos(calls_plain) == _visited_combos(calls_sel) == POPULATED
        assert len(calls_plain) == len(calls_sel) == len(POPULATED)
        # Neither path produced an empty (leaked) combo.
        assert not any(c["rows"] == 0 for c in calls_plain)
        assert not any(c["rows"] == 0 for c in calls_sel)
        # Neither path leaks internal tracking columns to the function.
        _assert_no_internal_columns(calls_plain)
        _assert_no_internal_columns(calls_sel)
