"""
MATLAB command service — generates ready-to-paste MATLAB commands.

Extracts the orchestration logic from server.py's _h_generate_matlab_command.
"""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger(__name__)


def _entities_script() -> "str | None":
    """The configured legacy ``[matlab] entities_file`` script, if any — its
    declarations have to be in scope before a generated command references
    one by name."""
    from scistack_gui import matlab_registry

    config = getattr(matlab_registry, "_config", None)
    entities = getattr(config, "matlab_entities_file", None)
    return str(entities) if entities else None


def _entities_file() -> "str | None":
    """The configured TOML ``entities_file``, if any.

    Read from the *Python* registry's config rather than
    ``matlab_registry``'s: the entities file is language-neutral now, so a
    MATLAB-only project still has one, and the two registries hold the same
    ``SciStackConfig`` anyway.
    """
    from scistack_gui import registry

    config = getattr(registry, "_config", None)
    entities = getattr(config, "entities_file", None)
    return str(entities) if entities else None


def _normalize_input_types(input_types: dict) -> "tuple[dict, list[str]]":
    """Collapse a target's ``input_types`` to the flat ``{param: type_name}``
    shape ``api.matlab_command``'s generator expects.

    ``derive_target_for_node``'s never-run fallback (``resolve_function_
    edges``) returns each param as a LIST of candidate producer types —
    even a single candidate is ``["RawSignal"]``, not ``"RawSignal"`` —
    unlike real DB-history variants, which are already flat. A one-item
    list collapses to its item; a param with 0 or >1 candidates has no
    single MATLAB-safe value (the generator has no ``EachOf(...)``
    support), so it's reported back as unresolved instead of guessing.

    Returns ``(flat_input_types, unresolved_param_names)``.
    """
    flat: dict = {}
    unresolved: list[str] = []
    for param, type_val in input_types.items():
        if isinstance(type_val, list):
            if len(type_val) == 1:
                flat[param] = type_val[0]
            else:
                unresolved.append(param)
        else:
            flat[param] = type_val
    return flat, unresolved


def _sort_inferred_by_params_order(
    inferred: list[str], params_types: list[str]
) -> list[str]:
    """Sort edge-inferred class names to match the function signature order.

    ``inferred`` contains BaseVariable class names (e.g. ``["Force_Right", "Time"]``).
    ``params_types`` contains MATLAB output parameter names in signature order
    (e.g. ``["time", "force_right"]``).  Both are normalized to lowercase with
    underscores removed before matching so that ``"Force_Right"`` matches
    ``"force_right"`` and ``"Time"`` matches ``"time"``.

    Inferred types that cannot be matched to any param name are appended at the end.
    """

    def normalize(s: str) -> str:
        return s.lower().replace("_", "")

    norm_params = [normalize(p) for p in params_types]
    norm_to_class = {normalize(c): c for c in inferred}

    ordered: list[str] = []
    used: set[str] = set()
    for norm_p in norm_params:
        cls = norm_to_class.get(norm_p)
        if cls and cls not in used:
            ordered.append(cls)
            used.add(cls)

    for cls in inferred:
        if cls not in used:
            ordered.append(cls)

    return ordered


def _fn_node_ids(function_name: str, manual_edges: list[dict], manual_nodes: dict):
    """Every canvas node id that represents *function_name* — the legacy
    ``fn__{name}`` form, manual nodes carrying it as their label, and any
    edge endpoint whose bare id is ``fn__{name}`` or ``fn__{name}__{suffix}``
    (a wiring id, a manual suffix, or either with a ``::{scope}`` placement).
    """
    from scistack_gui.domain.graph_builder import strip_placement

    prefix = f"fn__{function_name}"
    ids = {prefix}
    for nid, meta in manual_nodes.items():
        if meta.get("type") == "functionNode" and meta.get("label") == function_name:
            ids.add(nid)
    for edge in manual_edges:
        for endpoint in (edge.get("source"), edge.get("target")):
            if not endpoint or endpoint in ids:
                continue
            bare = strip_placement(endpoint)
            if bare == prefix or bare.startswith(prefix + "__"):
                ids.add(endpoint)
    return ids


def _resolve_matlab_wiring(function_name: str, manual_edges: list[dict], manual_nodes: dict):
    """``ResolvedEdges`` for *function_name*'s canvas wiring.

    The MATLAB command generators used to hand-roll this edge scan twice
    (once here per function, once in the pipeline generator), which is how
    they and the Python execution path drifted apart — they read the
    ``in__{param}`` handle to map a PathInput to the parameter it fills,
    while ``build_run_inputs`` matched by name and could not. One resolver
    now serves both (``feedback_avoid_scifor_scidb_duplication``).
    """
    from scistack_gui.domain.edge_resolver import resolve_function_edges

    return resolve_function_edges(
        fn_node_ids=_fn_node_ids(function_name, manual_edges, manual_nodes),
        manual_edges=manual_edges,
        manual_nodes=manual_nodes,
        existing_node_labels={},
    )


def _collect_sweep_params(
    function_name: str, saved_sweeps: dict, manual_edges: list[dict], manual_nodes: dict
) -> dict[str, list]:
    """``{param_name: [values]}`` for every Parameter node wired into
    *function_name*.

    Unlike PathInput, a Parameter has no DB-history representation at all —
    it always fans out to ``EachOf`` fresh at execution time, never staged as
    one recorded value (see docs/claude/code-discovery-categories.md) — so
    this only ever has ONE source (registry + edge), not the two-source
    DB-variants-then-edges resolution ``path_input_params`` needs. Shared
    between ``generate_matlab_command`` (single function) and
    ``generate_matlab_pipeline_command`` (whole pipeline, called per node).

    Keyed by parameter name, looked up by declared name — the two differ
    whenever a Parameter feeds a parameter of another name.
    """
    resolved = _resolve_matlab_wiring(function_name, manual_edges, manual_nodes)
    return {
        param_name: saved_sweeps[decl_name]
        for param_name, decl_name in resolved.parameter_params.items()
        if decl_name in saved_sweeps
    }


def _collect_edge_path_inputs(
    function_name: str, saved_pis: dict, manual_edges: list[dict], manual_nodes: dict
) -> dict[str, dict]:
    """``{param_name: {"template", "root_folder"}}`` for every PathInput node
    wired into *function_name*, resolved from the edge that names the
    parameter — never from a name coincidence."""
    resolved = _resolve_matlab_wiring(function_name, manual_edges, manual_nodes)
    return {
        param_name: {
            "template": saved_pis[decl_name].get("template", ""),
            "root_folder": saved_pis[decl_name].get("root_folder"),
        }
        for param_name, decl_name in resolved.path_input_params.items()
        if decl_name in saved_pis
    }


def generate_matlab_command(function_name: str, db, params: dict) -> dict:
    """Generate a ready-to-paste MATLAB command for a pipeline function.

    Args:
        function_name: Name of the pipeline function.
        db: DatabaseManager instance.
        params: Full RPC params dict (schema_filter, schema_level, etc.).

    Returns:
        {"command": str} with the MATLAB command string.
    """
    from scistack_gui import layout as layout_store
    from scistack_gui import matlab_registry
    from scistack_gui import registry
    from scistack_gui.api.matlab_command import generate_matlab_command as _fmt
    from scistack_gui.db import get_db_path
    from scistack_gui.domain.edge_resolver import infer_manual_fn_output_types
    from scistack_gui.domain.graph_builder import parse_path_input, path_input_display

    db_path = str(get_db_path())

    # Collect addpath directories from MATLAB config.
    addpath_dirs: list[str] = []
    if matlab_registry._config is not None:
        addpath_dirs = [str(p) for p in matlab_registry._config.matlab_addpath]

    # Prepend the scimatlab MATLAB package directory.
    from scistack_gui.server import _find_scimatlab_matlab_dir

    scimatlab_dir = _find_scimatlab_matlab_dir()
    if scimatlab_dir:
        addpath_dirs = [scimatlab_dir] + addpath_dirs
        logger.info(
            "generate_matlab_command: prepended scimatlab dir: %s", scimatlab_dir
        )
    else:
        logger.warning(
            "generate_matlab_command: scimatlab MATLAB directory not found; "
            "scihist.* / scidb.* may be unavailable in MATLAB"
        )

    # Resolve variants from DB history.
    all_variants = db.list_pipeline_variants()
    fn_variants = [v for v in all_variants if v["function_name"] == function_name]

    # Collect PathInput param mappings.
    path_input_params: dict[str, dict] = {}
    for v in fn_variants:
        for param_name, type_val in (v.get("input_types") or {}).items():
            pi = parse_path_input(str(type_val))
            if pi is not None:
                path_input_params[param_name] = pi

    # Source 2: canvas edges — for functions not yet in the DB, and as the
    # live overlay for those that are (the edge's current PathInput wins
    # over whatever template history happens to have recorded).
    saved_pis = {
        name: path_input_display(obj)
        for name, obj in registry.get_path_inputs_registry().items()
    }
    manual_edges = layout_store.read_manual_edges()
    manual_nodes = layout_store.get_manual_nodes()
    path_input_params.update(
        _collect_edge_path_inputs(function_name, saved_pis, manual_edges, manual_nodes)
    )

    # Collect Parameter mappings (registry + edges only — no DB-history
    # source, see _collect_sweep_params).
    saved_sweeps = {
        name: list(sw.alternatives)
        for name, sw in registry.get_parameters_registry().items()
    }
    sweep_params = _collect_sweep_params(
        function_name, saved_sweeps, manual_edges, manual_nodes
    )

    # Infer output types from manual edges when no DB variants exist.
    # Always prefer edge inference over params-supplied output_types for
    # functions with no DB history — the node's output_types field may contain
    # MATLAB function output parameter names (e.g. "time") rather than the
    # BaseVariable class names (e.g. "Time") for first-run MATLAB functions.
    # Edge inference gives correct class names but in arbitrary edge order; we
    # re-sort them to match the function signature order from params.
    output_types: list[str] = params.get("output_types") or []
    if not fn_variants:
        inferred = infer_manual_fn_output_types(
            _fn_node_ids(function_name, manual_edges, manual_nodes),
            manual_edges,
            manual_nodes,
            existing_node_labels={},
        )
        if inferred:
            # Re-order inferred class names to match the function parameter order
            # from params.output_types (which has the correct signature order but
            # may use lowercase MATLAB param names instead of class names).
            params_output_types = params.get("output_types") or []
            if params_output_types:
                inferred = _sort_inferred_by_params_order(inferred, params_output_types)
            logger.info(
                "generate_matlab_command: inferred output_types=%s from manual edges "
                "(overrides params output_types=%s)",
                inferred,
                output_types,
            )
            output_types = inferred
        elif not output_types:
            logger.warning(
                "generate_matlab_command: no DB variants and no edge-inferred outputs "
                "for '%s' — outputs will be empty",
                function_name,
            )

    # Resolve project root so relative PathInput templates get an explicit
    # root_folder in the generated script (MATLAB's CWD is a temp dir, so
    # CWD-relative paths would be wrong without it).
    project_root: str | None = None
    from scistack_gui import registry as _reg

    if _reg._config is not None:
        project_root = str(_reg._config.project_root)

    logger.info(
        "generate_matlab_command: fn=%s, total_variants=%d, fn_variants=%d, "
        "path_input_params=%d, output_types=%s, project_root=%s",
        function_name,
        len(all_variants),
        len(fn_variants),
        len(path_input_params),
        output_types,
        project_root,
    )

    cmd = _fmt(
        function_name=function_name,
        db_path=db_path,
        schema_keys=list(db.dataset_schema_keys),
        variants=fn_variants if fn_variants else params.get("variants"),
        schema_filter=params.get("schema_filter"),
        schema_level=params.get("schema_level"),
        addpath_dirs=addpath_dirs if addpath_dirs else None,
        python_executable=sys.executable,
        path_inputs=path_input_params if path_input_params else None,
        sweeps=sweep_params if sweep_params else None,
        output_types=output_types if output_types else None,
        project_root=project_root,
        entities_script=_entities_script(),
        entities_file=_entities_file(),
    )
    logger.info(
        "generate_matlab_command: fn=%s, command_length=%d", function_name, len(cmd)
    )
    return {"command": cmd}


def generate_matlab_pipeline_command(pipeline_id: str, db, params: dict) -> dict:
    """Generate a ready-to-paste whole-pipeline MATLAB script.

    Scopes to every MATLAB function node in ``pipeline_id`` (via
    ``execution_service._scope_function_node_ids`` +
    ``matlab_registry.is_matlab_function``), resolving each node's
    target(s) with ``execution_service.derive_target_for_node`` — the same
    per-node target derivation ``build_backend_pipeline`` uses for Python
    pipeline runs, so a MATLAB pipeline run sees identical targets to a
    Python pipeline run or a ``code_export_service`` export of the same
    scope. Python function nodes sharing the scope are excluded (a
    MATLAB-only script cannot register a Python step into the same
    in-process ``scidb.Pipeline`` the MATLAB session builds — see
    ``api.matlab_command.generate_matlab_pipeline_command``'s docstring)
    and reported back via ``warnings`` instead of silently vanishing.

    Args:
        pipeline_id: The GUI pipeline scope id.
        db: DatabaseManager instance.
        params: Full RPC params dict (``mode``, ``target``, ``finalized``,
            ``skip_computed``, ``schema_filter``, ``schema_level``).

    Returns:
        {"command": str, "warnings": list[str]}
    """
    from scistack_gui import layout as layout_store
    from scistack_gui import matlab_registry
    from scistack_gui import pipeline_store
    from scistack_gui import registry as _reg
    from scistack_gui.api.matlab_command import (
        generate_matlab_pipeline_command as _fmt,
    )
    from scistack_gui.db import get_db_path
    from scistack_gui.domain.graph_builder import parse_path_input, path_input_display
    from scistack_gui.domain.variant_resolver import (
        filter_hidden_targets,
        hidden_call_ids_for_fn,
    )
    from scistack_gui.services.execution_service import (
        _scope_function_node_ids,
        apply_pending_overrides,
        derive_target_for_node,
    )

    db_path = str(get_db_path())

    addpath_dirs: list[str] = []
    if matlab_registry._config is not None:
        addpath_dirs = [str(p) for p in matlab_registry._config.matlab_addpath]

    from scistack_gui.server import _find_scimatlab_matlab_dir

    scimatlab_dir = _find_scimatlab_matlab_dir()
    if scimatlab_dir:
        addpath_dirs = [scimatlab_dir] + addpath_dirs
        logger.info(
            "generate_matlab_pipeline_command: prepended scimatlab dir: %s",
            scimatlab_dir,
        )
    else:
        logger.warning(
            "generate_matlab_pipeline_command: scimatlab MATLAB directory not "
            "found; scihist.* / scidb.* may be unavailable in MATLAB"
        )

    project_root: str | None = None
    if _reg._config is not None:
        project_root = str(_reg._config.project_root)

    pending_consts = pipeline_store.get_pending_constants(db)
    hidden_ids = pipeline_store.get_hidden_node_ids(db)
    saved_pis = {
        name: path_input_display(obj)
        for name, obj in _reg.get_path_inputs_registry().items()
    }
    saved_sweeps = {
        name: list(sw.alternatives) for name, sw in _reg.get_parameters_registry().items()
    }
    manual_edges = layout_store.read_manual_edges()
    manual_nodes = layout_store.get_manual_nodes()

    steps: list[dict] = []
    warnings: list[str] = []
    excluded_python: set[str] = set()
    for node_id, fn_label in _scope_function_node_ids(db, pipeline_id):
        if not matlab_registry.is_matlab_function(fn_label):
            excluded_python.add(fn_label)
            continue

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
        unique_targets: list[dict] = []
        for target in targets:
            key = (tuple(sorted(target["constants"].items())), target["output_type"])
            if key in seen_target_keys:
                continue
            seen_target_keys.add(key)
            flat_input_types, unresolved = _normalize_input_types(
                target.get("input_types") or {}
            )
            if unresolved:
                warnings.append(
                    f"'{fn_label}': param(s) {sorted(unresolved)} have more "
                    "than one candidate producer type — target skipped "
                    "(MATLAB generation doesn't support EachOf-style "
                    "multi-type inputs)"
                )
                continue
            unique_targets.append({**target, "input_types": flat_input_types})

        # Path inputs for this function — same two-source resolution
        # (DB-variant input_types, then canvas edges as the live overlay) as
        # generate_matlab_command, applied per-node here.
        path_input_params: dict[str, dict] = {}
        for t in unique_targets:
            for param_name, type_val in (t.get("input_types") or {}).items():
                pi = parse_path_input(str(type_val))
                if pi is not None:
                    path_input_params[param_name] = pi
        path_input_params.update(
            _collect_edge_path_inputs(fn_label, saved_pis, manual_edges, manual_nodes)
        )

        sweep_params = _collect_sweep_params(
            fn_label, saved_sweeps, manual_edges, manual_nodes
        )

        steps.append(
            {
                "function_name": fn_label,
                "variants": unique_targets,
                "schema_filter": params.get("schema_filter"),
                "schema_level": params.get("schema_level"),
                "path_inputs": path_input_params if path_input_params else None,
                "sweeps": sweep_params if sweep_params else None,
            }
        )

    for fn_label in sorted(excluded_python):
        warnings.append(
            f"'{fn_label}' is a Python function — excluded from the MATLAB "
            "pipeline script; run it separately"
        )

    logger.info(
        "generate_matlab_pipeline_command: pipeline=%s, matlab_steps=%d, "
        "excluded_python=%d, project_root=%s",
        pipeline_id,
        len(steps),
        len(excluded_python),
        project_root,
    )

    cmd = _fmt(
        pipeline_id=pipeline_id,
        steps=steps,
        db_path=db_path,
        schema_keys=list(db.dataset_schema_keys),
        mode=params.get("mode", "all"),
        target=params.get("target", ""),
        finalized=params.get("finalized"),
        skip_computed=params.get("skip_computed", True),
        addpath_dirs=addpath_dirs if addpath_dirs else None,
        python_executable=sys.executable,
        project_root=project_root,
        entities_script=_entities_script(),
        entities_file=_entities_file(),
    )
    logger.info(
        "generate_matlab_pipeline_command: pipeline=%s, command_length=%d",
        pipeline_id,
        len(cmd),
    )
    return {"command": cmd, "warnings": warnings}
