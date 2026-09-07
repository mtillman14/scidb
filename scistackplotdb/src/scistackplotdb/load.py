"""
Loading scidb variables into long-format frames.

The long format itself is nearly free — schema keys are already ordinary
columns once a variable is joined to ``_schema``, which is the same shape
``stat_`` functions receive via ``as_table``. What this module adds is the
part a flat CSV never needed: attaching branch params as columns, and knowing
which schema keys a given variable actually occupies.

Queries go through ``_fetchall``/``_fetchone`` (never ``_execute(...).fetchall()``
— see docs/claude on DuckDB fetch locking) and batch the branch-params walk
rather than asking per record (the N+1 trap).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from scistacklog import Log

LAYER = "scistackplotdb"

#: Column name given to the producing function's version when a variable holds
#: records built by more than one version of its function's source. Named like
#: the stack's other synthetic factor (``source.FIELD_FACTOR`` = ``ColName``)
#: rather than after a database column, because that is what it is to a reader
#: of the figure: a condition, not a record attribute.
VERSION_FACTOR = "CodeVersion"

#: Level given to records that have no producing function at all (raw saves) in
#: a variable that otherwise does carry versions. Without it those rows would
#: hold NaN in the version column and drop silently out of every facet.
RAW_VERSION_LEVEL = "(raw)"

#: Per-row flag for "this record's code version is the newest at ITS OWN schema
#: location". Not a variant factor — a helper the default pin filters on.
#:
#: Pinning has to happen on this rather than on ``CodeVersion == "v2"``, and the
#: difference is not cosmetic. ``CodeVersion`` is numbered per variable type so
#: its levels mean the same thing everywhere, which means pinning a level drops
#: every schema location that was never re-run under the newest code —
#: silently losing subjects from the figure. This flag is resolved per location,
#: so pinning it keeps each location's own newest record and loses nothing.
LATEST_COLUMN = "CodeIsLatest"


@dataclass
class VariableFrame:
    """A variable's records as a long frame, plus what its columns mean."""

    name: str
    frame: pd.DataFrame
    #: Schema keys this variable actually occupies (non-null for its records).
    levels: list[str] = field(default_factory=list)
    #: Data column(s) of the variable's table, excluding record_id.
    data_columns: list[str] = field(default_factory=list)
    #: Variant columns attached from the provenance graph — branch params, plus
    #: the producing function's version when there is more than one.
    variant_columns: list[str] = field(default_factory=list)
    #: Name of the per-row "this is my location's newest code version" flag, or
    #: None when the variable holds only one version. See :data:`LATEST_COLUMN`.
    latest_column: str | None = None

    @property
    def value_column(self) -> str:
        return self.data_columns[0] if self.data_columns else self.name


def schema_keys(db) -> list[str]:
    return list(db._duck.dataset_schema)


def registered_variables(db) -> list[str]:
    rows = db._duck._fetchall("SELECT variable_name FROM _variables ORDER BY variable_name")
    return [row[0] for row in rows]


def table_name_for(db, variable: str) -> str:
    """
    Resolve a variable's data table.

    ``_registered_types.table_name`` is deliberately NOT unique (see the note
    in ``DatabaseManager._ensure_meta_tables``), so every query below also
    filters on ``_record.type`` — reading a shared table without that filter
    would silently mix two variables' records into one plot.
    """
    row = db._duck._fetchone(
        "SELECT table_name FROM _registered_types WHERE type_name = ?", [variable]
    )
    return row[0] if row and row[0] else f"{variable}_data"


def data_columns_for(db, variable: str) -> list[str]:
    table = table_name_for(db, variable)
    rows = db._duck._fetchall(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = ? AND column_name != 'record_id' "
        "ORDER BY ordinal_position",
        [table],
    )
    return [row[0] for row in rows]


def sample_value(db, variable: str) -> Any:
    """
    One value from a variable's data column — enough to classify its shape.

    Deliberately a value rather than a declared SQL type name: the duckdb
    client's own Python type for a cell (float for a scalar column, list for a
    LIST column) is the ground truth, with no dependency on how DuckDB spells
    list/array types across versions. The GUI's pre-existing
    ``_numeric_plot_kind`` made the same call for the same reason.
    """
    columns = data_columns_for(db, variable)
    if not columns:
        return None
    table = table_name_for(db, variable)
    row = db._duck._fetchone(
        f'SELECT t."{columns[0]}" FROM "{table}" t '
        f"JOIN _record r ON t.record_id = r.record_id "
        f"WHERE r.type = ? AND r.excluded IS DISTINCT FROM TRUE "
        f"AND t.\"{columns[0]}\" IS NOT NULL LIMIT 1",
        [variable],
    )
    return row[0] if row else None


def variable_levels(db, variable: str) -> list[str]:
    """
    Which schema keys a variable occupies, without loading any data.

    ``describe()`` needs this for every registered variable, and loading each
    one's full frame to find out would mean reading every 1-D array in the
    database just to open the panel. COUNT ignores NULLs, so one row of counts
    says exactly which keys are populated.
    """
    keys = schema_keys(db)
    if not keys:
        return []
    counts = ", ".join(f'COUNT(s."{key}")' for key in keys)
    row = db._duck._fetchone(
        f"SELECT {counts} FROM _record r "
        f"LEFT JOIN _schema s ON r.schema_id = s.schema_id "
        f"WHERE r.type = ? AND r.excluded IS DISTINCT FROM TRUE",
        [variable],
    )
    if row is None:
        return []
    return [key for key, count in zip(keys, row, strict=True) if count]


def load_variable(db, variable: str, *, with_variants: bool = True) -> VariableFrame:
    """Load every non-excluded record of ``variable`` as a long frame."""
    with Log.timer("load_variable", layer=LAYER, extra=variable):
        keys = schema_keys(db)
        columns = data_columns_for(db, variable)
        if not columns:
            Log.warn("variable %r has no data columns", variable, layer=LAYER)
            return VariableFrame(name=variable, frame=pd.DataFrame())

        table = table_name_for(db, variable)
        schema_select = "".join(f', s."{key}"' for key in keys)
        data_select = "".join(f', t."{column}"' for column in columns)
        query = (
            f"SELECT t.record_id{data_select}{schema_select} "
            f'FROM "{table}" t '
            f"JOIN _record r ON t.record_id = r.record_id "
            f"LEFT JOIN _schema s ON r.schema_id = s.schema_id "
            f"WHERE r.type = ? AND r.excluded IS DISTINCT FROM TRUE"
        )
        rows = db._duck._fetchall(query, [variable])

        frame = pd.DataFrame(
            rows, columns=["record_id", *columns, *keys]
        )
        for key in keys:
            frame[key] = frame[key].map(lambda v: None if v is None else str(v))

        levels = [key for key in keys if frame[key].notna().any()]
        variant_columns: list[str] = []
        latest_column: str | None = None
        if with_variants and len(frame):
            frame, variant_columns, latest_column = attach_variants(db, frame)

        Log.info(
            "loaded %s: %d record(s), levels=%s, variants=%s",
            variable,
            len(frame),
            levels,
            variant_columns or "none",
            layer=LAYER,
        )
        return VariableFrame(
            name=variable,
            frame=frame,
            levels=levels,
            data_columns=columns,
            variant_columns=variant_columns,
            latest_column=latest_column,
        )


def attach_variants(
    db, frame: pd.DataFrame
) -> tuple[pd.DataFrame, list[str], str | None]:
    """
    Add one column per thing that distinguishes these records, from the
    provenance graph: each branch param, plus the producing function's version.

    Returns ``(frame, variant_columns, latest_column)`` — the last being the
    name of the :data:`LATEST_COLUMN` flag when versions are in play, or None.

    This is the correctness-critical step. A variable produced at two filter
    cutoffs has **two records per schema combination**; without these columns
    those rows look like replicates of one another and get overplotted — a
    figure that is wrong in a way that looks like data. With them, the variant
    is an ordinary factor the user must assign (``roles.validate`` refuses to
    let a multi-level variant sit unassigned).

    Branch params alone were not enough. Two records produced by **different
    versions of the same function's source** carry identical branch params, so
    they arrived here indistinguishable and were overplotted as replicates —
    precisely the failure this function exists to prevent, reached by the one
    route it did not cover. ``fn_version`` closes it; scidb sets it only when a
    variable type genuinely holds more than one version, so nothing changes for
    the ordinary single-version case.

    See ``docs/claude/function-version-variants.md``.
    """
    from scidb.provenance_query import variant_identity_batch

    record_ids = frame["record_id"].tolist()
    ident = variant_identity_batch(db._duck, record_ids)

    keys: list[str] = []
    for info in ident.values():
        for key in info["branch_params"]:
            if key not in keys:
                keys.append(key)

    for key in keys:
        frame[key] = [
            _stringify(ident.get(rid, {}).get("branch_params", {}).get(key))
            for rid in record_ids
        ]

    versions = [(ident.get(rid) or {}).get("fn_version") for rid in record_ids]
    latest_column = None
    if any(versions):
        # Never shadow a schema key or a branch param that happens to be called
        # CodeVersion — same guard as the field factor in `source._melt_fields`.
        column = VERSION_FACTOR
        while column in frame.columns:
            column += "_"
        levels = [v or RAW_VERSION_LEVEL for v in versions]
        frame[column] = levels
        keys.append(column)

        latest_column = LATEST_COLUMN
        while latest_column in frame.columns:
            latest_column += "_"
        # Deliberately NOT appended to `keys`: it is a filter helper, not a
        # condition anyone plots by. Keeping it out of the variant columns also
        # keeps it out of `hierarchy.join_frames`, which selects only levels,
        # the value and the variant columns — so a two-measure join simply
        # drops it and falls back to showing every version.
        frame[latest_column] = [
            bool((ident.get(rid) or {}).get("is_latest")) for rid in record_ids
        ]

        Log.info(
            "attached %r: %d record(s) span %d function version(s) %s (%d row(s) "
            "current) — these would otherwise plot as replicates of each other",
            column,
            len(record_ids),
            len(set(levels)),
            sorted(set(levels)),
            int(frame[latest_column].sum()),
            layer=LAYER,
        )

    if not keys:
        return frame, [], None

    Log.debug("attached %d variant column(s): %s", len(keys), keys, layer=LAYER)
    return frame, keys, latest_column


def _stringify(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return str(value)
    return str(value)
