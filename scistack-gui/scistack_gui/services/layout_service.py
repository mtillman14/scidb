"""
Layout service — single source of truth for layout CRUD operations.

Thin orchestration keeping protocol adapters from importing data access directly.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _notify_dag_updated() -> None:
    """Broadcast dag_updated after a WIRING mutation (node create/delete,
    edge create/delete) so the canvas refetches and freshly placed nodes
    get their real DB-checked state — a re-dropped, re-wired function that
    is already computed must come back GREEN, not the frontend-local red
    (user-found 2026-07-19). Deliberately NOT called for position-only
    writes: drags would trigger a full graph rebuild per drop."""
    from scistack_gui.api.ws import push_message

    push_message({"type": "dag_updated"})


def get_layout(pipeline_id: str = "main") -> dict:
    from scistack_gui import layout as layout_store

    return layout_store.read_layout(pipeline_id)


def put_layout(
    node_id: str,
    x: float,
    y: float,
    node_type: str | None = None,
    label: str | None = None,
    pipeline_id: str = "main",
) -> dict:
    from scistack_gui import layout as layout_store

    logger.info(
        "[layout_service] put_layout called (node_id=%r, type=%r, label=%r, position=(%.1f, %.1f), scope=%r)",
        node_id,
        node_type,
        label,
        x,
        y,
        pipeline_id,
    )
    if node_type and label:
        logger.info("[layout_service] Creating/updating manual node")
        if node_type == "functionNode":
            from scistack_gui import matlab_registry

            if matlab_registry.is_matlab_function(label):
                info = matlab_registry.get_matlab_function(label)
                logger.info(
                    "[layout_service] Function node placed: %r (MATLAB, n_outputs=%d, output_names=%s)",
                    label,
                    info.n_outputs,
                    info.output_names,
                )
            else:
                logger.info("[layout_service] Function node placed: %r (Python)", label)
        else:
            logger.debug(
                "[layout_service] Node added to DAG: node_id=%r, type=%r, label=%r",
                node_id,
                node_type,
                label,
            )
        layout_store.write_manual_node(
            node_id, x, y, node_type, label, pipeline_id=pipeline_id
        )
        logger.info("[layout_service] Manual node created/updated successfully")
        _notify_dag_updated()
    else:
        logger.info("[layout_service] Updating node position only (no type/label)")
        layout_store.write_node_position(node_id, x, y, pipeline_id=pipeline_id)
        logger.info("[layout_service] Node position updated successfully")
    return {"ok": True}


def delete_layout(node_id: str) -> dict:
    from scistack_gui import layout as layout_store

    logger.info("[layout_service] delete_layout called (node_id=%r)", node_id)
    layout_store.delete_node(node_id)
    logger.info("[layout_service] Node deleted successfully")
    _notify_dag_updated()
    return {"ok": True}


def put_edge(
    db,
    edge_id: str,
    source: str,
    target: str,
    source_handle: str | None = None,
    target_handle: str | None = None,
) -> dict:
    from scistack_gui import layout as layout_store
    from scistack_gui import pipeline_store
    from scistack_gui.domain.graph_builder import candidate_edge_id, find_cycle
    from scistack_gui.domain.scope_filter import node_scope

    logger.info(
        "[layout_service] put_edge called (edge_id=%r, source=%r, target=%r, source_handle=%r, target_handle=%r)",
        edge_id,
        source,
        target,
        source_handle,
        target_handle,
    )

    # If this connection recreates a previously-hidden DB-derived edge
    # (same source/target — the candidate id is deterministic, see
    # graph_builder.candidate_edge_id), unhide the ORIGINAL edge instead of
    # creating a redundant manual one. This is what makes delete+reconnect
    # idempotent: state/execution recompute fresh from the real DB history
    # under the original edge id, not a new manual-edge id. Scoped to the
    # connection's own scope (derived from its endpoints, same as
    # delete_edge below) so reconnecting in one pipeline never unhides
    # another pipeline's independent placement of the same shared wiring.
    candidate = candidate_edge_id(source, target)
    if candidate is not None:
        manual_nodes = pipeline_store.get_manual_nodes(db)
        positions_by_scope = layout_store.read_positions_by_scope()
        scope_id = node_scope(target, manual_nodes, positions_by_scope)
        if candidate in pipeline_store.get_hidden_edge_ids(db, scope_id):
            logger.info(
                "[layout_service] put_edge: reconnecting hidden DB-derived edge %r "
                "in scope=%r — unhiding instead of creating a manual edge",
                candidate,
                scope_id,
            )
            pipeline_store.unhide_edge(db, candidate, scope_id)
            _notify_dag_updated()
            return {"ok": True, "unhidden": candidate}

    # Checked against manual edges only (not the full DB-derived data-lineage
    # graph): computing that graph (domain.pipeline_service.get_pipeline_graph
    # -> api.pipeline._build_graph) has a side effect — it PERSISTS manual-node
    # graduation as part of building the response — so calling it here, before
    # this edge's wiring is fully in place, can graduate a node prematurely on
    # its still-incomplete wiring (regression found via
    # test_differently_wired_manual_node_does_not_graduate_or_show_green and
    # friends). A cycle closed purely through immutable, already-executed
    # DB-derived edges plus this one new manual edge won't be caught here —
    # it still surfaces at run time as scidb's PipelineCycleError.
    existing_edges = [e for e in layout_store.read_manual_edges() if e["id"] != edge_id]
    cycle_path = find_cycle(existing_edges, source, target)
    if cycle_path is not None:
        logger.warning(
            "[layout_service] put_edge rejected — would create a cycle: %s",
            " -> ".join(cycle_path),
        )
        raise ValueError(
            f"connecting '{source}' to '{target}' would create a dependency "
            f"cycle: {' -> '.join(cycle_path)}"
        )
    layout_store.write_manual_edge(
        {
            "id": edge_id,
            "source": source,
            "target": target,
            "sourceHandle": source_handle,
            "targetHandle": target_handle,
        }
    )
    logger.info("[layout_service] Edge created successfully")
    _notify_dag_updated()
    return {"ok": True}


def delete_edge(
    db,
    edge_id: str,
    source: str = "",
    target: str = "",
    source_handle: str | None = None,
    target_handle: str | None = None,
) -> dict:
    from scistack_gui import layout as layout_store
    from scistack_gui import pipeline_store
    from scistack_gui.domain.scope_filter import node_scope

    logger.info("[layout_service] delete_edge called (edge_id=%r)", edge_id)
    # Whether an edge is "manual" is decided by ACTUAL membership in the
    # manual-edges table, not the `manual__` id prefix — that prefix is
    # only the frontend's own naming convention for edges it creates via
    # onConnect; put_edge accepts any caller-supplied id, so a manual edge
    # can legitimately have a differently-shaped id (e.g. existing tests
    # PUT arbitrary ids like "e_del").
    is_manual = any(e["id"] == edge_id for e in layout_store.read_manual_edges())
    if is_manual:
        layout_store.delete_manual_edge(edge_id)
        logger.info("[layout_service] Manual edge hard-deleted")
    else:
        # DB-derived edge: never delete data, only hide it — build_edges
        # excludes it on every rebuild until unhide_edge (see put_edge's
        # reconnect-detection) or the restore panel brings it back. Scoped
        # to the edge's own scope (derived from its endpoints — same
        # canonical id shared by another pipeline's independent placement
        # of this wiring must stay visible there; see
        # plan-scope-hidden-nodes-edges.md).
        manual_nodes = pipeline_store.get_manual_nodes(db)
        positions_by_scope = layout_store.read_positions_by_scope()
        scope_id = (
            node_scope(target, manual_nodes, positions_by_scope)
            if target
            else node_scope(source, manual_nodes, positions_by_scope)
            if source
            else pipeline_store.ROOT_PIPELINE_ID
        )
        logger.info(
            "[layout_service] delete_edge: hiding DB-derived edge in scope=%r",
            scope_id,
        )
        pipeline_store.hide_edge(
            db, edge_id, source, target, source_handle, target_handle, scope_id
        )
        logger.info("[layout_service] DB-derived edge hidden")
    _notify_dag_updated()
    return {"ok": True}


def unhide_edge(db, edge_id: str, pipeline_id: str = "main") -> dict:
    from scistack_gui import pipeline_store

    logger.info(
        "[layout_service] unhide_edge called (edge_id=%r, pipeline_id=%r)",
        edge_id,
        pipeline_id,
    )
    pipeline_store.unhide_edge(db, edge_id, pipeline_id)
    _notify_dag_updated()
    return {"ok": True}


def get_hidden_edges(db, pipeline_id: "str | None" = None) -> dict:
    from scistack_gui import pipeline_store

    return {"edges": pipeline_store.list_hidden_edges(db, pipeline_id)}


def get_notes() -> dict[str, str]:
    from scistack_gui import layout as layout_store

    return layout_store.read_notes()


def set_note(key: str, text: str) -> dict:
    from scistack_gui import layout as layout_store

    layout_store.write_note(key, text)
    return {"ok": True}


def get_constants() -> list[str]:
    from scistack_gui import layout as layout_store

    return layout_store.read_all_constant_names()


def create_constant(name: str) -> dict:
    from scistack_gui import layout as layout_store

    logger.debug("Node created (added to palette): type=constant, name=%r", name)
    layout_store.write_constant(name)
    return {"ok": True}


def delete_constant(name: str) -> dict:
    from scistack_gui import layout as layout_store

    layout_store.delete_constant(name)
    return {"ok": True}


def get_path_inputs() -> list[dict]:
    from scistack_gui import layout as layout_store

    return layout_store.read_all_path_input_names()


def create_path_input(
    name: str, template: str = "", root_folder: str | None = None
) -> dict:
    from scistack_gui import layout as layout_store

    logger.debug(
        "Node created (added to palette): type=pathInput, name=%r, template=%r, root_folder=%r",
        name,
        template,
        root_folder,
    )
    layout_store.write_path_input(name, template, root_folder)
    return {"ok": True}


def update_path_input(
    name: str, template: str = "", root_folder: str | None = None
) -> dict:
    from scistack_gui import layout as layout_store

    logger.debug(
        "PathInput updated: name=%r, template=%r, root_folder=%r",
        name,
        template,
        root_folder,
    )
    layout_store.write_path_input(name, template, root_folder)
    return {"ok": True}


def delete_path_input(name: str) -> dict:
    from scistack_gui import layout as layout_store

    layout_store.delete_path_input(name)
    return {"ok": True}


def add_path_input_alternate(
    name: str, template: str, root_folder: str | None = None
) -> dict:
    from scistack_gui import layout as layout_store

    logger.debug(
        "PathInput alternate added: name=%r, template=%r, root_folder=%r",
        name,
        template,
        root_folder,
    )
    index = layout_store.add_path_input_alternate(name, template, root_folder)
    return {"ok": True, "index": index}


def remove_path_input_alternate(name: str, index: int) -> dict:
    from scistack_gui import layout as layout_store

    layout_store.remove_path_input_alternate(name, index)
    return {"ok": True}


def get_sweeps() -> list[dict]:
    from scistack_gui import layout as layout_store

    return layout_store.read_all_sweep_names()


def create_sweep(name: str) -> dict:
    from scistack_gui import layout as layout_store

    logger.debug("Node created (added to palette): type=sweep, name=%r", name)
    layout_store.write_sweep(name, [])
    return {"ok": True}


def update_sweep(name: str, values: "list[float | int]") -> dict:
    from scistack_gui import layout as layout_store

    logger.debug("Sweep updated: name=%r, %d value(s)", name, len(values))
    layout_store.write_sweep(name, values)
    return {"ok": True}


def delete_sweep(name: str) -> dict:
    from scistack_gui import layout as layout_store

    layout_store.delete_sweep(name)
    return {"ok": True}


def deep_copy_path_input(node_id: str) -> dict:
    """Give one PathInput node its own independent named definition —
    opt-in fork; every other placement of the original name is untouched.
    See pipeline_store's module docstring for the "shared by default"
    PathInput design this is the escape hatch for.
    """
    from scistack_gui import layout as layout_store
    from scistack_gui import pipeline_store as ps
    from scistack_gui.db import get_db
    from scistack_gui.domain.graph_builder import strip_placement
    from scistack_gui.domain.scope_filter import node_scope

    db = get_db()
    manual_nodes = ps.get_manual_nodes(db)
    meta = manual_nodes.get(node_id)
    bare_id = strip_placement(node_id)
    if meta is not None:
        if meta.get("type") != "pathInputNode":
            raise ValueError(f"'{node_id}' is not a PathInput node")
        old_name = meta["label"]
    elif bare_id.startswith("pathInput__"):
        parts = bare_id.split("__")
        old_name = parts[1] if len(parts) >= 2 else None
    else:
        old_name = None
    if not old_name:
        raise ValueError(f"'{node_id}' is not a PathInput node")

    positions_by_scope = layout_store.read_positions_by_scope()
    pipeline_id = node_scope(node_id, manual_nodes, positions_by_scope)
    pos = positions_by_scope.get(pipeline_id, {}).get(node_id, {"x": 0.0, "y": 0.0})

    new_name = layout_store.deep_copy_path_input(old_name)

    # Upsert guarantees a row exists whether or not this node was manual
    # before (a DB-derived PathInput node has no _pipeline_nodes row until
    # its first override) — position is passed through unchanged.
    layout_store.write_manual_node(
        node_id, pos["x"], pos["y"], "pathInputNode", new_name, pipeline_id=pipeline_id
    )
    return {"ok": True, "name": new_name}


def put_pending_constant(name: str, value: str) -> dict:
    from scistack_gui import layout as layout_store

    logger.info(
        "[layout_service] put_pending_constant called (name=%r, value=%r)", name, value
    )
    layout_store.add_pending_constant(name, value)
    logger.info("[layout_service] Pending constant value added successfully")
    return {"ok": True}


def delete_pending_constant(name: str, value: str) -> dict:
    from scistack_gui import layout as layout_store

    logger.info(
        "[layout_service] delete_pending_constant called (name=%r, value=%r)",
        name,
        value,
    )
    layout_store.remove_pending_constant(name, value)
    logger.info("[layout_service] Pending constant value removed successfully")
    return {"ok": True}


def put_node_config(db, node_id: str, config: dict) -> dict:
    from scistack_gui import pipeline_store

    pipeline_store.update_node_config(db, node_id, config)
    return {"ok": True}


def hide_variant_combo(
    db, function_name: str, node_id: str | None, variant_key: dict
) -> dict:
    """Hide one row of a function's constant Cartesian product — never
    deletes data, only excludes it from display and future runs."""
    from scistack_gui import pipeline_store
    from scistack_gui.domain.graph_builder import fn_node_id
    from scistack_gui.services.execution_service import resolve_combo_call_ids

    logger.info(
        "[layout_service] hide_variant_combo called (function_name=%r, "
        "node_id=%r, variant_key=%r)",
        function_name,
        node_id,
        variant_key,
    )
    call_ids = resolve_combo_call_ids(db, function_name, node_id, variant_key)
    for cid in call_ids:
        pipeline_store.hide_combo(
            db, fn_node_id(function_name, cid), function_name, variant_key
        )
    logger.info(
        "[layout_service] hide_variant_combo: hid %d call site(s)", len(call_ids)
    )
    _notify_dag_updated()
    return {"ok": True, "hidden_count": len(call_ids)}


def unhide_variant_combo(db, node_id: str) -> dict:
    from scistack_gui import pipeline_store

    logger.info("[layout_service] unhide_variant_combo called (node_id=%r)", node_id)
    pipeline_store.unhide_combo(db, node_id)
    _notify_dag_updated()
    return {"ok": True}


def get_hidden_combos(db, function_name: str) -> dict:
    from scistack_gui import pipeline_store

    return {"combos": pipeline_store.list_hidden_combos(db, function_name)}
