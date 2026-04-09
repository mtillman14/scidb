"""
Tests for aggregation mode in for_each — iterating over a subset of schema keys.

When metadata_iterables covers fewer keys than the database schema, records at
lower schema levels are aggregated into multi-row DataFrames rather than being
processed individually.

Covers:
- No schema keys iterated (full aggregation): all records in one call
- Partial schema keys iterated: lower-level records aggregated per iterated key
- All schema keys iterated (baseline): one record per call
- Aggregation with constants (branch_params)
- Save behavior in aggregation mode
"""

import numpy as np
import pandas as pd
import pytest
import scifor as _scifor

from scidb import BaseVariable, configure_database, for_each


# ---------------------------------------------------------------------------
# Schema and fixtures
# ---------------------------------------------------------------------------

SCHEMA = ["subject", "session"]


@pytest.fixture
def db(tmp_path):
    """Fresh database with subject/session schema for each test."""
    _scifor.set_schema([])
    db = configure_database(tmp_path / "test_agg.duckdb", SCHEMA)
    yield db
    _scifor.set_schema([])
    db.close()


# ---------------------------------------------------------------------------
# Variable types
# ---------------------------------------------------------------------------

class RawSignal(BaseVariable):
    pass


class Aggregated(BaseVariable):
    pass


# ---------------------------------------------------------------------------
# Pipeline functions — these record what they receive for assertions
# ---------------------------------------------------------------------------

_last_call = {}


def aggregate_sum(signal):
    """Sum scalar values from the aggregated input."""
    _last_call.clear()
    if isinstance(signal, pd.DataFrame):
        _last_call["type"] = "dataframe"
        _last_call["nrows"] = len(signal)
        _last_call["columns"] = list(signal.columns)
        return signal.select_dtypes(include="number").values.sum()
    if isinstance(signal, np.ndarray):
        _last_call["type"] = "ndarray"
        _last_call["shape"] = signal.shape
        return signal.sum()
    _last_call["type"] = "scalar"
    return signal


def weighted_sum(signal, weight):
    """Multiply aggregated sum by a constant weight."""
    _last_call.clear()
    if isinstance(signal, np.ndarray):
        _last_call["type"] = "ndarray"
        _last_call["shape"] = signal.shape
        return signal.sum() * weight
    _last_call["type"] = "scalar"
    return signal * weight


# ---------------------------------------------------------------------------
# 1. Full aggregation — no schema keys iterated
# ---------------------------------------------------------------------------

class TestFullAggregation:
    """for_each with no metadata_iterables aggregates all records into one call."""

    def test_all_records_aggregated_into_single_call(self, db):
        """With 0 iterated keys and 4 records, function should be called once."""
        for subj in ["S01", "S02"]:
            for sess in ["1", "2"]:
                RawSignal.save(1.0, subject=subj, session=sess)

        result = for_each(aggregate_sum, {"signal": RawSignal}, [Aggregated],
                          save=False)

        assert result is not None
        assert len(result) == 1, "Expected exactly 1 iteration (full aggregation)"
        assert result["Aggregated"].iloc[0] == 4.0  # 4 records × 1.0

    def test_function_receives_all_rows(self, db):
        """The function should receive data from all 4 schema locations."""
        for subj in ["S01", "S02"]:
            for sess in ["1", "2"]:
                RawSignal.save(10.0, subject=subj, session=sess)

        for_each(aggregate_sum, {"signal": RawSignal}, [Aggregated], save=False)

        assert _last_call["type"] == "ndarray"
        assert _last_call["shape"][0] == 4  # 4 rows

    def test_single_record_full_aggregation(self, db):
        """Edge case: 1 record with no iterated keys still works."""
        RawSignal.save(5.0, subject="S01", session="1")

        result = for_each(aggregate_sum, {"signal": RawSignal}, [Aggregated],
                          save=False)

        assert result is not None
        assert len(result) == 1
        assert result["Aggregated"].iloc[0] == 5.0

    def test_result_value_correct(self, db):
        """Verify the aggregated computation produces the right value."""
        RawSignal.save(1.0, subject="S01", session="1")
        RawSignal.save(2.0, subject="S01", session="2")
        RawSignal.save(3.0, subject="S02", session="1")

        result = for_each(aggregate_sum, {"signal": RawSignal}, [Aggregated],
                          save=False)

        assert result is not None
        assert result["Aggregated"].iloc[0] == 6.0


# ---------------------------------------------------------------------------
# 2. Partial aggregation — subset of schema keys iterated
# ---------------------------------------------------------------------------

class TestPartialAggregation:
    """for_each iterating over a subset of schema keys aggregates lower-level records."""

    def test_iterate_subject_aggregates_sessions(self, db):
        """Iterating over subject only: each call gets all sessions for that subject."""
        RawSignal.save(1.0, subject="S01", session="1")
        RawSignal.save(2.0, subject="S01", session="2")
        RawSignal.save(3.0, subject="S02", session="1")
        RawSignal.save(4.0, subject="S02", session="2")

        result = for_each(aggregate_sum, {"signal": RawSignal}, [Aggregated],
                          subject=["S01", "S02"], save=False)

        assert result is not None
        assert len(result) == 2, "Expected 2 iterations (one per subject)"
        # S01: 1+2=3, S02: 3+4=7
        values = sorted(result["Aggregated"].tolist())
        assert values == [3.0, 7.0]

    def test_iterate_subject_with_uneven_sessions(self, db):
        """Subjects with different numbers of sessions still aggregate correctly."""
        RawSignal.save(1.0, subject="S01", session="1")
        RawSignal.save(2.0, subject="S01", session="2")
        RawSignal.save(3.0, subject="S01", session="3")
        RawSignal.save(10.0, subject="S02", session="1")

        result = for_each(aggregate_sum, {"signal": RawSignal}, [Aggregated],
                          subject=["S01", "S02"], save=False)

        assert result is not None
        assert len(result) == 2
        values = dict(zip(result["subject"].tolist(), result["Aggregated"].tolist()))
        assert values["S01"] == 6.0   # 1+2+3
        assert values["S02"] == 10.0


# ---------------------------------------------------------------------------
# 3. Full iteration baseline — all schema keys iterated
# ---------------------------------------------------------------------------

class TestFullIterationBaseline:
    """for_each with all schema keys iterated behaves as before (no aggregation)."""

    def test_each_record_processed_individually(self, db):
        """With all keys iterated, each subject×session is a separate call."""
        RawSignal.save(1.0, subject="S01", session="1")
        RawSignal.save(2.0, subject="S01", session="2")
        RawSignal.save(3.0, subject="S02", session="1")

        result = for_each(aggregate_sum, {"signal": RawSignal}, [Aggregated],
                          subject=["S01", "S02"], session=["1", "2"],
                          save=False)

        assert result is not None
        assert len(result) == 3, "Expected 3 iterations (one per existing record)"
        values = sorted(result["Aggregated"].tolist())
        assert values == [1.0, 2.0, 3.0]


# ---------------------------------------------------------------------------
# 4. Aggregation with constants
# ---------------------------------------------------------------------------

class TestAggregationWithConstants:
    """Aggregation mode works correctly when constants are passed."""

    def test_full_aggregation_with_constant(self, db):
        """Constants are passed alongside the aggregated data."""
        RawSignal.save(1.0, subject="S01", session="1")
        RawSignal.save(2.0, subject="S02", session="1")

        result = for_each(weighted_sum, {"signal": RawSignal, "weight": 10},
                          [Aggregated], save=False)

        assert result is not None
        assert len(result) == 1
        assert result["Aggregated"].iloc[0] == 30.0  # (1+2) * 10

    def test_partial_aggregation_with_constant(self, db):
        """Constants work alongside partial aggregation."""
        RawSignal.save(1.0, subject="S01", session="1")
        RawSignal.save(2.0, subject="S01", session="2")
        RawSignal.save(3.0, subject="S02", session="1")

        result = for_each(weighted_sum, {"signal": RawSignal, "weight": 2},
                          [Aggregated], subject=["S01", "S02"], save=False)

        assert result is not None
        assert len(result) == 2
        values = dict(zip(result["subject"].tolist(), result["Aggregated"].tolist()))
        assert values["S01"] == 6.0   # (1+2) * 2
        assert values["S02"] == 6.0   # 3 * 2


# ---------------------------------------------------------------------------
# 5. Aggregation with save
# ---------------------------------------------------------------------------

class TestAggregationSave:
    """Aggregation mode can save results (no branch_params from upstream)."""

    def test_full_aggregation_save(self, db):
        """Results from full aggregation can be saved and loaded."""
        RawSignal.save(1.0, subject="S01", session="1")
        RawSignal.save(2.0, subject="S02", session="1")

        # Full aggregation produces a result with no schema metadata.
        # save=True should not crash even though there are no schema keys.
        result = for_each(aggregate_sum, {"signal": RawSignal}, [Aggregated],
                          save=True)

        assert result is not None
        assert len(result) == 1
        assert result["Aggregated"].iloc[0] == 3.0
