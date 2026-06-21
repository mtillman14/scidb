"""Tests for the bipartite read side (Phase 4).

Covers the graph-backed reimplementations and new capabilities:
- get_provenance over the graph (function_name / constants)
- get_derived_branch_params (§6)
- get_pipeline reconstruction nodes + edges (§8)
- get_execution_audit (§9b)
- has_lineage true for computed, false for raw

get_upstream_provenance's full contract is exercised by test_branch_params.py;
here we add the new methods.
"""

import numpy as np
import pytest
import scifor as _scifor

from scidb import BaseVariable, configure_database, for_each


SCHEMA = ["subject", "session"]


@pytest.fixture
def db(tmp_path):
    _scifor.set_schema([])
    db = configure_database(tmp_path / "test_read.duckdb", SCHEMA)
    yield db
    _scifor.set_schema([])
    db.close()


class RawSignal(BaseVariable):
    pass


class Filtered(BaseVariable):
    pass


class Spikes(BaseVariable):
    pass


def bandpass(signal, low_hz):
    return signal * low_hz


def detect_spikes(signal, threshold):
    return (signal > threshold).astype(float)


def _two_step(db):
    RawSignal.save(np.array([1.0, 2.0, 3.0]), subject="S01", session="1")
    for_each(bandpass, {"signal": RawSignal, "low_hz": 20}, [Filtered],
             subject=["S01"], session=["1"])
    for_each(detect_spikes, {"signal": Filtered, "threshold": 0.5}, [Spikes],
             subject=["S01"], session=["1"])
    return Spikes.load(subject="S01", session="1")


# ---------------------------------------------------------------------------
# get_provenance
# ---------------------------------------------------------------------------
def test_get_provenance_over_graph(db):
    RawSignal.save(np.array([1.0, 2.0]), subject="S01", session="1")
    for_each(bandpass, {"signal": RawSignal, "low_hz": 20}, [Filtered],
             subject=["S01"], session=["1"])
    f = Filtered.load(subject="S01", session="1")

    prov = db.get_provenance(Filtered, version=f.record_id)
    assert prov is not None
    assert prov["function_name"] == "bandpass"
    assert prov["function_hash"]
    assert prov["constants"] == {"low_hz": 20}
    assert [i["variable_type"] for i in prov["inputs"]] == ["RawSignal"]


def test_get_provenance_none_for_raw(db):
    RawSignal.save(np.array([1.0]), subject="S01", session="1")
    raw = RawSignal.load(subject="S01", session="1")
    assert db.get_provenance(RawSignal, version=raw.record_id) is None


# ---------------------------------------------------------------------------
# get_derived_branch_params (§6)
# ---------------------------------------------------------------------------
def test_derived_branch_params_accumulates(db):
    s = _two_step(db)
    bp = db.get_derived_branch_params(s.record_id)
    assert bp == {"bandpass.low_hz": 20, "detect_spikes.threshold": 0.5}


def test_derived_branch_params_empty_for_raw(db):
    RawSignal.save(np.array([1.0]), subject="S01", session="1")
    raw = RawSignal.load(subject="S01", session="1")
    assert db.get_derived_branch_params(raw.record_id) == {}


# ---------------------------------------------------------------------------
# get_pipeline (§8)
# ---------------------------------------------------------------------------
def test_get_pipeline_nodes_and_edges(db):
    s = _two_step(db)
    pipe = db.get_pipeline(s.record_id)

    types = [n["variable_type"] for n in pipe["nodes"]]
    assert types == ["Spikes", "Filtered", "RawSignal"]

    # Two edges: RawSignal->Filtered (signal), Filtered->Spikes (signal).
    edge_pairs = {(e["from_record_id"], e["to_record_id"]) for e in pipe["edges"]}
    assert len(edge_pairs) == 2
    for e in pipe["edges"]:
        assert e["param_name"] == "signal"


# ---------------------------------------------------------------------------
# get_execution_audit (§9b)
# ---------------------------------------------------------------------------
def test_execution_audit_records_run(db):
    RawSignal.save(np.array([1.0, 2.0]), subject="S01", session="1")
    for_each(bandpass, {"signal": RawSignal, "low_hz": 20}, [Filtered],
             subject=["S01"], session=["1"])
    f = Filtered.load(subject="S01", session="1")

    audit = db.get_execution_audit(f.record_id)
    assert len(audit) >= 1
    entry = audit[0]
    assert entry["function_name"] == "bandpass"
    assert entry["timestamp"]
    assert set(entry.keys()) == {"timestamp", "user_id", "where_clause", "function_name"}


# ---------------------------------------------------------------------------
# consumed_input_schema_ids (§10 "where= redesign" (B) — semantic variant match)
# ---------------------------------------------------------------------------
def test_consumed_input_schema_ids(db):
    from scidb import provenance_query

    RawSignal.save(np.array([1.0, 2.0]), subject="S01", session="1")
    raw = RawSignal.load(subject="S01", session="1")
    for_each(bandpass, {"signal": RawSignal, "low_hz": 20}, [Filtered],
             subject=["S01"], session=["1"])
    f = Filtered.load(subject="S01", session="1")

    # Filtered's producing invocation consumed the one RawSignal input; the
    # consumed set is that input's schema location.
    raw_sid = db._duck._fetchall(
        "SELECT schema_id FROM _record WHERE record_id = ?", [raw.record_id]
    )[0][0]
    consumed = provenance_query.consumed_input_schema_ids(db._duck, [f.record_id])
    assert consumed[f.record_id] == frozenset({raw_sid})


def test_consumed_input_schema_ids_empty_for_raw(db):
    from scidb import provenance_query

    RawSignal.save(np.array([1.0]), subject="S01", session="1")
    raw = RawSignal.load(subject="S01", session="1")
    # Raw records have no producing invocation → no consumed inputs → no entry.
    assert provenance_query.consumed_input_schema_ids(db._duck, [raw.record_id]) == {}


# ---------------------------------------------------------------------------
# has_lineage
# ---------------------------------------------------------------------------
def test_has_lineage_true_for_computed_false_for_raw(db):
    RawSignal.save(np.array([1.0, 2.0]), subject="S01", session="1")
    raw = RawSignal.load(subject="S01", session="1")
    for_each(bandpass, {"signal": RawSignal, "low_hz": 20}, [Filtered],
             subject=["S01"], session=["1"])
    f = Filtered.load(subject="S01", session="1")

    assert db.has_lineage(f.record_id) is True
    assert db.has_lineage(raw.record_id) is False
