"""A dict-valued record must reach the next function as a dict.

A variable whose value is a dict is stored one DuckDB column per key
(sciduckdb ``multi_column`` mode) and loaded by ``for_each`` in the spread
layout, so a single record looks exactly like a one-row table by the time
scifor extracts it per combo.

Regression this pins (see .claude/plan-matlab-struct-and-iteration-26-09-02.md,
defect 3): the consuming function received a 1xN DataFrame, so every key
access returned a Series instead of the array that was saved. From MATLAB the
same path produced a 1xN table whose fields were 1x1 cells.

``DatabaseManager._load_record`` already rebuilds the dict for a single-record
``.load()``, and ``_load_as_df_via_iterator`` already keeps a ``nested`` dict
whole — only the batched spread path lost it.
"""

import numpy as np
import pytest

import scifor as _scifor
from scidb import BaseVariable, configure_database, for_each

SCHEMA = ["subject", "trial"]


@pytest.fixture
def db(tmp_path):
    _scifor.set_schema([])
    db = configure_database(tmp_path / "test_dict_roundtrip.duckdb", SCHEMA)
    yield db
    _scifor.set_schema([])
    db.close()


class RawEmg(BaseVariable):
    """Records are dicts: one key per muscle."""


class Envelope(BaseVariable):
    pass


class PlainTable(BaseVariable):
    """Records are DataFrames — the shape that must NOT be converted."""


# ---------------------------------------------------------------------------
# The round-trip
# ---------------------------------------------------------------------------


def test_dict_record_arrives_as_a_dict(db):
    for subject in (1, 2):
        RawEmg.save(
            {"RHAM": np.array([1.0, 2.0]) * subject, "RVL": np.array([3.0])},
            subject=subject,
            trial=1,
        )

    received = []

    def summarize(emg):
        received.append(emg)
        return float(np.max(emg["RHAM"]))

    for_each(
        summarize,
        {"emg": RawEmg},
        [Envelope],
        subject=[1, 2],
        trial=[1],
        save=False,
    )

    assert len(received) == 2
    assert all(isinstance(r, dict) for r in received), [type(r) for r in received]
    assert all(sorted(r) == ["RHAM", "RVL"] for r in received)
    assert np.allclose(received[0]["RHAM"], [1.0, 2.0])
    assert np.allclose(received[1]["RHAM"], [2.0, 4.0])


def test_dataframe_record_is_still_a_frame(db):
    """The mark is per-storage-mode, not per-shape: a DataFrame-valued
    variable with several columns keeps its frame."""
    import pandas as pd

    PlainTable.save(pd.DataFrame({"a": [1.0], "b": [2.0]}), subject=1, trial=1)

    received = []
    for_each(
        lambda tbl: received.append(tbl) or 0.0,
        {"tbl": PlainTable},
        [Envelope],
        subject=[1],
        trial=[1],
        save=False,
    )

    assert len(received) == 1
    assert not isinstance(received[0], dict)


def test_as_table_still_delivers_the_frame(db):
    """``as_table`` is an explicit request for the spread columns."""
    RawEmg.save({"RHAM": np.array([1.0]), "RVL": np.array([2.0])}, subject=1, trial=1)

    received = []
    for_each(
        lambda emg: received.append(emg) or 0.0,
        {"emg": RawEmg},
        [Envelope],
        as_table=True,
        subject=[1],
        trial=[1],
        save=False,
    )

    assert not isinstance(received[0], dict)


def test_column_selection_still_selects_columns(db):
    """Spreading exists so ``Type("col")`` works; the mark must not undo it."""
    RawEmg.save({"RHAM": np.array([1.0]), "RVL": np.array([2.0])}, subject=1, trial=1)

    received = []
    for_each(
        lambda emg: received.append(emg) or 0.0,
        {"emg": RawEmg["RHAM"]},
        [Envelope],
        subject=[1],
        trial=[1],
        save=False,
    )

    assert not isinstance(received[0], dict)


def test_coarser_iteration_still_aggregates_to_a_frame(db):
    """Two records under one combo have no single dict to collapse into."""
    for trial in (1, 2):
        RawEmg.save(
            {"RHAM": np.array([float(trial)]), "RVL": np.array([0.0])},
            subject=1,
            trial=trial,
        )

    received = []
    for_each(
        lambda emg: received.append(emg) or 0.0,
        {"emg": RawEmg},
        [Envelope],
        subject=[1],
        save=False,
    )

    assert len(received) == 1
    assert not isinstance(received[0], dict)


# ---------------------------------------------------------------------------
# The accessor scidb uses to decide
# ---------------------------------------------------------------------------


def test_mapping_data_columns_reports_dict_keys(db):
    RawEmg.save({"RHAM": np.array([1.0]), "RVL": np.array([2.0])}, subject=1, trial=1)
    assert db.mapping_data_columns(RawEmg) == ["RHAM", "RVL"]


def test_mapping_data_columns_is_none_for_other_modes(db):
    import pandas as pd

    PlainTable.save(pd.DataFrame({"a": [1.0]}), subject=1, trial=1)
    Envelope.save(np.array([1.0, 2.0]), subject=1, trial=1)

    assert db.mapping_data_columns(PlainTable) is None
    assert db.mapping_data_columns(Envelope) is None


def test_mapping_data_columns_is_none_for_an_unknown_type(db):
    class NeverSaved(BaseVariable):
        pass

    assert db.mapping_data_columns(NeverSaved) is None
