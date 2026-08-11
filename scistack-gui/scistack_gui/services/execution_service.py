"""
Execution service — the document→backend pipeline compiler (G2).

Two jobs:

1. **Target derivation** (`derive_fn_targets`): what for_each call(s) does a
   function node represent? DB history (pipeline variants) first, manual
   edges + pending constants as the never-run fallback — extracted from the
   run thread so per-node runs and pipeline runs derive identically.
2. **Compilation** (`build_backend_pipeline`): turn a GUI pipeline scope
   (document nodes + use edges) into an in-session ``scidb.Pipeline`` —
   each function node's targets register via ``for_each(...,
   pipeline=pipe)``; use rows become ``parent.use(child.bind(**binding))``.
   Pipelines are built fresh per request (in-session objects; the document
   is the persistent form — spec persistence stays deliberately unbuilt).

``plan_pipeline`` is the plan-preview data source (R2): compile, then
``pipe.plan(target)`` — nothing executes.
"""

from __future__ import annotations

import ast
import logging
from itertools import product

logger = logging.getLogger(__name__)


def derive_fn_targets(db, function_name: str) -> list[dict]:
    """The for_each target(s) a function node represents.

    Each target: ``{"input_types": {param: type-or-list}, "output_type":
    str, "constants": {name: typed value}}`` — DB pipeline variants when
    history exists (manual output wiring overrides stale DB outputs),
    otherwise inferred from manual edges + pending constants. Returns []
    when nothing is derivable (no history AND no output wiring).
    """
    from scistack_gui import pipeline_store
    from scistack_gui.api.pipeline import _fn_params_from_registry
    from scistack_gui.domain.edge_resolver import (
        infer_manual_fn_output_types,
        resolve_function_edges,
    )
    from scistack_gui.domain.graph_builder import fn_node_id

    all_variants = db.list_pipeline_variants()
    fn_variants = [v for v in all_variants if v["function_name"] == function_name]

    all_edges = pipeline_store.get_manual_edges(db)
    manual_nodes = pipeline_store.get_manual_nodes(db)

    fn_node_ids = {f"fn__{function_name}"}  # legacy/manual edges
    for v in fn_variants:
        cid = v.get("call_id")
        if cid:
            fn_node_ids.add(fn_node_id(function_name, cid))
    for nid, meta in manual_nodes.items():
        if meta["type"] == "functionNode" and meta["label"] == function_name:
            fn_node_ids.add(nid)
    # Manual edges may reference WIRING-GROUPED node ids (fn__{fn}__{wid} —
    # the canvas groups call sites since 2026-07-18) whose suffix is not any
    # call_id: adopt any edge endpoint whose parsed fn name matches.
    from scistack_gui.domain.graph_builder import parse_fn_node_id

    for edge in all_edges:
        for endpoint in (edge.get("source"), edge.get("target")):
            if endpoint and endpoint not in fn_node_ids:
                parsed_ep = parse_fn_node_id(endpoint)
                if parsed_ep is not None and parsed_ep[0] == function_name:
                    fn_node_ids.add(endpoint)

    manual_output_types = infer_manual_fn_output_types(
        fn_node_ids, all_edges, manual_nodes, existing_node_labels={}
    )

    from scistack_gui.domain.variant_resolver import filter_disconnected_targets

    hidden_edge_ids = pipeline_store.get_hidden_edge_ids(db)
    if hidden_edge_ids and fn_variants:
        before = len(fn_variants)
        fn_variants = filter_disconnected_targets(
            fn_variants, function_name, hidden_edge_ids, all_edges, manual_nodes
        )
        if len(fn_variants) != before:
            logger.info(
                "[execution] '%s': %d target(s) excluded — disconnected wiring",
                function_name,
                before - len(fn_variants),
            )

    if fn_variants and manual_output_types:
        # User rewired outputs: current wiring overrides stale DB history.
        logger.info(
            "[execution] '%s': overriding DB output types with manual wiring %s",
            function_name,
            manual_output_types,
        )
        overridden, seen_constants = [], set()
        for v in fn_variants:
            key = tuple(sorted(v["constants"].items()))
            if key in seen_constants:
                continue
            seen_constants.add(key)
            for out in manual_output_types:
                overridden.append({**v, "output_type": out})
        fn_variants = overridden

    if fn_variants:
        return fn_variants

    # Never-run fallback: infer the call from manual edges.
    sig_params = _fn_params_from_registry(function_name)
    resolved = resolve_function_edges(
        fn_node_ids=fn_node_ids,
        manual_edges=all_edges,
        manual_nodes=manual_nodes,
        existing_node_labels={},
        sig_params=sig_params,
    )
    if not resolved.output_types:
        logger.warning(
            "[execution] '%s': no DB history and no output "
            "wiring — no targets derivable",
            function_name,
        )
        return []

    inferred_constants: dict[str, list] = {}
    if resolved.constant_names:
        pending = pipeline_store.get_pending_constants(db)
        for cname in resolved.constant_names:
            typed_vals = []
            for raw in pending.get(cname, set()):
                try:
                    typed_vals.append(ast.literal_eval(raw))
                except (ValueError, SyntaxError):
                    typed_vals.append(raw)
            if typed_vals:
                inferred_constants[cname] = typed_vals
            else:
                logger.warning(
                    "[execution] '%s': constant '%s' wired but has no pending values",
                    function_name,
                    cname,
                )

    if inferred_constants:
        const_names = sorted(inferred_constants.keys())
        targets = []
        for combo in product(*(inferred_constants[c] for c in const_names)):
            constants = dict(zip(const_names, combo, strict=False))
            for out in resolved.output_types:
                targets.append(
                    {
                        "input_types": resolved.input_types,
                        "output_type": out,
                        "constants": constants,
                    }
                )
        return targets
    return [
        {"input_types": resolved.input_types, "output_type": out, "constants": {}}
        for out in resolved.output_types
    ]


def derive_target_for_node(db, node_id: str) -> list[dict]:
    """The for_each target(s) that ONE SPECIFIC function node represents.

    ``derive_fn_targets`` resolves by function NAME across every node/call
    site sharing that name — correct as long as a name has only ever had
    ONE wiring, but the same function name can now legitimately have
    multiple independent wirings on one canvas (e.g. compute_rolling_vo2
    fed by RawVO2 in one node and by RawHeartRate in another — see
    api/pipeline.py's wiring-conflict guard, which keeps such nodes from
    merging/showing each other's state). Resolving purely by name can't
    tell them apart for EXECUTION either: clicking Run on the RawHeartRate
    node used to silently re-run the RawVO2 node's real DB history instead
    (found via a real GUI session). This resolves by the exact node
    clicked, using its own embedded wiring (already-graduated nodes) or
    its own resolved edges (still-manual nodes) to select only the
    matching real history / infer a fresh target — never anything
    belonging to a different node that merely shares the label.

    Returns the same shape as ``derive_fn_targets`` (a list of
    ``{"input_types", "output_type", "constants"}`` dicts — one per known
    constant-value variant of THIS wiring, or one freshly-inferred target
    if it has never been run), or ``[]`` if ``node_id`` isn't a function
    node or nothing is derivable from it.
    """
    from scistack_gui import pipeline_store
    from scistack_gui.api.pipeline import _fn_params_from_registry
    from scistack_gui.domain.edge_resolver import resolve_function_edges
    from scistack_gui.domain.graph_builder import parse_fn_node_id, wiring_id

    manual_nodes = pipeline_store.get_manual_nodes(db)
    all_edges = pipeline_store.get_manual_edges(db)

    meta = manual_nodes.get(node_id)
    parsed = parse_fn_node_id(node_id)
    resolved = None
    if meta is not None:
        if meta["type"] != "functionNode":
            return []
        function_name = meta["label"]
        node_wiring = None  # resolved from this node's own edges, below
    elif parsed is not None:
        function_name, node_wiring = parsed
    else:
        return []

    all_variants = db.list_pipeline_variants()
    fn_variants = [v for v in all_variants if v["function_name"] == function_name]

    if node_wiring is None:
        # Manual (not yet graduated) node — resolve ITS OWN wiring from
        # its own edges only, never from any other node sharing the label.
        sig_params = _fn_params_from_registry(function_name)
        resolved = resolve_function_edges(
            fn_node_ids={node_id},
            manual_edges=all_edges,
            manual_nodes=manual_nodes,
            existing_node_labels={},
            sig_params=sig_params,
        )
        if not resolved.output_types:
            return []
        inferred_inputs = {p: ts[0] for p, ts in resolved.input_types.items() if ts}
        node_wiring = wiring_id(function_name, inferred_inputs, set(resolved.output_types))

    matching = [
        v
        for v in fn_variants
        if wiring_id(function_name, v["input_types"], {v["output_type"]}) == node_wiring
    ]
    hidden_edge_ids = pipeline_store.get_hidden_edge_ids(db)
    if hidden_edge_ids and matching:
        from scistack_gui.domain.variant_resolver import filter_disconnected_targets

        before = len(matching)
        matching = filter_disconnected_targets(
            matching, function_name, hidden_edge_ids, all_edges, manual_nodes
        )
        if len(matching) != before:
            logger.info(
                "[execution] node %s ('%s'): %d target(s) excluded — disconnected wiring",
                node_id,
                function_name,
                before - len(matching),
            )
    if matching:
        return matching
    if resolved is None:
        # An already-graduated node whose embedded wiring matches nothing
        # in current history (stale) — nothing safe to run as this node.
        return []

    # Never run with this wiring before — infer constant values from (in
    # order): pending (staged-but-unrun) values, then real DB history for
    # this FUNCTION regardless of wiring (a constant's known values are a
    # function-level property — e.g. compute_rolling_vo2's window_seconds
    # already has a real, known value from the RawVO2 call site, and a
    # user wiring the SAME shared constant node into a new RawHeartRate
    # wiring clearly means to reuse it, not re-stage it from scratch).
    inferred_constants: dict[str, list] = {}
    if resolved.constant_names:
        pending = pipeline_store.get_pending_constants(db)
        for cname in resolved.constant_names:
            typed_vals = []
            for raw in pending.get(cname, set()):
                try:
                    typed_vals.append(ast.literal_eval(raw))
                except (ValueError, SyntaxError):
                    typed_vals.append(raw)
            if not typed_vals:
                known_vals = {
                    v["constants"][cname]
                    for v in fn_variants
                    if cname in v.get("constants", {})
                }
                if known_vals:
                    typed_vals = sorted(known_vals, key=str)
                    logger.debug(
                        "[execution] '%s' (node %s): constant '%s' has no "
                        "pending value — reusing known value(s) %s from "
                        "other call site(s) of this function",
                        function_name,
                        node_id,
                        cname,
                        typed_vals,
                    )
            if typed_vals:
                inferred_constants[cname] = typed_vals
            else:
                logger.warning(
                    "[execution] '%s' (node %s): constant '%s' wired but "
                    "has no pending or known values",
                    function_name,
                    node_id,
                    cname,
                )

    if inferred_constants:
        const_names = sorted(inferred_constants.keys())
        return [
            {
                "input_types": resolved.input_types,
                "output_type": out,
                "constants": dict(zip(const_names, combo, strict=False)),
            }
            for combo in product(*(inferred_constants[c] for c in const_names))
            for out in resolved.output_types
        ]
    return [
        {"input_types": resolved.input_types, "output_type": out, "constants": {}}
        for out in resolved.output_types
    ]


def disconnected_reason(db, function_name: str, node_id: "str | None" = None) -> "str | None":
    """Human-readable reason *function_name* (or one specific node's own
    wiring, if ``node_id`` is given) can't run right now because a
    required input edge is hidden — None if it's runnable, INCLUDING the
    case where it simply has no DB history yet (a different, unrelated
    situation the caller already messages separately).

    Cheap, independent of ``derive_fn_targets``/``derive_target_for_node``
    (which already silently exclude disconnected targets) — this exists so
    callers that get an empty target list can tell "disconnected" apart
    from "never run" and surface the right explicit error (see api/run.py).
    """
    from scistack_gui import pipeline_store
    from scistack_gui.domain.graph_builder import (
        manual_edge_handle_index,
        parse_fn_node_id,
        wiring_id,
    )

    hidden_edge_ids = pipeline_store.get_hidden_edge_ids(db)
    if not hidden_edge_ids:
        return None

    manual_index = manual_edge_handle_index(pipeline_store.get_manual_edges(db))

    node_wiring = None
    if node_id:
        parsed = parse_fn_node_id(node_id)
        if parsed is not None:
            node_wiring = parsed[1]

    all_variants = db.list_pipeline_variants()
    for v in all_variants:
        if v["function_name"] != function_name:
            continue
        wid = wiring_id(function_name, v["input_types"], {v["output_type"]})
        if node_wiring is not None and wid != node_wiring:
            continue
        for pname, vtype in v["input_types"].items():
            candidate = f"e__{vtype}__{function_name}__{wid}"
            if candidate in hidden_edge_ids and (function_name, wid, f"in__{pname}") not in manual_index:
                return f"input '{pname}' is disconnected — reconnect it before running"
        for cname in v.get("constants", {}).keys():
            candidate = f"e__{cname}__{function_name}__{wid}"
            if candidate in hidden_edge_ids and (function_name, wid, f"const__{cname}") not in manual_index:
                return f"input '{cname}' is disconnected — reconnect it before running"
    return None


def disconnected_report_entries(db, pipeline_id: str) -> list[dict]:
    """Synthetic report entries (compatible in shape with scidb's
    Pipeline.last_run_report) for functions in *pipeline_id*'s scope that
    won't actually run because a required input is disconnected (direct)
    or because an upstream producer is (cascaded) — computed independently
    of the compiled scidb.Pipeline and merged into the response by
    run_pipeline/plan_pipeline, never mutating scidb's own report object
    (this "disconnected" concept is GUI-authored state, scistack-gui's own
    layer — see plan-edge-hide-delete.md).
    """
    from scistack_gui import pipeline_store
    from scistack_gui.domain.graph_builder import hidden_wirings, wirings_downstream_of

    hidden_edge_ids = pipeline_store.get_hidden_edge_ids(db)
    if not hidden_edge_ids:
        return []

    scidb_agg = db.get_aggregated_variants()
    fn_input_params: dict = {}
    fn_outputs: dict = {}
    fn_constants: dict = {}
    for (fn_name, call_id), fn_data in scidb_agg["functions"].items():
        fkey = (fn_name, call_id)
        fn_input_params[fkey] = fn_data["input_params"]
        fn_outputs[fkey] = set(fn_data["outputs"])
        fn_constants[fkey] = set(fn_data["constants"].keys())
    path_inputs: dict = {
        param_name: {"functions": {tuple(f) for f in pi_data["functions"]}}
        for param_name, pi_data in scidb_agg["path_inputs"].items()
    }

    manual_edges = pipeline_store.get_manual_edges(db)
    seed = hidden_wirings(
        fn_input_params, fn_outputs, fn_constants, path_inputs, hidden_edge_ids,
        manual_edges=manual_edges,
    )
    if not seed:
        return []
    downstream = wirings_downstream_of(fn_input_params, fn_outputs, seed)

    scope_labels = set(_scope_function_labels(db, pipeline_id))

    def _entry(fn: str, reason: str) -> dict:
        return {
            "step": fn,
            "label": fn,
            "pipeline": pipeline_id,
            "completed": 0,
            "failed": 0,
            "no_data": 0,
            "total": 0,
            "cancelled": False,
            "skipped": True,
            "skip_reason": reason,
        }

    from scistack_gui.domain.graph_builder import manual_edge_handle_index

    manual_index = manual_edge_handle_index(manual_edges)

    entries: list[dict] = []
    seen_labels: set[str] = set()
    for fn, wid in sorted(seed):
        if fn not in scope_labels or fn in seen_labels:
            continue
        seen_labels.add(fn)
        reason = "required input disconnected"
        for fkey, params in fn_input_params.items():
            if fkey[0] != fn:
                continue
            for pname, vtype in params.items():
                if (
                    f"e__{vtype}__{fn}__{wid}" in hidden_edge_ids
                    and (fn, wid, f"in__{pname}") not in manual_index
                ):
                    reason = f"input '{pname}' disconnected"
                    break
            for cname in fn_constants.get(fkey, set()):
                if (
                    f"e__{cname}__{fn}__{wid}" in hidden_edge_ids
                    and (fn, wid, f"const__{cname}") not in manual_index
                ):
                    reason = f"input '{cname}' disconnected"
                    break
        entries.append(_entry(fn, reason))
    for fn, _wid in sorted(downstream):
        if fn not in scope_labels or fn in seen_labels:
            continue
        seen_labels.add(fn)
        entries.append(_entry(fn, "upstream input unavailable"))

    if entries:
        logger.info(
            "[execution] scope %s: %d function(s) skipped (disconnected/cascaded)",
            pipeline_id,
            len(entries),
        )
    return entries


def resolve_combo_call_ids(
    db, function_name: str, node_id: str | None, variant_key: dict
) -> list[str]:
    """Turn one Variants-table row (its constant axes) into the call_id(s)
    to hide/unhide — usually one, occasionally more if multiple output
    types share the same constants. Entries with no computable call_id
    (an unresolved multi-type input) are silently skipped — fail safe, see
    ``variant_resolver.compute_call_id``.
    """
    from scistack_gui import pipeline_store
    from scistack_gui.domain.variant_resolver import constants_match, resolve_target_call_id

    targets = (
        derive_target_for_node(db, node_id)
        if node_id
        else derive_fn_targets(db, function_name)
    )
    pending_consts = pipeline_store.get_pending_constants(db)
    targets = apply_pending_overrides(targets, pending_consts)
    matches = [t for t in targets if constants_match(t["constants"], variant_key)]

    node_config: dict = {}
    if node_id:
        node_config = pipeline_store.get_manual_nodes(db).get(node_id, {}).get("config") or {}
    run_opts = node_config.get("runOptions") or {}
    pending_names = set(pending_consts)

    cids: list[str] = []
    for t in matches:
        cid = resolve_target_call_id(
            function_name,
            t,
            pending_names,
            distribute=run_opts.get("distribute", False),
            as_table=run_opts.get("as_table"),
        )
        if cid is not None:
            cids.append(cid)
    return cids


def apply_pending_overrides(targets: list[dict], pending_constants: dict) -> list[dict]:
    """Staged pending values override DB history on every derived target
    that uses the constant — the SHARED seam for eager per-node runs and
    compiled pipeline runs, so both materialize staged values identically
    (Strategy 2: first staged value wins, replacing the DB value; string
    values are literal_eval'd so ``"10"`` runs as ``10``).

    Overriding can collapse targets that differed only in the overridden
    constant into duplicates — callers should re-deduplicate after.
    Returns a new list; input targets are not mutated.
    """
    if not pending_constants:
        return targets
    out = []
    for target in targets:
        constants = dict(target["constants"])
        overridden = []
        for const_name, values in pending_constants.items():
            if const_name in constants and values:
                raw = next(iter(values))
                try:
                    typed = ast.literal_eval(raw)
                except (ValueError, SyntaxError):
                    typed = raw
                constants[const_name] = typed
                overridden.append(const_name)
        if overridden:
            logger.info(
                "[execution] pending override on %s target: %s",
                target.get("output_type"),
                {k: constants[k] for k in overridden},
            )
            out.append({**target, "constants": constants})
        else:
            out.append(target)
    return out


def _build_inputs(target: dict):
    """for_each inputs dict from a derived target (types + constants)."""
    from scidb import EachOf
    from scistack_gui import registry

    inputs: dict = {}
    for param, type_names in target["input_types"].items():
        if isinstance(type_names, list):
            if len(type_names) > 1:
                inputs[param] = EachOf(
                    *(registry.get_variable_class(t) for t in type_names)
                )
            elif type_names:
                inputs[param] = registry.get_variable_class(type_names[0])
        else:
            inputs[param] = registry.get_variable_class(type_names)
    inputs.update(target["constants"])
    return inputs


def _scope_function_node_ids(db, pipeline_id: str) -> list[tuple[str, str]]:
    """Distinct (node_id, function_label) pairs whose nodes live in
    ``pipeline_id`` — manual function nodes by pipeline_id, DB-derived
    fn__ nodes by where their position is saved (same membership rule as
    the canvas).

    One entry per WIRING, not per function name: the same function name
    can have more than one independent wiring on a canvas at once (e.g.
    compute_rolling_vo2 fed by RawVO2 in one node and by RawHeartRate in
    another — see api/pipeline.py's wiring-conflict guard). Collapsing to
    distinct names here would make ``build_backend_pipeline`` derive
    targets by name (``derive_fn_targets``, which resolves across EVERY
    wiring sharing that name) instead of by the exact node
    (``derive_target_for_node``) — silently pipeline-running a sibling
    wiring's real DB history that isn't even the one on screen, and
    resurrecting a stale node for it once the run lands. See
    derive_target_for_node's docstring for the same bug, previously fixed
    for the single-node Run path but not this one.
    """
    from scistack_gui import layout as layout_store
    from scistack_gui import pipeline_store
    from scistack_gui.domain.graph_builder import (
        fn_node_id,
        parse_fn_node_id,
        wiring_id,
    )
    from scistack_gui.domain.scope_filter import node_scope

    manual_nodes = pipeline_store.get_manual_nodes(db)
    positions_by_scope = layout_store.read_positions_by_scope()

    seen: set[str] = set()
    node_ids: list[tuple[str, str]] = []

    def _add(nid: str, label: str) -> None:
        if nid not in seen:
            seen.add(nid)
            node_ids.append((nid, label))

    for nid, meta in manual_nodes.items():
        if (
            meta.get("type") == "functionNode"
            and (meta.get("pipeline_id") or "main") == pipeline_id
        ):
            _add(nid, meta["label"])
    placed_wirings: set[tuple[str, str]] = set()
    for _scope_id, positions in positions_by_scope.items():
        for nid in positions:
            parsed = parse_fn_node_id(nid)
            if parsed is None or nid in manual_nodes:
                continue
            placed_wirings.add(parsed)
            if node_scope(nid, manual_nodes, positions_by_scope) == pipeline_id:
                _add(nid, parsed[0])
    # DB-derived wirings with NO saved position default to root — one
    # entry per distinct (fn_name, wiring_id) among the unplaced variants,
    # not one per fn_name (a name can have several unplaced wirings at
    # once, each needing its own step).
    if pipeline_id == "main":
        for v in db.list_pipeline_variants():
            fn = v["function_name"]
            wid = wiring_id(fn, v["input_types"], {v["output_type"]})
            if (fn, wid) not in placed_wirings:
                _add(fn_node_id(fn, wid), fn)
    return node_ids


def _scope_function_labels(db, pipeline_id: str) -> list[str]:
    """Distinct function labels represented in ``pipeline_id`` — for
    reporting only (e.g. the disconnected-steps summary), where
    collapsing sibling wirings of the same name to one label is fine.
    Execution must stay wiring-scoped — see _scope_function_node_ids."""
    labels: list[str] = []
    for _nid, label in _scope_function_node_ids(db, pipeline_id):
        if label not in labels:
            labels.append(label)
    return labels


def build_backend_pipeline(db, pipeline_id: str, _built: dict | None = None):
    """Compile one GUI pipeline scope into an in-session scidb.Pipeline.

    Function nodes register their derived targets as deferred steps
    (``pipeline=pipe`` — never ambient, so nothing else in the process is
    affected); use rows compose recursively with their bindings. Shared
    children compile once per request (``_built`` memo), preserving the
    backend's diamond dedup by object identity.
    """
    from scidb.pipeline import Pipeline

    from scidb import for_each
    from scistack_gui import pipeline_store, registry
    from scistack_gui.domain.variant_resolver import (
        filter_hidden_targets,
        hidden_call_ids_for_fn,
    )

    if _built is None:
        _built = {}
    if pipeline_id in _built:
        return _built[pipeline_id]

    names = {p["pipeline_id"]: p["name"] for p in pipeline_store.list_pipelines(db)}
    pipe = Pipeline(names.get(pipeline_id, pipeline_id), db=db)
    _built[pipeline_id] = pipe

    # Steps iterate the full schema grid, like a hand-written script's
    # ``for_each(..., subject=subjects)``. Passed as EXPLICIT metadata
    # iterables (not schema_level) so a use-edge binding's ``iterate``
    # overrides compose per key instead of conflicting with schema_level
    # (for_each forbids mixing the two). Without iterables, for_each pools
    # every schema row into ONE call — functions written per-combo then
    # crash on multi-row tables (found via gui_test_data 2026-07-18).
    schema_iterables = {
        key: db.distinct_schema_values(key) for key in db.dataset_schema_keys
    }

    # Staged pending constants override DB history at compile time, so the
    # plan previews the staged variant and pull runs materialize it — same
    # helper as the eager run thread (Stage 2 of wiring-grouped plan).
    # Post-override dedup keys on (constants, output_type) — overriding can
    # collapse constant-only differences, but a multi-output fn's per-output
    # targets must all survive.
    pending_consts = pipeline_store.get_pending_constants(db)

    # Hidden combos (see plan-combo-hiding.md) — this path never passes
    # distribute/as_table to for_each (below), so filtering here must use
    # the same False/None it actually runs with, not a node's persisted
    # runOptions; a hidden pending combo hashed with a different
    # distribute/as_table simply won't match and fails safe (reappears)
    # rather than mis-hiding a different combo.
    hidden_ids = pipeline_store.get_hidden_node_ids(db)

    for node_id, fn_label in _scope_function_node_ids(db, pipeline_id):
        try:
            fn = registry.get_function(fn_label)
        except KeyError:
            logger.warning(
                "[execution] scope %s: function '%s' not in registry — skipped",
                pipeline_id,
                fn_label,
            )
            continue
        # Scoped to THIS node's own wiring (derive_target_for_node), never
        # every node/call site sharing fn_label — see
        # _scope_function_node_ids for why (same fix as the single-node
        # Run path's node_id-scoped derivation in api/run.py).
        targets = apply_pending_overrides(
            derive_target_for_node(db, node_id), pending_consts
        )
        targets = filter_hidden_targets(
            targets,
            fn_label,
            hidden_call_ids_for_fn(hidden_ids, fn_label),
            pending_consts,
            distribute=False,
            as_table=None,
        )
        seen_target_keys: set = set()
        for target in targets:
            target_key = (
                tuple(sorted(target["constants"].items())),
                target["output_type"],
            )
            if target_key in seen_target_keys:
                continue
            seen_target_keys.add(target_key)
            try:
                inputs = _build_inputs(target)
                output_cls = registry.get_variable_class(target["output_type"])
            except KeyError as exc:
                logger.warning(
                    "[execution] scope %s: '%s' target skipped (%s)",
                    pipeline_id,
                    fn_label,
                    exc,
                )
                continue
            for_each(fn, inputs, [output_cls], db=db, pipeline=pipe, **schema_iterables)

    for use in pipeline_store.get_pipeline_uses(db, pipeline_id):
        child = build_backend_pipeline(db, use["child_pipeline_id"], _built)
        binding = use.get("binding") or {}
        if binding:
            pipe.use(
                child.bind(
                    key_map=binding.get("key_map"),
                    params=binding.get("params"),
                    iterate=binding.get("iterate"),
                )
            )
        else:
            pipe.use(child)

    logger.info(
        "[execution] compiled scope %s -> pipeline '%s' (%d own step(s), %d use(s))",
        pipeline_id,
        pipe.name,
        len(pipe.steps),
        len(pipe.uses),
    )
    return pipe


def _discard_compiled(built: dict) -> None:
    """Compiled pipelines are per-request transients: drop them from
    scidb's session bookkeeping so a long-running server doesn't
    accumulate them."""
    for pipe in built.values():
        pipe.discard()


def plan_pipeline(db, pipeline_id: str, target: str = "") -> list[dict]:
    """The plan-preview data (R2): compile + plan; nothing executes.

    Entries: step, pipeline, endpoint, state (green/red/unknown), n_combos.
    Functions excluded from compilation because a required input is
    disconnected (direct) or starved by one (cascaded) still appear here —
    synthetic entries with n_combos=0 and a skip_reason — rather than
    silently vanishing from the preview.
    """
    built: dict = {}
    try:
        pipe = build_backend_pipeline(db, pipeline_id, built)
        entries = pipe.plan(target=target or None)
    finally:
        _discard_compiled(built)
    result = [
        {
            "step": e["step"],
            "pipeline": e["pipeline"],
            "endpoint": bool(e["endpoint"]),
            "state": e["state"],
            "n_combos": len(e["combos"]),
        }
        for e in entries
    ]
    planned_steps = {e["step"] for e in result}
    for skipped in disconnected_report_entries(db, pipeline_id):
        if skipped["step"] in planned_steps:
            continue
        result.append(
            {
                "step": skipped["step"],
                "pipeline": skipped["pipeline"],
                "endpoint": False,
                "state": "red",
                "n_combos": 0,
                "skip_reason": skipped["skip_reason"],
            }
        )
    return result


def run_pipeline(
    db,
    pipeline_id: str,
    mode: str = "all",
    target: str = "",
    finalized: bool | None = None,
    skip_computed: bool = True,
) -> dict:
    """Compile + execute through the backend verbs (synchronous — the run
    API wraps this in its background-thread/relay machinery).

    mode: "all" -> run_all; "until" -> run_until(target);
    "endpoints" -> run_endpoints(finalized=...); "show" -> show(target)
    (draft-run one endpoint + ancestors, zero endpoint records — the
    returned "rendered" list of paths/payloads is the ONLY handle on the
    draft outputs).
    """
    built: dict = {}
    rendered: list = []
    try:
        pipe = build_backend_pipeline(db, pipeline_id, built)
        if mode == "all":
            pipe.run_all(skip_computed=skip_computed)
        elif mode == "until":
            pipe.run_until(target, finalized=finalized, skip_computed=skip_computed)
        elif mode == "endpoints":
            pipe.run_endpoints(
                finalized=bool(finalized),
                skip_computed=skip_computed,
                include_used=True,
            )
        elif mode == "show":
            rendered = pipe.show(target, skip_computed=skip_computed)
        else:
            raise ValueError(f"unknown run mode {mode!r}")
    finally:
        _discard_compiled(built)
    # for_each never raises on iteration failures (continue-and-report),
    # so the caller decides success from the per-step report. Functions
    # excluded from compilation because a required input is disconnected
    # never reach scidb's own report — appended here instead of silently
    # vanishing from what the user sees (see disconnected_report_entries).
    report = list(pipe.last_run_report) + disconnected_report_entries(db, pipeline_id)
    return {
        "ok": True,
        "pipeline": pipe.name,
        "mode": mode,
        "report": report,
        "rendered": rendered,
    }
