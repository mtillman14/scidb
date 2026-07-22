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
        logger.debug("[layout] Layout file does not exist, returning empty structure")
        return {
            "positions": {},
            "constants": [],
            "path_inputs": [],
            "positions_scoped": True,
        }
    with p.open() as f:
        raw = json.load(f)
    logger.debug("[layout] Loaded layout file with %d top-level keys", len(raw))
    # Migrate legacy flat format: { "node_id": {"x":..,"y":..}, ... }
    if raw and "positions" not in raw:
        logger.debug(
            "[layout] Migrating legacy flat format to nested positions structure"
        )
        raw = {"positions": raw, "constants": [], "path_inputs": []}
    raw.setdefault("positions", {})
    raw.setdefault("constants", [])
    raw.setdefault("path_inputs", [])
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
    logger.debug(
        "[layout] Layout has %d scope(s), %d constants, %d path_inputs",
        len(raw["positions"]),
        len(raw["constants"]),
        len(raw["path_inputs"]),
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
        "[layout] Writing %d positions, %d constants, %d path_inputs",
        len(data.get("positions", {})),
        len(data.get("constants", [])),
        len(data.get("path_inputs", [])),
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
    # If the user is re-adding a node that was previously hidden, unhide it.
    # Also unhide the canonical DB-derived ID for this type/label.
    logger.info("[layout] Unhiding node (in case it was previously deleted)")
    pipeline_store.unhide_node(db, node_id)
    prefix_map = {
        "variableNode": "var__",
        "functionNode": "fn__",
        "constantNode": "const__",
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
            pipeline_store.unhide_nodes_by_prefix(db, f"fn__{label}__")
            # Also unhide the legacy fn__{label} form for older layouts.
            pipeline_store.unhide_node(db, f"fn__{label}")
            logger.debug("[layout] Unhid all function nodes with label=%r", label)
        else:
            canonical_id = f"{prefix}{label}"
            pipeline_store.unhide_node(db, canonical_id)
            logger.debug("[layout] Unhid canonical node %r", canonical_id)
    logger.info("[layout] Manual node written successfully")


def get_manual_nodes() -> dict[str, dict]:
    return pipeline_store.get_manual_nodes(get_db())


def delete_node(node_id: str) -> None:
    """Remove a node's position (JSON) and manual-node entry (DB).

    For DB-derived nodes (var__, fn__, const__, pathInput__), also mark them
    as hidden so _build_graph won't recreate them from pipeline history.
    """
    logger.info("[layout] delete_node called (node_id=%r)", node_id)
    logger.info("[layout] Removing position from JSON")
    data = _load()
    for scope in data["positions"].values():
        scope.pop(node_id, None)
    _save(data)
    logger.info("[layout] Deleting node metadata from DuckDB")
    db = get_db()
    pipeline_store.delete_node(db, node_id)
    # Hide DB-derived nodes so they don't reappear from list_pipeline_variants().
    logger.info("[layout] Marking node as hidden (so it won't be auto-recreated)")
    pipeline_store.hide_node(db, node_id)
    logger.info("[layout] Node deleted successfully")


def read_constants() -> list[str]:
    return _load()["constants"]


def read_all_constant_names() -> list[str]:
    """All constant names visible in the palette or already on the canvas.

    Sources (unioned):
    - ``constants[]``: palette items created via the "+" button.
    - manual constant nodes in DB (type ``constantNode``).
    - Canonical DB-derived constant IDs in positions (``const__name``).
    """
    data = _load()
    names: set[str] = set(data["constants"])
    manual_nodes = pipeline_store.get_manual_nodes(get_db())
    # Manually dragged constant nodes — label is the true constant name.
    for meta in manual_nodes.values():
        if meta.get("type") == "constantNode":
            names.add(meta["label"])
    # Canonical DB-derived constant nodes not already covered by manual_nodes.
    for node_id in _positions_all(data):
        if node_id.startswith("const__") and node_id not in manual_nodes:
            names.add(node_id[len("const__") :])
    return sorted(names)


def write_constant(name: str) -> None:
    data = _load()
    if name not in data["constants"]:
        data["constants"].append(name)
    _save(data)


def delete_constant(name: str) -> None:
    data = _load()
    data["constants"] = [c for c in data["constants"] if c != name]
    _save(data)


def read_all_path_input_names() -> list[dict]:
    """All path inputs visible in the palette or already on the canvas.

    Sources (unioned):
    - ``path_inputs[]``: palette items created via the "+" button.
    - Canonical DB-derived pathInput IDs in positions (``pathInput__name``).
    """
    data = _load()
    by_name: dict[str, dict] = {}
    for pi in data["path_inputs"]:
        by_name[pi["name"]] = pi
    for node_id in _positions_all(data):
        if node_id.startswith("pathInput__"):
            # Node IDs are "pathInput__<name>__<random>"; extract just <name>.
            parts = node_id.split("__")
            name = parts[1] if len(parts) >= 2 else node_id[len("pathInput__") :]
            if name not in by_name:
                by_name[name] = {"name": name, "template": "", "root_folder": None}
    return sorted(by_name.values(), key=lambda p: p["name"])


def write_path_input(name: str, template: str, root_folder: str | None = None) -> None:
    data = _load()
    # Update existing or append new.
    for pi in data["path_inputs"]:
        if pi["name"] == name:
            pi["template"] = template
            pi["root_folder"] = root_folder
            _save(data)
            return
    data["path_inputs"].append(
        {"name": name, "template": template, "root_folder": root_folder}
    )
    _save(data)


def delete_path_input(name: str) -> None:
    data = _load()
    data["path_inputs"] = [p for p in data["path_inputs"] if p["name"] != name]
    _save(data)


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
