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
    edge_id: str,
    source: str,
    target: str,
    source_handle: str | None = None,
    target_handle: str | None = None,
) -> dict:
    from scistack_gui import layout as layout_store

    logger.info(
        "[layout_service] put_edge called (edge_id=%r, source=%r, target=%r, source_handle=%r, target_handle=%r)",
        edge_id,
        source,
        target,
        source_handle,
        target_handle,
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


def delete_edge(edge_id: str) -> dict:
    from scistack_gui import layout as layout_store

    logger.info("[layout_service] delete_edge called (edge_id=%r)", edge_id)
    layout_store.delete_manual_edge(edge_id)
    logger.info("[layout_service] Edge deleted successfully")
    _notify_dag_updated()
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
