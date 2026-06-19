"""Tests for the bipartite provenance identity helpers and schema (Phase 2).

Covers ``scidb.provenance``:
- content-addressed ids are deterministic / idempotent (re-run → same id)
- distinct inputs (function, value, binding set, output slot) → distinct ids
- identity-neutral facts (where, binding order, as_table order) don't shift ids
- run_id is fresh per call (NOT content-addressed)
- the seven tables are created with the expected columns
"""

import scidb.provenance as prov
from scidb import configure_database


# ---------------------------------------------------------------------------
# Constant record ids
# ---------------------------------------------------------------------------
def test_constant_id_deterministic():
    assert prov.compute_constant_record_id(20) == prov.compute_constant_record_id(20)


def test_constant_id_distinguishes_values():
    assert prov.compute_constant_record_id(20) != prov.compute_constant_record_id(21)


def test_constant_id_is_16_hex():
    rid = prov.compute_constant_record_id("hello")
    assert len(rid) == 16 and all(c in "0123456789abcdef" for c in rid)


def test_constant_value_rendering():
    assert prov.constant_value_repr(20) == "20"
    assert prov.constant_value_type(20) == "int"
    assert prov.constant_value_type("x") == "str"


# ---------------------------------------------------------------------------
# Invocation ids
# ---------------------------------------------------------------------------
def test_invocation_id_deterministic():
    a = prov.compute_invocation_id("fnhash", [], False, [("signal", "rid1"), ("low_hz", "ridc")])
    b = prov.compute_invocation_id("fnhash", [], False, [("signal", "rid1"), ("low_hz", "ridc")])
    assert a == b


def test_invocation_id_binding_order_insensitive():
    a = prov.compute_invocation_id("fn", [], False, [("a", "r1"), ("b", "r2")])
    b = prov.compute_invocation_id("fn", [], False, [("b", "r2"), ("a", "r1")])
    assert a == b


def test_invocation_id_function_hash_matters():
    a = prov.compute_invocation_id("fnA", [], False, [("a", "r1")])
    b = prov.compute_invocation_id("fnB", [], False, [("a", "r1")])
    assert a != b


def test_invocation_id_binding_value_matters():
    a = prov.compute_invocation_id("fn", [], False, [("low_hz", prov.compute_constant_record_id(20))])
    b = prov.compute_invocation_id("fn", [], False, [("low_hz", prov.compute_constant_record_id(21))])
    assert a != b


def test_invocation_id_as_table_matters():
    a = prov.compute_invocation_id("fn", [], False, [("x", "r1")])
    b = prov.compute_invocation_id("fn", ["x"], False, [("x", "r1")])
    assert a != b


def test_invocation_id_as_table_order_insensitive():
    a = prov.compute_invocation_id("fn", ["x", "y"], False, [("x", "r1")])
    b = prov.compute_invocation_id("fn", ["y", "x"], False, [("x", "r1")])
    assert a == b


def test_invocation_id_distribute_matters():
    a = prov.compute_invocation_id("fn", [], False, [("x", "r1")])
    b = prov.compute_invocation_id("fn", [], True, [("x", "r1")])
    assert a != b


# ---------------------------------------------------------------------------
# Output record ids
# ---------------------------------------------------------------------------
def test_output_id_deterministic():
    a = prov.compute_output_record_id("Filtered", 1, "ch", "inv1", 0)
    b = prov.compute_output_record_id("Filtered", 1, "ch", "inv1", 0)
    assert a == b


def test_output_id_output_num_matters():
    a = prov.compute_output_record_id("T", 1, "ch", "inv1", 0)
    b = prov.compute_output_record_id("T", 1, "ch", "inv1", 1)
    assert a != b


def test_output_id_invocation_matters():
    a = prov.compute_output_record_id("T", 1, "ch", "invA", 0)
    b = prov.compute_output_record_id("T", 1, "ch", "invB", 0)
    assert a != b


def test_output_id_content_matters():
    a = prov.compute_output_record_id("T", 1, "chA", "inv", 0)
    b = prov.compute_output_record_id("T", 1, "chB", "inv", 0)
    assert a != b


# ---------------------------------------------------------------------------
# Run ids — fresh per call
# ---------------------------------------------------------------------------
def test_run_id_is_fresh():
    assert prov.generate_run_id() != prov.generate_run_id()


def test_run_id_is_16_hex():
    rid = prov.generate_run_id()
    assert len(rid) == 16 and all(c in "0123456789abcdef" for c in rid)


# ---------------------------------------------------------------------------
# Schema creation
# ---------------------------------------------------------------------------
def test_provenance_tables_created(tmp_path):
    db = configure_database(tmp_path / "prov.duckdb", ["subject", "trial"])
    try:
        names = {
            r[0] for r in db._duck._fetchall(
                "SELECT table_name FROM information_schema.tables"
            )
        }
        for t in (
            "_record", "_constant", "_invocation", "_invocation_input",
            "_invocation_output", "_run", "_run_invocation",
        ):
            assert t in names, f"missing table {t}"
    finally:
        db.close()


def test_record_table_columns(tmp_path):
    db = configure_database(tmp_path / "prov2.duckdb", ["subject"])
    try:
        cols = {
            r[0] for r in db._duck._fetchall(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = '_record'"
            )
        }
        assert cols == {
            "record_id", "created_at", "type", "schema_id",
            "content_hash", "schema_version", "excluded",
        }
    finally:
        db.close()
