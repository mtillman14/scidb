"""
Pipeline import/export between SciStack users (to-do #7,
plan-pipeline-import-export.md).

Exports one pipeline's DOCUMENT (wiring, layout, config) — recursively
including every pipeline it uses, so the result is self-contained — as a
single portable JSON file. Never exports data/records/run history: a
node's ``label`` is just a name the importing user's OWN registry resolves
locally, same as any manual node already works today. Constants/
PathInputs/Sweeps referenced by name are REUSED locally when that name
already exists there (user-confirmed decision, 2026-08-13) — the same
"shared by name" convention ``scope_service.duplicate_pipeline`` already
established for PathInput.

Deliberately NOT exported: hidden nodes/edges/combos
(``_pipeline_hidden_nodes/_edges/_combos``). All three apply exclusively
to DB-DERIVED ("graduated") wiring — content that only exists because the
exporting user already ran it locally. A freshly-imported pipeline has no
execution history in the target database, so nothing auto-derives there
yet regardless of whether a hide record is carried over — the exporting
user's past "I cut this auto-derived edge" choice isn't portable data,
it's tied to a run history that doesn't exist on the other end. Hidden
PORTS (``_pipeline_hidden_ports``) DO export: that's a pure wiring-shape
override, present the moment nodes/edges are placed, independent of any
execution history.

Import uses the same "fresh id + remap" pattern
``scope_service._clone_nodes`` already uses within one database, just
spanning a DATABASE boundary and every table that function doesn't touch
(hidden ports, globals, hypothesis tag).

**Identity-based reuse (2026-08-14, user-reported):** every pipeline in
the closure — root AND submodules, at any nesting depth — carries a
stable portable identity: its ``pipeline_id``, minted once at creation
and preserved verbatim through export/import (never regenerated), rather
than treated as a fresh-per-import id. On import, each pipeline resolves
against the LOCAL pipeline (if any) already holding that same id:
  - same id, IDENTICAL content (own nodes/edges/hidden-ports, AND
    recursively every submodule it uses) -> REUSED in place, unhidden if
    it was hidden. No new pipeline is created.
  - same id, DIFFERENT content (locally edited/diverged since export) ->
    forked: a fresh id is minted and the name is suffixed
    ("... (imported)"/"(imported 2)"/...) if it collides with any local
    name (hidden included). The existing local pipeline is untouched.
  - id not seen locally at all -> created fresh, PRESERVING the imported
    id; name is only suffixed if it collides with some other local
    pipeline's name.
Pipeline NAMES are consequently not required to be globally unique —
two different users' independently-created, same-named pipelines simply
coexist locally under distinct ids, deduplicated by suffix on display
name only. See ``_resolve_pipeline``/``_content_signature``.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

FORMAT_VERSION = 1

_PREFIX_BY_TYPE = {
    "functionNode": "fn",
    "variableNode": "var",
    "constantNode": "const",
    "pathInputNode": "pathInput",
    "sweepNode": "sweep",
}

# Node types whose label names a global (name-shared, not scope-scoped)
# definition that needs bundling alongside the wiring that references it.
_GLOBAL_NODE_TYPES = ("constantNode", "pathInputNode", "sweepNode")


def _closure_pipeline_ids(db, root_pipeline_id: str) -> list[str]:
    """``root_pipeline_id`` + every pipeline it uses, recursively (BFS) —
    so the export is self-contained regardless of nesting depth."""
    from scistack_gui import pipeline_store as ps

    seen = [root_pipeline_id]
    seen_set = {root_pipeline_id}
    i = 0
    while i < len(seen):
        pid = seen[i]
        i += 1
        for use in ps.get_pipeline_uses(db, pid):
            child = use["child_pipeline_id"]
            if child not in seen_set:
                seen_set.add(child)
                seen.append(child)
    return seen


def export_pipeline(db, pipeline_id: str) -> dict:
    """Build the portable document for ``pipeline_id`` + every pipeline it
    (transitively) uses. See module docstring for what is/isn't included."""
    from scistack_gui import layout as layout_store
    from scistack_gui import pipeline_store as ps
    from scistack_gui.services.pipeline_service import get_pipeline_graph

    pipeline_ids = _closure_pipeline_ids(db, pipeline_id)
    pipeline_id_set = set(pipeline_ids)
    names_by_id = {p["pipeline_id"]: p["name"] for p in ps.list_pipelines(db)}
    positions_by_scope = layout_store.read_positions_by_scope()

    nodes: list[dict] = []
    connectable_ids: set[str] = set()  # real node ids + pipelineNode use_ids
    referenced_names: dict[str, set[str]] = {t: set() for t in _GLOBAL_NODE_TYPES}

    graphs_by_pid: dict[str, dict] = {}
    for pid in pipeline_ids:
        graph = get_pipeline_graph(db, pid)
        graphs_by_pid[pid] = graph
        manual_nodes = ps.get_manual_nodes(db, pid)
        scope_positions = positions_by_scope.get(pid, {})
        for node in graph["nodes"]:
            nid = node["id"]
            ntype = node["type"]
            if ntype == "pipelineNode":
                connectable_ids.add(nid)  # captured via `uses` below, not `nodes`
                continue
            label = node.get("data", {}).get("label", "")
            pos = scope_positions.get(nid, {"x": 0.0, "y": 0.0})
            config = manual_nodes.get(nid, {}).get("config") or {}
            nodes.append({
                "node_id": nid,
                "pipeline_id": pid,
                "node_type": ntype,
                "label": label,
                "config": config,
                "x": pos.get("x", 0.0),
                "y": pos.get("y", 0.0),
            })
            connectable_ids.add(nid)
            if ntype in referenced_names:
                referenced_names[ntype].add(label)

    edges: list[dict] = []
    seen_edge_ids: set[str] = set()
    for pid in pipeline_ids:
        for e in graphs_by_pid[pid]["edges"]:
            eid = e["id"]
            if eid in seen_edge_ids:
                continue
            if e["source"] not in connectable_ids or e["target"] not in connectable_ids:
                continue
            seen_edge_ids.add(eid)
            edges.append({
                "edge_id": eid,
                "source": e["source"],
                "target": e["target"],
                "source_handle": e.get("sourceHandle"),
                "target_handle": e.get("targetHandle"),
            })

    uses: list[dict] = []
    for pid in pipeline_ids:
        scope_positions = positions_by_scope.get(pid, {})
        for use in ps.get_pipeline_uses(db, pid):
            if use["child_pipeline_id"] not in pipeline_id_set:
                continue  # defensive; shouldn't happen given the closure walk above
            pos = scope_positions.get(use["use_id"], {"x": 0.0, "y": 0.0})
            uses.append({
                "use_id": use["use_id"],
                "parent_pipeline_id": pid,
                "child_pipeline_id": use["child_pipeline_id"],
                "binding": use["binding"] or {},
                "x": pos.get("x", 0.0),
                "y": pos.get("y", 0.0),
            })

    hidden_ports: list[dict] = []
    for pid in pipeline_ids:
        hp = ps.get_hidden_ports(db, pid)
        for direction, var_types in hp.items():
            for var_type in var_types:
                hidden_ports.append({
                    "pipeline_id": pid, "direction": direction, "var_type": var_type,
                })

    all_pending = ps.get_pending_constants(db)
    constants = {
        name: sorted(all_pending.get(name, set()))
        for name in sorted(referenced_names["constantNode"])
    }

    all_path_inputs = {pi["name"]: pi for pi in layout_store.read_all_path_input_names()}
    path_inputs = [
        all_path_inputs[name]
        for name in sorted(referenced_names["pathInputNode"])
        if name in all_path_inputs
    ]

    all_sweeps = {sw["name"]: sw for sw in layout_store.read_all_sweep_names()}
    sweeps = [
        all_sweeps[name]
        for name in sorted(referenced_names["sweepNode"])
        if name in all_sweeps
    ]

    hypothesis = None
    hyp_by_id = {h["pipeline_id"]: h for h in ps.list_hypotheses(db)}
    if pipeline_id in hyp_by_id:
        h = hyp_by_id[pipeline_id]
        hypothesis = {
            "research_question": h["research_question"],
            "hypothesis_statement": h["hypothesis_statement"],
            "evidence_for": h["evidence_for"],
            "evidence_against": h["evidence_against"],
        }

    document = {
        "format_version": FORMAT_VERSION,
        "root_pipeline_id": pipeline_id,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "pipelines": [
            {"pipeline_id": pid, "name": names_by_id.get(pid, pid), "is_root": pid == pipeline_id}
            for pid in pipeline_ids
        ],
        "hypothesis": hypothesis,
        "nodes": nodes,
        "edges": edges,
        "uses": uses,
        "hidden_ports": hidden_ports,
        "constants": constants,
        "path_inputs": path_inputs,
        "sweeps": sweeps,
    }
    logger.info(
        "[portability] export_pipeline(%s): %d pipeline(s), %d node(s), %d edge(s), "
        "%d use(s), %d constant(s), %d path_input(s), %d sweep(s)",
        pipeline_id, len(pipeline_ids), len(nodes), len(edges), len(uses),
        len(constants), len(path_inputs), len(sweeps),
    )
    return document


EXPORT_DIRNAME = "exports"


def export_pipeline_to_file(db, pipeline_id: str) -> dict:
    """``export_pipeline`` + write the document to
    ``{project_dir}/exports/`` (mirrors ``endpoint_service.write_report``'s
    "write into the project directory, return the path" pattern) — also
    returns the document itself so the frontend can offer a browser
    download without a second round trip."""
    import json
    import re
    from pathlib import Path

    document = export_pipeline(db, pipeline_id)
    root = next(p for p in document["pipelines"] if p["is_root"])
    safe_name = re.sub(r"[^\w.-]+", "_", root["name"]).strip("_") or "pipeline"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    out_dir = Path(str(db.dataset_db_path)).resolve().parent / EXPORT_DIRNAME
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{safe_name}_{timestamp}.json"
    out_path.write_text(json.dumps(document, indent=2))

    logger.info("[portability] export written: %s", out_path)
    return {"path": str(out_path), "document": document}


def _unique_name(existing: set[str], desired: str) -> str:
    """First name not already in ``existing`` — ``desired``, or
    ``"{desired} (imported)"``, ``"{desired} (imported 2)"``, ... —
    ``create_pipeline`` requires globally-unique names."""
    if desired not in existing:
        return desired
    candidate = f"{desired} (imported)"
    n = 2
    while candidate in existing:
        candidate = f"{desired} (imported {n})"
        n += 1
    return candidate


def _canon(value) -> str:
    import json

    return json.dumps(value or {}, sort_keys=True)


def _content_signature(nodes, edges, hidden_ports, uses) -> tuple:
    """A hashable, order-independent fingerprint of one scope's OWN
    content (never recurses itself — the caller feeds it already-resolved
    child identities via ``uses``, which is what makes the comparison
    recursive overall — see ``_resolve_pipeline``).

    ``nodes``: iterable of (node_type, label, config dict).
    ``edges``: iterable of ((src_type, src_label), (tgt_type, tgt_label),
        source_handle, target_handle) — endpoints already resolved to
        canonical (type, label) pairs, not raw ids (ids are never
        comparable across a database/scope boundary).
    ``hidden_ports``: iterable of (direction, var_type).
    ``uses``: iterable of (child_identity, binding dict) — ``child_identity``
        is the RESOLVED pipeline_id the use points at (a local pid on the
        local side; the already-resolved new pid on the document side —
        see ``_resolve_pipeline``), so two uses only compare equal when
        they point at the same actual (or actually-matched) child.
    """
    nodes_sig = frozenset((t, lb, _canon(c)) for t, lb, c in nodes)
    edges_sig = frozenset((s, t, sh, th) for s, t, sh, th in edges)
    hidden_sig = frozenset(hidden_ports)
    uses_sig = frozenset((child, _canon(binding)) for child, binding in uses)
    return (nodes_sig, edges_sig, hidden_sig, uses_sig)


def _document_pipeline_signature(document: dict, old_pid: str, child_resolution: dict) -> tuple:
    """``_content_signature`` for one exported pipeline_id's OWN content,
    given its children's ALREADY-RESOLVED new pipeline_ids
    (``child_resolution``: old_child_pid -> new_pid)."""
    nodes_here = [n for n in document["nodes"] if n["pipeline_id"] == old_pid]
    node_label_by_id = {n["node_id"]: (n["node_type"], n["label"]) for n in nodes_here}
    uses_here = [u for u in document.get("uses", []) if u["parent_pipeline_id"] == old_pid]
    use_label_by_id = {
        u["use_id"]: ("pipelineNode", child_resolution[u["child_pipeline_id"]])
        for u in uses_here
    }
    label_by_id = {**node_label_by_id, **use_label_by_id}
    connectable = set(label_by_id)

    nodes = [(n["node_type"], n["label"], n.get("config") or {}) for n in nodes_here]
    edges = [
        (
            label_by_id.get(e["source"], (None, None)),
            label_by_id.get(e["target"], (None, None)),
            e.get("source_handle"),
            e.get("target_handle"),
        )
        for e in document.get("edges", [])
        if e["source"] in connectable and e["target"] in connectable
    ]
    hidden = [
        (hp["direction"], hp["var_type"])
        for hp in document.get("hidden_ports", [])
        if hp["pipeline_id"] == old_pid
    ]
    uses = [(child_resolution[u["child_pipeline_id"]], u.get("binding") or {}) for u in uses_here]
    return _content_signature(nodes, edges, hidden, uses)


def _local_pipeline_signature(db, pipeline_id: str) -> tuple:
    """``_content_signature`` for an EXISTING local pipeline's OWN
    content — the comparison target for ``_document_pipeline_signature``."""
    from scistack_gui import pipeline_store as ps
    from scistack_gui.services.pipeline_service import get_pipeline_graph

    graph = get_pipeline_graph(db, pipeline_id)
    manual_nodes = ps.get_manual_nodes(db, pipeline_id)

    nodes = []
    label_by_id: dict[str, tuple] = {}
    for node in graph["nodes"]:
        if node["type"] == "pipelineNode":
            continue
        label = node.get("data", {}).get("label", "")
        config = manual_nodes.get(node["id"], {}).get("config") or {}
        nodes.append((node["type"], label, config))
        label_by_id[node["id"]] = (node["type"], label)

    uses_here = ps.get_pipeline_uses(db, pipeline_id)
    for u in uses_here:
        label_by_id[u["use_id"]] = ("pipelineNode", u["child_pipeline_id"])

    edges = [
        (
            label_by_id.get(e["source"], (None, None)),
            label_by_id.get(e["target"], (None, None)),
            e.get("sourceHandle"),
            e.get("targetHandle"),
        )
        for e in graph["edges"]
    ]
    hp = ps.get_hidden_ports(db, pipeline_id)
    hidden = [("input", t) for t in hp["input"]] + [("output", t) for t in hp["output"]]
    uses = [(u["child_pipeline_id"], u.get("binding") or {}) for u in uses_here]
    return _content_signature(nodes, edges, hidden, uses)


def _resolve_pipeline(
    db, document: dict, old_pid: str,
    resolution: dict, reused: set, existing_names: set,
) -> str:
    """Post-order resolve ``old_pid`` -> a local pipeline_id, recursing
    into children FIRST (equality can only be judged once every child is
    already resolved — see module docstring's "Identity-based reuse").
    ``old_pid`` IS the portable identity (preserved verbatim through
    export), so resolution is a lookup by id, not by name:
      - a local pipeline already holds this id and its content
        (recursively) matches -> REUSED (unhidden if needed).
      - a local pipeline already holds this id but content diverged ->
        forked: fresh id, name suffixed on collision.
      - no local pipeline holds this id -> created fresh, PRESERVING the
        id; name suffixed only if it collides with some other pipeline.
    Memoized in ``resolution`` (also handles a submodule shared by more
    than one parent in the closure); reused old_pids are recorded into
    ``reused`` so the caller can skip re-creating their nodes/edges/uses/
    hidden-ports (they already exist, verbatim, as part of the match).
    """
    if old_pid in resolution:
        return resolution[old_pid]

    from scistack_gui import pipeline_store as ps

    name = next(p["name"] for p in document["pipelines"] if p["pipeline_id"] == old_pid)

    child_resolution: dict[str, str] = {}
    for u in document.get("uses", []):
        if u["parent_pipeline_id"] == old_pid:
            child_resolution[u["child_pipeline_id"]] = _resolve_pipeline(
                db, document, u["child_pipeline_id"], resolution, reused, existing_names
            )

    local = ps.get_pipeline(db, old_pid)
    if local is not None:
        try:
            doc_sig = _document_pipeline_signature(document, old_pid, child_resolution)
            match = doc_sig == _local_pipeline_signature(db, old_pid)
        except Exception:
            # Equality-checking must never block an import — fail safe to
            # "no match" (forks into a fresh, renamed copy, same as any
            # other content mismatch).
            logger.warning(
                "[portability] import: content comparison for '%s' (%s) failed; "
                "treating as diverged", name, old_pid, exc_info=True,
            )
            match = False
        if match:
            if local["hidden"]:
                ps.unhide_pipeline(db, old_pid)
                logger.info(
                    "[portability] import: unhiding local pipeline '%s' (%s) — "
                    "identical content", name, old_pid,
                )
            else:
                logger.info(
                    "[portability] import: reusing local pipeline '%s' (%s) — "
                    "identical content", name, old_pid,
                )
            resolution[old_pid] = old_pid
            reused.add(old_pid)
            return old_pid
        logger.info(
            "[portability] import: local pipeline '%s' (%s) has diverged content — "
            "forking a new copy", name, old_pid,
        )

    # No local match by identity (either this id is unseen locally, or it
    # IS seen but content forked, in which case old_pid is already taken
    # by the diverged local pipeline and a fresh id is required).
    new_pid = old_pid if local is None else f"pipe_{uuid.uuid4().hex[:12]}"
    new_name = _unique_name(existing_names, name)
    existing_names.add(new_name)
    created_pid = ps.create_pipeline(db, new_name, pipeline_id=new_pid)
    resolution[old_pid] = created_pid
    return created_pid


def _unresolved_labels(node_docs: list[dict]) -> list[str]:
    """function/variable labels the import placed a node for that aren't
    in the LOCAL registry yet — informational only (see module docstring:
    nothing blocks the import on this)."""
    from scidb import BaseVariable
    from scistack_gui import matlab_registry, registry

    unresolved: set[str] = set()
    for n in node_docs:
        ntype, label = n["node_type"], n["label"]
        if ntype == "functionNode":
            if label not in registry._functions and not matlab_registry.is_matlab_function(label):
                unresolved.add(label)
        elif ntype == "variableNode":
            if label not in BaseVariable._all_subclasses:
                unresolved.add(label)
    return sorted(unresolved)


def import_pipeline_document(db, document: dict) -> dict:
    """Recreate an exported document in ``db``. Pipeline ids are preserved
    as the portable identity used for reuse/fork decisions — see module
    docstring's "Identity-based reuse"; node/edge/use ids are always fresh.
    Returns ``{"ok", "pipeline_id" (the resolved root), "reused": {...},
    "unresolved_labels": [...]}``."""
    from scistack_gui import layout as layout_store
    from scistack_gui import pipeline_store as ps

    version = document.get("format_version")
    if version != FORMAT_VERSION:
        raise ValueError(f"unsupported export format_version: {version!r}")

    root_old_id = document["root_pipeline_id"]

    # Captured BEFORE any node/position writes below — read_all_constant_
    # names/read_all_path_input_names/read_all_sweep_names ALSO scan saved
    # positions for canonical const__/pathInput__/sweep__-prefixed ids as
    # a fallback discovery mechanism (same prefix scheme the fresh node
    # ids minted below use), so capturing these AFTER creating nodes would
    # make every freshly-imported name look like it "already existed
    # locally" — it would just be finding the node this same call just
    # wrote a position for.
    local_constant_names = set(layout_store.read_all_constant_names())
    local_path_input_names = {pi["name"] for pi in layout_store.read_all_path_input_names()}
    local_sweep_names = {sw["name"] for sw in layout_store.read_all_sweep_names()}

    # ALL pipelines, hidden included — matches create_pipeline's own
    # uniqueness check (pipeline_store.py), so a name suffix decided here
    # never turns out to collide with a hidden pipeline down the line.
    existing_names = {p["name"] for p in ps.list_all_pipelines(db)}
    pipeline_id_map: dict[str, str] = {}
    reused_pipelines: set[str] = set()  # old_pids reused verbatim from a local match
    new_root_pid = _resolve_pipeline(
        db, document, root_old_id, pipeline_id_map, reused_pipelines, existing_names
    )
    reused_pipeline_names = sorted(
        next(p["name"] for p in document["pipelines"] if p["pipeline_id"] == old_pid)
        for old_pid in reused_pipelines
    )
    if document.get("hypothesis"):
        h = document["hypothesis"]
        ps.tag_as_hypothesis(db, new_root_pid)
        ps.update_hypothesis(
            db, new_root_pid,
            research_question=h.get("research_question", ""),
            hypothesis_statement=h.get("hypothesis_statement", ""),
            evidence_for=h.get("evidence_for", []),
            evidence_against=h.get("evidence_against", []),
        )

    # A reused pipeline's own nodes/uses/edges/hidden-ports already exist,
    # verbatim, as part of the local match found for it — recreating them
    # would duplicate content INSIDE what's meant to be the one shared
    # pipeline. owning_pid_of resolves an edge endpoint (real node OR a
    # placed submodule/use) back to the scope it belongs to, so edges can
    # be skipped the same way.
    owning_pid_of: dict[str, str] = {n["node_id"]: n["pipeline_id"] for n in document["nodes"]}
    owning_pid_of.update(
        {u["use_id"]: u["parent_pipeline_id"] for u in document.get("uses", [])}
    )

    node_id_map: dict[str, str] = {}
    for n in document["nodes"]:
        old_pid = n["pipeline_id"]
        if old_pid in reused_pipelines:
            continue
        new_pid = pipeline_id_map.get(old_pid)
        if new_pid is None:
            continue  # defensive; every node's pipeline_id is in `pipelines`
        prefix = _PREFIX_BY_TYPE.get(n["node_type"], n["node_type"])
        new_id = f"{prefix}__{n['label']}__{uuid.uuid4().hex[:8]}"
        node_id_map[n["node_id"]] = new_id
        ps.write_manual_node(db, new_id, n["node_type"], n["label"], new_pid)
        if n.get("config"):
            ps.update_node_config(db, new_id, n["config"])
        layout_store.write_node_position(
            new_id, n.get("x", 0.0), n.get("y", 0.0), pipeline_id=new_pid
        )

    for u in document.get("uses", []):
        if u["parent_pipeline_id"] in reused_pipelines:
            continue  # already exists as part of the reused parent's own content
        new_parent = pipeline_id_map.get(u["parent_pipeline_id"])
        new_child = pipeline_id_map.get(u["child_pipeline_id"])
        if new_parent is None or new_child is None:
            logger.warning(
                "[portability] import: dropping use %r (parent/child not in this import)",
                u["use_id"],
            )
            continue
        new_use_id = ps.add_pipeline_use(db, new_parent, new_child, u.get("binding") or {})
        node_id_map[u["use_id"]] = new_use_id
        layout_store.write_node_position(
            new_use_id, u.get("x", 0.0), u.get("y", 0.0), pipeline_id=new_parent
        )

    n_edges = 0
    for e in document.get("edges", []):
        if owning_pid_of.get(e["source"]) in reused_pipelines:
            continue  # already exists as part of the reused scope's own content
        src = node_id_map.get(e["source"])
        tgt = node_id_map.get(e["target"])
        if src is None or tgt is None:
            logger.warning(
                "[portability] import: dropping edge %r -> %r (endpoint not found)",
                e["source"], e["target"],
            )
            continue
        ps.write_manual_edge(db, {
            "id": f"edge_{uuid.uuid4().hex[:12]}",
            "source": src,
            "target": tgt,
            "sourceHandle": e.get("source_handle"),
            "targetHandle": e.get("target_handle"),
        })
        n_edges += 1

    for hp in document.get("hidden_ports", []):
        if hp["pipeline_id"] in reused_pipelines:
            continue  # already exists as part of the reused scope's own content
        new_pid = pipeline_id_map.get(hp["pipeline_id"])
        if new_pid is None:
            continue
        ps.hide_port(db, new_pid, hp["direction"], hp["var_type"])

    reused_constants = []
    for name, values in document.get("constants", {}).items():
        if name in local_constant_names:
            reused_constants.append(name)
            continue
        layout_store.write_constant(name)
        for v in values:
            ps.add_pending_constant(db, name, v)

    reused_path_inputs = []
    for pi in document.get("path_inputs", []):
        if pi["name"] in local_path_input_names:
            reused_path_inputs.append(pi["name"])
            continue
        layout_store.write_path_input(pi["name"], pi.get("template", ""), pi.get("root_folder"))
        for alt in pi.get("alternate_templates", []):
            layout_store.add_path_input_alternate(
                pi["name"], alt.get("template", ""), alt.get("root_folder")
            )

    reused_sweeps = []
    for sw in document.get("sweeps", []):
        if sw["name"] in local_sweep_names:
            reused_sweeps.append(sw["name"])
            continue
        layout_store.write_sweep(sw["name"], sw.get("values", []))

    unresolved = _unresolved_labels(document["nodes"])

    logger.info(
        "[portability] import_pipeline_document: %d pipeline(s) (%d reused), %d node(s), "
        "%d edge(s) -> root=%s (reused %d constant(s), %d path_input(s), %d sweep(s); "
        "%d unresolved label(s))",
        len(pipeline_id_map), len(reused_pipelines), len(document["nodes"]), n_edges, new_root_pid,
        len(reused_constants), len(reused_path_inputs), len(reused_sweeps),
        len(unresolved),
    )
    return {
        "ok": True,
        "pipeline_id": new_root_pid,
        "reused": {
            "pipelines": reused_pipeline_names,
            "constants": reused_constants,
            "path_inputs": reused_path_inputs,
            "sweeps": reused_sweeps,
        },
        "unresolved_labels": unresolved,
    }
