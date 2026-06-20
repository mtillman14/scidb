"""Write the bipartite provenance graph from the for_each save path.

This is the save-side companion to ``scidb.provenance`` (identity + schema).
It writes the structural provenance graph:

- ``_record``     — one entity row per output and per constant
- ``_constant``   — value/repr/type for each constant entity
- ``_invocation`` — one activity row per unique function call
- ``_invocation_input``  — edges: call → its inputs (variables AND constants)
- ``_invocation_output`` — edges: call → its outputs (by output_num)
- ``_run`` / ``_run_invocation`` — append-only audit of this execution

Everything is content-addressed and inserted ``ON CONFLICT DO NOTHING``, so
re-running an identical pipeline writes no duplicate provenance — only a fresh
``_run`` row.

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
    PATHINPUT_TYPE,
    compute_constant_record_id,
    compute_invocation_id,
    compute_pathinput_record_id,
    constant_value_repr,
    constant_value_type,
    generate_run_id,
    normalize_as_table,
)

logger = logging.getLogger(__name__)

__all__ = [
    "GraphRecord", "record_run", "compute_input_selectors",
    "record_direct_save", "invocation_id_for_meta",
]


def record_direct_save(duck, output_record_id: str, kwargs: dict, created_at: str) -> None:
    """Anchor a direct ``.save(..., kw=v)`` call's non-schema kwargs in the graph
    as a *synthetic save invocation* (see ``provenance.SAVE_FUNCTION_NAME``).

    Inserts: one constant ``_record`` + ``_constant`` per kwarg, a synthetic
    ``_invocation`` (``function_name = SAVE_FUNCTION_NAME``, no real function), a
    ``_invocation_input`` edge per kwarg, and one ``_invocation_output`` edge
    (output_num 0) to the saved record. ``derived_branch_params`` then recovers
    the kwargs — replacing the old ``version_keys`` variant-distinguisher role.

    Runs **inside the caller's transaction** (no begin/commit). Idempotent via
    ON CONFLICT DO NOTHING. No-op when ``kwargs`` is empty.
    """
    from .provenance import (
        CONSTANT_TYPE,
        SAVE_FUNCTION_NAME,
        compute_constant_record_id,
        compute_save_invocation_id,
    )

    if not kwargs:
        return

    save_inv_id = compute_save_invocation_id(output_record_id)
    entity_rows = []
    constant_rows = []
    input_edges = []
    for name, value in kwargs.items():
        chash = canonical_hash(value)
        crid = compute_constant_record_id(value)
        entity_rows.append((crid, created_at, CONSTANT_TYPE, None, chash, None, False))
        constant_rows.append(
            (crid, constant_value_repr(value), constant_value_type(value), chash)
        )
        input_edges.append((save_inv_id, str(name), crid, None))

    con = duck.con
    con.executemany(
        "INSERT INTO _record "
        "(record_id, created_at, type, schema_id, content_hash, schema_version, excluded) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (record_id) DO NOTHING",
        entity_rows,
    )
    con.executemany(
        "INSERT INTO _constant (record_id, value_repr, value_type, content_hash) "
        "VALUES (?, ?, ?, ?) ON CONFLICT (record_id) DO NOTHING",
        constant_rows,
    )
    con.execute(
        "INSERT INTO _invocation "
        "(invocation_id, function_name, function_hash, as_table, distribute) "
        "VALUES (?, ?, ?, ?, ?) ON CONFLICT (invocation_id) DO NOTHING",
        [save_inv_id, SAVE_FUNCTION_NAME, "", [], False],
    )
    con.executemany(
        "INSERT INTO _invocation_input "
        "(invocation_id, param_name, input_record_id, selector) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT (invocation_id, param_name, input_record_id) DO NOTHING",
        input_edges,
    )
    con.execute(
        "INSERT INTO _invocation_output (invocation_id, output_num, output_record_id) "
        "VALUES (?, ?, ?) ON CONFLICT (invocation_id, output_num) DO NOTHING",
        [save_inv_id, 0, output_record_id],
    )
    logger.debug(
        "record_direct_save: %s → save_inv %s with %d kwarg constant(s)",
        output_record_id, save_inv_id, len(kwargs),
    )


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
    __slots__ = ("type_name", "schema_version", "output_num", "record_id", "meta")

    def __init__(self, type_name, schema_version, output_num, record_id, meta):
        self.type_name = type_name
        self.schema_version = schema_version
        self.output_num = output_num
        self.record_id = record_id
        self.meta = meta


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


def _pathinput_specs(meta: dict) -> dict[str, str]:
    """PathInput specs from ``__inputs`` → ``{param_name: spec_json_str}``.

    ``__inputs`` carries each loadable input's ``to_key()``; PathInput's is a JSON
    string ``{"__type": "PathInput", ...}``. Returns those entries verbatim (the
    exact spec string) so they can be stored as PathInput input records.
    """
    inputs = _parse_json_dict(meta.get("__inputs"))
    out: dict[str, str] = {}
    for param, val in inputs.items():
        if not isinstance(val, str) or not val.startswith("{"):
            continue
        try:
            parsed = json.loads(val)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, dict) and parsed.get("__type") == "PathInput":
            out[param] = val
    return out


def _normalize_as_table(meta: dict, loadable_params: list[str]) -> list[str]:
    """Resolve the ``__as_table`` flag to a sorted list of aggregated params.

    Delegates to :func:`scidb.provenance.normalize_as_table` so the save path and
    the skip/predict path (§9c) compute identical ``invocation_id``s.
    """
    return normalize_as_table(meta.get("__as_table"), loadable_params)


def invocation_id_for_meta(meta: dict) -> str:
    """The ``invocation_id`` for a record's ``save_metadata`` — identical to what
    :func:`record_run` computes for it (same binding assembly via the shared
    ``_variable_bindings`` / ``_constant_bindings`` / ``_normalize_as_table``
    helpers). Pure function of the metadata; used by ``record_run`` itself and by
    the generates_file lineage-only save to key its ``generated:{invocation_id}``
    record.
    """
    from .provenance import compute_constant_record_id, compute_invocation_id

    var_b = _variable_bindings(meta)
    const_b = _constant_bindings(meta)
    loadable_params = (
        list(_parse_json_dict(meta.get("__inputs")).keys())
        or [p for p, _r, _s in var_b]
    )
    as_table = _normalize_as_table(meta, loadable_params)
    distribute = bool(meta.get("__distribute", False))
    bindings: list[tuple[str, str, str | None]] = list(var_b)
    for param, value in const_b.items():
        bindings.append((param, compute_constant_record_id(value), None))
    return compute_invocation_id(meta.get("__fn_hash") or "", as_table, distribute, bindings)


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

        # Identity computed via the shared helper so the generates_file
        # lineage-only save (which keys generated:{invocation_id}) and this save
        # path can never disagree.
        inv_id = invocation_id_for_meta(meta)
        # Store NULL (not []) for "no aggregation" — avoids empty-list bind
        # ambiguity on the VARCHAR[] column; identity hashing treats them alike.
        invocation_rows[inv_id] = (
            inv_id, fn_name, fn_hash, as_table or None, distribute,
        )
        for param, rid, selector in bindings:
            input_edges[(inv_id, param, rid)] = selector

        # PathInput-spec edges: config-level (template+root_folder), recorded as
        # distinctly-typed input records so variant queries can surface them.
        # Added AFTER inv_id is computed → deliberately NOT part of identity.
        for param, spec in _pathinput_specs(meta).items():
            prid = compute_pathinput_record_id(spec)
            ch = canonical_hash(spec)
            constant_rows[prid] = (prid, spec, "PathInput", ch)
            entity_rows.setdefault(prid, (prid, created_at, PATHINPUT_TYPE, None, ch, None, False))
            input_edges[(inv_id, param, prid)] = None

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

    Used by :func:`record_run` (the for_each save path). All graph inserts are
    idempotent (``ON CONFLICT DO NOTHING``); the ``_run`` row is always appended.
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
            "(invocation_id, function_name, function_hash, as_table, distribute) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT (invocation_id) DO NOTHING",
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
