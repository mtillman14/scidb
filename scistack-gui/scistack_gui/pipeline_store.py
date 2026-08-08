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
        CREATE TABLE IF NOT EXISTS _pipeline_hidden_nodes (
            node_id VARCHAR PRIMARY KEY
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


def graduate_manual_node(db, old_id: str, new_id: str) -> None:
    """Remove the manual node entry for old_id (the DB-derived node takes over).

    Also rewrites any manual edges that reference old_id so they point to
    new_id instead of becoming dangling.
    """
    _duck(db)._execute("DELETE FROM _pipeline_nodes WHERE node_id = ?", [old_id])
    # Update edges that reference the old node ID.
    _duck(db)._execute(
        "UPDATE _pipeline_edges SET source = ? WHERE source = ?",
        [new_id, old_id],
    )
    _duck(db)._execute(
        "UPDATE _pipeline_edges SET target = ? WHERE target = ?",
        [new_id, old_id],
    )


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
    """All pipeline scopes: [{"pipeline_id", "name"}], root first."""
    _ensure_tables(db)
    rows = _duck(db)._fetchall(
        "SELECT pipeline_id, name FROM _pipelines ORDER BY (pipeline_id != ?), name",
        [ROOT_PIPELINE_ID],
    )
    return [{"pipeline_id": r[0], "name": r[1]} for r in rows]


def create_pipeline(db, name: str) -> str:
    """Create a new (empty) pipeline scope; returns its pipeline_id."""
    _ensure_tables(db)
    name = str(name).strip()
    if not name:
        raise ValueError("pipeline name must be non-empty")
    existing = {p["name"] for p in list_pipelines(db)}
    if name in existing:
        raise ValueError(f"a pipeline named '{name}' already exists")
    pipeline_id = f"pipe_{uuid.uuid4().hex[:12]}"
    _duck(db)._execute(
        "INSERT INTO _pipelines (pipeline_id, name) VALUES (?, ?)",
        [pipeline_id, name],
    )
    logger.info("[pipeline_store] create_pipeline: '%s' -> %s", name, pipeline_id)
    return pipeline_id


def rename_pipeline(db, pipeline_id: str, name: str) -> None:
    _ensure_tables(db)
    if pipeline_id == ROOT_PIPELINE_ID:
        raise ValueError("the root pipeline cannot be renamed")
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


def delete_pipeline(db, pipeline_id: str) -> None:
    """Delete an EMPTY-of-consumers pipeline scope and its contents.

    Refuses the root and any pipeline still placed on another canvas
    (delete those pipeline nodes first — fail fast beats silent cascade).
    Cascades: own nodes, edges between them, its outgoing use rows (and
    THEIR canvas node rows live in this scope, so they go with the nodes).
    """
    _ensure_tables(db)
    if pipeline_id == ROOT_PIPELINE_ID:
        raise ValueError("the root pipeline cannot be deleted")
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
        "[pipeline_store] delete_pipeline: %s (%d node(s) removed)",
        pipeline_id,
        len(node_ids),
    )


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
    """Hypothesis-tagged pipelines, root first: [{"pipeline_id", "name",
    "research_question", "hypothesis_statement", "evidence_for",
    "evidence_against"}]."""
    _ensure_tables(db)
    rows = _duck(db)._fetchall(
        "SELECT p.pipeline_id, p.name, h.research_question, "
        "h.hypothesis_statement, h.evidence_for, h.evidence_against "
        "FROM _hypotheses h JOIN _pipelines p ON p.pipeline_id = h.pipeline_id "
        "ORDER BY (p.pipeline_id != ?), p.name",
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


def delete_hypothesis(db, pipeline_id: str) -> None:
    """Delete a hypothesis: its metadata row, then the underlying pipeline
    (reuses delete_pipeline's root/consumer guards)."""
    _ensure_tables(db)
    delete_pipeline(db, pipeline_id)
    _duck(db)._execute("DELETE FROM _hypotheses WHERE pipeline_id = ?", [pipeline_id])
    logger.info("[pipeline_store] delete_hypothesis: %s", pipeline_id)


# ---------------------------------------------------------------------------
# Hidden nodes (user-deleted DB-derived nodes)
# ---------------------------------------------------------------------------


def hide_node(db, node_id: str) -> None:
    """Mark a DB-derived node as hidden so _build_graph won't recreate it."""
    _ensure_tables(db)
    _duck(db)._execute(
        "INSERT INTO _pipeline_hidden_nodes (node_id) VALUES (?) "
        "ON CONFLICT DO NOTHING",
        [node_id],
    )


def unhide_node(db, node_id: str) -> None:
    """Remove a node from the hidden list (e.g. when user re-adds it)."""
    _duck(db)._execute(
        "DELETE FROM _pipeline_hidden_nodes WHERE node_id = ?", [node_id]
    )


def unhide_nodes_by_prefix(db, prefix: str) -> None:
    """Remove all hidden nodes whose IDs start with ``prefix``.

    Used when a user re-adds a function node by label: composite DB-derived
    IDs (``fn__{label}__{call_id}``) don't match a single canonical ID, so
    we unhide every call-site node sharing the prefix.
    """
    _duck(db)._execute(
        "DELETE FROM _pipeline_hidden_nodes WHERE node_id LIKE ?",
        [prefix + "%"],
    )


def get_hidden_node_ids(db) -> set[str]:
    """Return the set of node IDs that the user has explicitly deleted."""
    _ensure_tables(db)
    rows = _duck(db)._fetchall("SELECT node_id FROM _pipeline_hidden_nodes")
    return {row[0] for row in rows}


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
