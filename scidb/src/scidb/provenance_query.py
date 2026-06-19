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
from .provenance import CONSTANT_TYPE

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
        if node is None or node["type"] == CONSTANT_TYPE:
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
    inv_rows = duck._fetchall(
        "SELECT invocation_id, function_name, function_hash FROM _invocation"
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
                "WHERE ii.invocation_id = ? AND r.type != ?",
                [inv_id, CONSTANT_TYPE],
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


# ---------------------------------------------------------------------------
# Node completeness (§9c) — expected vs. present invocation membership
# ---------------------------------------------------------------------------
def present_invocations(duck, inv_ids) -> set:
    """Subset of ``inv_ids`` that exist in ``_invocation``."""
    ids = list(inv_ids)
    if not ids:
        return set()
    placeholders = ", ".join(["?"] * len(ids))
    rows = duck._fetchall(
        f"SELECT invocation_id FROM _invocation WHERE invocation_id IN ({placeholders})",
        ids,
    )
    return {r[0] for r in rows}


def function_variant_configs(duck, fn_name: str) -> list[dict]:
    """Distinct config "shapes" ``fn_name`` has been invoked with (from the graph).

    Each config: ``{input_types: {param: type}, selectors: {param: selector},
    constants: {param: value}, as_table: [...], distribute: bool}``. Deduped
    fn-hash-independently — a config is the call's wiring (which input *types*,
    which constants, which flags), the graph-derived equivalent of the old
    ``list_pipeline_variants`` grouping. Used to predict expected invocation_ids
    for input data that exists now but may not have been run yet.
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
        at = sorted(as_table) if as_table else []
        key = (
            tuple(sorted(input_types.items())),
            tuple(sorted(selectors.items())),
            tuple(sorted((k, repr(v)) for k, v in constants.items())),
            tuple(at),
            bool(distribute),
        )
        if key not in configs:
            configs[key] = {
                "input_types": input_types,
                "selectors": selectors,
                "constants": constants,
                "as_table": at,
                "distribute": bool(distribute),
            }
    return list(configs.values())


def _current_records_by_schema(duck, variable_name: str) -> dict:
    """``{schema_id: [record_id, ...]}`` for the latest non-excluded records of a
    variable type (one per distinct producing variant / raw save)."""
    rows = duck._fetchall(
        "SELECT record_id, schema_id FROM _record_metadata "
        "WHERE variable_name = ? AND COALESCE(excluded, FALSE) = FALSE",
        [variable_name],
    )
    out: dict = {}
    for rid, sid in rows:
        out.setdefault(sid, []).append(rid)
    return out


def expected_invocations_for_function(db, fn_name: str, fn_hash: str) -> dict:
    """Expected ``{invocation_id: schema_id}`` for ``fn_name`` (§9c).

    Union of:
      * the persisted snapshot in ``_for_each_expected`` (covers PathInput-only
        functions and combos that failed/were skipped), and
      * a live prediction from current input data for each known variant config —
        so input data added *after* the last run still surfaces as missing.

    Membership of these ids in ``_invocation`` is the completeness signal.
    """
    from .provenance import compute_constant_record_id, compute_invocation_id

    duck = db._duck
    expected: dict = {}

    # (a) persisted snapshot
    for inv_id, sid in duck._fetchall(
        "SELECT invocation_id, schema_id FROM _for_each_expected WHERE function_name = ?",
        [fn_name],
    ):
        expected[inv_id] = sid

    # (b) live prediction per variant config × current input data
    for cfg in function_variant_configs(duck, fn_name):
        input_types = cfg["input_types"]
        if not input_types:
            continue  # PathInput/no-DB-input config — snapshot covers it
        selectors = cfg["selectors"]
        const_bindings = [
            (p, compute_constant_record_id(v)) for p, v in cfg["constants"].items()
        ]
        # records per param, grouped by schema_id
        per_param = {
            param: _current_records_by_schema(duck, vtype)
            for param, vtype in input_types.items()
        }
        # schema locations where every input param has at least one record
        common_schema = set.intersection(
            *[set(m.keys()) for m in per_param.values()]
        ) if per_param else set()
        for sid in common_schema:
            # cross-product of each param's records at this schema location
            import itertools
            param_names = list(input_types.keys())
            choices = [[(p, rid) for rid in per_param[p][sid]] for p in param_names]
            for combo in itertools.product(*choices):
                bindings = [(p, rid, selectors.get(p)) for p, rid in combo]
                bindings += [(p, crid, None) for p, crid in const_bindings]
                inv_id = compute_invocation_id(
                    fn_hash, cfg["as_table"], cfg["distribute"], bindings,
                )
                expected.setdefault(inv_id, sid)

    return expected
