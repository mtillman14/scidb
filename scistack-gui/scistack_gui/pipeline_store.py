"""
DuckDB-backed store for manually-declared pipeline nodes and edges.

Replaces the manual_nodes / manual_edges sections of the JSON layout file so
that DuckDB is the single source of truth for pipeline structure.  Node
positions (x/y) remain in the JSON file as cosmetic data only.

Tables created in the user's .duckdb file:

    _pipelines      (pipeline_id, name)
    _pipeline_nodes (node_id, node_type, label, config, pipeline_id)
    _pipeline_edges (edge_id, source, target, source_handle, target_handle)
    _pipeline_uses  (use_id, parent_pipeline_id, child_pipeline_id, binding_json)
    _hypotheses     (pipeline_id, research_question, hypothesis_statement,
                      evidence_for, evidence_against)

These tables are created lazily on first access so they are always present
regardless of whether init_db() or configure_database() was used to open the DB.

Nested pipelines (GUI stage, plan-gui-nested-pipelines.md)
----------------------------------------------------------
Every node belongs to exactly one pipeline SCOPE (``pipeline_id``); the
reserved root scope is ``main`` and always exists.  A pipeline placed as a
node on a parent canvas is one ``_pipeline_uses`` row: the canvas node's
``node_id`` IS the ``use_id`` (``node_type='pipelineNode'``), so the same
child pipeline placed twice — with different bindings = two backend
variants — is two nodes.  ``binding_json`` holds ``{key_map, params,
iterate}`` (empty = identity), mirroring scidb's ``Pipeline.bind()``.

These tables are the GUI's DOCUMENT (what the user drew) — NOT backend
spec persistence, which is deliberately unbuilt: at run time the GUI
constructs in-session ``scidb.Pipeline`` objects from this document.

Hypothesis tabs
---------------
A "hypothesis" is not a separate structure — it is a top-level pipeline
scope (a row in ``_pipelines``) tagged with a row in ``_hypotheses``
(research question, hypothesis statement, evidence for/against). The
reserved root scope (``main``) is tagged as a hypothesis too, the same as
any other — it is simply the default one, not a special "scratch" scope.
A pipeline used purely as a submodule (placed via ``_pipeline_uses`` and
never tagged) has no ``_hypotheses`` row and does not appear as a tab.

Edges carry no scope column: an edge lives in the scope of the nodes it
connects (both endpoints are always in one scope; service-level queries
filter edges via node membership).

Migration
---------
On first access (detected by the migration sentinel key in the JSON layout),
any manual_nodes and manual_edges entries in the JSON are written to the DB
and removed from the JSON.  This is a one-time, idempotent operation.
Scope columns/tables migrate in-place in ``_ensure_tables`` (ALTER +
backfill to ``main``), same pattern as the ``config`` column.
"""

import json
import logging
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

_MIGRATION_SENTINEL = "pipeline_db_migrated"

# The reserved root scope: pre-scoping documents live here after migration.
ROOT_PIPELINE_ID = "main"


def _duck(db):
    """Return the SciDuck instance from a DatabaseManager."""
    return db._duck


def _ensure_tables(db) -> None:
    """Create pipeline tables if they don't already exist."""
    _duck(db)._execute("""
        CREATE TABLE IF NOT EXISTS _pipeline_nodes (
            node_id   VARCHAR PRIMARY KEY,
            node_type VARCHAR NOT NULL,
            label     VARCHAR NOT NULL
        )
    """)
    _duck(db)._execute("""
        CREATE TABLE IF NOT EXISTS _pipeline_edges (
            edge_id       VARCHAR PRIMARY KEY,
            source        VARCHAR NOT NULL,
            target        VARCHAR NOT NULL,
            source_handle VARCHAR,
            target_handle VARCHAR
        )
    """)
    _duck(db)._execute("""
        CREATE TABLE IF NOT EXISTS _pipeline_pending_constants (
            constant_name VARCHAR NOT NULL,
            value         VARCHAR NOT NULL,
            PRIMARY KEY (constant_name, value)
        )
    """)
    _duck(db)._execute("""
        CREATE TABLE IF NOT EXISTS _pipeline_builtin_functions (
            name     VARCHAR PRIMARY KEY,
            language VARCHAR NOT NULL
        )
    """)
    _duck(db)._execute("""
        CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes (
            pipeline_id VARCHAR NOT NULL DEFAULT 'main',
            node_id     VARCHAR NOT NULL,
            PRIMARY KEY (pipeline_id, node_id)
        )
    """)
    # Scoping migration: this table originally keyed on node_id ALONE (one
    # hide record per canonical id, GLOBAL across every pipeline scope) —
    # wrong once two hypothesis pipelines can independently place the SAME
    # canonical id (graph_builder.wiring_id is scope-independent by design;
    # see plan-scope-hidden-nodes-edges.md). A single-column PK can't hold
    # one row per (scope, id), so recreate with the composite key,
    # backfilling existing rows to the root scope (their only prior
    # meaning). Self-limiting like every other ALTER migration in this
    # file: the ADD COLUMN fails (column already exists) on every call
    # after the first, including for a freshly-created table above.
    try:
        _duck(db)._execute(
            "ALTER TABLE _pipeline_hidden_nodes ADD COLUMN pipeline_id VARCHAR DEFAULT 'main'"
        )
        old_rows = _duck(db)._fetchall(
            "SELECT node_id, pipeline_id FROM _pipeline_hidden_nodes"
        )
        _duck(db)._execute("DROP TABLE _pipeline_hidden_nodes")
        _duck(db)._execute("""
            CREATE TABLE _pipeline_hidden_nodes (
                pipeline_id VARCHAR NOT NULL DEFAULT 'main',
                node_id     VARCHAR NOT NULL,
                PRIMARY KEY (pipeline_id, node_id)
            )
        """)
        for node_id, pid in old_rows:
            _duck(db)._execute(
                "INSERT INTO _pipeline_hidden_nodes (pipeline_id, node_id) "
                "VALUES (?, ?) ON CONFLICT DO NOTHING",
                [pid or ROOT_PIPELINE_ID, node_id],
            )
        logger.info(
            "[pipeline_store] scoping migration: recreated _pipeline_hidden_nodes "
            "with composite (pipeline_id, node_id) key (%d row(s) backfilled to '%s')",
            len(old_rows),
            ROOT_PIPELINE_ID,
        )
    except Exception:
        pass  # Already migrated (composite key exists), or freshly created above.
    _duck(db)._execute("""
        CREATE TABLE IF NOT EXISTS _pipeline_hidden_combos (
            node_id       VARCHAR PRIMARY KEY,
            function_name VARCHAR NOT NULL,
            variant_key   VARCHAR NOT NULL
        )
    """)
    _duck(db)._execute("""
        CREATE TABLE IF NOT EXISTS _pipeline_hidden_edges (
            pipeline_id   VARCHAR NOT NULL DEFAULT 'main',
            edge_id       VARCHAR NOT NULL,
            source        VARCHAR NOT NULL,
            target        VARCHAR NOT NULL,
            source_handle VARCHAR,
            target_handle VARCHAR,
            PRIMARY KEY (pipeline_id, edge_id)
        )
    """)
    # Same scoping migration as _pipeline_hidden_nodes above, for edges.
    try:
        _duck(db)._execute(
            "ALTER TABLE _pipeline_hidden_edges ADD COLUMN pipeline_id VARCHAR DEFAULT 'main'"
        )
        old_edge_rows = _duck(db)._fetchall(
            "SELECT edge_id, source, target, source_handle, target_handle, "
            "pipeline_id FROM _pipeline_hidden_edges"
        )
        _duck(db)._execute("DROP TABLE _pipeline_hidden_edges")
        _duck(db)._execute("""
            CREATE TABLE _pipeline_hidden_edges (
                pipeline_id   VARCHAR NOT NULL DEFAULT 'main',
                edge_id       VARCHAR NOT NULL,
                source        VARCHAR NOT NULL,
                target        VARCHAR NOT NULL,
                source_handle VARCHAR,
                target_handle VARCHAR,
                PRIMARY KEY (pipeline_id, edge_id)
            )
        """)
        for edge_id, source, target, source_handle, target_handle, pid in old_edge_rows:
            _duck(db)._execute(
                "INSERT INTO _pipeline_hidden_edges (pipeline_id, edge_id, "
                "source, target, source_handle, target_handle) "
                "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
                [pid or ROOT_PIPELINE_ID, edge_id, source, target, source_handle, target_handle],
            )
        logger.info(
            "[pipeline_store] scoping migration: recreated _pipeline_hidden_edges "
            "with composite (pipeline_id, edge_id) key (%d row(s) backfilled to '%s')",
            len(old_edge_rows),
            ROOT_PIPELINE_ID,
        )
    except Exception:
        pass  # Already migrated (composite key exists), or freshly created above.
    # Hidden subpipeline ports (to-do #9) — a scope's exposed inputs/
    # outputs are computed automatically from wiring (see
    # domain.scope_filter.document_interface); this table is a per-scope
    # manual override suppressing one type's port, toggled by right-
    # clicking a variable node inside the subpipeline's own canvas. Same
    # composite-key/scoping shape as _pipeline_hidden_edges from the start
    # (no migration needed — this table is new).
    _duck(db)._execute("""
        CREATE TABLE IF NOT EXISTS _pipeline_hidden_ports (
            pipeline_id VARCHAR NOT NULL DEFAULT 'main',
            direction   VARCHAR NOT NULL,
            var_type    VARCHAR NOT NULL,
            PRIMARY KEY (pipeline_id, direction, var_type)
        )
    """)
    # Add config column if missing (migration for existing DBs).
    try:
        _duck(db)._execute(
            "ALTER TABLE _pipeline_nodes ADD COLUMN config VARCHAR DEFAULT '{}'"
        )
    except Exception:
        pass  # Column already exists

    # --- Nested-pipeline scoping (GUI stage) ---
    _duck(db)._execute("""
        CREATE TABLE IF NOT EXISTS _pipelines (
            pipeline_id VARCHAR PRIMARY KEY,
            name        VARCHAR NOT NULL
        )
    """)
    # Hidden pipelines (never deleted, same ethos as hide_node/hide_edge):
    # migration for existing DBs.
    try:
        _duck(db)._execute(
            "ALTER TABLE _pipelines ADD COLUMN hidden BOOLEAN DEFAULT FALSE"
        )
    except Exception:
        pass  # Column already exists
    _duck(db)._execute("""
        CREATE TABLE IF NOT EXISTS _pipeline_uses (
            use_id             VARCHAR PRIMARY KEY,
            parent_pipeline_id VARCHAR NOT NULL,
            child_pipeline_id  VARCHAR NOT NULL,
            binding_json       VARCHAR DEFAULT '{}'
        )
    """)
    # The root scope always exists; pre-scoping nodes backfill into it.
    _duck(db)._execute(
        "INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?) "
        "ON CONFLICT DO NOTHING",
        [ROOT_PIPELINE_ID, ROOT_PIPELINE_ID],
    )
    try:
        _duck(db)._execute(
            f"ALTER TABLE _pipeline_nodes ADD COLUMN pipeline_id VARCHAR "
            f"DEFAULT '{ROOT_PIPELINE_ID}'"
        )
        logger.info(
            "[pipeline_store] scoping migration: added pipeline_id "
            "column to _pipeline_nodes (existing nodes -> '%s')",
            ROOT_PIPELINE_ID,
        )
    except Exception:
        pass  # Column already exists
    _duck(db)._execute(
        "UPDATE _pipeline_nodes SET pipeline_id = ? WHERE pipeline_id IS NULL",
        [ROOT_PIPELINE_ID],
    )

    # --- Hypothesis tabs (a hypothesis is a tagged top-level pipeline) ---
    _duck(db)._execute("""
        CREATE TABLE IF NOT EXISTS _hypotheses (
            pipeline_id          VARCHAR PRIMARY KEY,
            research_question    VARCHAR DEFAULT '',
            hypothesis_statement VARCHAR DEFAULT '',
            evidence_for         VARCHAR DEFAULT '[]',
            evidence_against     VARCHAR DEFAULT '[]'
        )
    """)
    # The root pipeline is the default hypothesis, tagged the same as any
    # other (one-time, idempotent — existing DBs backfill on next access).
    _duck(db)._execute(
        "INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING",
        [ROOT_PIPELINE_ID],
    )


def migrate_from_json(db, layout_path: Path) -> None:
    """One-time migration: move manual_nodes/manual_edges from JSON into DB.

    Safe to call repeatedly — checks the migration sentinel before acting.
    """
    logger.info(
        "[pipeline_store] migrate_from_json called (layout_path=%s)", layout_path
    )
    _ensure_tables(db)

    if not layout_path.exists():
        logger.debug("[pipeline_store] Layout file does not exist, skipping migration")
        return

    logger.info("[pipeline_store] Loading layout JSON file")
    with layout_path.open() as f:
        try:
            data = json.load(f)
        except Exception:
            logger.debug("[pipeline_store] Failed to parse JSON, skipping migration")
            return

    if data.get(_MIGRATION_SENTINEL):
        logger.debug(
            "[pipeline_store] Migration already completed (sentinel found), skipping"
        )
        return  # Already migrated.

    logger.info("[pipeline_store] Migrating manual_nodes and manual_edges to DuckDB")
    manual_nodes: dict = data.get("manual_nodes", {})
    manual_edges: list = data.get("manual_edges", [])
    logger.debug(
        "[pipeline_store] Found %d manual nodes and %d manual edges in JSON",
        len(manual_nodes),
        len(manual_edges),
    )

    migrated_nodes = 0
    for node_id, meta in manual_nodes.items():
        node_type = meta.get("type", "")
        label = meta.get("label", "")
        if node_type and label:
            _upsert_node(db, node_id, node_type, label)
            migrated_nodes += 1

    migrated_edges = 0
    for edge in manual_edges:
        edge_id = edge.get("id", "")
        if edge_id:
            _upsert_edge(
                db,
                edge_id,
                edge.get("source", ""),
                edge.get("target", ""),
                edge.get("sourceHandle"),
                edge.get("targetHandle"),
            )
            migrated_edges += 1

    logger.info(
        "[pipeline_store] Writing migration sentinel to JSON and removing migrated data"
    )
    # Clear migrated keys from JSON and write sentinel.
    data.pop("manual_nodes", None)
    data.pop("manual_edges", None)
    data[_MIGRATION_SENTINEL] = True
    with layout_path.open("w") as f:
        json.dump(data, f, indent=2)

    logger.info(
        "[pipeline_store] Migration complete - migrated %d nodes and %d edges from JSON to DuckDB",
        migrated_nodes,
        migrated_edges,
    )


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


def get_manual_nodes(db, pipeline_id: "str | None" = None) -> dict[str, dict]:
    """Return {node_id: {"type", "label", "pipeline_id"[, "config"]}}.

    ``pipeline_id=None`` returns ALL scopes (pre-scoping behavior — every
    existing caller keeps working); pass a scope to filter to one canvas.
    """
    _ensure_tables(db)
    if pipeline_id is None:
        rows = _duck(db)._fetchall(
            "SELECT node_id, node_type, label, config, pipeline_id FROM _pipeline_nodes"
        )
    else:
        rows = _duck(db)._fetchall(
            "SELECT node_id, node_type, label, config, pipeline_id "
            "FROM _pipeline_nodes WHERE pipeline_id = ?",
            [pipeline_id],
        )
    result = {}
    for row in rows:
        entry: dict = {
            "type": row[1],
            "label": row[2],
            "pipeline_id": row[4] or ROOT_PIPELINE_ID,
        }
        if row[3] and row[3] != "{}":
            try:
                entry["config"] = json.loads(row[3])
            except (json.JSONDecodeError, TypeError):
                pass
        result[row[0]] = entry
    return result


def write_builtin_function(db, name: str, language: str) -> None:
    """Persist a manually-declared built-in/library function reference
    (e.g. ``numpy.mean``, MATLAB ``mean``) so it survives registry
    refreshes and server restarts — unlike file-based functions, there's
    no source file on disk to rediscover it from."""
    logger.info(
        "[pipeline_store] write_builtin_function called (name=%r, language=%r)",
        name,
        language,
    )
    _ensure_tables(db)
    _duck(db)._execute(
        "INSERT INTO _pipeline_builtin_functions (name, language) VALUES (?, ?) "
        "ON CONFLICT (name) DO UPDATE SET language = excluded.language",
        [name, language],
    )


def get_builtin_functions(db) -> list[dict]:
    """Return every persisted built-in/library function reference as
    ``[{"name": ..., "language": ...}, ...]``."""
    _ensure_tables(db)
    rows = _duck(db)._fetchall("SELECT name, language FROM _pipeline_builtin_functions")
    return [{"name": row[0], "language": row[1]} for row in rows]


def write_manual_node(
    db, node_id: str, node_type: str, label: str, pipeline_id: str = ROOT_PIPELINE_ID
) -> None:
    logger.info(
        "[pipeline_store] write_manual_node called (node_id=%r, type=%r, "
        "label=%r, pipeline_id=%r)",
        node_id,
        node_type,
        label,
        pipeline_id,
    )
    _ensure_tables(db)
    logger.info("[pipeline_store] Upserting node into _pipeline_nodes table")
    _upsert_node(db, node_id, node_type, label, pipeline_id)
    logger.info("[pipeline_store] Node written to DuckDB successfully")


def update_node_config(db, node_id: str, config: dict) -> None:
    """Update just the config JSON for an existing node."""
    _ensure_tables(db)
    _duck(db)._execute(
        "UPDATE _pipeline_nodes SET config = ? WHERE node_id = ?",
        [json.dumps(config), node_id],
    )


def delete_node(db, node_id: str) -> None:
    logger.info("[pipeline_store] delete_node called (node_id=%r)", node_id)
    _duck(db)._execute("DELETE FROM _pipeline_nodes WHERE node_id = ?", [node_id])
    logger.info("[pipeline_store] Node deleted from _pipeline_nodes table")


def move_pipeline_use_parent(db, use_id: str, new_parent_pipeline_id: str) -> None:
    """Move an existing pipeline-node PLACEMENT to a new parent scope
    (extract-to-submodule regrouping a selection that includes one).

    A placed pipeline node's rendering scope is ``_pipeline_uses.
    parent_pipeline_id`` (see api/pipeline.py's ``_build_graph`` docstring
    — pipelineNode entries come from ``scope_service.build_pipeline_nodes``,
    driven by this column), NOT its ``_pipeline_nodes.pipeline_id`` — the
    two must move together (pair with move_node_scope) or the node ends up
    inconsistent: present in the new scope's node list but still rendered
    as a use of the old parent.
    """
    _duck(db)._execute(
        "UPDATE _pipeline_uses SET parent_pipeline_id = ? WHERE use_id = ?",
        [new_parent_pipeline_id, use_id],
    )


def move_node_scope(db, node_id: str, new_pipeline_id: str) -> None:
    """Move an existing node's scope (extract-to-submodule).

    A no-op if ``node_id`` has no ``_pipeline_nodes`` row (a pure
    DB-derived node whose scope is entirely position-based — the caller
    also moves its saved position, which is what actually re-scopes it).
    """
    _duck(db)._execute(
        "UPDATE _pipeline_nodes SET pipeline_id = ? WHERE node_id = ?",
        [new_pipeline_id, node_id],
    )


def rename_edge_endpoints(db, old_id: str, new_id: str) -> None:
    """Rewrite any manual edges referencing old_id to point to new_id
    instead of becoming dangling — shared by graduation and by re-keying
    an already-placement-qualified node moved to a new scope (extraction).
    """
    _duck(db)._execute(
        "UPDATE _pipeline_edges SET source = ? WHERE source = ?",
        [new_id, old_id],
    )
    _duck(db)._execute(
        "UPDATE _pipeline_edges SET target = ? WHERE target = ?",
        [new_id, old_id],
    )


def graduate_manual_node(db, old_id: str, new_id: str) -> None:
    """Remove the manual node entry for old_id (the DB-derived node takes over).

    Also rewrites any manual edges that reference old_id so they point to
    new_id instead of becoming dangling.
    """
    _duck(db)._execute("DELETE FROM _pipeline_nodes WHERE node_id = ?", [old_id])
    rename_edge_endpoints(db, old_id, new_id)


# ---------------------------------------------------------------------------
# Edges
# ---------------------------------------------------------------------------


def get_manual_edges(db) -> list[dict]:
    """Return all manual edges as a list of dicts."""
    _ensure_tables(db)
    rows = _duck(db)._fetchall(
        "SELECT edge_id, source, target, source_handle, target_handle "
        "FROM _pipeline_edges"
    )
    result = []
    for edge_id, source, target, source_handle, target_handle in rows:
        entry: dict = {"id": edge_id, "source": source, "target": target}
        if source_handle is not None:
            entry["sourceHandle"] = source_handle
        if target_handle is not None:
            entry["targetHandle"] = target_handle
        result.append(entry)
    return result


def write_manual_edge(db, edge: dict) -> None:
    logger.info(
        "[pipeline_store] write_manual_edge called (edge_id=%r, source=%r, target=%r, source_handle=%r, target_handle=%r)",
        edge.get("id"),
        edge.get("source"),
        edge.get("target"),
        edge.get("sourceHandle") or edge.get("source_handle"),
        edge.get("targetHandle") or edge.get("target_handle"),
    )
    _ensure_tables(db)
    logger.info("[pipeline_store] Upserting edge into _pipeline_edges table")
    _upsert_edge(
        db,
        edge["id"],
        edge.get("source", ""),
        edge.get("target", ""),
        edge.get("sourceHandle") or edge.get("source_handle"),
        edge.get("targetHandle") or edge.get("target_handle"),
    )
    logger.info("[pipeline_store] Edge written to DuckDB successfully")


def delete_manual_edge(db, edge_id: str) -> None:
    logger.info("[pipeline_store] delete_manual_edge called (edge_id=%r)", edge_id)
    _duck(db)._execute("DELETE FROM _pipeline_edges WHERE edge_id = ?", [edge_id])
    logger.info("[pipeline_store] Edge deleted from _pipeline_edges table")


# ---------------------------------------------------------------------------
# Pending constants
# ---------------------------------------------------------------------------


def add_pending_constant(db, const_name: str, value: str) -> None:
    logger.info(
        "[pipeline_store] add_pending_constant called (const_name=%r, value=%r)",
        const_name,
        value,
    )
    _ensure_tables(db)
    logger.info(
        "[pipeline_store] Inserting pending constant into _pipeline_pending_constants table"
    )
    _duck(db)._execute(
        "INSERT INTO _pipeline_pending_constants (constant_name, value) VALUES (?, ?) "
        "ON CONFLICT DO NOTHING",
        [const_name, value],
    )
    logger.info("[pipeline_store] Pending constant added successfully")


def remove_pending_constant(db, const_name: str, value: str) -> None:
    logger.info(
        "[pipeline_store] remove_pending_constant called (const_name=%r, value=%r)",
        const_name,
        value,
    )
    _duck(db)._execute(
        "DELETE FROM _pipeline_pending_constants WHERE constant_name = ? AND value = ?",
        [const_name, value],
    )
    logger.info(
        "[pipeline_store] Pending constant removed from _pipeline_pending_constants table"
    )


def get_pending_constants(db) -> dict[str, set[str]]:
    """Return {constant_name: {value, ...}} for all pending constant values."""
    _ensure_tables(db)
    rows = _duck(db)._fetchall(
        "SELECT constant_name, value FROM _pipeline_pending_constants"
    )
    result: dict[str, set[str]] = {}
    for const_name, value in rows:
        result.setdefault(const_name, set()).add(value)
    return result


# ---------------------------------------------------------------------------
# Pipelines (nested-pipeline scopes)
# ---------------------------------------------------------------------------


def list_pipelines(db) -> list[dict]:
    """All VISIBLE pipeline scopes: [{"pipeline_id", "name"}], root first.
    Hidden pipelines (see hide_pipeline) are excluded — use
    list_hidden_pipelines for those."""
    _ensure_tables(db)
    rows = _duck(db)._fetchall(
        "SELECT pipeline_id, name FROM _pipelines WHERE NOT hidden "
        "ORDER BY (pipeline_id != ?), name",
        [ROOT_PIPELINE_ID],
    )
    return [{"pipeline_id": r[0], "name": r[1]} for r in rows]


def list_all_pipelines(db) -> list[dict]:
    """Every pipeline scope regardless of hidden state:
    [{"pipeline_id", "name", "hidden"}], root first. Used where a name
    collision must be avoided against hidden pipelines too (see
    ``list_pipelines``'s docstring and ``create_pipeline``'s uniqueness
    check, which already does this)."""
    _ensure_tables(db)
    rows = _duck(db)._fetchall(
        "SELECT pipeline_id, name, hidden FROM _pipelines "
        "ORDER BY (pipeline_id != ?), name",
        [ROOT_PIPELINE_ID],
    )
    return [{"pipeline_id": r[0], "name": r[1], "hidden": bool(r[2])} for r in rows]


def get_pipeline(db, pipeline_id: str) -> "dict | None":
    """Single pipeline scope by id, regardless of hidden state —
    {"pipeline_id", "name", "hidden"}, or None if no such pipeline
    exists locally."""
    _ensure_tables(db)
    rows = _duck(db)._fetchall(
        "SELECT pipeline_id, name, hidden FROM _pipelines WHERE pipeline_id = ?",
        [pipeline_id],
    )
    if not rows:
        return None
    r = rows[0]
    return {"pipeline_id": r[0], "name": r[1], "hidden": bool(r[2])}


def create_pipeline(db, name: str, pipeline_id: "str | None" = None) -> str:
    """Create a new (empty) pipeline scope; returns its pipeline_id.

    ``pipeline_id``: explicit id to use instead of minting a fresh one —
    used by pipeline import to PRESERVE a document's portable identity
    (see ``portability_service._resolve_pipeline``) rather than always
    generating a new one. Defaults to minting fresh, as before.
    """
    _ensure_tables(db)
    name = str(name).strip()
    if not name:
        raise ValueError("pipeline name must be non-empty")
    # Uniqueness is checked against ALL pipelines, hidden included — two
    # pipelines sharing a name would be confusing the moment either is
    # unhidden, even if only one is visible right now.
    existing = {
        r[0] for r in _duck(db)._fetchall("SELECT name FROM _pipelines")
    }
    if name in existing:
        raise ValueError(f"a pipeline named '{name}' already exists")
    pipeline_id = pipeline_id or f"pipe_{uuid.uuid4().hex[:12]}"
    _duck(db)._execute(
        "INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?)",
        [pipeline_id, name],
    )
    logger.info("[pipeline_store] create_pipeline: '%s' -> %s", name, pipeline_id)
    return pipeline_id


def rename_pipeline(db, pipeline_id: str, name: str) -> None:
    """Rename any pipeline scope, including the root — 'main' is just the
    default hypothesis, not a special scratch scope (see module docstring)."""
    _ensure_tables(db)
    name = str(name).strip()
    if not name:
        raise ValueError("pipeline name must be non-empty")
    _duck(db)._execute(
        "UPDATE _pipelines SET name = ? WHERE pipeline_id = ?",
        [name, pipeline_id],
    )
    # Pipeline-node labels on parent canvases display the child's name.
    _duck(db)._execute(
        "UPDATE _pipeline_nodes SET label = ? WHERE node_id IN "
        "(SELECT use_id FROM _pipeline_uses WHERE child_pipeline_id = ?)",
        [name, pipeline_id],
    )


def _hard_delete_pipeline(db, pipeline_id: str) -> None:
    """Internal-only, REAL delete of a pipeline scope and its contents.

    Not the user-facing "delete" operation (see hide_pipeline for that —
    per project ethos, user-facing removal never deletes data). This exists
    only to roll back a pipeline that never became valid, e.g.
    duplicate_pipeline's post-copy compile-sanity-check failure: there is no
    user-visible content to preserve, so a real delete is correct here.
    """
    _ensure_tables(db)
    node_rows = _duck(db)._fetchall(
        "SELECT node_id FROM _pipeline_nodes WHERE pipeline_id = ?",
        [pipeline_id],
    )
    node_ids = [r[0] for r in node_rows]
    for nid in node_ids:
        _duck(db)._execute(
            "DELETE FROM _pipeline_edges WHERE source = ? OR target = ?",
            [nid, nid],
        )
    _duck(db)._execute(
        "DELETE FROM _pipeline_nodes WHERE pipeline_id = ?", [pipeline_id]
    )
    _duck(db)._execute(
        "DELETE FROM _pipeline_uses WHERE parent_pipeline_id = ?", [pipeline_id]
    )
    _duck(db)._execute("DELETE FROM _pipelines WHERE pipeline_id = ?", [pipeline_id])
    logger.info(
        "[pipeline_store] _hard_delete_pipeline: %s (%d node(s) removed)",
        pipeline_id,
        len(node_ids),
    )


def hide_pipeline(db, pipeline_id: str) -> None:
    """Hide a pipeline scope (user-facing "delete") without touching its
    contents — never delete data, per project ethos (see hide_node/
    hide_edge/hide_combo for the same pattern at node/edge granularity).

    Refuses any pipeline still placed on another canvas (remove those
    pipeline nodes first — fail fast beats a canvas silently pointing at
    invisible content) and refuses to hide the last remaining VISIBLE
    pipeline — 'main' has no special protection beyond that; it is simply
    the default hypothesis (see module docstring). Positions are left
    intact so unhide_pipeline fully restores the canvas.
    """
    _ensure_tables(db)
    consumers = _duck(db)._fetchall(
        "SELECT p.name FROM _pipeline_uses u JOIN _pipelines p "
        "ON p.pipeline_id = u.parent_pipeline_id WHERE u.child_pipeline_id = ?",
        [pipeline_id],
    )
    if consumers:
        names = sorted({r[0] for r in consumers})
        raise ValueError(
            f"pipeline is still used by {names} — remove those pipeline nodes first"
        )
    visible_count = _duck(db)._fetchall(
        "SELECT COUNT(*) FROM _pipelines WHERE NOT hidden"
    )[0][0]
    if visible_count <= 1:
        raise ValueError("cannot hide the last remaining pipeline")
    _duck(db)._execute(
        "UPDATE _pipelines SET hidden = TRUE WHERE pipeline_id = ?", [pipeline_id]
    )
    logger.info("[pipeline_store] hide_pipeline: %s", pipeline_id)


def unhide_pipeline(db, pipeline_id: str) -> None:
    _ensure_tables(db)
    _duck(db)._execute(
        "UPDATE _pipelines SET hidden = FALSE WHERE pipeline_id = ?", [pipeline_id]
    )
    logger.info("[pipeline_store] unhide_pipeline: %s", pipeline_id)


def list_hidden_pipelines(db) -> list[dict]:
    """Hidden pipelines: [{"pipeline_id", "name", "is_hypothesis"}] — the
    restore panel's data (both the hypothesis-tab strip and the plain
    Submodules list draw from this same set)."""
    _ensure_tables(db)
    rows = _duck(db)._fetchall(
        "SELECT p.pipeline_id, p.name, h.pipeline_id IS NOT NULL "
        "FROM _pipelines p LEFT JOIN _hypotheses h ON h.pipeline_id = p.pipeline_id "
        "WHERE p.hidden ORDER BY p.name"
    )
    return [
        {"pipeline_id": r[0], "name": r[1], "is_hypothesis": bool(r[2])}
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Pipeline uses (pipeline-as-node edges between scopes)
# ---------------------------------------------------------------------------


def _uses_reachable(db, start_id: str) -> set:
    """Pipeline ids reachable from start_id through _pipeline_uses edges."""
    reachable: set = set()
    frontier = [start_id]
    while frontier:
        current = frontier.pop()
        rows = _duck(db)._fetchall(
            "SELECT child_pipeline_id FROM _pipeline_uses WHERE parent_pipeline_id = ?",
            [current],
        )
        for (child,) in rows:
            if child not in reachable:
                reachable.add(child)
                frontier.append(child)
    return reachable


def add_pipeline_use(
    db, parent_pipeline_id: str, child_pipeline_id: str, binding: "dict | None" = None
) -> str:
    """Place ``child`` as a pipeline NODE on ``parent``'s canvas.

    One _pipeline_uses row + one canvas node whose node_id IS the use_id
    (same child twice = two nodes; bindings live on the use edge — G1).
    Rejects cycles at creation (mirrors scidb's PipelineCycleError).
    Returns the use_id.
    """
    _ensure_tables(db)
    known = {p["pipeline_id"] for p in list_pipelines(db)}
    for pid in (parent_pipeline_id, child_pipeline_id):
        if pid not in known:
            raise ValueError(f"unknown pipeline_id '{pid}'")
    if child_pipeline_id == parent_pipeline_id or parent_pipeline_id in _uses_reachable(
        db, child_pipeline_id
    ):
        raise ValueError(
            f"placing this pipeline would create a dependency cycle "
            f"('{child_pipeline_id}' already reaches '{parent_pipeline_id}')"
        )
    use_id = f"use_{uuid.uuid4().hex[:12]}"
    _duck(db)._execute(
        "INSERT INTO _pipeline_uses "
        "(use_id, parent_pipeline_id, child_pipeline_id, binding_json) "
        "VALUES (?, ?, ?, ?)",
        [use_id, parent_pipeline_id, child_pipeline_id, json.dumps(binding or {})],
    )
    child_name = next(
        p["name"] for p in list_pipelines(db) if p["pipeline_id"] == child_pipeline_id
    )
    _upsert_node(db, use_id, "pipelineNode", child_name, parent_pipeline_id)
    logger.info(
        "[pipeline_store] add_pipeline_use: '%s' placed on '%s' "
        "(use_id=%s, binding=%s)",
        child_pipeline_id,
        parent_pipeline_id,
        use_id,
        binding or {},
    )
    return use_id


def remove_pipeline_use(db, use_id: str) -> None:
    """Remove a pipeline node: the use row, its canvas node, its edges."""
    _ensure_tables(db)
    _duck(db)._execute("DELETE FROM _pipeline_uses WHERE use_id = ?", [use_id])
    _duck(db)._execute("DELETE FROM _pipeline_nodes WHERE node_id = ?", [use_id])
    _duck(db)._execute(
        "DELETE FROM _pipeline_edges WHERE source = ? OR target = ?",
        [use_id, use_id],
    )
    logger.info("[pipeline_store] remove_pipeline_use: %s", use_id)


def get_pipeline_uses(db, parent_pipeline_id: "str | None" = None) -> list[dict]:
    """Use edges: [{"use_id", "parent_pipeline_id", "child_pipeline_id",
    "binding"}] — all of them, or one parent's."""
    _ensure_tables(db)
    if parent_pipeline_id is None:
        rows = _duck(db)._fetchall(
            "SELECT use_id, parent_pipeline_id, child_pipeline_id, "
            "binding_json FROM _pipeline_uses"
        )
    else:
        rows = _duck(db)._fetchall(
            "SELECT use_id, parent_pipeline_id, child_pipeline_id, "
            "binding_json FROM _pipeline_uses WHERE parent_pipeline_id = ?",
            [parent_pipeline_id],
        )
    result = []
    for use_id, parent_id, child_id, binding_json in rows:
        try:
            binding = json.loads(binding_json) if binding_json else {}
        except (json.JSONDecodeError, TypeError):
            binding = {}
        result.append(
            {
                "use_id": use_id,
                "parent_pipeline_id": parent_id,
                "child_pipeline_id": child_id,
                "binding": binding,
            }
        )
    return result


def update_use_binding(db, use_id: str, binding: dict) -> None:
    """Replace a use edge's binding ({key_map, params, iterate} subset)."""
    _ensure_tables(db)
    allowed = {"key_map", "params", "iterate"}
    unknown = set(binding) - allowed
    if unknown:
        raise ValueError(
            f"unknown binding key(s) {sorted(unknown)} — allowed: {sorted(allowed)}"
        )
    _duck(db)._execute(
        "UPDATE _pipeline_uses SET binding_json = ? WHERE use_id = ?",
        [json.dumps(binding), use_id],
    )
    logger.info("[pipeline_store] update_use_binding: %s -> %s", use_id, binding)


# ---------------------------------------------------------------------------
# Hypotheses (tagged top-level pipelines, rendered as tabs)
# ---------------------------------------------------------------------------


def _loads_list(raw: "str | None") -> list:
    try:
        return json.loads(raw) if raw else []
    except (json.JSONDecodeError, TypeError):
        return []


def list_hypotheses(db) -> list[dict]:
    """VISIBLE hypothesis-tagged pipelines, root first: [{"pipeline_id",
    "name", "research_question", "hypothesis_statement", "evidence_for",
    "evidence_against"}]. Hidden ones (see hide_pipeline) are excluded —
    their _hypotheses metadata row is left untouched so unhide_pipeline
    brings the tab back with research question/evidence intact."""
    _ensure_tables(db)
    rows = _duck(db)._fetchall(
        "SELECT p.pipeline_id, p.name, h.research_question, "
        "h.hypothesis_statement, h.evidence_for, h.evidence_against "
        "FROM _hypotheses h JOIN _pipelines p ON p.pipeline_id = h.pipeline_id "
        "WHERE NOT p.hidden ORDER BY (p.pipeline_id != ?), p.name",
        [ROOT_PIPELINE_ID],
    )
    return [
        {
            "pipeline_id": pipeline_id,
            "name": name,
            "research_question": question or "",
            "hypothesis_statement": statement or "",
            "evidence_for": _loads_list(ev_for),
            "evidence_against": _loads_list(ev_against),
        }
        for pipeline_id, name, question, statement, ev_for, ev_against in rows
    ]


def tag_as_hypothesis(db, pipeline_id: str) -> None:
    """Tag an EXISTING pipeline as a hypothesis (e.g. after duplicating
    one) — a no-op if it's already tagged."""
    _ensure_tables(db)
    _duck(db)._execute(
        "INSERT INTO _hypotheses (pipeline_id) VALUES (?) ON CONFLICT DO NOTHING",
        [pipeline_id],
    )
    logger.info("[pipeline_store] tag_as_hypothesis: %s", pipeline_id)


def create_hypothesis(db, name: str) -> str:
    """Create a new pipeline and tag it as a hypothesis; returns its pipeline_id."""
    _ensure_tables(db)
    pipeline_id = create_pipeline(db, name)
    _duck(db)._execute("INSERT INTO _hypotheses (pipeline_id) VALUES (?)", [pipeline_id])
    logger.info("[pipeline_store] create_hypothesis: '%s' -> %s", name, pipeline_id)
    return pipeline_id


def update_hypothesis(
    db,
    pipeline_id: str,
    research_question: "str | None" = None,
    hypothesis_statement: "str | None" = None,
    evidence_for: "list | None" = None,
    evidence_against: "list | None" = None,
) -> None:
    """Update whichever fields are provided; ``None`` leaves a field unchanged."""
    _ensure_tables(db)
    known = _duck(db)._fetchall(
        "SELECT 1 FROM _hypotheses WHERE pipeline_id = ?", [pipeline_id]
    )
    if not known:
        raise ValueError(f"'{pipeline_id}' is not a hypothesis pipeline")
    fields, values = [], []
    if research_question is not None:
        fields.append("research_question = ?")
        values.append(research_question)
    if hypothesis_statement is not None:
        fields.append("hypothesis_statement = ?")
        values.append(hypothesis_statement)
    if evidence_for is not None:
        fields.append("evidence_for = ?")
        values.append(json.dumps(evidence_for))
    if evidence_against is not None:
        fields.append("evidence_against = ?")
        values.append(json.dumps(evidence_against))
    if not fields:
        return
    values.append(pipeline_id)
    _duck(db)._execute(
        f"UPDATE _hypotheses SET {', '.join(fields)} WHERE pipeline_id = ?", values
    )
    logger.info("[pipeline_store] update_hypothesis: %s", pipeline_id)


def hide_hypothesis(db, pipeline_id: str) -> None:
    """Hide a hypothesis tab (reuses hide_pipeline's consumer/last-visible
    guards). Its _hypotheses metadata row is left untouched — unhiding
    brings the tab back with research question/evidence intact."""
    _ensure_tables(db)
    hide_pipeline(db, pipeline_id)
    logger.info("[pipeline_store] hide_hypothesis: %s", pipeline_id)


# ---------------------------------------------------------------------------
# Hidden nodes (user-deleted DB-derived nodes)
# ---------------------------------------------------------------------------


def hide_node(db, node_id: str, pipeline_id: str = ROOT_PIPELINE_ID) -> None:
    """Mark a DB-derived node as hidden IN ``pipeline_id`` so that scope's
    _build_graph won't recreate it — a canonical id shared by another
    pipeline scope's independent placement of the same wiring (see
    graph_builder.wiring_id) is untouched (plan-scope-hidden-nodes-edges.md).
    """
    _ensure_tables(db)
    _duck(db)._execute(
        "INSERT INTO _pipeline_hidden_nodes (pipeline_id, node_id) VALUES (?, ?) "
        "ON CONFLICT DO NOTHING",
        [pipeline_id, node_id],
    )


def unhide_node(db, node_id: str, pipeline_id: str = ROOT_PIPELINE_ID) -> None:
    """Remove a node from ``pipeline_id``'s hidden list (e.g. re-added there)."""
    _duck(db)._execute(
        "DELETE FROM _pipeline_hidden_nodes WHERE pipeline_id = ? AND node_id = ?",
        [pipeline_id, node_id],
    )


def unhide_nodes_by_prefix(
    db, prefix: str, pipeline_id: str = ROOT_PIPELINE_ID
) -> None:
    """Remove all of ``pipeline_id``'s hidden nodes whose IDs start with
    ``prefix``.

    Used when a user re-adds a function node by label: composite DB-derived
    IDs (``fn__{label}__{call_id}``) don't match a single canonical ID, so
    we unhide every call-site node sharing the prefix.
    """
    _duck(db)._execute(
        "DELETE FROM _pipeline_hidden_nodes WHERE pipeline_id = ? AND node_id LIKE ?",
        [pipeline_id, prefix + "%"],
    )


def get_hidden_node_ids(db, pipeline_id: "str | None" = None) -> set[str]:
    """Return the set of node IDs hidden in ``pipeline_id``.

    ``pipeline_id=None`` (default) returns every scope's hidden ids unioned
    — for callers that intentionally check hidden-ness independent of scope
    (currently the execution/run-readiness path, which is not yet
    scope-aware — see plan-scope-hidden-nodes-edges.md follow-up). Canvas
    rendering (api.pipeline._build_graph) passes its own scope so a delete
    in one pipeline never hides a shared-wiring node in another.

    Pending-constant combo hides (_pipeline_hidden_combos) remain globally
    scoped by design (deferred, same follow-up) and are always unioned in
    regardless of ``pipeline_id`` so that existing behavior is unchanged.
    """
    _ensure_tables(db)
    if pipeline_id is None:
        rows = _duck(db)._fetchall("SELECT node_id FROM _pipeline_hidden_nodes")
    else:
        rows = _duck(db)._fetchall(
            "SELECT node_id FROM _pipeline_hidden_nodes WHERE pipeline_id = ?",
            [pipeline_id],
        )
    hidden = {row[0] for row in rows}
    combo_rows = _duck(db)._fetchall("SELECT node_id FROM _pipeline_hidden_combos")
    hidden.update(row[0] for row in combo_rows)
    return hidden


# ---------------------------------------------------------------------------
# Hidden combos (one specific constant-value row of a function's Cartesian
# product, never a whole node) — never deletes data, only hides it. Reuses
# hide_node/unhide_node for the shared node_id space (fn__{fn}__{call_id}) so
# a combo hidden before it's ever run and later actually run land on the
# same id; the structural variant_key is kept alongside so a hidden combo
# can be shown back (a call_id hash can't be reversed) for the restore UI.
# ---------------------------------------------------------------------------


def hide_combo(db, node_id: str, function_name: str, variant_key: dict) -> None:
    """Hide one call-site's Cartesian-product row without deleting anything."""
    _ensure_tables(db)
    hide_node(db, node_id)
    _duck(db)._execute(
        "INSERT INTO _pipeline_hidden_combos (node_id, function_name, variant_key) "
        "VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
        [node_id, function_name, json.dumps(variant_key, sort_keys=True)],
    )


def unhide_combo(db, node_id: str) -> None:
    """Restore a previously hidden combo."""
    _ensure_tables(db)
    unhide_node(db, node_id)
    _duck(db)._execute(
        "DELETE FROM _pipeline_hidden_combos WHERE node_id = ?", [node_id]
    )


def list_hidden_combos(db, function_name: str) -> list[dict]:
    """Return hidden combos for one function as {"node_id", "variant_key"}."""
    _ensure_tables(db)
    rows = _duck(db)._fetchall(
        "SELECT node_id, variant_key FROM _pipeline_hidden_combos "
        "WHERE function_name = ?",
        [function_name],
    )
    return [
        {"node_id": node_id, "variant_key": json.loads(variant_key)}
        for node_id, variant_key in rows
    ]


# ---------------------------------------------------------------------------
# Hidden edges (user-deleted DB-derived edges) — never deletes data, only
# hides it, same ethos as hide_node/hide_combo. Hiding an INBOUND edge
# (variable/constant/pathInput -> function) additionally makes the target
# function's wiring "disconnected" for run-state and execution purposes
# (see domain.graph_builder.hidden_wirings) — hiding an OUTBOUND edge
# (function -> variable) is purely cosmetic. Manual (``manual__``) edges
# are hard-deleted instead of hidden (see layout_service.delete_edge);
# this table is for DB-derived edges only.
# ---------------------------------------------------------------------------


def hide_edge(
    db,
    edge_id: str,
    source: str = "",
    target: str = "",
    source_handle: "str | None" = None,
    target_handle: "str | None" = None,
    pipeline_id: str = ROOT_PIPELINE_ID,
) -> None:
    """Mark a DB-derived edge as hidden IN ``pipeline_id`` so that scope's
    build_edges won't recreate it — an edge id shared by another pipeline
    scope's independent placement of the same wiring is untouched (see
    hide_node and plan-scope-hidden-nodes-edges.md)."""
    logger.info(
        "[pipeline_store] hide_edge called (edge_id=%r, source=%r, target=%r, "
        "pipeline_id=%r)",
        edge_id,
        source,
        target,
        pipeline_id,
    )
    _ensure_tables(db)
    _duck(db)._execute(
        "INSERT INTO _pipeline_hidden_edges "
        "(pipeline_id, edge_id, source, target, source_handle, target_handle) "
        "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
        [pipeline_id, edge_id, source, target, source_handle, target_handle],
    )


def unhide_edge(db, edge_id: str, pipeline_id: str = ROOT_PIPELINE_ID) -> None:
    """Restore a previously hidden edge in ``pipeline_id``."""
    logger.info(
        "[pipeline_store] unhide_edge called (edge_id=%r, pipeline_id=%r)",
        edge_id,
        pipeline_id,
    )
    _duck(db)._execute(
        "DELETE FROM _pipeline_hidden_edges WHERE pipeline_id = ? AND edge_id = ?",
        [pipeline_id, edge_id],
    )


def get_hidden_edge_ids(db, pipeline_id: "str | None" = None) -> set[str]:
    """Return the set of edge IDs hidden in ``pipeline_id``.

    ``pipeline_id=None`` (default) returns every scope's hidden ids unioned
    — see get_hidden_node_ids for why (same execution-path caveat)."""
    _ensure_tables(db)
    if pipeline_id is None:
        rows = _duck(db)._fetchall("SELECT edge_id FROM _pipeline_hidden_edges")
    else:
        rows = _duck(db)._fetchall(
            "SELECT edge_id FROM _pipeline_hidden_edges WHERE pipeline_id = ?",
            [pipeline_id],
        )
    return {row[0] for row in rows}


def list_hidden_edges(db, pipeline_id: "str | None" = None) -> list[dict]:
    """Hidden edges with enough context to label a restore-list entry.

    ``pipeline_id=None`` (default) lists every scope's hidden edges; pass a
    scope to restrict to just that pipeline's own hidden edges (the restore
    panel — see plan-scope-hidden-nodes-edges.md)."""
    _ensure_tables(db)
    if pipeline_id is None:
        rows = _duck(db)._fetchall(
            "SELECT edge_id, source, target, source_handle, target_handle "
            "FROM _pipeline_hidden_edges"
        )
    else:
        rows = _duck(db)._fetchall(
            "SELECT edge_id, source, target, source_handle, target_handle "
            "FROM _pipeline_hidden_edges WHERE pipeline_id = ?",
            [pipeline_id],
        )
    return [
        {
            "edge_id": edge_id,
            "source": source,
            "target": target,
            "source_handle": source_handle,
            "target_handle": target_handle,
        }
        for edge_id, source, target, source_handle, target_handle in rows
    ]


# ---------------------------------------------------------------------------
# Hidden subpipeline ports (to-do #9) — a manual override on top of
# domain.scope_filter.document_interface's automatic type-level port
# computation. Never deletes wiring, only suppresses one type's exposed
# dot on a scope's interface; the internal node that produces/consumes
# that type stays fully visible on its own canvas at all times, so
# there's no separate restore list (unlike hidden edges/nodes) — un-hiding
# is just toggling the same right-click item again.
# ---------------------------------------------------------------------------


def hide_port(db, pipeline_id: str, direction: str, var_type: str) -> None:
    """Suppress ``var_type``'s exposed ``direction`` ('input'|'output')
    port on ``pipeline_id``'s subpipeline interface."""
    logger.info(
        "[pipeline_store] hide_port called (pipeline_id=%r, direction=%r, var_type=%r)",
        pipeline_id,
        direction,
        var_type,
    )
    _ensure_tables(db)
    _duck(db)._execute(
        "INSERT INTO _pipeline_hidden_ports (pipeline_id, direction, var_type) "
        "VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
        [pipeline_id, direction, var_type],
    )


def unhide_port(db, pipeline_id: str, direction: str, var_type: str) -> None:
    """Restore a previously hidden port."""
    logger.info(
        "[pipeline_store] unhide_port called (pipeline_id=%r, direction=%r, var_type=%r)",
        pipeline_id,
        direction,
        var_type,
    )
    _duck(db)._execute(
        "DELETE FROM _pipeline_hidden_ports "
        "WHERE pipeline_id = ? AND direction = ? AND var_type = ?",
        [pipeline_id, direction, var_type],
    )


def get_hidden_ports(db, pipeline_id: str) -> dict:
    """One scope's hidden ports: ``{"input": {type, ...}, "output": {type, ...}}``
    — what the right-click context menu needs to decide Show vs Hide."""
    _ensure_tables(db)
    rows = _duck(db)._fetchall(
        "SELECT direction, var_type FROM _pipeline_hidden_ports WHERE pipeline_id = ?",
        [pipeline_id],
    )
    result: dict[str, set[str]] = {"input": set(), "output": set()}
    for direction, var_type in rows:
        result[direction].add(var_type)
    return result


def get_hidden_ports_by_scope(db) -> dict[str, dict[str, set[str]]]:
    """Every scope's hidden ports, keyed by pipeline_id — the shape
    domain.scope_filter.document_interface needs (it recurses across
    scopes via nested ``uses``, so it needs every scope's own hides on
    hand at once, not just the scope being asked about)."""
    _ensure_tables(db)
    rows = _duck(db)._fetchall(
        "SELECT pipeline_id, direction, var_type FROM _pipeline_hidden_ports"
    )
    result: dict[str, dict[str, set[str]]] = {}
    for pid, direction, var_type in rows:
        scope = result.setdefault(pid, {"input": set(), "output": set()})
        scope[direction].add(var_type)
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _upsert_node(
    db, node_id: str, node_type: str, label: str, pipeline_id: str = ROOT_PIPELINE_ID
) -> None:
    _duck(db)._execute(
        "INSERT INTO _pipeline_nodes (node_id, node_type, label, pipeline_id) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT (node_id) DO UPDATE SET node_type = excluded.node_type, "
        "label = excluded.label, pipeline_id = excluded.pipeline_id",
        [node_id, node_type, label, pipeline_id],
    )


def _upsert_edge(
    db, edge_id: str, source: str, target: str, source_handle, target_handle
) -> None:
    _duck(db)._execute(
        "INSERT INTO _pipeline_edges "
        "(edge_id, source, target, source_handle, target_handle) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT (edge_id) DO UPDATE SET source = excluded.source, "
        "target = excluded.target, source_handle = excluded.source_handle, "
        "target_handle = excluded.target_handle",
        [edge_id, source, target, source_handle, target_handle],
    )
