"""
Pure scope logic for nested pipelines (plan-gui-nested-pipelines.md Part A).

Three concerns, all side-effect-free:

- **Membership**: which pipeline scope a node belongs to. Manual nodes carry
  a ``pipeline_id`` in the document; DB-derived nodes (var__/fn__/const__/
  pathInput__ built from history) belong to the scope their POSITION is
  saved in — dragging a node onto a sub-pipeline's canvas writes its
  position into that scope, which IS the membership record. A node with no
  saved position anywhere defaults to the root scope.
- **Filtering**: restrict a fully-built graph to one scope (nodes by
  membership, edges by both-endpoints-kept).
- **Document interface**: a pipeline scope's ports — variable types consumed
  inside but not produced inside (inputs) and types produced inside
  (outputs) — the GUI-document mirror of scidb's ``Pipeline.interface()``,
  recursing through nested pipeline uses (acyclic by store guard).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

ROOT = "main"


def node_scope(node_id: str, manual_nodes: dict,
               positions_by_scope: dict) -> str:
    """The pipeline scope a node belongs to (see module docstring)."""
    meta = manual_nodes.get(node_id)
    if meta is not None:
        return meta.get("pipeline_id") or ROOT
    for scope_id, positions in positions_by_scope.items():
        if node_id in positions:
            return scope_id
    return ROOT


def filter_graph_to_scope(nodes: list[dict], edges: list[dict],
                          scope_id: str, manual_nodes: dict,
                          positions_by_scope: dict) -> tuple[list, list]:
    """Restrict a fully-built graph to one scope.

    Nodes keep membership per :func:`node_scope`; an edge survives when
    BOTH endpoints' scopes are this scope — judged by node_scope, not by
    kept-node membership, so a dangling manual edge (an endpoint id that
    matches no built node, e.g. a legacy ``fn__{name}`` reference) defaults
    to root and stays on the root canvas exactly as it did pre-scoping.
    """
    kept_nodes = [
        n for n in nodes
        if node_scope(n["id"], manual_nodes, positions_by_scope) == scope_id
    ]
    kept_edges = [
        e for e in edges
        if node_scope(e["source"], manual_nodes, positions_by_scope) == scope_id
        and node_scope(e["target"], manual_nodes, positions_by_scope) == scope_id
    ]
    logger.debug(
        "[scope_filter] scope %s: kept %d/%d node(s), %d/%d edge(s)",
        scope_id, len(kept_nodes), len(nodes), len(kept_edges), len(edges),
    )
    return kept_nodes, kept_edges


def _var_label(node_id: str, manual_nodes: dict) -> str | None:
    """Variable-type label for a node id, or None if not a variable node."""
    meta = manual_nodes.get(node_id)
    if meta is not None:
        return meta["label"] if meta.get("type") == "variableNode" else None
    if node_id.startswith("var__"):
        return node_id[len("var__"):]
    return None


def document_interface(scope_id: str, manual_nodes: dict, edges: list[dict],
                       uses_by_parent: dict,
                       positions_by_scope: dict | None = None,
                       _visiting: frozenset = frozenset()) -> dict:
    """A scope's ports from the DOCUMENT graph: ``{"inputs": [...],
    "outputs": [...]}`` as sorted variable-type labels.

    consumed = variable→function edges inside the scope; produced =
    function→variable edges inside the scope. Nested pipeline uses recurse:
    a child's inputs join consumed, its outputs join produced (matching how
    the composed backend graph would union). ``uses_by_parent`` maps
    ``parent_pipeline_id -> [{"use_id", "child_pipeline_id", ...}]``.
    """
    if scope_id in _visiting:  # defensive; the store rejects cycles
        return {"inputs": [], "outputs": []}
    positions_by_scope = positions_by_scope or {}

    # Scope membership: manual nodes by pipeline_id, DB-derived nodes by
    # where their position lives (same rule as node_scope).
    scope_nodes = {
        nid for nid, meta in manual_nodes.items()
        if (meta.get("pipeline_id") or ROOT) == scope_id
    }
    scope_nodes |= set(positions_by_scope.get(scope_id, {})) - set(manual_nodes)
    consumed: set[str] = set()
    produced: set[str] = set()
    for e in edges:
        src, tgt = e["source"], e["target"]
        src_label = _var_label(src, manual_nodes)
        tgt_label = _var_label(tgt, manual_nodes)
        # var -> fn (consumption): source is a variable, target in scope.
        if src_label is not None and tgt in scope_nodes:
            consumed.add(src_label)
        # fn -> var (production): target is a variable, source in scope.
        if tgt_label is not None and src in scope_nodes:
            produced.add(tgt_label)

    for use in uses_by_parent.get(scope_id, []):
        child_iface = document_interface(
            use["child_pipeline_id"], manual_nodes, edges, uses_by_parent,
            positions_by_scope, _visiting | {scope_id},
        )
        consumed.update(child_iface["inputs"])
        produced.update(child_iface["outputs"])

    return {
        "inputs": sorted(consumed - produced),
        "outputs": sorted(produced),
    }
