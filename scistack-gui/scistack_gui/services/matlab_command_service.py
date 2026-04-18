"""
MATLAB command service — generates ready-to-paste MATLAB commands.

Extracts the orchestration logic from server.py's _h_generate_matlab_command.
"""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger(__name__)


def generate_matlab_command(function_name: str, db, params: dict) -> dict:
    """Generate a ready-to-paste MATLAB command for a pipeline function.

    Args:
        function_name: Name of the pipeline function.
        db: DatabaseManager instance.
        params: Full RPC params dict (schema_filter, schema_level, etc.).

    Returns:
        {"command": str} with the MATLAB command string.
    """
    from scistack_gui.api.matlab_command import generate_matlab_command as _fmt
    from scistack_gui.db import get_db_path
    from scistack_gui import matlab_registry
    from scistack_gui import layout as layout_store
    from scistack_gui.domain.graph_builder import parse_path_input
    from scistack_gui.domain.edge_resolver import infer_manual_fn_output_types

    db_path = str(get_db_path())

    # Collect addpath directories from MATLAB config.
    addpath_dirs: list[str] = []
    if matlab_registry._config is not None:
        addpath_dirs = [str(p) for p in matlab_registry._config.matlab_addpath]

    # Prepend the sci-matlab MATLAB package directory.
    from scistack_gui.server import _find_sci_matlab_matlab_dir
    sci_matlab_dir = _find_sci_matlab_matlab_dir()
    if sci_matlab_dir:
        addpath_dirs = [sci_matlab_dir] + addpath_dirs
        logger.info("generate_matlab_command: prepended sci-matlab dir: %s", sci_matlab_dir)
    else:
        logger.warning(
            "generate_matlab_command: sci-matlab MATLAB directory not found; "
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

    # Source 2: layout manual edges — for functions not yet in the DB.
    saved_pis = {pi["name"]: pi for pi in layout_store.read_all_path_input_names()}
    for edge in layout_store.read_manual_edges():
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        th = edge.get("targetHandle", "")
        if not (src.startswith("pathInput__") and th.startswith("in__")):
            continue
        tgt_parts = tgt.split("__")
        if len(tgt_parts) < 2 or tgt_parts[0] != "fn":
            continue
        tgt_fn_name = tgt_parts[1]
        if tgt_fn_name != function_name:
            continue
        pi_name = src.split("__")[1] if len(src.split("__")) >= 2 else src[len("pathInput__"):]
        param_name = th[len("in__"):]
        if pi_name in saved_pis:
            path_input_params[param_name] = {
                "template": saved_pis[pi_name].get("template", ""),
                "root_folder": saved_pis[pi_name].get("root_folder"),
            }

    # Overlay saved templates onto DB-variant-derived PathInput params.
    for param_name, pi in path_input_params.items():
        for edge in layout_store.read_manual_edges():
            th = edge.get("targetHandle", "")
            if th == f"in__{param_name}":
                src = edge.get("source", "")
                pi_name = src.split("__")[1] if len(src.split("__")) >= 2 else ""
                if pi_name in saved_pis and saved_pis[pi_name].get("template"):
                    pi["template"] = saved_pis[pi_name]["template"]
                    pi["root_folder"] = saved_pis[pi_name].get("root_folder")

    # Infer output types from manual edges when no DB variants exist.
    output_types: list[str] = params.get("output_types") or []
    if not output_types and not fn_variants:
        manual_nodes = layout_store.get_manual_nodes()
        fn_node_ids = {f"fn__{function_name}"}
        for nid, meta in manual_nodes.items():
            if meta.get("type") == "functionNode" and meta.get("label") == function_name:
                fn_node_ids.add(nid)
        output_types = infer_manual_fn_output_types(
            fn_node_ids, layout_store.read_manual_edges(),
            manual_nodes, existing_node_labels={})
        logger.info("generate_matlab_command: inferred output_types=%s from manual edges", output_types)

    logger.info("generate_matlab_command: fn=%s, total_variants=%d, fn_variants=%d, "
                "path_input_params=%d, output_types=%s",
                function_name, len(all_variants), len(fn_variants),
                len(path_input_params), output_types)

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
        output_types=output_types if output_types else None,
    )
    logger.info("generate_matlab_command: fn=%s, command_length=%d", function_name, len(cmd))
    return {"command": cmd}
