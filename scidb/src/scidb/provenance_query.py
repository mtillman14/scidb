"""Read side of the bipartite provenance graph.

Pure SQL traversal over ``_invocation`` / ``_invocation_input`` /
``_invocation_output`` (plus ``_record`` / ``_constant``), replacing the old
``version_keys`` / ``branch_params`` JSON-parsing heuristics with
provably-correct, indexable edge walks. See ``docs/claude/lineage-simplification.md``
§6 (derived branch_params), §8 (pipeline reconstruction), §9b (execution audit).

``DatabaseManager`` methods delegate here; the functions take a ``DatabaseManager``
(for ``_duck`` and ``dataset_schema_keys``) or a raw ``SciDuck``.
"""

from __future__ import annotations

import ast
import logging

from .database import _from_schema_str
from .provenance import CONSTANT_TYPE, PATHINPUT_TYPE, SAVE_FUNCTION_NAME

logger = logging.getLogger(__name__)


def _safe_literal(value_repr):
    """Recover a typed constant value from its ``repr`` (``_constant.value_repr``).

    ``value_repr`` is ``repr(value)``, so ``ast.literal_eval`` round-trips
    int/float/str/bool/None/tuple/list/dict-of-literals back to the original
    value. Non-literal reprs (e.g. numpy) fall back to the raw string.
    """
    if value_repr is None:
        return None
    try:
        return ast.literal_eval(value_repr)
    except (ValueError, SyntaxError):
        return value_repr


# ---------------------------------------------------------------------------
# Primitive lookups
# ---------------------------------------------------------------------------
def producing_invocation(duck, record_id: str):
    """The invocation that produced ``record_id`` → ``(inv_id, fn_name, fn_hash)``
    or ``None`` for raw/manual records (no producing invocation)."""
    rows = duck._fetchall(
        "SELECT io.invocation_id, inv.function_name, inv.function_hash "
        "FROM _invocation_output io "
        "JOIN _invocation inv ON inv.invocation_id = io.invocation_id "
        "WHERE io.output_record_id = ? "
        "ORDER BY io.invocation_id LIMIT 1",
        [record_id],
    )
    return rows[0] if rows else None


def output_num_for(duck, record_id: str):
    """The ``output_num`` slot this record occupies on its producing invocation,
    or ``None`` if it has no producing invocation. Distinguishes the multiple
    records a single flatten/distribute call emits."""
    rows = duck._fetchall(
        "SELECT output_num FROM _invocation_output WHERE output_record_id = ? LIMIT 1",
        [record_id],
    )
    return rows[0][0] if rows else None


# ---------------------------------------------------------------------------
# Batched lookups — same results as the per-record primitives above, but built
# with O(depth) bulk queries instead of O(records × depth) round-trips. Used by
# the hot load paths (_find_record collapse, _assemble_df_from_records_and_data)
# where the per-record form was the dominant cost on large result sets.
# ---------------------------------------------------------------------------
def _chunked_in(duck, sql_template: str, ids, tail_params=None, chunk: int = 900):
    """Run ``sql_template`` (containing a single ``{ph}`` placeholder-list slot)
    over ``ids`` in chunks, returning the concatenated rows.

    ``tail_params`` are appended after the id placeholders on every chunk (for
    queries with trailing constant params, e.g. type filters).
    """
    tail_params = list(tail_params or [])
    out: list = []
    ids = list(ids)
    for start in range(0, len(ids), chunk):
        chunk_ids = ids[start : start + chunk]
        placeholders = ", ".join(["?"] * len(chunk_ids))
        sql = sql_template.format(ph=placeholders)
        out.extend(duck._fetchall(sql, chunk_ids + tail_params))
    return out


def producing_invocation_batch(duck, record_ids) -> dict:
    """Batched :func:`producing_invocation`.

    ``{record_id: (inv_id, fn_name, fn_hash)}`` for records that have a producing
    invocation (raw/manual records are absent from the map). Matches the
    per-record function's "lowest invocation_id wins" tie-break.
    """
    ids = [r for r in dict.fromkeys(record_ids)]
    if not ids:
        return {}
    rows = _chunked_in(
        duck,
        "SELECT io.output_record_id, io.invocation_id, inv.function_name, inv.function_hash "
        "FROM _invocation_output io "
        "JOIN _invocation inv ON inv.invocation_id = io.invocation_id "
        "WHERE io.output_record_id IN ({ph})",
        ids,
    )
    out: dict = {}
    for out_rid, inv_id, fn_name, fn_hash in rows:
        prev = out.get(out_rid)
        # ORDER BY io.invocation_id LIMIT 1 ⇒ keep the lowest invocation_id.
        if prev is None or inv_id < prev[0]:
            out[out_rid] = (inv_id, fn_name, fn_hash)
    return out


def output_num_batch(duck, record_ids) -> dict:
    """Batched :func:`output_num_for` — ``{record_id: output_num}`` for records
    with a producing invocation (lowest invocation_id wins, mirroring LIMIT 1)."""
    ids = [r for r in dict.fromkeys(record_ids)]
    if not ids:
        return {}
    rows = _chunked_in(
        duck,
        "SELECT output_record_id, invocation_id, output_num "
        "FROM _invocation_output WHERE output_record_id IN ({ph})",
        ids,
    )
    best: dict = {}
    out: dict = {}
    for out_rid, inv_id, onum in rows:
        if out_rid not in best or inv_id < best[out_rid]:
            best[out_rid] = inv_id
            out[out_rid] = onum
    return out


def _build_upstream_closure(duck, seed_record_ids, max_depth: int = 20):
    """Load the full upstream subgraph reachable from ``seed_record_ids`` into
    in-memory adjacency maps using O(max_depth) batched queries.

    Returns ``(rec_to_inv, inv_constants, inv_var_inputs)`` where:

    * ``rec_to_inv``: ``{record_id: (inv_id, fn_name)}`` for produced records
    * ``inv_constants``: ``{inv_id: {f"{fn_name}.{param}": value}}``
    * ``inv_var_inputs``: ``{inv_id: [input_record_id, ...]}`` (variable inputs
      only; constants and PathInput specs excluded — matching
      :func:`invocation_inputs`)

    Together these let a caller reproduce :func:`derived_branch_params` for every
    seed with a pure-Python walk and zero further DB round-trips.
    """
    rec_to_inv: dict = {}
    inv_constants: dict = {}
    inv_var_inputs: dict = {}
    inv_fn_name: dict = {}  # invocation_id -> function_name (for constant namespacing)

    seen_records: set = set()
    frontier = list(dict.fromkeys(seed_record_ids))
    depth = 0
    while frontier and depth <= max_depth:
        new_records = [r for r in frontier if r not in seen_records]
        seen_records.update(new_records)
        if not new_records:
            break

        # 1) producing invocation (+ fn_name) for each frontier record.
        inv_rows = _chunked_in(
            duck,
            "SELECT io.output_record_id, io.invocation_id, inv.function_name "
            "FROM _invocation_output io "
            "JOIN _invocation inv ON inv.invocation_id = io.invocation_id "
            "WHERE io.output_record_id IN ({ph})",
            new_records,
        )
        for out_rid, inv_id, fn_name in inv_rows:
            prev = rec_to_inv.get(out_rid)
            if prev is None or inv_id < prev[0]:
                rec_to_inv[out_rid] = (inv_id, fn_name)
            inv_fn_name[inv_id] = fn_name

        # 2) inputs for the newly discovered invocations (skip ones already loaded).
        inv_ids = list(dict.fromkeys(
            rec_to_inv[r][0] for r in new_records
            if r in rec_to_inv and rec_to_inv[r][0] not in inv_var_inputs
        ))
        if not inv_ids:
            depth += 1
            frontier = []
            continue

        in_rows = _chunked_in(
            duck,
            "SELECT ii.invocation_id, ii.param_name, ii.input_record_id, r.type, c.value_repr "
            "FROM _invocation_input ii "
            "LEFT JOIN _record r ON r.record_id = ii.input_record_id "
            "LEFT JOIN _constant c ON c.record_id = ii.input_record_id "
            "WHERE ii.invocation_id IN ({ph})",
            inv_ids,
        )
        for inv_id in inv_ids:
            inv_var_inputs.setdefault(inv_id, [])
            inv_constants.setdefault(inv_id, {})
        next_frontier: list = []
        var_pairs: dict = {}  # inv_id -> [(param_name, in_rid), ...] for stable sort
        for inv_id, param_name, in_rid, rtype, value_repr in in_rows:
            if rtype == PATHINPUT_TYPE:
                continue  # PathInput spec — neither variable nor sweep constant
            if rtype == CONSTANT_TYPE:
                # Namespace by the producing function name (as derived_branch_params).
                fn_name = inv_fn_name.get(inv_id)
                inv_constants[inv_id][f"{fn_name}.{param_name}"] = _safe_literal(value_repr)
            else:
                var_pairs.setdefault(inv_id, []).append((param_name, in_rid))
                next_frontier.append(in_rid)
        # Match invocation_inputs' sort (param_name, record_id) so the per-record
        # DFS visits ancestors in the same order as derived_branch_params.
        for inv_id, pairs in var_pairs.items():
            inv_var_inputs[inv_id] = [rid for _p, rid in sorted(pairs)]

        depth += 1
        frontier = next_frontier

    return rec_to_inv, inv_constants, inv_var_inputs


def branch_params_batch(duck, record_ids, max_depth: int = 20) -> dict:
    """Batched :func:`derived_branch_params` — ``{record_id: {fn.param: value}}``.

    Builds the upstream closure once (O(max_depth) bulk queries), then accumulates
    each requested record's branch params with an in-memory walk identical in
    semantics to the per-record version (same DFS order, same last-write-wins on
    a namespaced-key collision), so results match byte-for-byte.
    """
    seeds = [r for r in dict.fromkeys(record_ids)]
    if not seeds:
        return {}
    rec_to_inv, inv_constants, inv_var_inputs = _build_upstream_closure(
        duck, seeds, max_depth
    )
    out: dict = {}
    for seed in seeds:
        bp: dict = {}
        visited: set = set()
        stack = [(seed, 0)]
        while stack:
            cur, depth = stack.pop()
            if cur in visited or depth > max_depth:
                continue
            visited.add(cur)
            inv = rec_to_inv.get(cur)
            if inv is None:
                continue
            inv_id, _fn_name = inv
            for nkey, value in inv_constants.get(inv_id, {}).items():
                bp[nkey] = value
            for child in inv_var_inputs.get(inv_id, ()):
                stack.append((child, depth + 1))
        out[seed] = bp
    return out


def invocation_inputs(duck, invocation_id: str):
    """Split an invocation's input edges into variable inputs and constants.

    Returns ``(var_inputs, constants)`` where ``var_inputs`` is a list of
    ``{record_id, param_name, variable_type}`` (sorted by param) and
    ``constants`` is ``{param_name: typed_value}``.
    """
    rows = duck._fetchall(
        "SELECT ii.param_name, ii.input_record_id, r.type, c.value_repr "
        "FROM _invocation_input ii "
        "LEFT JOIN _record r ON r.record_id = ii.input_record_id "
        "LEFT JOIN _constant c ON c.record_id = ii.input_record_id "
        "WHERE ii.invocation_id = ?",
        [invocation_id],
    )
    var_inputs = []
    constants = {}
    for param_name, in_rid, rtype, value_repr in rows:
        if rtype == PATHINPUT_TYPE:
            continue  # PathInput spec — not a variable nor a sweep constant
        if rtype == CONSTANT_TYPE:
            constants[param_name] = _safe_literal(value_repr)
        else:
            var_inputs.append({
                "record_id": in_rid,
                "param_name": param_name,
                "variable_type": rtype,
            })
    var_inputs.sort(key=lambda d: (d["param_name"], d["record_id"]))
    return var_inputs, constants


def invocation_path_inputs(duck, invocation_id: str) -> dict[str, str]:
    """``{param_name: spec_json_str}`` for an invocation's PathInput inputs.

    The spec string is ``PathInput.to_key()`` (JSON: template, root_folder, …),
    stored as a distinctly-typed (:data:`PATHINPUT_TYPE`) input record.
    """
    rows = duck._fetchall(
        "SELECT ii.param_name, c.value_repr "
        "FROM _invocation_input ii "
        "JOIN _record r ON r.record_id = ii.input_record_id "
        "JOIN _constant c ON c.record_id = ii.input_record_id "
        "WHERE ii.invocation_id = ? AND r.type = ?",
        [invocation_id, PATHINPUT_TYPE],
    )
    return {param: spec for param, spec in rows}


def stored_invocation_signature(duck, record_id: str):
    """Signature of the invocation that produced ``record_id``, for skip_computed.

    Returns ``None`` if the record has no producing invocation (raw/manual), else
    ``{"function_hash", "var_inputs", "const_hashes"}`` where ``var_inputs`` maps
    ``param -> (input_record_id, selector)`` and ``const_hashes`` maps
    ``param -> content_hash``. This is the new-table replacement for the old
    ``_lineage`` reads (function hash + input edges + constant records).
    """
    inv = producing_invocation(duck, record_id)
    if inv is None:
        return None
    inv_id, _fn_name, fn_hash = inv
    rows = duck._fetchall(
        "SELECT ii.param_name, ii.input_record_id, ii.selector, r.type, c.content_hash "
        "FROM _invocation_input ii "
        "LEFT JOIN _record r ON r.record_id = ii.input_record_id "
        "LEFT JOIN _constant c ON c.record_id = ii.input_record_id "
        "WHERE ii.invocation_id = ?",
        [inv_id],
    )
    var_inputs: dict[str, tuple] = {}
    const_hashes: dict[str, str] = {}
    for param, in_rid, selector, rtype, chash in rows:
        if rtype == PATHINPUT_TYPE:
            continue  # PathInput spec — excluded from identity / staleness
        if rtype == CONSTANT_TYPE:
            const_hashes[param] = chash
        else:
            var_inputs[param] = (in_rid, selector)
    return {"function_hash": fn_hash, "var_inputs": var_inputs, "const_hashes": const_hashes}


def _fetch_record_node(duck, record_id: str, schema_keys: list[str]):
    """``{type, schema}`` for a variable record, or ``None`` if absent.

    Constants are not pipeline nodes, so callers filter them out by ``type``.
    """
    schema_cols = ", ".join(f's."{k}"' for k in schema_keys)
    select_extra = (", " + schema_cols) if schema_keys else ""
    rows = duck._fetchall(
        f"SELECT r.type{select_extra} "
        f"FROM _record r LEFT JOIN _schema s ON r.schema_id = s.schema_id "
        f"WHERE r.record_id = ?",
        [record_id],
    )
    if not rows:
        return None
    row = rows[0]
    schema = {}
    for i, key in enumerate(schema_keys):
        val = row[1 + i]
        if val is not None:
            schema[key] = _from_schema_str(val)
    return {"type": row[0], "schema": schema}


# ---------------------------------------------------------------------------
# Derived branch_params (§6)
# ---------------------------------------------------------------------------
def derived_branch_params(duck, record_id: str, max_depth: int = 20) -> dict:
    """Accumulated constants up the ancestry, namespaced ``function.param``.

    The exact ``{fn.param: value}`` map the old system stored in the
    ``branch_params`` column, now derived from the graph instead of stored.
    """
    bp: dict = {}
    visited: set = set()
    stack = [(record_id, 0)]
    while stack:
        cur, depth = stack.pop()
        if cur in visited or depth > max_depth:
            continue
        visited.add(cur)
        inv = producing_invocation(duck, cur)
        if inv is None:
            continue
        inv_id, fn_name, _ = inv
        var_inputs, constants = invocation_inputs(duck, inv_id)
        for param, value in constants.items():
            bp[f"{fn_name}.{param}"] = value
        for inp in var_inputs:
            stack.append((inp["record_id"], depth + 1))
    return bp


# ---------------------------------------------------------------------------
# Upstream provenance — provably-correct edge walk (replaces the heuristic)
# ---------------------------------------------------------------------------
def upstream_provenance(db, record_id: str, max_depth: int = 20) -> list[dict]:
    """BFS over the bipartite graph from ``record_id`` toward its roots.

    Same node shape as the legacy heuristic implementation::

        {record_id, variable_type, schema, branch_params, function_name,
         constants, depth, inputs:[{record_id, param_name, variable_type}]}

    but every edge is a stored fact (no ``branch_params``-subset guessing).
    Returns ``[]`` for an unknown ``record_id``.
    """
    duck = db._duck
    schema_keys = list(db.dataset_schema_keys)

    visited: set = set()
    result: list = []
    queue: list = [(record_id, 0)]

    while queue:
        rid, depth = queue.pop(0)
        if rid in visited or depth > max_depth:
            continue
        visited.add(rid)

        node = _fetch_record_node(duck, rid, schema_keys)
        if node is None or node["type"] in (CONSTANT_TYPE, PATHINPUT_TYPE):
            continue

        inv = producing_invocation(duck, rid)
        if inv is not None:
            inv_id, fn_name, _fn_hash = inv
            var_inputs, constants = invocation_inputs(duck, inv_id)
        else:
            fn_name, var_inputs, constants = None, [], {}

        result.append({
            "record_id": rid,
            "variable_type": node["type"],
            "schema": node["schema"],
            "branch_params": derived_branch_params(duck, rid, max_depth),
            "function_name": fn_name,
            "constants": constants,
            "depth": depth,
            "inputs": var_inputs,
        })

        for inp in var_inputs:
            queue.append((inp["record_id"], depth + 1))

    return result


# ---------------------------------------------------------------------------
# Pipeline reconstruction (§8) — nodes + edges DAG for the queried record
# ---------------------------------------------------------------------------
def pipeline(db, record_id: str, max_depth: int = 20) -> dict:
    """Full upstream DAG for ``record_id`` as ``{"nodes": [...], "edges": [...]}``.

    ``nodes`` reuses :func:`upstream_provenance`'s node shape; ``edges`` are
    ``{from_record_id, to_record_id, param_name}`` (from upstream input → the
    record that consumed it). Provably correct — every edge is stored.
    """
    nodes = upstream_provenance(db, record_id, max_depth)
    edges = []
    for node in nodes:
        for inp in node["inputs"]:
            edges.append({
                "from_record_id": inp["record_id"],
                "to_record_id": node["record_id"],
                "param_name": inp["param_name"],
            })
    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
# Execution audit (§9b) — who/when/which filter produced a record
# ---------------------------------------------------------------------------
def execution_audit(duck, record_id: str) -> list[dict]:
    """Every run that (re)produced ``record_id``, oldest first.

    Each entry: ``{timestamp, user_id, where_clause, function_name}``. Because
    re-runs append ``_run`` rows, a changed ``where=`` filter shows up as
    distinct audit rows rather than being lost to first-wins.
    """
    rows = duck._fetchall(
        "SELECT run.timestamp, run.user_id, run.where_clause, inv.function_name "
        "FROM _invocation_output io "
        "JOIN _invocation inv ON inv.invocation_id = io.invocation_id "
        "JOIN _run_invocation ri ON ri.invocation_id = io.invocation_id "
        "JOIN _run run ON run.run_id = ri.run_id "
        "WHERE io.output_record_id = ? "
        "ORDER BY run.timestamp",
        [record_id],
    )
    return [
        {"timestamp": ts, "user_id": uid, "where_clause": wc, "function_name": fn}
        for ts, uid, wc, fn in rows
    ]


# ---------------------------------------------------------------------------
# Single-record provenance (§7) — flat dict for a record's producing call
# ---------------------------------------------------------------------------
def provenance(duck, record_id: str) -> dict | None:
    """``{function_name, function_hash, inputs, constants}`` for ``record_id``.

    ``inputs`` is the list of variable input descriptors; ``constants`` the
    ``{param: value}`` map. ``None`` if the record has no producing invocation.
    """
    inv = producing_invocation(duck, record_id)
    if inv is None:
        return None
    inv_id, fn_name, fn_hash = inv
    var_inputs, constants = invocation_inputs(duck, inv_id)
    return {
        "function_name": fn_name,
        "function_hash": fn_hash,
        "inputs": var_inputs,
        "constants": constants,
    }


# ---------------------------------------------------------------------------
# Abstract pipeline structure (§ schema-blind) — unique fn/type wiring
# ---------------------------------------------------------------------------
def pipeline_structure(duck) -> list[dict]:
    """Unique ``(function_name, function_hash, output_type, input_types)`` tuples.

    Describes how variable *types* flow through functions, independent of data
    instances or schema locations.
    """
    # Exclude synthetic save invocations — they anchor direct-save kwargs, not
    # pipeline functions, and must not appear as nodes in the structure.
    inv_rows = duck._fetchall(
        "SELECT invocation_id, function_name, function_hash FROM _invocation "
        "WHERE function_name != ?",
        [SAVE_FUNCTION_NAME],
    )
    seen: set = set()
    results: list = []
    for inv_id, fn_name, fn_hash in inv_rows:
        out_types = [
            r[0] for r in duck._fetchall(
                "SELECT DISTINCT r.type FROM _invocation_output io "
                "JOIN _record r ON r.record_id = io.output_record_id "
                "WHERE io.invocation_id = ?",
                [inv_id],
            )
        ]
        in_types = tuple(sorted(
            r[0] for r in duck._fetchall(
                "SELECT r.type FROM _invocation_input ii "
                "JOIN _record r ON r.record_id = ii.input_record_id "
                "WHERE ii.invocation_id = ? AND r.type NOT IN (?, ?)",
                [inv_id, CONSTANT_TYPE, PATHINPUT_TYPE],
            )
        ))
        for out_type in out_types:
            key = (fn_name, fn_hash, out_type, in_types)
            if key in seen:
                continue
            seen.add(key)
            results.append({
                "function_name": fn_name,
                "function_hash": fn_hash,
                "output_type": out_type,
                "input_types": list(in_types),
            })
    return results


def has_producing_invocation(duck, record_id: str) -> bool:
    """True if ``record_id`` was produced by a recorded invocation."""
    rows = duck._fetchall(
        "SELECT 1 FROM _invocation_output WHERE output_record_id = ? LIMIT 1",
        [record_id],
    )
    return bool(rows)


def consumed_input_schema_ids(duck, record_ids) -> dict[str, frozenset]:
    """``{record_id: frozenset(schema_id, ...)}`` — the *schema locations* of the
    variable inputs each record's producing invocation consumed.

    This is the semantic identity of a ``where=`` variant (§10, "where= redesign"
    (B)): a ``where=`` filter's only effect on the computation is which input
    records survive it, and the graph already records those as the invocation's
    input edges. Reducing them to their **schema_ids** (stable locations, unlike
    record_ids which change on every input re-save) gives a content-edit-stable key
    that load can match against a freshly-resolved filter — making ``A & B`` and
    ``B & A`` (and other textually-different but equivalent filters) match, which
    the brittle ``where_clause`` string comparison cannot.

    Constants and PathInput specs are excluded (no schema location); NULL schema_ids
    are dropped. Raw records (no producing invocation) get no entry.
    """
    ids = [r for r in dict.fromkeys(record_ids)]
    if not ids:
        return {}
    placeholders = ", ".join(["?"] * len(ids))
    rows = duck._fetchall(
        f"SELECT io.output_record_id, r.schema_id "
        f"FROM _invocation_output io "
        f"JOIN _invocation_input ii ON ii.invocation_id = io.invocation_id "
        f"JOIN _record r ON r.record_id = ii.input_record_id "
        f"WHERE io.output_record_id IN ({placeholders}) "
        f"AND r.type NOT IN (?, ?) AND r.schema_id IS NOT NULL",
        ids + [CONSTANT_TYPE, PATHINPUT_TYPE],
    )
    acc: dict[str, set] = {}
    for rid, schema_id in rows:
        acc.setdefault(rid, set()).add(schema_id)
    return {rid: frozenset(s) for rid, s in acc.items()}


# ---------------------------------------------------------------------------
# Node completeness (§9c) — expected vs. present invocation membership
# ---------------------------------------------------------------------------
def present_invocation_schema_pairs(duck, inv_ids) -> set:
    """``{(invocation_id, schema_id)}`` actually produced — i.e. each invocation
    paired with the schema locations where it emitted an output record.

    Granularity is per (invocation, schema_id), not per invocation, because a
    PathInput-only function has no per-combo bindings → all its combos share one
    invocation_id, distinguished only by the output's schema location. For
    variable-input functions each combo already has a distinct invocation_id, so
    this reduces to plain invocation presence.
    """
    ids = list(inv_ids)
    if not ids:
        return set()
    placeholders = ", ".join(["?"] * len(ids))
    rows = duck._fetchall(
        f"SELECT DISTINCT io.invocation_id, r.schema_id "
        f"FROM _invocation_output io "
        f"JOIN _record r ON r.record_id = io.output_record_id "
        f"WHERE io.invocation_id IN ({placeholders})",
        ids,
    )
    return {(r[0], r[1]) for r in rows}


def function_variant_configs(duck, fn_name: str) -> list[dict]:
    """Distinct config "shapes" ``fn_name`` has been invoked with (from the graph).

    Each config: ``{input_types: {param: type}, selectors: {param: selector},
    constants: {param: value}, path_inputs: {param: to_key-json},
    as_table: [...], distribute: bool, invocation_ids: {inv_id, ...}}``.
    Deduped fn-hash-independently — a config is the call's wiring (which
    input *types*, which constants, which flags), the graph-derived
    equivalent of the old ``list_pipeline_variants`` grouping. Used to
    predict expected invocation_ids for input data that exists now but may
    not have been run yet, and (via :func:`config_call_id` +
    ``invocation_ids``) to scope node-state checks to one call site.
    """
    inv_rows = duck._fetchall(
        "SELECT invocation_id, as_table, distribute FROM _invocation WHERE function_name = ?",
        [fn_name],
    )
    configs: dict = {}
    for inv_id, as_table, distribute in inv_rows:
        var_inputs, constants = invocation_inputs(duck, inv_id)
        # selectors per param from the edges
        sel_rows = duck._fetchall(
            "SELECT param_name, selector FROM _invocation_input "
            "WHERE invocation_id = ? AND selector IS NOT NULL",
            [inv_id],
        )
        selectors = {p: s for p, s in sel_rows}
        input_types = {i["param_name"]: i["variable_type"] for i in var_inputs}
        path_inputs = invocation_path_inputs(duck, inv_id)
        at = sorted(as_table) if as_table else []
        key = (
            tuple(sorted(input_types.items())),
            tuple(sorted(selectors.items())),
            tuple(sorted((k, repr(v)) for k, v in constants.items())),
            tuple(sorted(path_inputs.items())),
            tuple(at),
            bool(distribute),
        )
        if key not in configs:
            configs[key] = {
                "input_types": input_types,
                "selectors": selectors,
                "constants": constants,
                "path_inputs": path_inputs,
                "as_table": at,
                "distribute": bool(distribute),
                "invocation_ids": set(),
            }
        configs[key]["invocation_ids"].add(inv_id)
    return list(configs.values())


def config_call_id(fn_name: str, cfg: dict) -> str:
    """The call-site id a variant config reconstructs to.

    Rebuilds the same version-keys payload ``pipeline_variants`` uses
    (``__fn``/``__inputs`` incl. PathInput to_key specs/``__constants``/
    ``__distribute``/``__as_table``) so the result matches the forward
    ``ForEachConfig.to_call_id`` for plain inputs — one recipe, both
    directions.
    """
    from .foreach_config import call_id_from_version_keys

    merged_inputs = {**cfg.get("input_types", {}), **cfg.get("path_inputs", {})}
    vk: dict = {"__fn": fn_name}
    if merged_inputs:
        vk["__inputs"] = merged_inputs
    vk["__constants"] = cfg.get("constants", {})
    if cfg.get("distribute"):
        vk["__distribute"] = True
    if cfg.get("as_table"):
        vk["__as_table"] = cfg["as_table"]
    return call_id_from_version_keys(vk)


def pipeline_variants(duck, output_type: str | None = None) -> list[dict]:
    """Distinct pipeline step variants, derived from the graph.

    Graph-native replacement for the old ``version_keys``-grouped
    ``list_pipeline_variants``. A variant is one ``(output_type, function_name,
    input_types, constants, output_num)`` combination — config-level
    (fn-hash- and instance-independent). Synthetic ``__save__`` invocations are
    excluded (they are not pipeline steps).

    Each dict: ``function_name``, ``output_type``, ``call_id`` (reusing
    ``call_id_from_version_keys`` over the reconstructed config signature, so it
    matches the forward ``ForEachConfig.to_call_id`` for plain inputs),
    ``input_types`` (param→type), ``constants`` (param→typed value),
    ``output_num`` (int|None), ``record_count`` (distinct output records).
    """
    from .foreach_config import call_id_from_version_keys

    inv_rows = duck._fetchall(
        "SELECT invocation_id, function_name, as_table, distribute FROM _invocation "
        "WHERE function_name != ?",
        [SAVE_FUNCTION_NAME],
    )

    groups: dict = {}        # group_key -> info dict
    group_records: dict = {}  # group_key -> set(output_record_id)

    for inv_id, fn_name, as_table, distribute in inv_rows:
        var_inputs, constants = invocation_inputs(duck, inv_id)
        input_types = {i["param_name"]: i["variable_type"] for i in var_inputs}
        # PathInput specs ride in input_types as their to_key() JSON string —
        # preserves the legacy contract (get_aggregated_variants parses them) and
        # call_id parity (forward to_call_id includes them in __inputs).
        input_types.update(invocation_path_inputs(duck, inv_id))
        at = sorted(as_table) if as_table else []

        # NB: where= is NOT part of config-variant identity. A where= filter's
        # only effect on the computation is the surviving input set, already folded
        # into invocation_id; its where_clause string is display-only (§10 where=
        # redesign). So two for_each calls differing only by where= are the same
        # config variant here.

        out_rows = duck._fetchall(
            "SELECT io.output_num, io.output_record_id, rec.type "
            "FROM _invocation_output io JOIN _record rec ON rec.record_id = io.output_record_id "
            "WHERE io.invocation_id = ?",
            [inv_id],
        )
        for output_num, out_rid, out_type in out_rows:
            if output_type is not None and out_type != output_type:
                continue
            gkey = (
                out_type, fn_name,
                tuple(sorted(input_types.items())),
                tuple(sorted((k, repr(v)) for k, v in constants.items())),
                output_num,
                tuple(at), bool(distribute),
            )
            if gkey not in groups:
                vk: dict = {"__fn": fn_name}
                if input_types:
                    vk["__inputs"] = input_types
                vk["__constants"] = constants
                if distribute:
                    vk["__distribute"] = True
                if at:
                    vk["__as_table"] = at
                groups[gkey] = {
                    "function_name": fn_name,
                    "output_type": out_type,
                    "call_id": call_id_from_version_keys(vk),
                    "input_types": input_types,
                    "constants": constants,
                    "output_num": output_num,
                }
                group_records[gkey] = set()
            group_records[gkey].add(out_rid)

    return [
        {**groups[gkey], "record_count": len(group_records[gkey])}
        for gkey in groups
    ]


def _producing_variant_key(duck, record_id: str):
    """A hashable key for the producing *variant* of a record: the constant
    bindings (sweep params) of its producing invocation, or ``None`` for raw
    records (no producing invocation).

    Re-saves and re-runs under the same constant config share a key (one is the
    superseding version of the other); genuinely different variants — the same
    type produced with different constants at the same schema — get different
    keys and so coexist. Input record_ids are deliberately excluded: re-running
    on a changed upstream input is the *same* variant, just newer.
    """
    inv = producing_invocation(duck, record_id)
    if inv is None:
        return None
    inv_id = inv[0]
    _var_inputs, constants = invocation_inputs(duck, inv_id)
    return tuple(sorted((k, repr(v)) for k, v in constants.items()))


def _current_records_by_schema(duck, variable_name: str) -> dict:
    """``{schema_id: [record_id, ...]}`` for the *current* records of a variable
    type — the latest non-excluded record per ``(schema location, producing
    variant)``.

    A re-save creates a new record_id at the same ``(schema, variant)``; only the
    newest is current. Superseded records MUST NOT be enumerated: each one would
    otherwise contribute a stale invocation to the expected set (inflating
    ``counts`` and, in the re-save-before-first-run edge case, producing a false
    "missing" → false red). Distinct variants at one schema are kept separately —
    they are concurrently valid.

    Note: resolves each record's producing variant via the graph (two extra
    queries per record). Fine at current scale; a candidate for a single-query
    optimization later.
    """
    rows = duck._fetchall(
        "SELECT rm.record_id, r.schema_id, rm.timestamp FROM _record_save rm "
        "JOIN _record r ON r.record_id = rm.record_id "
        "WHERE r.type = ? AND COALESCE(r.excluded, FALSE) = FALSE",
        [variable_name],
    )
    # Latest record per (schema_id, producing-variant key).
    best: dict = {}  # (schema_id, variant_key) -> (timestamp, record_id)
    for rid, sid, ts in rows:
        key = (sid, _producing_variant_key(duck, rid))
        prev = best.get(key)
        if prev is None or ts > prev[0]:
            best[key] = (ts, rid)
    out: dict = {}
    for (sid, _vkey), (_ts, rid) in best.items():
        out.setdefault(sid, []).append(rid)
    return out


def _predict_config_invocations(duck, fn_hash: str, cfg: dict, into: set) -> None:
    """Add expected ``(invocation_id, schema_id)`` pairs for one config × current
    input data into ``into``. Cross-products each input param's current records at
    every schema location where all params have data."""
    import itertools
    from .provenance import compute_constant_record_id, compute_invocation_id

    input_types = cfg["input_types"]
    if not input_types:
        return  # PathInput/no-DB-input config — realized_inputless_invocations covers it
    selectors = cfg["selectors"]
    const_bindings = [
        (p, compute_constant_record_id(v)) for p, v in cfg["constants"].items()
    ]
    per_param = {
        param: _current_records_by_schema(duck, vtype)
        for param, vtype in input_types.items()
    }
    common_schema = set.intersection(
        *[set(m.keys()) for m in per_param.values()]
    ) if per_param else set()
    param_names = list(input_types.keys())
    for sid in common_schema:
        choices = [[(p, rid) for rid in per_param[p][sid]] for p in param_names]
        for combo in itertools.product(*choices):
            bindings = [(p, rid, selectors.get(p)) for p, rid in combo]
            bindings += [(p, crid, None) for p, crid in const_bindings]
            inv_id = compute_invocation_id(
                fn_hash, cfg["as_table"], cfg["distribute"], bindings,
            )
            into.add((inv_id, sid))


def config_from_inputs(inputs: dict) -> dict:
    """Build a variant config (same shape as :func:`function_variant_configs`
    entries) from a for_each-style ``inputs`` dict — used to predict expected
    invocations for a function that has never run yet.

    Mirrors ``ForEachConfig._get_direct_constants`` / the save path: loadable
    specs become input_types (by class name), ColumnSelection contributes a
    selector, PathInput/PathOutput/ColName are excluded, everything else is a
    constant. ``as_table``/``distribute`` aren't expressible here → defaults.
    """
    from .foreach import _is_loadable
    from .colname import ColName
    from .column_selection import ColumnSelection
    from .fixed import Fixed
    from .provenance_save import compute_input_selectors
    try:
        from scifor import PathInput as _PathInput, PathOutput as _PathOutput
    except ImportError:
        _PathInput = _PathOutput = None

    input_types: dict = {}
    constants: dict = {}
    for name, spec in inputs.items():
        if _PathInput is not None and isinstance(spec, _PathInput):
            continue
        if _PathOutput is not None and isinstance(spec, _PathOutput):
            continue
        if isinstance(spec, ColName):
            continue
        if _is_loadable(spec):
            vt = spec
            if isinstance(vt, Fixed):
                vt = vt.var_type
            if isinstance(vt, ColumnSelection):
                vt = vt.var_type
            if isinstance(vt, type):
                input_types[name] = vt.__name__
        else:
            constants[name] = spec
    return {
        "input_types": input_types,
        "selectors": compute_input_selectors(inputs),
        "constants": constants,
        "as_table": [],
        "distribute": False,
    }


def realized_inputless_invocations(duck, fn_name: str) -> set:
    """``{(invocation_id, schema_id)}`` for invocations of ``fn_name`` that have
    **no variable inputs** (only constants, or nothing) — i.e. PathInput-only
    loaders and similar source nodes.

    These have no DB input data to predict an expected set from, so their
    *realized* output locations ARE their expected set: present == expected →
    the node reports green when run, red when never run (a partially-run loader
    still reads green — there is no live source for the combos that *should*
    exist but were never produced).

    Pure structural read from the graph — no invocation_id recomputation, so no
    predicted-vs-realized drift.
    """
    out: set = set()
    for (inv_id,) in duck._fetchall(
        "SELECT invocation_id FROM _invocation WHERE function_name = ?",
        [fn_name],
    ):
        has_var_input = duck._fetchall(
            "SELECT 1 FROM _invocation_input ii "
            "JOIN _record r ON r.record_id = ii.input_record_id "
            "WHERE ii.invocation_id = ? AND r.type NOT IN (?, ?) LIMIT 1",
            [inv_id, CONSTANT_TYPE, PATHINPUT_TYPE],
        )
        if has_var_input:
            continue  # has variable inputs → live prediction handles it
        for (sid,) in duck._fetchall(
            "SELECT DISTINCT r.schema_id FROM _invocation_output io "
            "JOIN _record r ON r.record_id = io.output_record_id "
            "WHERE io.invocation_id = ?",
            [inv_id],
        ):
            out.add((inv_id, sid))
    return out


def realized_inputless_schema_ids(duck, fn_name: str, const_rids: dict) -> set:
    """Schema_ids where ``fn_name`` produced output via an **inputless** invocation
    whose constant inputs exactly match ``const_rids`` (``{param: constant_record_id}``).

    Used by the PathInput-node outdated check (``state.check_pathinput_node_state``)
    to find the locations the loader has *actually* produced under the current
    constant config. Constants are content-addressed, so matching is a plain
    record_id dict-equality — no value round-trip and no invocation_id recompute
    (the only hashing is the caller's ``compute_constant_record_id`` on the live
    constants, which is identical everywhere). PathInput specs are deliberately
    NOT part of this match: a template change does not fork a variant (see §10 #6).
    """
    by_inv: dict = {}
    for inv_id, sid in realized_inputless_invocations(duck, fn_name):
        by_inv.setdefault(inv_id, set()).add(sid)
    out: set = set()
    for inv_id, sids in by_inv.items():
        rows = duck._fetchall(
            "SELECT ii.param_name, ii.input_record_id FROM _invocation_input ii "
            "JOIN _record r ON r.record_id = ii.input_record_id "
            "WHERE ii.invocation_id = ? AND r.type = ?",
            [inv_id, CONSTANT_TYPE],
        )
        if {p: rid for p, rid in rows} == const_rids:
            out |= sids
    return out


def expected_invocations_for_function(db, fn_name: str, fn_hash: str,
                                      inputs_fallback: dict | None = None,
                                      call_id: str | None = None) -> set:
    """Expected ``{(invocation_id, schema_id)}`` pairs for ``fn_name`` (§9c).

    Derived live from the graph (no persisted snapshot — see the removal of
    ``_for_each_expected``). Union of:
      * the realized inputless invocations of the function (zero-DB-input loaders
        whose expected set is exactly what they have produced — see
        :func:`realized_inputless_invocations`),
      * a live prediction from current input data for each variant config the
        function has already been run with (so input data added *after* the last
        run still surfaces as missing), and
      * a live prediction from ``inputs_fallback`` when provided — lets a
        never-run function enumerate its expected combos from its declared inputs.

    ``call_id`` scopes the check to ONE call site: only variant configs whose
    :func:`config_call_id` matches contribute (predictions AND realized
    inputless pairs, the latter restricted to matching configs'
    ``invocation_ids``), so a fn reused across call sites never blurs — one
    site's partial run cannot redden another's fully-run node.

    Each pair's presence (an output of that invocation at that schema location)
    is the completeness signal — see :func:`present_invocation_schema_pairs`.

    Note: a zero-input function (e.g. a PathInput-only loader) has no input data
    to enumerate, so it contributes only the invocations it has already realized.
    Such a node therefore reports **green** (run, even partially) or **red**
    (never run) — there is no live source for the set of combos it *should*
    produce, so un-run combos cannot be detected.
    """
    duck = db._duck
    expected: set = set()

    configs = function_variant_configs(duck, fn_name)
    if call_id is not None:
        matched = [c for c in configs
                   if config_call_id(fn_name, c) == call_id]
        logger.debug(
            "expected_invocations(%s): call_id=%s matched %d/%d config(s)",
            fn_name, call_id, len(matched), len(configs),
        )
        configs = matched
        scoped_inv_ids = set().union(
            *[c["invocation_ids"] for c in configs]) if configs else set()

    # (a) realized inputless invocations (PathInput-only loaders, etc.)
    realized = realized_inputless_invocations(duck, fn_name)
    if call_id is not None:
        realized = {(i, s) for i, s in realized if i in scoped_inv_ids}
    expected |= realized

    # (b) live prediction per known variant config × current input data
    for cfg in configs:
        _predict_config_invocations(duck, fn_hash, cfg, expected)

    # (c) live prediction from the declared inputs (never-run fallback) —
    # under call_id scoping, only when the declared config IS that call site.
    if inputs_fallback:
        fallback_cfg = config_from_inputs(inputs_fallback)
        if call_id is None or config_call_id(fn_name, fallback_cfg) == call_id:
            _predict_config_invocations(duck, fn_hash, fallback_cfg, expected)

    return expected
