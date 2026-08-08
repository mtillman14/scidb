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


def list_hypotheses() -> dict:
    """Hypothesis-tagged pipelines — the tab strip's data."""
    from scistack_gui import pipeline_store as ps
    from scistack_gui.db import get_db

    return {"hypotheses": ps.list_hypotheses(get_db())}


def create_hypothesis(name: str) -> dict:
    from scistack_gui import pipeline_store as ps
    from scistack_gui.db import get_db

    pipeline_id = ps.create_hypothesis(get_db(), name)
    return {"ok": True, "pipeline_id": pipeline_id, "name": name}


def update_hypothesis(
    pipeline_id: str,
    research_question: str | None = None,
    hypothesis_statement: str | None = None,
    evidence_for: list | None = None,
    evidence_against: list | None = None,
) -> dict:
    from scistack_gui import pipeline_store as ps
    from scistack_gui.db import get_db

    ps.update_hypothesis(
        get_db(),
        pipeline_id,
        research_question=research_question,
        hypothesis_statement=hypothesis_statement,
        evidence_for=evidence_for,
        evidence_against=evidence_against,
    )
    return {"ok": True}


def delete_hypothesis(pipeline_id: str) -> dict:
    """Delete a hypothesis (store guards apply) and drop its saved positions."""
    from scistack_gui import layout as layout_store
    from scistack_gui import pipeline_store as ps
    from scistack_gui.db import get_db

    ps.delete_hypothesis(get_db(), pipeline_id)
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


def extract_to_submodule(pipeline_id: str, node_ids: list[str], name: str) -> dict:
    """Select existing nodes on ``pipeline_id``'s canvas and turn them into
    a new, immediately-reusable submodule pipeline.

    This is a MOVE (the selected nodes disappear from the parent canvas),
    replaced by one pipeline node placing the new submodule at the
    selection's centroid.

    Boundary edges (exactly one endpoint moved) are deliberately left
    UNCHANGED, not deleted — ``domain.scope_filter.document_interface``
    computes a scope's ports purely from which edges touch nodes IN that
    scope, regardless of where the other endpoint lives, so the original
    edge is exactly what makes the new submodule's interface (inputs/
    outputs) compute correctly. It simply stops rendering on either
    canvas once its endpoints split across two scopes (both
    ``filter_graph_to_scope`` checks require same-scope endpoints) — which
    is fine, since the moved node no longer renders on the parent canvas
    either. What the parent canvas needs INSTEAD is a new, additional edge
    from the kept node to the placed pipeline node's port, purely for
    visual continuity (matching how a hand-built submodule is normally
    wired: variable nodes connect to `in__{type}`/`out__{type}` handles).
    A boundary edge whose kept side isn't a variable-type node has no
    expressible port and is left without a visual replacement (rare/
    unsupported wiring) — it still contributes to the interface via the
    mechanism above.
    """
    import uuid

    from scistack_gui import layout as layout_store
    from scistack_gui import pipeline_store as ps
    from scistack_gui.db import get_db
    from scistack_gui.domain.edge_resolver import node_id_to_var_label
    from scistack_gui.domain.scope_filter import node_scope

    db = get_db()
    node_id_set = set(node_ids)
    if not node_id_set:
        raise ValueError("select at least one node to extract")

    manual_nodes = ps.get_manual_nodes(db)
    positions_by_scope = layout_store.read_positions_by_scope()
    for nid in node_id_set:
        scope = node_scope(nid, manual_nodes, positions_by_scope)
        if scope != pipeline_id:
            raise ValueError(f"node '{nid}' is not on pipeline '{pipeline_id}'")

    all_edges = ps.get_manual_edges(db)

    # Classify boundary edges (exactly one endpoint moved) — see docstring
    # for why the originals are kept rather than deleted.
    new_edges: list[dict] = []  # {source, target, sourceHandle, targetHandle}
    for e in all_edges:
        src, tgt = e["source"], e["target"]
        src_moved, tgt_moved = src in node_id_set, tgt in node_id_set
        if src_moved == tgt_moved:
            continue  # both moved (internal) or neither (irrelevant) — untouched

        if src_moved:
            var_label = node_id_to_var_label(tgt, {}, manual_nodes)
            if var_label is None:
                logger.warning(
                    "[scope_service] extract_to_submodule: boundary edge "
                    "%s -> %s has no variable-type node on the kept side; "
                    "no visual replacement added", src, tgt,
                )
                continue
            new_edges.append({
                "source": "__NEW_USE__", "target": tgt,
                "sourceHandle": f"out__{var_label}", "targetHandle": e.get("targetHandle"),
            })
        else:
            var_label = node_id_to_var_label(src, {}, manual_nodes)
            if var_label is None:
                logger.warning(
                    "[scope_service] extract_to_submodule: boundary edge "
                    "%s -> %s has no variable-type node on the kept side; "
                    "no visual replacement added", src, tgt,
                )
                continue
            new_edges.append({
                "source": src, "target": "__NEW_USE__",
                "sourceHandle": e.get("sourceHandle"), "targetHandle": f"in__{var_label}",
            })

    # Centroid of the selection's CURRENT positions, for the placed node.
    parent_positions = positions_by_scope.get(pipeline_id, {})
    selected_positions = [parent_positions[n] for n in node_id_set if n in parent_positions]
    cx = sum(p["x"] for p in selected_positions) / len(selected_positions) if selected_positions else 0.0
    cy = sum(p["y"] for p in selected_positions) / len(selected_positions) if selected_positions else 0.0

    new_pid = ps.create_pipeline(db, name)

    for nid in node_id_set:
        # A selected node may itself be an existing submodule placement —
        # its rendering scope is the USE row's parent, not just its
        # _pipeline_nodes row (see move_pipeline_use_parent's docstring);
        # both must move together.
        if manual_nodes.get(nid, {}).get("type") == "pipelineNode":
            ps.move_pipeline_use_parent(db, nid, new_pid)
        ps.move_node_scope(db, nid, new_pid)
        layout_store.move_node_position(nid, new_pid)

    use_result = add_pipeline_use(pipeline_id, new_pid, None, cx, cy)
    use_id = use_result["use_id"]

    seen: set[tuple] = set()
    for spec in new_edges:
        source = use_id if spec["source"] == "__NEW_USE__" else spec["source"]
        target = use_id if spec["target"] == "__NEW_USE__" else spec["target"]
        key = (source, target, spec["sourceHandle"], spec["targetHandle"])
        if key in seen:
            continue  # de-dupe: multiple original edges collapsing onto one port
        seen.add(key)
        ps.write_manual_edge(db, {
            "id": f"edge_{uuid.uuid4().hex[:12]}",
            "source": source,
            "target": target,
            "sourceHandle": spec["sourceHandle"],
            "targetHandle": spec["targetHandle"],
        })

    logger.info(
        "[scope_service] extract_to_submodule: %d node(s) from '%s' -> new "
        "pipeline '%s' (%s), %d boundary edge(s) added for visual continuity",
        len(node_id_set), pipeline_id, name, new_pid, len(seen),
    )
    return {"ok": True, "pipeline_id": new_pid, "use_id": use_id}


def duplicate_pipeline(pipeline_id: str, new_name: str) -> dict:
    """Fork ``pipeline_id``'s own MANUAL nodes into a brand-new,
    independent pipeline the user can freely edit (e.g. "gait symmetry"
    -> "gait speed"), while keeping any placed submodule pointing at the
    SAME child pipeline — the shared submodule itself is never
    duplicated, since factoring something out as a submodule is
    precisely what makes it reusable across hypotheses.

    Deliberately does NOT touch already-executed ("graduated") DB-derived
    nodes (variable-type nodes, and function nodes matching an existing
    call site) — found via a real test failure during implementation:
    those have a single GLOBAL, scope-singular canonical identity in this
    system (``var__{Type}``, `fn__{fn}__{call_id}`` are unique document-
    wide). Creating a second manual node with the same label doesn't
    produce an independent copy — the next graph build "graduates" it by
    label match and TRANSFERS the canonical node's position to wherever
    the new manual node was placed, silently stealing it away from the
    original pipeline. So graduated content is left alone (still
    implicitly shared/global, matching "code and variables reference the
    same ground truth"); only genuinely manual (not-yet-graduated) nodes
    are safe to fork, along with PathInput nodes, whose name-identity is
    deliberately shared by reference rather than position-exclusive
    (Stage 2) — copying the node (same name) is always safe there.

    What forks is the per-node GUI config (schemaFilter/schemaLevel/
    runOptions, and eventually whereFilters) and the manual wiring, since
    each copy gets its own node_id — copying those verbatim is what makes
    the duplicate compute IDENTICALLY to the original until the user
    changes something (at which point scidb naturally creates an
    independent variant, no special handling needed).
    """
    import uuid

    from scistack_gui import layout as layout_store
    from scistack_gui import pipeline_store as ps
    from scistack_gui.db import get_db

    db = get_db()
    manual_nodes = ps.get_manual_nodes(db, pipeline_id)
    all_manual_edges = ps.get_manual_edges(db)
    old_positions = layout_store.read_positions_by_scope().get(pipeline_id, {})
    offset = 40.0
    prefix_by_type = {
        "functionNode": "fn",
        "variableNode": "var",
        "constantNode": "const",
        "pathInputNode": "pathInput",
    }

    new_pid = ps.create_pipeline(db, new_name)
    old_to_new: dict[str, str] = {}

    # Submodule placements: fresh use_id, same child_pipeline_id, binding
    # copied (the duplicate's binding becomes independently editable from
    # here on — nothing special needed, it's just a normal column value).
    for use in ps.get_pipeline_uses(db, pipeline_id):
        pos = old_positions.get(use["use_id"], {"x": 0.0, "y": 0.0})
        result = add_pipeline_use(
            new_pid, use["child_pipeline_id"], dict(use["binding"]),
            pos["x"] + offset, pos["y"] + offset,
        )
        old_to_new[use["use_id"]] = result["use_id"]

    # Everything else genuinely manual: fresh node_id + config copied
    # verbatim (pipelineNode rows are handled above via the use rows).
    for old_id, meta in manual_nodes.items():
        node_type = meta["type"]
        if node_type == "pipelineNode":
            continue
        label = meta["label"]
        prefix = prefix_by_type.get(node_type, node_type)
        new_id = f"{prefix}__{label}__{uuid.uuid4().hex[:8]}"
        old_to_new[old_id] = new_id

        ps.write_manual_node(db, new_id, node_type, label, new_pid)
        config = meta.get("config")
        if config:
            ps.update_node_config(db, new_id, config)

        pos = old_positions.get(old_id, {"x": 0.0, "y": 0.0})
        layout_store.write_node_position(new_id, pos["x"] + offset, pos["y"] + offset, pipeline_id=new_pid)

    # Internal edges: only those wholly within the duplicated (manual) set
    # — an edge touching a graduated node we deliberately left alone has
    # no duplicate endpoint to reconnect to.
    n_edges = 0
    for e in all_manual_edges:
        src, tgt = old_to_new.get(e["source"]), old_to_new.get(e["target"])
        if src is None or tgt is None:
            continue
        ps.write_manual_edge(db, {
            "id": f"edge_{uuid.uuid4().hex[:12]}",
            "source": src,
            "target": tgt,
            "sourceHandle": e.get("sourceHandle"),
            "targetHandle": e.get("targetHandle"),
        })
        n_edges += 1

    # Sanity-check: the copy must compile like any other pipeline. A
    # failure here means something in the copy was inconsistent — clean up
    # rather than leave a broken pipeline in the document.
    from scistack_gui.services.execution_service import (
        _discard_compiled,
        build_backend_pipeline,
    )

    built: dict = {}
    try:
        build_backend_pipeline(db, new_pid, built)
    except Exception as exc:
        ps.delete_pipeline(db, new_pid)
        layout_store.drop_scope_positions(new_pid)
        raise ValueError(f"duplicated pipeline failed to compile: {exc}") from exc
    finally:
        _discard_compiled(built)

    logger.info(
        "[scope_service] duplicate_pipeline: '%s' -> '%s' (%s): %d node(s), "
        "%d edge(s)",
        pipeline_id, new_name, new_pid, len(old_to_new), n_edges,
    )
    return {"ok": True, "pipeline_id": new_pid}


def duplicate_hypothesis(pipeline_id: str, new_name: str) -> dict:
    """Duplicate a hypothesis's pipeline AND tag the copy as its own
    hypothesis (see duplicate_pipeline) — used by the tab strip's
    "Duplicate" action so the result shows up as a new tab, e.g. "gait
    symmetry" -> "gait speed"."""
    from scistack_gui import pipeline_store as ps
    from scistack_gui.db import get_db

    result = duplicate_pipeline(pipeline_id, new_name)
    ps.tag_as_hypothesis(get_db(), result["pipeline_id"])
    return result


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
