"""
Scope service — nested-pipeline operations shared by both protocol adapters.

Wraps pipeline_store's scope/use CRUD with layout-side effects (positions
live in the JSON file per scope) and computes pipeline-node data (document
interface = ports) for the graph endpoint. Store-level ValueErrors (cycle,
root guards, unknown ids, duplicate names) pass through for the adapters to
map to protocol errors.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def list_pipelines() -> dict:
    """All scopes + all use edges — the sidebar / breadcrumb data."""
    from scistack_gui import pipeline_store as ps
    from scistack_gui.db import get_db

    db = get_db()
    return {
        "pipelines": ps.list_pipelines(db),
        "uses": ps.get_pipeline_uses(db),
    }


def create_pipeline(name: str) -> dict:
    from scistack_gui import pipeline_store as ps
    from scistack_gui.db import get_db

    pipeline_id = ps.create_pipeline(get_db(), name)
    return {"ok": True, "pipeline_id": pipeline_id, "name": name}


def rename_pipeline(pipeline_id: str, name: str) -> dict:
    from scistack_gui import pipeline_store as ps
    from scistack_gui.db import get_db

    ps.rename_pipeline(get_db(), pipeline_id, name)
    return {"ok": True}


def delete_pipeline(pipeline_id: str) -> dict:
    """Delete a scope (store guards apply) and drop its saved positions."""
    from scistack_gui import layout as layout_store
    from scistack_gui import pipeline_store as ps
    from scistack_gui.db import get_db

    ps.delete_pipeline(get_db(), pipeline_id)
    layout_store.drop_scope_positions(pipeline_id)
    return {"ok": True}


def add_pipeline_use(
    parent_pipeline_id: str,
    child_pipeline_id: str,
    binding: dict | None = None,
    x: float = 0.0,
    y: float = 0.0,
) -> dict:
    """Place a pipeline node on a parent canvas (use row + node + position)."""
    from scistack_gui import layout as layout_store
    from scistack_gui import pipeline_store as ps
    from scistack_gui.db import get_db

    use_id = ps.add_pipeline_use(
        get_db(), parent_pipeline_id, child_pipeline_id, binding
    )
    layout_store.write_node_position(use_id, x, y, pipeline_id=parent_pipeline_id)
    return {"ok": True, "use_id": use_id}


def remove_pipeline_use(use_id: str) -> dict:
    from scistack_gui import layout as layout_store
    from scistack_gui import pipeline_store as ps
    from scistack_gui.db import get_db

    ps.remove_pipeline_use(get_db(), use_id)
    layout_store.drop_node_positions(use_id)
    return {"ok": True}


def update_use_binding(use_id: str, binding: dict) -> dict:
    from scistack_gui import pipeline_store as ps
    from scistack_gui.db import get_db

    ps.update_use_binding(get_db(), use_id, binding)
    return {"ok": True}


def pipeline_interface(pipeline_id: str) -> dict:
    """A scope's ports from the document graph (see domain.scope_filter)."""
    from scistack_gui import layout as layout_store
    from scistack_gui import pipeline_store as ps
    from scistack_gui.db import get_db
    from scistack_gui.domain.scope_filter import document_interface

    db = get_db()
    manual_nodes = ps.get_manual_nodes(db)
    edges = ps.get_manual_edges(db)
    uses_by_parent: dict = {}
    for use in ps.get_pipeline_uses(db):
        uses_by_parent.setdefault(use["parent_pipeline_id"], []).append(use)
    positions_by_scope = layout_store.read_positions_by_scope()
    return document_interface(
        pipeline_id, manual_nodes, edges, uses_by_parent, positions_by_scope
    )


def build_pipeline_nodes(db, scope_id: str) -> list[dict]:
    """The pipelineNode entries for one canvas: one per use row on
    ``scope_id``, carrying the child's name, binding, and ports."""
    from scistack_gui import layout as layout_store
    from scistack_gui import pipeline_store as ps
    from scistack_gui.domain.scope_filter import document_interface

    all_uses = ps.get_pipeline_uses(db)
    uses_by_parent: dict = {}
    for use in all_uses:
        uses_by_parent.setdefault(use["parent_pipeline_id"], []).append(use)
    if not uses_by_parent.get(scope_id):
        return []

    manual_nodes = ps.get_manual_nodes(db)
    edges = ps.get_manual_edges(db)
    positions_by_scope = layout_store.read_positions_by_scope()
    names = {p["pipeline_id"]: p["name"] for p in ps.list_pipelines(db)}

    nodes = []
    for use in uses_by_parent[scope_id]:
        child_id = use["child_pipeline_id"]
        iface = document_interface(
            child_id, manual_nodes, edges, uses_by_parent, positions_by_scope
        )
        nodes.append(
            {
                "id": use["use_id"],
                "type": "pipelineNode",
                "position": {"x": 0, "y": 0},
                "data": {
                    "label": names.get(child_id, child_id),
                    "child_pipeline_id": child_id,
                    "binding": use["binding"],
                    "inputs": iface["inputs"],
                    "outputs": iface["outputs"],
                },
            }
        )
    logger.info(
        "[scope_service] built %d pipelineNode(s) for scope %s", len(nodes), scope_id
    )
    return nodes
