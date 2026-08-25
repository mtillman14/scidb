"""
Node position and pipeline structure persistence.

Positions (x/y) are stored in a JSON file alongside the .duckdb file:
  experiment.duckdb  →  experiment.layout.json

Manual pipeline nodes and edges are stored in the DuckDB database via
pipeline_store.  The JSON file retains only positions and the migration
sentinel; all structural pipeline data lives in DuckDB.

JSON format (post-migration):
{
  "positions": { "node_id": { "x": float, "y": float }, ... },
  "pipeline_db_migrated": true
}
"""

import json
import logging
from pathlib import Path

from scistack_gui import pipeline_store
from scistack_gui.db import get_db, get_db_path

logger = logging.getLogger(__name__)


def _layout_path() -> Path:
    return get_db_path().with_suffix(".layout.json")


def _load() -> dict:
    """Load and normalise the layout file (positions only, post-migration).

    Positions are PER-SCOPE (nested pipelines): ``positions`` maps
    ``pipeline_id -> {node_id: {x, y}}``. Pre-scoping files (flat
    ``node_id -> {x, y}``) migrate under the root scope on load, marked by
    the ``positions_scoped`` flag.
    """
    p = _layout_path()
    logger.debug("[layout] Loading layout file from %s", p)
    if not p.exists():
        # Deliberately NOT a hand-maintained duplicate of the defaults set
        # below (a second "what are the defaults" list next to the
        # setdefault calls has already drifted out of sync once — missing
        # path_inputs/sweeps after their removal, and separately missing
        # "notes" entirely, both silent until a fresh/never-written project
        # hit this branch). Empty dict + fall through to the same
        # normalization every other path goes through.
        logger.debug("[layout] Layout file does not exist, using empty defaults")
        raw = {}
    else:
        with p.open() as f:
            raw = json.load(f)
    logger.debug("[layout] Loaded layout file with %d top-level keys", len(raw))
    # Migrate legacy flat format: { "node_id": {"x":..,"y":..}, ... }
    if raw and "positions" not in raw:
        logger.debug(
            "[layout] Migrating legacy flat format to nested positions structure"
        )
        raw = {"positions": raw, "constants": []}
    raw.setdefault("positions", {})
    raw.setdefault("constants", [])
    # "path_inputs"/"sweeps" keys are no longer read or written (both are
    # source-scanned now — see docs/claude/code-discovery-categories.md) but
    # are deliberately left in place if present on an old file rather than
    # popped, so a downgrade to a pre-migration build doesn't lose data.
    raw.setdefault("notes", {})
    # Migrate flat positions to per-scope: everything predating scoping
    # lived on the one canvas that is now the root pipeline.
    if not raw.get("positions_scoped"):
        logger.info(
            "[layout] scoping migration: moving %d flat position(s) "
            "under root scope '%s'",
            len(raw["positions"]),
            pipeline_store.ROOT_PIPELINE_ID,
        )
        raw["positions"] = (
            {pipeline_store.ROOT_PIPELINE_ID: raw["positions"]}
            if raw["positions"]
            else {}
        )
        raw["positions_scoped"] = True
    # One-time migration: DB-derived position keys (var__/fn__/param__/
    # pathInput__) become placement-qualified (canonical_id::scope) so the
    # SAME wiring can be independently placed in more than one scope
    # (see domain.graph_builder.placement_id). A bare id's current scope
    # bucket IS its one existing placement, so this preserves today's
    # behavior exactly for every pre-existing document.
    if not raw.get("placements_migrated"):
        from scistack_gui.domain.graph_builder import (
            PLACEMENT_SEP,
            _DB_DERIVED_PREFIXES,
            placement_id,
        )

        n_migrated = 0
        for scope, positions in raw["positions"].items():
            for node_id in list(positions.keys()):
                if PLACEMENT_SEP in node_id:
                    continue
                if not node_id.startswith(_DB_DERIVED_PREFIXES):
                    continue
                positions[placement_id(node_id, scope)] = positions.pop(node_id)
                n_migrated += 1
        raw["placements_migrated"] = True
        if n_migrated:
            logger.info(
                "[layout] placement migration: qualified %d DB-derived "
                "position(s) with their scope", n_migrated,
            )
    logger.debug(
        "[layout] Layout has %d scope(s), %d constants",
        len(raw["positions"]),
        len(raw["constants"]),
    )
    return raw


def _scope_positions(data: dict, pipeline_id: str) -> dict:
    """The (mutable) position dict for one scope, created on demand."""
    return data["positions"].setdefault(pipeline_id, {})


def _positions_all(data: dict) -> dict:
    """Merged {node_id: {x, y}} across all scopes (node ids are unique) —
    for the name-derivation helpers that scan canonical node ids."""
    merged: dict = {}
    for scope in data["positions"].values():
        merged.update(scope)
    return merged


def _save(data: dict) -> None:
    p = _layout_path()
    logger.debug("[layout] Saving layout file to %s", p)
    logger.debug(
        "[layout] Writing %d positions, %d constants",
        len(data.get("positions", {})),
        len(data.get("constants", [])),
    )
    with p.open("w") as f:
        json.dump(data, f, indent=2)
    logger.debug("[layout] Layout file saved successfully")


def read_positions_by_scope() -> dict:
    """All saved positions, scope-keyed: {pipeline_id: {node_id: {x, y}}}.

    The scope a DB-derived node's position lives in IS its scope membership
    (see domain.scope_filter.node_scope), so graph filtering reads this.
    """
    return {k: dict(v) for k, v in _load()["positions"].items()}


def drop_scope_positions(pipeline_id: str) -> None:
    """Remove a deleted scope's position map (scope teardown)."""
    data = _load()
    if data["positions"].pop(pipeline_id, None) is not None:
        _save(data)


def drop_node_positions(node_id: str) -> None:
    """Remove one node's position from every scope (position only — no
    manual-node/hide side effects, unlike delete_node)."""
    data = _load()
    changed = False
    for scope in data["positions"].values():
        changed = scope.pop(node_id, None) is not None or changed
    if changed:
        _save(data)


def move_node_position(
    node_id: str,
    new_pipeline_id: str,
    default_x: float = 0.0,
    default_y: float = 0.0,
    new_node_id: str | None = None,
) -> dict:
    """Move one node's saved position into a new scope (extract-to-submodule).

    Position IS the scope-membership record for DB-derived nodes (see
    domain.scope_filter.node_scope), so this alone re-scopes them; manual
    nodes additionally need their ``_pipeline_nodes.pipeline_id`` column
    rewritten (pipeline_store.move_node_scope), which takes priority when
    both exist. Returns the position that was moved (or the default, if the
    node had no saved position in any scope).

    ``node_id`` is placement-qualified for an already-graduated DB-derived
    node (``{canonical}::{old_scope}`` — see domain.graph_builder.
    placement_id) — its embedded scope would go STALE if the position were
    simply re-written under the same key in a new scope bucket (node_scope
    trusts that embedded suffix over which bucket holds it). Callers moving
    such a node must pass ``new_node_id`` (the re-keyed placement id for
    the destination scope); it defaults to ``node_id`` for manual nodes,
    which carry no scope in their id at all.
    """
    data = _load()
    pos = None
    for scope in data["positions"].values():
        found = scope.pop(node_id, None)
        if found is not None:
            pos = found
            break
    node_id = new_node_id or node_id
    if pos is None:
        pos = {"x": default_x, "y": default_y}
    _scope_positions(data, new_pipeline_id)[node_id] = pos
    _save(data)
    logger.info(
        "[layout] move_node_position: %r -> scope %r (%.1f, %.1f)",
        node_id, new_pipeline_id, pos["x"], pos["y"],
    )
    return pos


def read_layout(pipeline_id: str = pipeline_store.ROOT_PIPELINE_ID) -> dict:
    """Return one SCOPE's layout (positions + manual nodes from DB).

    Defaults to the root scope, which is where every pre-scoping document
    lives — existing callers see exactly what they saw before nesting.
    ``manual_edges`` is intentionally unfiltered here: DB-derived nodes'
    scope membership is graph_builder's business (service layer filters
    edges when composing a scoped canvas).
    """
    data = _load()
    db = get_db()
    return {
        "pipeline_id": pipeline_id,
        "positions": dict(_scope_positions(data, pipeline_id)),
        "manual_nodes": pipeline_store.get_manual_nodes(db, pipeline_id),
        "manual_edges": pipeline_store.get_manual_edges(db),
        "constants": data.get("constants", []),
    }


def write_node_position(
    node_id: str, x: float, y: float, pipeline_id: str = pipeline_store.ROOT_PIPELINE_ID
) -> None:
    logger.info(
        "[layout] write_node_position called (node_id=%r, x=%.1f, y=%.1f, scope=%r)",
        node_id,
        x,
        y,
        pipeline_id,
    )
    data = _load()
    logger.info("[layout] Writing position to JSON")
    _scope_positions(data, pipeline_id)[node_id] = {"x": x, "y": y}
    _save(data)
    logger.info("[layout] Node position written successfully")


def write_manual_node(
    node_id: str,
    x: float,
    y: float,
    node_type: str,
    label: str,
    pipeline_id: str = pipeline_store.ROOT_PIPELINE_ID,
) -> None:
    # Position goes to JSON; structural info goes to DB.
    logger.info(
        "[layout] write_manual_node called (node_id=%r, type=%r, label=%r, x=%.1f, y=%.1f, scope=%r)",
        node_id,
        node_type,
        label,
        x,
        y,
        pipeline_id,
    )
    logger.info("[layout] Writing position to JSON")
    data = _load()
    _scope_positions(data, pipeline_id)[node_id] = {"x": x, "y": y}
    _save(data)
    logger.info("[layout] Writing node metadata to DuckDB")
    db = get_db()
    pipeline_store.write_manual_node(db, node_id, node_type, label, pipeline_id)
    # If the user is re-adding a node that was previously hidden, unhide it
    # — scoped to THIS pipeline_id only, so re-adding a node here doesn't
    # resurrect another hypothesis pipeline's independent placement of the
    # same shared wiring (see plan-scope-hidden-nodes-edges.md).
    # Also unhide the canonical DB-derived ID for this type/label.
    logger.info(
        "[layout] Unhiding node in scope=%r (in case it was previously deleted)",
        pipeline_id,
    )
    pipeline_store.unhide_node(db, node_id, pipeline_id)
    from scistack_gui.domain.graph_builder import PARAM_ID_PREFIX

    prefix_map = {
        "variableNode": "var__",
        "functionNode": "fn__",
        "parameterNode": PARAM_ID_PREFIX,
        "pathInputNode": "pathInput__",
    }
    prefix = prefix_map.get(node_type)
    if prefix:
        logger.debug(
            "[layout] Unhiding canonical DB-derived nodes for type=%r, label=%r",
            node_type,
            label,
        )
        if node_type == "functionNode":
            # DB-derived function nodes use composite ``fn__{label}__{call_id}``
            # IDs — there can be multiple canonical nodes per label.  Unhide
            # every call-site node sharing the label.
            pipeline_store.unhide_nodes_by_prefix(db, f"fn__{label}__", pipeline_id)
            # Also unhide the legacy fn__{label} form for older layouts.
            pipeline_store.unhide_node(db, f"fn__{label}", pipeline_id)
            logger.debug("[layout] Unhid all function nodes with label=%r", label)
        else:
            canonical_id = f"{prefix}{label}"
            pipeline_store.unhide_node(db, canonical_id, pipeline_id)
            logger.debug("[layout] Unhid canonical node %r", canonical_id)
    logger.info("[layout] Manual node written successfully")


def get_manual_nodes() -> dict[str, dict]:
    return pipeline_store.get_manual_nodes(get_db())


def delete_node(node_id: str) -> None:
    """Remove a node's position (JSON) and manual-node entry (DB).

    For DB-derived nodes (var__, fn__, param__, pathInput__), also mark them
    as hidden so _build_graph won't recreate them from pipeline history.
    Hiding is scoped to the SCOPE ``node_id`` currently belongs to (resolved
    via domain.scope_filter.node_scope, the same "what scope is this node
    in" logic every other consumer trusts) — not global — so a delete in
    one pipeline never hides another pipeline's independent placement of
    the same shared wiring (graph_builder.wiring_id is scope-independent by
    design; see plan-scope-hidden-nodes-edges.md). The id is stripped to
    the bare canonical id before being stored/matched, since
    domain.graph_builder.filter_hidden checks bare prefixes.
    """
    from scistack_gui.domain.graph_builder import strip_placement
    from scistack_gui.domain.scope_filter import node_scope

    logger.info("[layout] delete_node called (node_id=%r)", node_id)
    db = get_db()
    # Resolve scope BEFORE removing the position — node_scope's fallback
    # for a bare (not placement-qualified) id scans saved positions.
    manual_nodes = pipeline_store.get_manual_nodes(db)
    positions_by_scope = read_positions_by_scope()
    scope_id = node_scope(node_id, manual_nodes, positions_by_scope)
    logger.info("[layout] Removing position from JSON")
    data = _load()
    for scope in data["positions"].values():
        scope.pop(node_id, None)
    _save(data)
    logger.info("[layout] Deleting node metadata from DuckDB")
    pipeline_store.delete_node(db, node_id)
    # Hide DB-derived nodes so they don't reappear from list_pipeline_variants().
    bare_id = strip_placement(node_id)
    logger.info(
        "[layout] Marking node as hidden in scope=%r (so it won't be auto-recreated there)",
        scope_id,
    )
    pipeline_store.hide_node(db, bare_id, scope_id)
    logger.info("[layout] Node deleted successfully")


def read_constants() -> list[str]:
    return _load()["constants"]


def read_all_constant_names() -> list[str]:
    """All Parameter names visible in the palette or already on the canvas.

    Sources (unioned):
    - ``constants[]``: palette items created via the "+" button.
    - manual Parameter nodes in DB (type ``parameterNode``).
    - Canonical DB-derived Parameter IDs in positions (``param__name``,
      possibly placement-qualified as ``param__name::{pipeline_id}``).
    """
    from scistack_gui.domain.graph_builder import PARAM_ID_PREFIX, strip_placement

    data = _load()
    names: set[str] = set(data["constants"])
    manual_nodes = pipeline_store.get_manual_nodes(get_db())
    # Manually dragged Parameter nodes — label is the true parameter name.
    for meta in manual_nodes.values():
        if meta.get("type") == "parameterNode":
            names.add(meta["label"])
    # Canonical DB-derived Parameter nodes not already covered by manual_nodes.
    for node_id in _positions_all(data):
        bare_id = strip_placement(node_id)
        if bare_id.startswith(PARAM_ID_PREFIX) and node_id not in manual_nodes:
            names.add(bare_id[len(PARAM_ID_PREFIX) :])
    return sorted(names)


def write_constant(name: str) -> None:
    data = _load()
    if name not in data["constants"]:
        data["constants"].append(name)
    _save(data)


def delete_parameter_from_palette(name: str) -> None:
    """Remove a name from the layout.json palette list. Distinct from
    layout_service.delete_parameter, which hides the NODE."""
    data = _load()
    data["constants"] = [c for c in data["constants"] if c != name]
    _save(data)


def read_notes() -> dict[str, str]:
    return dict(_load()["notes"])


def write_note(key: str, text: str) -> None:
    """Persist (or clear) one item's free-text note.

    ``key`` is ``"{kind}:{name}"`` (see api/layout.py's ``PUT /notes/{key}``)
    — e.g. ``"variable:Position"`` or ``"submodule:pipe_abc123"`` (submodules
    key by pipeline_id, which survives renames; every other kind keys by its
    registered name). An empty/whitespace-only ``text`` removes the entry
    entirely, so the file doesn't accumulate empty-string notes.
    """
    logger.info("[layout] write_note called (key=%r, len(text)=%d)", key, len(text))
    data = _load()
    stripped = text.strip()
    if stripped:
        data["notes"][key] = text
    else:
        data["notes"].pop(key, None)
    _save(data)
    logger.debug("[layout] Note written successfully (key=%r)", key)


def read_manual_edges() -> list[dict]:
    return pipeline_store.get_manual_edges(get_db())


def write_manual_edge(edge: dict) -> None:
    logger.info(
        "[layout] write_manual_edge called (edge_id=%r, source=%r, target=%r)",
        edge.get("id"),
        edge.get("source"),
        edge.get("target"),
    )
    pipeline_store.write_manual_edge(get_db(), edge)
    logger.info("[layout] Edge written to DuckDB successfully")


def delete_manual_edge(edge_id: str) -> None:
    logger.info("[layout] delete_manual_edge called (edge_id=%r)", edge_id)
    pipeline_store.delete_manual_edge(get_db(), edge_id)
    logger.info("[layout] Edge deleted from DuckDB successfully")


def add_pending_constant(const_name: str, value: str) -> None:
    logger.info(
        "[layout] add_pending_constant called (name=%r, value=%r)", const_name, value
    )
    pipeline_store.add_pending_constant(get_db(), const_name, value)
    logger.info("[layout] Pending constant added to DuckDB successfully")


def remove_pending_constant(const_name: str, value: str) -> None:
    logger.info(
        "[layout] remove_pending_constant called (name=%r, value=%r)", const_name, value
    )
    pipeline_store.remove_pending_constant(get_db(), const_name, value)
    logger.info("[layout] Pending constant removed from DuckDB successfully")


def get_pending_constants() -> dict[str, set[str]]:
    return pipeline_store.get_pending_constants(get_db())


def graduate_manual_node(old_id: str, new_id: str) -> None:
    """Transfer position from a manual node to a DB-derived node ID and
    remove the manual entry. Scope-aware: the new id stays on whichever
    canvas the old node was placed on."""
    data = _load()
    for scope in data["positions"].values():
        old_pos = scope.get(old_id)
        if old_pos and new_id not in scope:
            scope[new_id] = old_pos
        scope.pop(old_id, None)
    _save(data)
    pipeline_store.graduate_manual_node(get_db(), old_id, new_id)
