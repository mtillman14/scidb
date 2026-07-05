"""Inspector — the read-only observability facade over a scidb database.

Every method returns plain dataclasses (JSON-serializable via
``dataclasses.asdict``) so the CLI, GUI, and MATLAB bridge all consume the
same shapes. Nothing here computes new state: each method is a thin shaping
layer over the core tables and the provenance_query primitives
(question → primitive mapping in docs/claude/observability-api-design.md).
"""

from __future__ import annotations

import functools
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd

from ..exceptions import NotFoundError
from ..log import Log

if TYPE_CHECKING:
    from ..database import DatabaseManager

# Internal (non-variable) entity types in _record, excluded from user-facing
# record counts everywhere.
_INTERNAL_RECORD_TYPES = ("__constant__", "__pathinput__")
_NOT_INTERNAL_SQL = (
    "type NOT IN (" + ", ".join(f"'{t}'" for t in _INTERNAL_RECORD_TYPES) + ")"
)


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class DbOverview:
    db_path: str
    db_size_bytes: int
    schema_keys: list[str]
    n_schema_locations: int
    n_variables: int
    n_records: int            # variable records only (constants/pathinputs excluded)
    n_excluded_records: int
    n_invocations: int        # real function calls (synthetic __save__ anchors excluded)
    n_runs: int
    last_save: str | None     # ISO timestamp of newest _record_save event
    last_run: str | None      # ISO timestamp of newest _run row


@dataclass
class VariableSummary:
    name: str
    schema_level: str | None
    dtype: str | None
    description: str
    record_count: int         # distinct non-excluded record_ids of this type
    excluded_count: int
    variant_count: int        # distinct (fn, constants, output) variants producing it
    last_saved: str | None


@dataclass
class VariableDetail(VariableSummary):
    data_columns: list[str] = field(default_factory=list)
    records_by_level: dict[str, int] = field(default_factory=dict)


@dataclass
class SchemaNode:
    key: str                  # schema key name at this depth (e.g. "subject")
    value: str                # the key's value (e.g. "S01")
    schema_level: str | None  # set when this node is a realized _schema row
    schema_id: int | None
    record_count: int         # records at exactly this location
    children: list["SchemaNode"] = field(default_factory=list)


@dataclass
class SchemaTree:
    schema_keys: list[str]
    roots: list[SchemaNode] = field(default_factory=list)


@dataclass
class RecordSummary:
    record_id: str
    variable: str
    schema: dict[str, str]
    timestamp: str
    user_id: str | None
    content_hash: str
    schema_version: int
    excluded: bool


# ---------------------------------------------------------------------------
# Timing / logging decorator (NOTE 2: observe internals on every call)
# ---------------------------------------------------------------------------

def _timed(method):
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        t0 = time.perf_counter()
        result = method(self, *args, **kwargs)
        ms = (time.perf_counter() - t0) * 1000.0
        n = len(result) if isinstance(result, list) else 1
        Log.debug(f"inspect.{method.__name__}: {ms:.1f} ms, {n} result(s)")
        return result
    return wrapper


def _iso(ts) -> str | None:
    """Timestamp (datetime / pd.Timestamp / None / NaT) → ISO string or None."""
    if ts is None or (isinstance(ts, float) and pd.isna(ts)) or ts is pd.NaT:
        return None
    try:
        if pd.isna(ts):
            return None
    except (TypeError, ValueError):
        pass
    return ts.isoformat(sep=" ") if hasattr(ts, "isoformat") else str(ts)


class Inspector:
    """Read-side facade over a DatabaseManager.

    Constructed from a live DatabaseManager (``db.inspect``) or standalone
    via ``Inspector.open(path)``, which discovers the schema keys from the
    database itself and opens strictly read-only.
    """

    def __init__(self, db: "DatabaseManager", _owns_db: bool = False):
        self._db = db
        self._owns_db = _owns_db

    @classmethod
    def open(cls, db_path: str | Path) -> "Inspector":
        """Open an existing database read-only, discovering its schema keys."""
        from sciduckdb import schema_keys_from_db

        from ..database import DatabaseManager

        keys = schema_keys_from_db(db_path)
        db = DatabaseManager(db_path, keys, read_only=True)
        Log.info(f"Inspector.open: {db_path} (read-only, schema_keys={keys})")
        return cls(db, _owns_db=True)

    def close(self) -> None:
        """Close the underlying connection if this Inspector opened it."""
        if self._owns_db:
            self._db._duck.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- internal helpers ---------------------------------------------------

    @property
    def _duck(self):
        return self._db._duck

    def _scalar(self, sql: str, params=None, default=0):
        """One-value query; returns default if a referenced table is missing."""
        try:
            rows = self._duck._fetchall(sql, params)
        except Exception as e:  # missing table on a pre-provenance database
            Log.debug(f"inspect scalar query failed ({e}); returning {default!r}")
            return default
        val = rows[0][0] if rows else None
        return default if val is None else val

    def _variant_counts(self) -> dict[str, int]:
        """output_type → number of distinct pipeline variants (single batch query)."""
        if not self._duck._table_exists("_invocation"):
            return {}
        counts: dict[str, int] = {}
        for entry in self._db.list_pipeline_variants():
            out = entry.get("output_type")
            if out:
                counts[out] = counts.get(out, 0) + 1
        return counts

    # -- facade methods -----------------------------------------------------

    @_timed
    def overview(self) -> DbOverview:
        db_path = str(self._db.dataset_db_path)
        try:
            size = Path(db_path).stat().st_size
        except OSError:
            size = 0
        not_internal = _NOT_INTERNAL_SQL
        return DbOverview(
            db_path=db_path,
            db_size_bytes=int(size),
            schema_keys=list(self._db.dataset_schema_keys),
            n_schema_locations=int(self._scalar("SELECT COUNT(*) FROM _schema")),
            n_variables=int(self._scalar("SELECT COUNT(*) FROM _variables")),
            n_records=int(self._scalar(
                f"SELECT COUNT(*) FROM _record WHERE {not_internal}")),
            n_excluded_records=int(self._scalar(
                f"SELECT COUNT(*) FROM _record WHERE {not_internal} "
                f"AND COALESCE(excluded, FALSE)")),
            n_invocations=int(self._scalar(
                "SELECT COUNT(*) FROM _invocation WHERE function_name <> '__save__'")),
            n_runs=int(self._scalar("SELECT COUNT(*) FROM _run")),
            last_save=_iso(self._scalar(
                "SELECT MAX(timestamp) FROM _record_save", default=None)),
            last_run=_iso(self._scalar(
                "SELECT MAX(timestamp) FROM _run", default=None)),
        )

    @_timed
    def variables(self) -> list[VariableSummary]:
        rows = self._duck._fetchall(
            "SELECT v.variable_name, v.schema_level, v.dtype, v.description, "
            "COUNT(DISTINCT CASE WHEN NOT COALESCE(r.excluded, FALSE) "
            "                    THEN r.record_id END) AS record_count, "
            "COUNT(DISTINCT CASE WHEN COALESCE(r.excluded, FALSE) "
            "                    THEN r.record_id END) AS excluded_count, "
            "MAX(rs.timestamp) AS last_saved "
            "FROM _variables v "
            "LEFT JOIN _record r ON r.type = v.variable_name "
            "LEFT JOIN _record_save rs ON rs.record_id = r.record_id "
            "GROUP BY v.variable_name, v.schema_level, v.dtype, v.description "
            "ORDER BY v.variable_name"
        )
        variant_counts = self._variant_counts()
        return [
            VariableSummary(
                name=name,
                schema_level=level,
                dtype=dtype,
                description=desc or "",
                record_count=int(n),
                excluded_count=int(n_ex),
                variant_count=variant_counts.get(name, 0),
                last_saved=_iso(last),
            )
            for name, level, dtype, desc, n, n_ex, last in rows
        ]

    @_timed
    def variable(self, name: str) -> VariableDetail:
        name = getattr(name, "__name__", name)
        summary = next((v for v in self.variables() if v.name == name), None)
        if summary is None:
            raise NotFoundError(f"Variable type {name!r} is not registered in this database")

        # Data table columns (table name from _registered_types, fallback: name)
        table_name = self._scalar(
            "SELECT table_name FROM _registered_types WHERE type_name = ?",
            [name], default=name,
        )
        col_rows = self._duck._fetchall(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = ? ORDER BY ordinal_position",
            [table_name],
        )

        level_rows = self._duck._fetchall(
            "SELECT s.schema_level, COUNT(DISTINCT r.record_id) "
            "FROM _record r JOIN _schema s ON r.schema_id = s.schema_id "
            "WHERE r.type = ? AND NOT COALESCE(r.excluded, FALSE) "
            "GROUP BY s.schema_level",
            [name],
        )

        return VariableDetail(
            **summary.__dict__,
            data_columns=[r[0] for r in col_rows],
            records_by_level={level: int(n) for level, n in level_rows},
        )

    @_timed
    def schema_tree(self) -> SchemaTree:
        keys = list(self._db.dataset_schema_keys)
        tree = SchemaTree(schema_keys=keys)
        if not self._duck._table_exists("_schema"):
            return tree

        key_cols = ", ".join(f'"{k}"' for k in keys)
        rows = self._duck._fetchall(
            f"SELECT schema_id, schema_level, {key_cols} FROM _schema"
        )
        counts = {}
        if self._duck._table_exists("_record"):
            counts = dict(self._duck._fetchall(
                f"SELECT schema_id, COUNT(*) FROM _record "
                f"WHERE {_NOT_INTERNAL_SQL} "
                f"AND NOT COALESCE(excluded, FALSE) AND schema_id IS NOT NULL "
                f"GROUP BY schema_id"
            ))

        # Build the hierarchy: each _schema row is a node at its deepest
        # non-NULL key; ancestors are synthesized when no _schema row exists
        # for them (schema_id=None).
        nodes: dict[tuple, SchemaNode] = {}

        def node_at(path: tuple) -> SchemaNode:
            if path in nodes:
                return nodes[path]
            key, value = path[-1]
            node = SchemaNode(key=key, value=value, schema_level=None,
                              schema_id=None, record_count=0)
            nodes[path] = node
            if len(path) == 1:
                tree.roots.append(node)
            else:
                node_at(path[:-1]).children.append(node)
            return node

        for schema_id, schema_level, *values in rows:
            path = tuple(
                (k, str(v)) for k, v in zip(keys, values) if v is not None
            )
            if not path:
                continue
            node = node_at(path)
            node.schema_id = int(schema_id)
            node.schema_level = schema_level
            node.record_count = int(counts.get(schema_id, 0))

        def sort_rec(children: list[SchemaNode]):
            children.sort(key=lambda n: (n.key, n.value))
            for c in children:
                sort_rec(c.children)

        sort_rec(tree.roots)
        return tree

    @_timed
    def records(
        self,
        variable,
        latest: bool = True,
        include_excluded: bool = False,
        **metadata: Any,
    ) -> list[RecordSummary]:
        type_name = getattr(variable, "__name__", variable)
        nested = self._db._split_metadata(metadata)
        df = self._db._find_record(
            type_name,
            nested_metadata=nested,
            version_id="latest" if latest else "all",
            include_excluded=include_excluded,
        )
        keys = self._db.dataset_schema_keys
        out = []
        for _, row in df.iterrows():
            schema = {
                k: str(row[k]) for k in keys
                if k in row.index and row[k] is not None and not pd.isna(row[k])
            }
            out.append(RecordSummary(
                record_id=str(row["record_id"]),
                variable=str(row["variable_name"]),
                schema=schema,
                timestamp=_iso(row["timestamp"]) or "",
                user_id=None if pd.isna(row.get("user_id")) else str(row["user_id"]),
                content_hash=str(row["content_hash"]),
                schema_version=int(row["schema_version"]),
                excluded=bool(row["excluded"]),
            ))
        return out
