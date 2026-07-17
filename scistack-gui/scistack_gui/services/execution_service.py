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
    from scistack_gui import pipeline_store, registry
    from scistack_gui.api.pipeline import _fn_params_from_registry
    from scistack_gui.domain.edge_resolver import (
        infer_manual_fn_output_types,
        resolve_function_edges,
    )
    from scistack_gui.domain.graph_builder import fn_node_id

    all_variants = db.list_pipeline_variants()
    fn_variants = [v for v in all_variants
                   if v["function_name"] == function_name]

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

    manual_output_types = infer_manual_fn_output_types(
        fn_node_ids, all_edges, manual_nodes, existing_node_labels={})

    if fn_variants and manual_output_types:
        # User rewired outputs: current wiring overrides stale DB history.
        logger.info("[execution] '%s': overriding DB output types with "
                    "manual wiring %s", function_name, manual_output_types)
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
        logger.warning("[execution] '%s': no DB history and no output "
                       "wiring — no targets derivable", function_name)
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
                logger.warning("[execution] '%s': constant '%s' wired but "
                               "has no pending values", function_name, cname)

    if inferred_constants:
        const_names = sorted(inferred_constants.keys())
        targets = []
        for combo in product(*(inferred_constants[c] for c in const_names)):
            constants = dict(zip(const_names, combo))
            for out in resolved.output_types:
                targets.append({
                    "input_types": resolved.input_types,
                    "output_type": out,
                    "constants": constants,
                })
        return targets
    return [
        {"input_types": resolved.input_types, "output_type": out,
         "constants": {}}
        for out in resolved.output_types
    ]


def _build_inputs(target: dict):
    """for_each inputs dict from a derived target (types + constants)."""
    from scidb import EachOf
    from scistack_gui import registry

    inputs: dict = {}
    for param, type_names in target["input_types"].items():
        if isinstance(type_names, list):
            if len(type_names) > 1:
                inputs[param] = EachOf(
                    *(registry.get_variable_class(t) for t in type_names))
            elif type_names:
                inputs[param] = registry.get_variable_class(type_names[0])
        else:
            inputs[param] = registry.get_variable_class(type_names)
    inputs.update(target["constants"])
    return inputs


def _scope_function_labels(db, pipeline_id: str) -> list[str]:
    """Distinct function labels whose nodes live in ``pipeline_id`` —
    manual function nodes by pipeline_id, DB-derived fn__ nodes by where
    their position is saved (same membership rule as the canvas)."""
    from scistack_gui import layout as layout_store
    from scistack_gui import pipeline_store
    from scistack_gui.domain.graph_builder import parse_fn_node_id
    from scistack_gui.domain.scope_filter import node_scope

    manual_nodes = pipeline_store.get_manual_nodes(db)
    positions_by_scope = layout_store.read_positions_by_scope()

    labels: list[str] = []
    for nid, meta in manual_nodes.items():
        if meta.get("type") == "functionNode" and \
                (meta.get("pipeline_id") or "main") == pipeline_id:
            if meta["label"] not in labels:
                labels.append(meta["label"])
    for scope_id, positions in positions_by_scope.items():
        for nid in positions:
            parsed = parse_fn_node_id(nid)
            if parsed is None or nid in manual_nodes:
                continue
            if node_scope(nid, manual_nodes, positions_by_scope) == pipeline_id:
                if parsed[0] not in labels:
                    labels.append(parsed[0])
    # DB-derived fn nodes with NO saved position default to root.
    if pipeline_id == "main":
        for v in db.list_pipeline_variants():
            fn = v["function_name"]
            from scistack_gui.domain.graph_builder import fn_node_id as _fnid
            nid = _fnid(fn, v.get("call_id") or "")
            placed = any(nid in pos for pos in positions_by_scope.values())
            if not placed and fn not in labels:
                labels.append(fn)
    return labels


def build_backend_pipeline(db, pipeline_id: str,
                           _built: "dict | None" = None):
    """Compile one GUI pipeline scope into an in-session scidb.Pipeline.

    Function nodes register their derived targets as deferred steps
    (``pipeline=pipe`` — never ambient, so nothing else in the process is
    affected); use rows compose recursively with their bindings. Shared
    children compile once per request (``_built`` memo), preserving the
    backend's diamond dedup by object identity.
    """
    from scidb import for_each
    from scidb.pipeline import Pipeline
    from scistack_gui import pipeline_store, registry

    if _built is None:
        _built = {}
    if pipeline_id in _built:
        return _built[pipeline_id]

    names = {p["pipeline_id"]: p["name"]
             for p in pipeline_store.list_pipelines(db)}
    pipe = Pipeline(names.get(pipeline_id, pipeline_id), db=db)
    _built[pipeline_id] = pipe

    for fn_label in _scope_function_labels(db, pipeline_id):
        try:
            fn = registry.get_function(fn_label)
        except KeyError:
            logger.warning("[execution] scope %s: function '%s' not in "
                           "registry — skipped", pipeline_id, fn_label)
            continue
        for target in derive_fn_targets(db, fn_label):
            try:
                inputs = _build_inputs(target)
                output_cls = registry.get_variable_class(target["output_type"])
            except KeyError as exc:
                logger.warning("[execution] scope %s: '%s' target skipped "
                               "(%s)", pipeline_id, fn_label, exc)
                continue
            for_each(fn, inputs, [output_cls], db=db, pipeline=pipe,
                     schema_filter=None)

    for use in pipeline_store.get_pipeline_uses(db, pipeline_id):
        child = build_backend_pipeline(db, use["child_pipeline_id"], _built)
        binding = use.get("binding") or {}
        if binding:
            pipe.use(child.bind(
                key_map=binding.get("key_map"),
                params=binding.get("params"),
                iterate=binding.get("iterate"),
            ))
        else:
            pipe.use(child)

    logger.info("[execution] compiled scope %s -> pipeline '%s' "
                "(%d own step(s), %d use(s))",
                pipeline_id, pipe.name, len(pipe.steps), len(pipe.uses))
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
    """
    built: dict = {}
    try:
        pipe = build_backend_pipeline(db, pipeline_id, built)
        entries = pipe.plan(target=target or None)
    finally:
        _discard_compiled(built)
    return [
        {
            "step": e["step"],
            "pipeline": e["pipeline"],
            "endpoint": bool(e["endpoint"]),
            "state": e["state"],
            "n_combos": len(e["combos"]),
        }
        for e in entries
    ]


def run_pipeline(db, pipeline_id: str, mode: str = "all",
                 target: str = "", finalized: "bool | None" = None,
                 skip_computed: bool = True) -> dict:
    """Compile + execute through the backend verbs (synchronous — the run
    API wraps this in its background-thread/relay machinery).

    mode: "all" -> run_all; "until" -> run_until(target);
    "endpoints" -> run_endpoints(finalized=...).
    """
    built: dict = {}
    try:
        pipe = build_backend_pipeline(db, pipeline_id, built)
        if mode == "all":
            pipe.run_all(skip_computed=skip_computed)
        elif mode == "until":
            pipe.run_until(target, finalized=finalized,
                           skip_computed=skip_computed)
        elif mode == "endpoints":
            pipe.run_endpoints(finalized=bool(finalized),
                               skip_computed=skip_computed,
                               include_used=True)
        else:
            raise ValueError(f"unknown run mode {mode!r}")
    finally:
        _discard_compiled(built)
    return {"ok": True, "pipeline": pipe.name, "mode": mode}
