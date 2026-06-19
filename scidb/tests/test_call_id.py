"""Tests for _for_each_expected — the persisted expected-invocation set.

call_id is gone. Its job (keeping distinct for_each call sites from clobbering
each other's expected set) is now structural: each combo's expected
``invocation_id`` is config-specific, so distinct call sites coexist and
identical re-runs dedup, with no scoping key. These tests verify that on the
``_for_each_expected`` table directly.
"""

import numpy as np
import pytest
import scifor as _scifor

from scidb import BaseVariable, configure_database, for_each


SCHEMA = ["subject", "session"]


@pytest.fixture
def db(tmp_path):
    _scifor.set_schema([])
    db = configure_database(tmp_path / "test_call_id.duckdb", SCHEMA)
    yield db
    _scifor.set_schema([])
    db.close()


class RawSignal(BaseVariable):
    pass


class Filtered(BaseVariable):
    pass


def bandpass(signal, low_hz):
    return signal * low_hz


def _seed_raw(db, subjects, sessions, var=RawSignal):
    for s in subjects:
        for sess in sessions:
            var.save(np.array([1.0, 2.0, 3.0]), db=db, subject=s, session=sess)


def _expected_rows(db, fn_name):
    return db._duck._fetchall(
        "SELECT schema_id, invocation_id FROM _for_each_expected "
        "WHERE function_name = ? ORDER BY schema_id, invocation_id",
        [fn_name],
    )


def test_for_each_expected_schema(db):
    """Schema sanity: keyed on invocation_id, no call_id/branch_params columns."""
    cols = {
        c[0] for c in db._duck._fetchall(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = '_for_each_expected'"
        )
    }
    assert cols == {"function_name", "schema_id", "invocation_id"}


def test_same_call_site_rerun_is_idempotent(db):
    """Re-running an identical for_each → expected rows stable (ON CONFLICT)."""
    _seed_raw(db, subjects=["1", "2"], sessions=["A"])

    for _ in range(3):
        for_each(bandpass, inputs={"signal": RawSignal, "low_hz": 20},
                 outputs=[Filtered], db=db, subject=["1", "2"], session=["A"])

    rows = _expected_rows(db, "bandpass")
    assert len(rows) == 2, f"Expected 2 rows (2 subjects), got {rows}"


def test_two_call_sites_different_constants_coexist(db):
    """Same fn, different constants → distinct invocation_ids → both sets persist."""
    _seed_raw(db, subjects=["1", "2"], sessions=["A", "B"])

    for_each(bandpass, inputs={"signal": RawSignal, "low_hz": 20},
             outputs=[Filtered], db=db, subject=["1", "2"], session=["A"])
    for_each(bandpass, inputs={"signal": RawSignal, "low_hz": 50},
             outputs=[Filtered], db=db, subject=["1", "2"], session=["B"])

    rows = _expected_rows(db, "bandpass")
    inv_ids = {r[1] for r in rows}
    assert len(inv_ids) == 4, (
        f"Both call sites should keep their 2 invocations each (4 total); got {rows}"
    )


def test_two_call_sites_different_inputs_coexist(db):
    """Same fn + constants, different loadable input type → distinct invocations."""

    class AlternateRaw(BaseVariable):
        pass

    _seed_raw(db, subjects=["1"], sessions=["A"], var=RawSignal)
    _seed_raw(db, subjects=["1"], sessions=["A"], var=AlternateRaw)

    for_each(bandpass, inputs={"signal": RawSignal, "low_hz": 20},
             outputs=[Filtered], db=db, subject=["1"], session=["A"])
    for_each(bandpass, inputs={"signal": AlternateRaw, "low_hz": 20},
             outputs=[Filtered], db=db, subject=["1"], session=["A"])

    inv_ids = {r[1] for r in _expected_rows(db, "bandpass")}
    assert len(inv_ids) == 2, (
        f"Different input types should produce different invocations, got {inv_ids}"
    )
