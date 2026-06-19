"""Bipartite provenance model — identity helpers and schema.

This module implements the storage-side primitives for the simplified
provenance system described in ``docs/claude/lineage-simplification.md``.

The graph is **bipartite**: *records* (entities — variables and constants)
and *invocations* (activities — unique function calls). Data flow is captured
entirely by edges in ``_invocation_input`` / ``_invocation_output``, so
traversal is a plain recursive SQL join rather than Python-side JSON parsing.

Everything here is **content-addressed and idempotent**: re-running an
identical pipeline reproduces every id, so all inserts are
``ON CONFLICT DO NOTHING`` and no duplicate provenance is written. The one
exception is ``_run`` (the audit log), which gets a fresh row per execution.

Identity (see §5 of the design doc)::

    constant record_id = hash("__constant__" | content_hash(value))
    invocation_id      = hash(function_hash | as_table | distribute
                              | sorted(input bindings))
    output record_id   = hash(type | schema_version | content_hash(data)
                              | invocation_id | output_num)
    run_id             = fresh unique id per for_each execution (NOT addressed)
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from typing import Any, Iterable

from scicanonicalhash import canonical_hash

logger = logging.getLogger(__name__)

__all__ = [
    "CONSTANT_TYPE",
    "compute_constant_record_id",
    "constant_record_id_from_hash",
    "compute_invocation_id",
    "compute_output_record_id",
    "generate_run_id",
    "normalize_as_table",
    "constant_value_repr",
    "constant_value_type",
    "ensure_provenance_tables",
    "insert_record_entity",
    "insert_record_entities",
]

# Sentinel ``type`` value for constant records in ``_record``. Constants have
# no schema_id (schema-global) and no producing invocation.
CONSTANT_TYPE = "__constant__"

# All record_ids (variables, constants, outputs) are 16 hex chars so they join
# uniformly across the bipartite graph. Matches scicanonicalhash.generate_record_id.
_ID_LEN = 16


def _sha16(*parts: str) -> str:
    """SHA-256 of ``parts`` joined by ``|``, truncated to 16 hex chars."""
    combined = "|".join(parts).encode("utf-8")
    return hashlib.sha256(combined).hexdigest()[:_ID_LEN]


# ---------------------------------------------------------------------------
# Identity helpers
# ---------------------------------------------------------------------------
def constant_record_id_from_hash(content_hash: str) -> str:
    """Content-addressed constant id from a precomputed content hash.

    The hash must be ``canonical_hash(value)`` so this agrees with
    :func:`compute_constant_record_id`. Used by the lineage save path, which has
    the constant's hash (scilineage's ``value_hash`` == ``canonical_hash``) but
    not always the raw value.
    """
    return _sha16(CONSTANT_TYPE, f"content:{content_hash}")


def compute_constant_record_id(value: Any) -> str:
    """Content-addressed id for a constant value.

    Constants are schema-global: the same value reused anywhere in any pipeline
    maps to one ``_record`` / ``_constant`` row. The id depends only on the
    value's canonical content hash, not on where or how it is consumed.
    """
    rid = constant_record_id_from_hash(canonical_hash(value))
    logger.debug("compute_constant_record_id(%r) = %s", value, rid)
    return rid


def compute_invocation_id(
    function_hash: str,
    as_table: Iterable[str] | None,
    distribute: bool,
    input_bindings: Iterable[tuple],
) -> str:
    """Content-addressed id for a unique function call (an *activity*).

    Args:
        function_hash: AST hash of the function source (``compute_function_hash``).
        as_table: Resolved aggregated param names. Order-insensitive (sorted in).
        distribute: Post-call fan-out flag.
        input_bindings: Iterable of input edges, one per realized input (variable
            *and* constant). Each is ``(param_name, input_record_id)`` or
            ``(param_name, input_record_id, selector)``. ``selector`` qualifies
            wrappers that change *which* data is consumed without changing the
            record — notably ``ColumnSelection`` (e.g. ``{"columns": [...]}``) —
            so two calls selecting different columns of the same record get
            distinct ids. Order-insensitive.

    ``where`` is deliberately excluded — it only filters which records load, and
    its whole effect on the computation is the surviving input set = these very
    bindings (see §10.1). Re-running the same call reproduces this id exactly.
    """
    norm: list[tuple[str, str, str]] = []
    for b in input_bindings:
        if len(b) == 3:
            param, rid, selector = b
        else:
            (param, rid), selector = b, None
        norm.append((str(param), str(rid), "" if selector is None else str(selector)))
    bindings = sorted(norm)
    parts = [
        f"fn_hash:{function_hash}",
        f"as_table:{canonical_hash(sorted(as_table or []))}",
        f"distribute:{bool(distribute)}",
        f"inputs:{canonical_hash(bindings)}",
    ]
    inv_id = _sha16(*parts)
    logger.debug(
        "compute_invocation_id(fn_hash=%s, as_table=%s, distribute=%s, %d bindings) = %s",
        function_hash, sorted(as_table or []), bool(distribute), len(bindings), inv_id,
    )
    return inv_id


def compute_output_record_id(
    type_name: str,
    schema_version: int,
    content_hash: str,
    invocation_id: str,
    output_num: int,
) -> str:
    """Content-addressed id for a record produced by an invocation.

    Includes ``invocation_id`` (which folds in the function hash + every input
    record_id) and ``output_num`` so two outputs that differ only by an upstream
    constant — or by which slot of a multi-output call they came from — get
    distinct ids automatically. This is the structural replacement for the old
    ``__upstream``-in-``version_keys`` mechanism.
    """
    parts = [
        f"type:{type_name}",
        f"schema:{schema_version}",
        f"content:{content_hash}",
        f"invocation:{invocation_id}",
        f"output_num:{output_num}",
    ]
    rid = _sha16(*parts)
    logger.debug(
        "compute_output_record_id(type=%s, sv=%s, content=%s, inv=%s, out=%s) = %s",
        type_name, schema_version, content_hash[:12] if content_hash else None,
        invocation_id, output_num, rid,
    )
    return rid


def normalize_as_table(as_table_value, loadable_params) -> list[str]:
    """Resolve an ``as_table`` flag to a sorted list of aggregated param names.

    Shared by the save path and the skip/predict path so both compute the same
    ``invocation_id``. ``True`` means "aggregate every loadable input"; a list is
    used as-is. Order-insensitive (sorted).
    """
    if as_table_value is True:
        return sorted(str(p) for p in loadable_params)
    if isinstance(as_table_value, (list, tuple)):
        return sorted(str(x) for x in as_table_value)
    return []


def generate_run_id() -> str:
    """Fresh, non-content-addressed id for one ``for_each`` execution.

    Unlike everything else here this is intentionally unique per call so the
    ``_run`` audit log captures *every* execution event — even a re-run that
    reproduces existing (deduped) invocations.
    """
    return uuid.uuid4().hex[:_ID_LEN]


# ---------------------------------------------------------------------------
# Constant value rendering
# ---------------------------------------------------------------------------
def constant_value_repr(value: Any) -> str:
    """Human-readable rendering of a constant value for ``_constant.value_repr``."""
    return repr(value)


def constant_value_type(value: Any) -> str:
    """Type label for ``_constant.value_type`` (e.g. ``"int"``, ``"str"``)."""
    return type(value).__name__


# ---------------------------------------------------------------------------
# Record entity writes
# ---------------------------------------------------------------------------
# Every saved record — raw/manual AND computed — gets one ``_record`` row so the
# entities table is the complete node set for graph traversal. Computed records
# additionally get invocation/edge rows (see provenance_save.record_run); raw
# records have no producing invocation and terminate the upward walk.
_RECORD_INSERT = (
    "INSERT INTO _record "
    "(record_id, created_at, type, schema_id, content_hash, schema_version, excluded) "
    "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (record_id) DO NOTHING"
)


def insert_record_entity(
    duck,
    record_id: str,
    created_at: str,
    type_name: str,
    schema_id: int | None,
    content_hash: str | None,
    schema_version: int | None,
    excluded: bool = False,
) -> None:
    """Insert one ``_record`` entity row (idempotent)."""
    duck._execute(
        _RECORD_INSERT,
        [record_id, created_at, type_name, schema_id, content_hash, schema_version, excluded],
    )


def insert_record_entities(duck, rows: list[tuple]) -> None:
    """Bulk-insert ``_record`` rows. Each row is
    ``(record_id, created_at, type, schema_id, content_hash, schema_version, excluded)``."""
    if not rows:
        return
    duck.con.executemany(_RECORD_INSERT, rows)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
def ensure_provenance_tables(duck) -> None:
    """Create the seven bipartite provenance tables if absent.

    ``duck`` is a ``SciDuck`` instance (exposes ``_execute``). Tables:

    Identity/data: ``_record``, ``_constant``, ``_invocation``,
    ``_invocation_input``, ``_invocation_output``.
    Audit: ``_run``, ``_run_invocation``.

    See §4 of the design doc for the rationale (bipartite vs. flat edge table).
    """
    logger.debug("ensure_provenance_tables: creating bipartite provenance schema")

    # Entities: variables AND constants. Variables have a schema_id + a type
    # (class name) and their data lives in the per-type "<Type>_data" tables.
    # Constants have schema_id NULL, type '__constant__', value in _constant.
    # Content-addressed and immutable → ONE row, ON CONFLICT DO NOTHING.
    duck._execute("""
        CREATE TABLE IF NOT EXISTS _record (
            record_id      VARCHAR PRIMARY KEY,
            created_at     VARCHAR NOT NULL,
            type           VARCHAR NOT NULL,
            schema_id      INTEGER,
            content_hash   VARCHAR,
            schema_version INTEGER,
            excluded       BOOLEAN DEFAULT FALSE
        )
    """)

    # Constant values (parallel to a variable's "<Type>_data" table).
    duck._execute("""
        CREATE TABLE IF NOT EXISTS _constant (
            record_id    VARCHAR PRIMARY KEY,
            value_repr   VARCHAR,
            value_type   VARCHAR,
            content_hash VARCHAR
        )
    """)

    # Activities: one row per UNIQUE function call (content-addressed).
    # as_table/distribute are identity-bearing and stored as queryable columns.
    # where is NOT here — it is batch-level (see _run).
    # pipeline_hash is scilineage's compute_lineage_hash() for this call (fn hash
    # + classified inputs, output_num-independent). One per invocation; backs the
    # public find_by_lineage() lookup. Distinct from invocation_id (which is the
    # graph's own content hash over fn_hash + input record bindings).
    duck._execute("""
        CREATE TABLE IF NOT EXISTS _invocation (
            invocation_id VARCHAR PRIMARY KEY,
            function_name VARCHAR NOT NULL,
            function_hash VARCHAR NOT NULL,
            as_table      VARCHAR[],
            distribute    BOOLEAN DEFAULT FALSE,
            pipeline_hash VARCHAR
        )
    """)

    # What was fed into a call, and the argument slot it filled. ``selector``
    # qualifies wrappers that change which data is consumed without changing the
    # record (ColumnSelection: JSON like {"columns": [...]}); NULL otherwise.
    # It is folded into invocation_id so different selections don't collide.
    duck._execute("""
        CREATE TABLE IF NOT EXISTS _invocation_input (
            invocation_id   VARCHAR NOT NULL,
            param_name      VARCHAR NOT NULL,
            input_record_id VARCHAR NOT NULL,
            selector        VARCHAR,
            PRIMARY KEY (invocation_id, param_name, input_record_id)
        )
    """)

    # What a call produced. Multiple rows for multi-output functions.
    duck._execute("""
        CREATE TABLE IF NOT EXISTS _invocation_output (
            invocation_id    VARCHAR NOT NULL,
            output_num       INTEGER NOT NULL,
            output_record_id VARCHAR NOT NULL,
            PRIMARY KEY (invocation_id, output_num)
        )
    """)

    # Audit log: one row per for_each EXECUTION (fresh row every run, even when
    # it reproduces existing invocations). Captures when/who/where.
    duck._execute("""
        CREATE TABLE IF NOT EXISTS _run (
            run_id        VARCHAR PRIMARY KEY,
            timestamp     VARCHAR NOT NULL,
            user_id       VARCHAR,
            function_name VARCHAR NOT NULL,
            where_clause  VARCHAR
        )
    """)

    # Many-to-many: which invocations a run (re)produced.
    duck._execute("""
        CREATE TABLE IF NOT EXISTS _run_invocation (
            run_id        VARCHAR NOT NULL,
            invocation_id VARCHAR NOT NULL,
            PRIMARY KEY (run_id, invocation_id)
        )
    """)

    # Backfill: add the selector column to _invocation_input tables created
    # before it existed (additive migration over an in-progress beta DB).
    try:
        cols = {
            r[0] for r in duck._fetchall(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = '_invocation_input'"
            )
        }
        if "selector" not in cols:
            duck._execute("ALTER TABLE _invocation_input ADD COLUMN selector VARCHAR")
            logger.debug("ensure_provenance_tables: added selector column to _invocation_input")
        inv_cols = {
            r[0] for r in duck._fetchall(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = '_invocation'"
            )
        }
        if "pipeline_hash" not in inv_cols:
            duck._execute("ALTER TABLE _invocation ADD COLUMN pipeline_hash VARCHAR")
            logger.debug("ensure_provenance_tables: added pipeline_hash column to _invocation")
    except Exception:
        logger.debug("ensure_provenance_tables: column backfill check skipped", exc_info=True)

    # Indexes for upward/downward traversal (the recursive CTEs in §6/§8 join
    # output_record_id → invocation_id → input_record_id repeatedly).
    duck._execute(
        "CREATE INDEX IF NOT EXISTS idx_inv_output_rid "
        "ON _invocation_output (output_record_id)"
    )
    duck._execute(
        "CREATE INDEX IF NOT EXISTS idx_inv_input_inv "
        "ON _invocation_input (invocation_id)"
    )
    logger.debug("ensure_provenance_tables: done")
