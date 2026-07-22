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
    a = prov.compute_invocation_id(
        "fnhash", [], False, [("signal", "rid1"), ("low_hz", "ridc")]
    )
    b = prov.compute_invocation_id(
        "fnhash", [], False, [("signal", "rid1"), ("low_hz", "ridc")]
    )
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
    a = prov.compute_invocation_id(
        "fn", [], False, [("low_hz", prov.compute_constant_record_id(20))]
    )
    b = prov.compute_invocation_id(
        "fn", [], False, [("low_hz", prov.compute_constant_record_id(21))]
    )
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
# record_run's inlined invocation_id must agree with invocation_id_for_meta.
#
# record_run computes the id directly from the bindings/as_table/distribute it
# already assembled (a perf win — it no longer re-derives them via
# invocation_id_for_meta). The generates_file lineage-only save still keys on
# invocation_id_for_meta, so the two must stay byte-identical or those paths
# would disagree on identity.
# ---------------------------------------------------------------------------
def _inline_invocation_id(meta):
    """Reproduce the exact assembly record_run does inline for one record."""
    from scidb.provenance import (
        compute_invocation_id,
        constant_record_id_from_hash,
    )
    from scidb.provenance_save import (
        _constant_bindings,
        _normalize_as_table,
        _parse_json_dict,
        _variable_bindings,
    )

    from scicanonicalhash import canonical_hash

    var_b = _variable_bindings(meta)
    const_b = _constant_bindings(meta)
    loadable = list(_parse_json_dict(meta.get("__inputs")).keys()) or [
        p for p, _r, _s in var_b
    ]
    as_table = _normalize_as_table(meta, loadable)
    distribute = bool(meta.get("__distribute", False))
    bindings = list(var_b)
    for param, value in const_b.items():
        bindings.append(
            (param, constant_record_id_from_hash(canonical_hash(value)), None)
        )
    return compute_invocation_id(
        meta.get("__fn_hash") or "", as_table, distribute, bindings
    )


def test_inline_invocation_id_matches_helper():
    import json

    from scidb.provenance_save import invocation_id_for_meta

    metas = [
        # plain variable + constant
        {
            "__fn_hash": "h1",
            "__upstream": json.dumps({"__rid_signal": "rid_sig"}),
            "__constants": json.dumps({"low_hz": 20}),
        },
        # multiple constants, no variables
        {"__fn_hash": "h2", "__constants": json.dumps({"a": 1, "b": "x", "c": 3.5})},
        # aggregation flag + inputs list
        {
            "__fn_hash": "h3",
            "__upstream": json.dumps({"__rid_x": "r1", "__rid_y": "r2"}),
            "__inputs": json.dumps({"x": "k", "y": "k"}),
            "__as_table": True,
        },
        # distribute flag
        {
            "__fn_hash": "h4",
            "__upstream": json.dumps({"__rid_x": "r1"}),
            "__distribute": True,
        },
    ]
    for meta in metas:
        assert _inline_invocation_id(meta) == invocation_id_for_meta(meta)


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
            r[0]
            for r in db._duck._fetchall(
                "SELECT table_name FROM information_schema.tables"
            )
        }
        for t in (
            "_record",
            "_constant",
            "_invocation",
            "_invocation_input",
            "_invocation_output",
            "_run",
            "_run_invocation",
        ):
            assert t in names, f"missing table {t}"
    finally:
        db.close()


def test_record_table_columns(tmp_path):
    db = configure_database(tmp_path / "prov2.duckdb", ["subject"])
    try:
        cols = {
            r[0]
            for r in db._duck._fetchall(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = '_record'"
            )
        }
        assert cols == {
            "record_id",
            "created_at",
            "type",
            "schema_id",
            "content_hash",
            "schema_version",
            "excluded",
        }
    finally:
        db.close()
