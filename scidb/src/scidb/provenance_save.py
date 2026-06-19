"""Write the bipartite provenance graph from the for_each save path.

This is the save-side companion to ``scidb.provenance`` (identity + schema).
Where the old system wrote a ``_lineage`` row per output plus opaque
``version_keys`` / ``branch_params`` JSON, this writes the structural graph:

- ``_record``     — one entity row per output and per constant
- ``_constant``   — value/repr/type for each constant entity
- ``_invocation`` — one activity row per unique function call
- ``_invocation_input``  — edges: call → its inputs (variables AND constants)
- ``_invocation_output`` — edges: call → its outputs (by output_num)
- ``_run`` / ``_run_invocation`` — append-only audit of this execution

It runs **additively alongside** the legacy ``_lineage`` writes during the
migration (Phase 3); Phase 5 deletes the legacy path. Everything is
content-addressed and inserted ``ON CONFLICT DO NOTHING``, so re-running an
identical pipeline writes no duplicate provenance — only a fresh ``_run`` row.

The graph is built from the per-record ``save_metadata`` that for_each already
assembles, which carries ``__fn`` / ``__fn_hash`` (function identity),
``__upstream`` (``{__rid_<param>: record_id}`` — variable input edges),
``__constants`` (``{param: value}`` — constant inputs), and the
``__as_table`` / ``__distribute`` identity flags.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from scicanonicalhash import canonical_hash

from .provenance import (
    CONSTANT_TYPE,
    compute_constant_record_id,
    compute_invocation_id,
    constant_value_repr,
    constant_value_type,
    generate_run_id,
    normalize_as_table,
)

logger = logging.getLogger(__name__)

__all__ = [
    "GraphRecord", "record_run", "record_run_from_lineage", "compute_input_selectors",
    "expected_invocation_id",
]


def expected_invocation_id(
    combo: dict,
    fn_hash: str,
    constant_values: dict,
    selectors: dict,
    as_table_norm: list,
    distribute: bool,
) -> str:
    """The ``invocation_id`` a for_each combo *would* produce, computed before
    execution (the §9c "enabling property").

    Bindings = the combo's variable inputs (its ``__rid_<param>`` columns, with
    any ColumnSelection ``selectors``) plus the constant inputs (hashed to
    constant record_ids). This is identical to what :func:`record_run` writes at
    save time, so the predicted id matches the realized one — letting
    ``_persist_expected_combos`` record expected ids and ``check_node_state`` test
    their membership in ``_invocation``.
    """
    from .provenance import compute_constant_record_id, compute_invocation_id

    bindings: list[tuple[str, str, str | None]] = []
    for key, val in combo.items():
        if not key.startswith("__rid_") or val is None:
            continue
        param = key[len("__rid_"):]
        bindings.append((param, str(val), selectors.get(param)))
    for name, value in constant_values.items():
        bindings.append((name, compute_constant_record_id(value), None))
    return compute_invocation_id(fn_hash, as_table_norm, distribute, bindings)


def compute_input_selectors(inputs: dict) -> dict:
    """Map each input param to its identity-affecting ``selector`` JSON, or None.

    Currently only ``ColumnSelection`` (directly, or wrapped in ``Fixed``)
    produces a selector — the chosen columns — because selecting different
    columns of the same record is a different computation (§ ColumnSelection
    decision). Fixed/Variant/Merge resolve to whole records and need no selector;
    their effect is captured by *which* record_id the edge points at.
    """
    from .column_selection import ColumnSelection
    from .fixed import Fixed

    out: dict = {}
    for param, spec in inputs.items():
        cs = None
        if isinstance(spec, ColumnSelection):
            cs = spec
        elif isinstance(spec, Fixed) and isinstance(getattr(spec, "var_type", None), ColumnSelection):
            cs = spec.var_type
        if cs is not None and getattr(cs, "columns", None):
            out[param] = json.dumps({"columns": list(cs.columns)}, sort_keys=True)
        else:
            out[param] = None
    return out


# A saved output record awaiting graph insertion. ``meta`` is its
# ``save_metadata`` dict (carrying __fn/__fn_hash/__upstream/__constants/flags).
class GraphRecord:
    __slots__ = ("type_name", "schema_version", "output_num", "record_id", "meta",
                 "pipeline_hash")

    def __init__(self, type_name, schema_version, output_num, record_id, meta,
                 pipeline_hash=None):
        self.type_name = type_name
        self.schema_version = schema_version
        self.output_num = output_num
        self.record_id = record_id
        self.meta = meta
        # scilineage compute_lineage_hash() for this output's call, if known
        # (for_each lineage path). Stored on _invocation to back find_by_lineage.
        self.pipeline_hash = pipeline_hash


# ---------------------------------------------------------------------------
# meta → identity inputs
# ---------------------------------------------------------------------------
def _parse_json_dict(val: Any) -> dict:
    """Coerce a value that may be a dict or a JSON string into a dict."""
    if val is None:
        return {}
    if isinstance(val, str):
        try:
            return dict(json.loads(val or "{}"))
        except (json.JSONDecodeError, TypeError):
            return {}
    if isinstance(val, dict):
        return dict(val)
    return {}


def _variable_bindings(meta: dict) -> list[tuple[str, str, str | None]]:
    """Variable input edges as ``(param_name, record_id, selector)`` triples.

    Prefers ``__graph_var_bindings`` — the *complete* per-row binding set the
    save path assembles from every consumed input record (variables, Fixed,
    Variant, Merge constituents) with ColumnSelection selectors. Falls back to
    ``__upstream`` (``{__rid_<param>: record_id}``, no selectors) for the
    aggregation path, which builds upstream edges separately.
    """
    gvb = meta.get("__graph_var_bindings")
    if gvb:
        out = []
        for entry in gvb:
            param, rid, selector = entry
            if rid is None:
                continue
            out.append((param, str(rid), selector))
        return out

    upstream = _parse_json_dict(meta.get("__upstream"))
    out = []
    for key, rid in upstream.items():
        if rid is None:
            continue
        param = key[len("__rid_"):] if key.startswith("__rid_") else key
        out.append((param, str(rid), None))
    return out


def _constant_bindings(meta: dict) -> dict[str, Any]:
    """Constant inputs from ``__constants`` → ``{param_name: value}``."""
    return _parse_json_dict(meta.get("__constants"))


def _normalize_as_table(meta: dict, loadable_params: list[str]) -> list[str]:
    """Resolve the ``__as_table`` flag to a sorted list of aggregated params.

    Delegates to :func:`scidb.provenance.normalize_as_table` so the save path and
    the skip/predict path (§9c) compute identical ``invocation_id``s.
    """
    return normalize_as_table(meta.get("__as_table"), loadable_params)


# ---------------------------------------------------------------------------
# Output record metadata lookup
# ---------------------------------------------------------------------------
def _fetch_record_meta(duck, rids: list[str]) -> dict[str, dict]:
    """Latest ``content_hash`` / ``schema_id`` / ``schema_version`` / ``timestamp``
    per output record_id, read from ``_record_metadata`` (still authoritative
    during the additive migration)."""
    uniq = list(dict.fromkeys(rids))
    if not uniq:
        return {}
    placeholders = ", ".join(["?"] * len(uniq))
    rows = duck._fetchall(
        f"""
        SELECT record_id, content_hash, schema_id, schema_version, timestamp
        FROM (
            SELECT record_id, content_hash, schema_id, schema_version, timestamp,
                   ROW_NUMBER() OVER (PARTITION BY record_id ORDER BY timestamp DESC) AS rn
            FROM _record_metadata
            WHERE record_id IN ({placeholders})
        ) WHERE rn = 1
        """,
        uniq,
    )
    return {
        r[0]: {"content_hash": r[1], "schema_id": r[2], "schema_version": r[3], "timestamp": r[4]}
        for r in rows
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def record_run(
    db,
    graph_records: list[GraphRecord],
    *,
    function_name: str,
    where_clause: str | None,
    user_id: str | None,
) -> str | None:
    """Write the bipartite graph for ``graph_records`` plus a fresh ``_run`` row.

    Returns the ``run_id`` (or ``None`` if there was nothing to record).

    Idempotent for the graph (``ON CONFLICT DO NOTHING``); the ``_run`` /
    ``_run_invocation`` rows are always appended so the audit log captures this
    execution even when it reproduced existing invocations.
    """
    if not graph_records:
        return None

    duck = db._duck
    created_at = datetime.now().isoformat()
    meta_map = _fetch_record_meta(duck, [g.record_id for g in graph_records])

    # Accumulators (deduped by key so we can ON CONFLICT DO NOTHING cheaply).
    entity_rows: dict[str, tuple] = {}        # record_id -> _record row
    constant_rows: dict[str, tuple] = {}      # record_id -> _constant row
    invocation_rows: dict[str, tuple] = {}    # invocation_id -> _invocation row
    input_edges: dict[tuple[str, str, str], str | None] = {}   # (inv,param,rid) -> selector
    output_edges: dict[tuple[str, int], str] = {}     # (inv_id, output_num) -> rid
    run_inv_ids: set[str] = set()

    for g in graph_records:
        meta = g.meta
        fn_name = meta.get("__fn") or function_name or "unknown"
        fn_hash = meta.get("__fn_hash") or ""

        var_b = _variable_bindings(meta)   # list of (param, rid, selector)
        const_b = _constant_bindings(meta)
        loadable_params = (
            list(_parse_json_dict(meta.get("__inputs")).keys())
            or [p for p, _r, _s in var_b]
        )
        as_table = _normalize_as_table(meta, loadable_params)
        distribute = bool(meta.get("__distribute", False))

        # Assemble the full binding set (variables + constants) and the
        # constant entity/value rows it implies. Bindings are
        # (param, record_id, selector) triples; constants carry no selector.
        bindings: list[tuple[str, str, str | None]] = list(var_b)
        for param, value in const_b.items():
            crid = compute_constant_record_id(value)
            bindings.append((param, crid, None))
            ch = canonical_hash(value)
            constant_rows[crid] = (crid, constant_value_repr(value), constant_value_type(value), ch)
            entity_rows.setdefault(crid, (crid, created_at, CONSTANT_TYPE, None, ch, None, False))

        inv_id = compute_invocation_id(fn_hash, as_table, distribute, bindings)
        # Store NULL (not []) for "no aggregation" — avoids empty-list bind
        # ambiguity on the VARCHAR[] column; identity hashing treats them alike.
        invocation_rows[inv_id] = (
            inv_id, fn_name, fn_hash, as_table or None, distribute, g.pipeline_hash,
        )
        for param, rid, selector in bindings:
            input_edges[(inv_id, param, rid)] = selector

        # Output edge. One call can emit MANY records that share an invocation
        # and arrive with the same nominal output_num — notably flatten/distribute
        # modes (a returned DataFrame spread into one record per row). They are
        # genuinely distinct outputs, so assign each the next free output_num for
        # this invocation rather than colliding on the _invocation_output PK. The
        # order is the deterministic collection (row) order, so re-runs reproduce
        # the same assignment. An idempotent re-save (same record_id) is not a
        # collision and keeps its slot.
        okey = (inv_id, g.output_num)
        if okey in output_edges and output_edges[okey] != g.record_id:
            n = g.output_num
            while (inv_id, n) in output_edges and output_edges[(inv_id, n)] != g.record_id:
                n += 1
            okey = (inv_id, n)
        output_edges[okey] = g.record_id
        run_inv_ids.add(inv_id)

        # Output entity row (pull content_hash/schema_id from _record_metadata).
        cm = meta_map.get(g.record_id, {})
        entity_rows[g.record_id] = (
            g.record_id,
            cm.get("timestamp") or created_at,
            g.type_name,
            cm.get("schema_id"),
            cm.get("content_hash"),
            cm.get("schema_version") if cm.get("schema_version") is not None else g.schema_version,
            False,
        )

    run_id = generate_run_id()
    logger.debug(
        "record_run: run_id=%s fn=%s records=%d invocations=%d constants=%d edges_in=%d",
        run_id, function_name, len(graph_records), len(invocation_rows),
        len(constant_rows), len(input_edges),
    )
    _commit_graph(
        duck, run_id, created_at, user_id, function_name, where_clause,
        entity_rows, constant_rows, invocation_rows, input_edges,
        output_edges, run_inv_ids,
    )
    return run_id


def _commit_graph(
    duck, run_id, created_at, user_id, function_name, where_clause,
    entity_rows, constant_rows, invocation_rows, input_edges,
    output_edges, run_inv_ids,
) -> None:
    """Transactionally insert the assembled graph rows + the append-only run.

    Shared by :func:`record_run` (for_each path) and
    :func:`record_run_from_lineage` (single-record lineage path). All graph
    inserts are idempotent (``ON CONFLICT DO NOTHING``); the ``_run`` row is
    always appended.
    """
    duck._begin()
    try:
        con = duck.con
        con.executemany(
            "INSERT INTO _record "
            "(record_id, created_at, type, schema_id, content_hash, schema_version, excluded) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (record_id) DO NOTHING",
            list(entity_rows.values()),
        )
        if constant_rows:
            con.executemany(
                "INSERT INTO _constant (record_id, value_repr, value_type, content_hash) "
                "VALUES (?, ?, ?, ?) ON CONFLICT (record_id) DO NOTHING",
                list(constant_rows.values()),
            )
        con.executemany(
            "INSERT INTO _invocation "
            "(invocation_id, function_name, function_hash, as_table, distribute, pipeline_hash) "
            "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (invocation_id) DO NOTHING",
            list(invocation_rows.values()),
        )
        if input_edges:
            con.executemany(
                "INSERT INTO _invocation_input "
                "(invocation_id, param_name, input_record_id, selector) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT (invocation_id, param_name, input_record_id) DO NOTHING",
                [(inv, param, rid, sel) for (inv, param, rid), sel in input_edges.items()],
            )
        con.executemany(
            "INSERT INTO _invocation_output (invocation_id, output_num, output_record_id) "
            "VALUES (?, ?, ?) ON CONFLICT (invocation_id, output_num) DO NOTHING",
            [(inv, onum, rid) for (inv, onum), rid in output_edges.items()],
        )
        con.execute(
            "INSERT INTO _run (run_id, timestamp, user_id, function_name, where_clause) "
            "VALUES (?, ?, ?, ?, ?)",
            [run_id, created_at, user_id, function_name, where_clause],
        )
        con.executemany(
            "INSERT INTO _run_invocation (run_id, invocation_id) "
            "VALUES (?, ?) ON CONFLICT (run_id, invocation_id) DO NOTHING",
            [(run_id, inv) for inv in run_inv_ids],
        )
        duck._commit()
    except Exception:
        logger.exception("graph commit failed; rolling back for run_id=%s", run_id)
        try:
            duck._rollback()
        except Exception:
            pass
        raise


def record_run_from_lineage(
    db,
    output_record_id: str,
    type_name: str,
    schema_version: int,
    output_num: int,
    lineage: dict,
    *,
    where_clause: str | None,
    user_id: str | None,
    function_hash: str | None = None,
    pipeline_hash: str | None = None,
) -> str | None:
    """Write the bipartite graph for ONE record saved via the lineage save path.

    The for_each batch path uses :func:`record_run`; this is its counterpart for
    ``db.save(..., lineage=...)`` — the single-record path used by the MATLAB
    bridge and ``generates_file`` side-effect saves. It builds the same graph
    (one invocation + its input/output edges + constants) from the scilineage
    ``lineage`` dict (``function_name``/``function_hash``/``inputs``/``constants``)
    instead of from for_each's per-row metadata.

    Variable inputs come from ``inputs`` entries with ``source_type == "variable"``
    (carrying ``record_id``); constants come from the ``constants`` descriptors
    (``value_hash``/``value_repr``/``value_type``), whose ``value_hash`` is a
    ``canonical_hash`` so the constant record_id matches the for_each path.

    ``function_hash`` overrides the graph's stored hash. The for_each path stores
    ``compute_function_hash(fn, 16)`` (``__fn_hash``); ``lineage["function_hash"]``
    is instead ``LineageFcn.hash`` (a different scheme), so callers pass the
    16-char form here to keep both paths — and the staleness/skip read side —
    on one hashing recipe. Falls back to the lineage dict's value if omitted.
    """
    from .provenance import constant_record_id_from_hash, compute_invocation_id

    duck = db._duck
    created_at = datetime.now().isoformat()
    fn_name = lineage.get("function_name") or "unknown"
    fn_hash = function_hash if function_hash is not None else (lineage.get("function_hash") or "")

    entity_rows: dict[str, tuple] = {}
    constant_rows: dict[str, tuple] = {}
    bindings: list[tuple[str, str, str | None]] = []

    # Variable inputs (skip thunk/unsaved entries with no concrete record_id).
    for inp in lineage.get("inputs", []) or []:
        if not isinstance(inp, dict):
            continue
        if inp.get("source_type") != "variable":
            continue
        rid = inp.get("record_id")
        param = inp.get("name")
        if rid and param:
            bindings.append((param, str(rid), None))

    # Constants.
    for c in lineage.get("constants", []) or []:
        if not isinstance(c, dict):
            continue
        param = c.get("name")
        chash = c.get("value_hash")
        if not param or not chash:
            continue
        crid = constant_record_id_from_hash(chash)
        bindings.append((param, crid, None))
        constant_rows[crid] = (crid, c.get("value_repr"), c.get("value_type"), chash)
        entity_rows.setdefault(crid, (crid, created_at, CONSTANT_TYPE, None, chash, None, False))

    inv_id = compute_invocation_id(fn_hash, [], False, bindings)
    invocation_rows = {inv_id: (inv_id, fn_name, fn_hash, None, False, pipeline_hash)}
    input_edges = {(inv_id, p, r): s for p, r, s in bindings}
    output_edges = {(inv_id, int(output_num)): output_record_id}

    # Output entity row (pull schema/content from _record_metadata).
    cm = _fetch_record_meta(duck, [output_record_id]).get(output_record_id, {})
    entity_rows[output_record_id] = (
        output_record_id,
        cm.get("timestamp") or created_at,
        type_name,
        cm.get("schema_id"),
        cm.get("content_hash"),
        cm.get("schema_version") if cm.get("schema_version") is not None else schema_version,
        False,
    )

    run_id = generate_run_id()
    logger.debug(
        "record_run_from_lineage: run_id=%s fn=%s out=%s inv=%s bindings=%d",
        run_id, fn_name, output_record_id, inv_id, len(bindings),
    )
    _commit_graph(
        duck, run_id, created_at, user_id, fn_name, where_clause,
        entity_rows, constant_rows, invocation_rows, input_edges,
        output_edges, {inv_id},
    )
    return run_id
