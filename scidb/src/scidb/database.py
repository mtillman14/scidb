"""Database connection and management using SciDuck backend."""

import json
import os
import random
import threading
import time
import warnings
from datetime import datetime
from pathlib import Path
from typing import Type, Any

import numpy as np
import pandas as pd

from .exceptions import (
    AmbiguousParamError,
    AmbiguousVersionError,
    DatabaseNotConfiguredError,
    NotFoundError,
    NotRegisteredError,
)
from .hashing import generate_record_id, canonical_hash
from .log import Log
from .variable import BaseVariable


def _describe_data(val):
    """Return a short type/shape string for logging data values."""
    if isinstance(val, pd.DataFrame):
        return f"DataFrame {val.shape[0]}x{val.shape[1]} cols={list(val.columns)}"
    if isinstance(val, np.ndarray):
        return f"ndarray shape={val.shape} dtype={val.dtype}"
    if isinstance(val, (list, tuple)):
        return f"{type(val).__name__} len={len(val)}"
    if isinstance(val, dict):
        return f"dict keys={list(val.keys())}"
    return type(val).__name__


def _schema_str(value):
    """Stringify a schema key value, converting whole-number floats to int.

    Schema keys are stored as VARCHAR in DuckDB.  str(1.0) → "1.0" but
    str(1) → "1".  MATLAB sends all numbers as float, so without this
    conversion, queries and cache lookups fail because "1.0" ≠ "1".
    """
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _from_schema_str(value):
    """Convert a schema VARCHAR value back to a numeric type if possible.

    Schema keys are stored as VARCHAR, so loaded values are always strings.
    This restores the original type (int or float) so that user-facing
    metadata has the same type as what was originally saved.

    Only converts when the round-trip preserves the original string exactly.
    This keeps zero-padded identifiers like "01" as strings (since str(1) ==
    "1" ≠ "01"), which is critical for subject/trial IDs that must match
    what the user passed into for_each.
    """
    if not isinstance(value, str):
        return value
    try:
        as_int = int(value)
        if str(as_int) == value:
            return as_int
    except (ValueError, TypeError):
        pass
    try:
        as_float = float(value)
        if str(as_float) == value:
            return as_float
    except (ValueError, TypeError):
        pass
    return value

from sciduckdb import (
    SciDuck,
    _infer_duckdb_type, _python_to_storage, _storage_to_python,
    _storage_to_python_column,
    _infer_data_columns, _value_to_storage_row, _dataframe_to_storage_rows,
    _bulk_df_to_storage_rows,
    _flatten_dict, _unflatten_dict,
)


def _match_branch_param(branch_params_dict: dict, key: str, value: Any) -> bool:
    """Match a single branch_params filter key/value against a branch_params dict.

    1. Exact match (covers bare dynamic names and namespaced constant names).
    2. Suffix match for bare constant names (e.g. "low_hz" → "bandpass_filter.low_hz").
    Raises AmbiguousParamError if the bare name matches multiple namespaced keys.
    """
    # Exact match
    if key in branch_params_dict:
        return branch_params_dict[key] == value
    # Suffix match
    suffix = f".{key}"
    hits = [(k, v) for k, v in branch_params_dict.items() if k.endswith(suffix)]
    if len(hits) == 1:
        return hits[0][1] == value
    if len(hits) > 1:
        raise AmbiguousParamError(
            f"'{key}' matches multiple branch params: {[h[0] for h in hits]}"
        )
    return False


# Global database instance (thread-local for safety)
_local = threading.local()


def _is_tabular_dict(data):
    """Return True if data is a dict where ALL values are 1D (or Nx1 column-vector) numpy arrays of equal length."""
    if not isinstance(data, dict) or len(data) == 0:
        return False
    lengths = set()
    for k, v in data.items():
        if not isinstance(v, np.ndarray):
            return False
        # Accept 1D arrays, Nx1 column vectors, and 1xN row vectors (from MATLAB)
        if v.ndim == 1:
            lengths.add(v.shape[0])
        elif v.ndim == 2 and v.shape[0] == 1:
            lengths.add(v.shape[1])
        elif v.ndim == 2 and v.shape[1] == 1:
            lengths.add(v.shape[0])
        else:
            return False
    return len(lengths) == 1


def _get_leaf_paths(d, prefix=()):
    """Recursively get all leaf paths in a nested dict.

    A leaf is any value that is NOT a dict.  Returns a list of tuples,
    each tuple being the sequence of keys from root to leaf.
    """
    paths = []
    for key, value in d.items():
        current = prefix + (key,)
        if isinstance(value, dict):
            paths.extend(_get_leaf_paths(value, current))
        else:
            paths.append(current)
    return paths


def _get_nested_value(d, path):
    """Get a value from a nested dict following *path* (tuple of keys)."""
    current = d
    for key in path:
        current = current[key]
    return current


def _set_nested_value(d, path, value):
    """Set a value in a nested dict by *path*, creating intermediate dicts."""
    for key in path[:-1]:
        d = d.setdefault(key, {})
    d[path[-1]] = value


def _flatten_struct_columns(df):
    """Flatten DataFrame columns that contain nested dicts into dot-separated columns.

    For each object-dtype column whose first non-null value is a ``dict``,
    recursively extract all leaf paths and create new columns named
    ``"original_col.key1.key2.leaf"``.

    **Leaf handling:**
    - Scalar leaves (int, float, str, bool, None) are stored directly.
    - Array leaves (numpy arrays, Python lists) are serialised to a JSON
      string so every cell in the resulting column is a simple scalar type
      that DuckDB can ingest.

    Returns
    -------
    (flattened_df, struct_columns_info)
        *struct_columns_info* maps each flattened original column name to
        metadata needed by ``_unflatten_struct_columns`` on load.
        Empty dict when no struct columns are found.
    """
    if len(df) == 0:
        return df, {}

    struct_info = {}
    cols_to_drop = []
    new_col_data = {}  # ordered: col_name -> list of values

    for col_idx, col in enumerate(df.columns):
        if df[col].dtype != object:
            continue

        # Find first non-null value
        first_val = None
        for v in df[col]:
            if v is not None and not (isinstance(v, float) and np.isnan(v)):
                first_val = v
                break

        if not isinstance(first_val, dict):
            continue

        # This column contains nested dicts — flatten it
        leaf_paths = _get_leaf_paths(first_val)
        if not leaf_paths:
            continue

        array_leaves = {}  # dot_path -> {"dtype": ..., "shape": ...}

        for path in leaf_paths:
            dot_path = ".".join(path)
            flat_col_name = f"{col}.{dot_path}"
            values = []
            for row_val in df[col]:
                if row_val is None or (isinstance(row_val, float) and np.isnan(row_val)):
                    values.append(None)
                    continue
                try:
                    leaf = _get_nested_value(row_val, path)
                except (KeyError, TypeError):
                    values.append(None)
                    continue

                if isinstance(leaf, np.ndarray):
                    # Track array metadata from first occurrence
                    if dot_path not in array_leaves:
                        array_leaves[dot_path] = {
                            "dtype": str(leaf.dtype),
                            "shape": list(leaf.shape),
                        }
                    values.append(json.dumps(leaf.tolist()))
                elif isinstance(leaf, list):
                    if dot_path not in array_leaves:
                        array_leaves[dot_path] = {"dtype": "list"}
                    values.append(json.dumps(leaf))
                else:
                    values.append(leaf)

            new_col_data[flat_col_name] = values

        cols_to_drop.append(col)
        struct_info[col] = {
            "paths": [list(p) for p in leaf_paths],
            "array_leaves": array_leaves,
            "col_position": col_idx,
        }

    if not cols_to_drop:
        return df, {}

    result = df.drop(columns=cols_to_drop)
    for name, values in new_col_data.items():
        result[name] = values

    return result, struct_info


def _unflatten_struct_columns(df, struct_info):
    """Reconstruct nested-dict columns from dot-separated flat columns.

    Inverse of ``_flatten_struct_columns``.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with dot-separated columns produced by ``_flatten_struct_columns``.
    struct_info : dict
        The metadata dict that was stored alongside the data.

    Returns
    -------
    pd.DataFrame with the original nested-dict object columns restored.
    """
    if not struct_info:
        return df

    result = df.copy()

    # Process struct columns in reverse position order so inserts don't shift indices
    for col_name, info in sorted(
        ((k, v) for k, v in struct_info.items() if k != "__list_columns__"),
        key=lambda x: x[1]["col_position"],
        reverse=True,
    ):
        paths = [tuple(p) for p in info["paths"]]
        array_leaves = info.get("array_leaves", {})
        col_position = info["col_position"]

        # Collect all flat column names belonging to this struct
        flat_col_names = [f"{col_name}.{'.'.join(p)}" for p in paths]
        existing_flat = [c for c in flat_col_names if c in result.columns]

        if not existing_flat:
            continue

        # Build nested dicts row by row
        nested_values = []
        n_rows = len(result)

        for row_idx in range(n_rows):
            row_dict = {}
            for path, flat_col in zip(paths, flat_col_names):
                if flat_col not in result.columns:
                    continue
                val = result[flat_col].iloc[row_idx]
                dot_path = ".".join(path)

                # Restore arrays from JSON
                if dot_path in array_leaves and val is not None:
                    arr_meta = array_leaves[dot_path]
                    if isinstance(val, str):
                        parsed = json.loads(val)
                    else:
                        parsed = val
                    if arr_meta.get("dtype") == "list":
                        val = parsed
                    else:
                        val = np.array(parsed, dtype=np.dtype(arr_meta["dtype"]))
                        expected_shape = arr_meta.get("shape")
                        if (expected_shape and list(val.shape) != expected_shape
                                and val.size == np.prod(expected_shape)):
                            val = val.reshape(expected_shape)

                _set_nested_value(row_dict, path, val)
            nested_values.append(row_dict)

        # Drop the flat columns
        result = result.drop(columns=existing_flat)

        # Insert the reconstituted column at its original position
        # (clamped to current column count since other columns may have shifted)
        insert_pos = min(col_position, len(result.columns))
        result.insert(insert_pos, col_name, nested_values)

    # Convert list-valued cells to numpy arrays for MATLAB interop.
    # DuckDB DOUBLE[] columns come back as Python lists; old VARCHAR saves
    # come back as string representations like "[1.0, 2.0, 3.0]".
    for col in result.columns:
        if result[col].dtype != object:
            continue
        first_val = next(
            (v for v in result[col]
             if v is not None and not (isinstance(v, float) and np.isnan(v))),
            None,
        )
        if first_val is None:
            continue

        if isinstance(first_val, (list, np.ndarray)):
            # DuckDB DOUBLE[] returns as lists or numpy arrays — ensure numpy
            result[col] = result[col].apply(
                lambda v: np.array(v, dtype=float) if isinstance(v, list) else v)
        elif isinstance(first_val, str) and first_val.strip().startswith('['):
            # Backwards compat: parse VARCHAR strings from old saves
            def _parse_list_str(v):
                if not isinstance(v, str):
                    return v
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, list):
                        return np.array(parsed, dtype=float)
                except (json.JSONDecodeError, ValueError, TypeError):
                    pass
                return v
            result[col] = result[col].apply(_parse_list_str)

    return result


def get_user_id() -> str | None:
    """
    Get the current user ID from environment.

    The user ID is used for attribution in cross-user provenance tracking.
    Set the SCIDB_USER_ID environment variable to identify the current user.

    Returns:
        The user ID string, or None if not set.
    """
    return os.environ.get("SCIDB_USER_ID")


def _build_lineage_version_keys(result: Any) -> dict:
    """
    Build _record_metadata version_keys from a LineageFcnResult.

    Produces the same ``__fn`` / ``__fn_hash`` / ``__inputs`` / ``__constants``
    format that ``for_each`` writes, so ``list_pipeline_variants()`` and the
    GUI pipeline graph work without changes.

    Three kinds of inputs are recognised:
    - ``LineageFcnResult`` with ``_scidb_variable_type`` tag: upstream result
      that was saved before this call — type name comes from the tag.
    - ``BaseVariable`` instance: a loaded (saved) variable passed directly —
      type name comes from ``type(input_val).__name__``.  Works regardless of
      save order since the type is intrinsic to the object.
    - Everything else: treated as a constant.
    """
    import hashlib
    import inspect as _inspect

    try:
        from scilineage.core import LineageFcnResult
    except ImportError:
        return {}

    fn = result.invoked.fcn.fcn
    fn_name = fn.__name__

    try:
        src = _inspect.getsource(fn)
    except (OSError, TypeError):
        src = fn_name
    fn_hash = hashlib.sha256(src.encode()).hexdigest()[:16]

    input_types: dict = {}   # param_name → BaseVariable type name
    constants: dict = {}     # param_name → scalar value

    for param_name, input_val in result.invoked.inputs.items():
        if isinstance(input_val, LineageFcnResult):
            vtype = getattr(input_val, "_scidb_variable_type", None)
            if vtype:
                input_types[param_name] = vtype
            # No tag → upstream was never saved; skip the edge silently
        elif isinstance(input_val, BaseVariable):
            # Loaded variable passed directly — type is always available
            input_types[param_name] = type(input_val).__name__
        else:
            constants[param_name] = input_val

    keys: dict = {"__fn": fn_name, "__fn_hash": fn_hash}
    # Record the output's position in the function's signature (0-based). The GUI
    # uses this to map class names back to MATLAB param names for handle labels.
    output_num = getattr(result, "output_num", None)
    if output_num is not None:
        keys["__output_num"] = int(output_num)
    if input_types:
        keys["__inputs"] = json.dumps(input_types, sort_keys=True)
    if constants:
        keys["__constants"] = json.dumps(
            {k: str(v) for k, v in sorted(constants.items())},
        )
    return keys


def configure_database(
    dataset_db_path: str | Path,
    dataset_schema_keys: list[str],
) -> "DatabaseManager":
    """
    Configure the global database connection.

    Single-call setup that creates the database, auto-registers all known
    BaseVariable subclasses, and enables thunk caching.

    Args:
        dataset_db_path: Path to the DuckDB database file
        dataset_schema_keys: List of metadata keys that define the dataset schema
            (e.g., ["subject", "visit", "channel"]). These keys identify the
            logical location of data and are used for the folder hierarchy.
            Any metadata keys not in this list are treated as version parameters
            that distinguish different computational versions of the same data.

    Returns:
        The DatabaseManager instance
    """
    db = DatabaseManager(
        dataset_db_path,
        dataset_schema_keys=dataset_schema_keys,
    )
    for cls in BaseVariable._all_subclasses.values():
        db.register(cls)
    db.set_current_db()

    # Propagate schema keys to scifor so that DataFrame detection and
    # distribute=True work identically in DB-backed and standalone modes.
    try:
        import scifor
        scifor.set_schema(list(dataset_schema_keys))
    except ImportError:
        pass

    # Set log file path next to the database file
    from .log import Log
    log_path = Path(dataset_db_path).parent / "scidb.log"
    Log.set_path(str(log_path))
    Log.info(
        f"configure_database: path={dataset_db_path}, "
        f"schema_keys={list(dataset_schema_keys)}"
    )

    return db


def get_database() -> "DatabaseManager":
    """
    Get the global database connection.

    Returns:
        The DatabaseManager instance

    Raises:
        DatabaseNotConfiguredError: If configure_database() hasn't been called
    """
    db = getattr(_local, "database", None)
    if db is None:
        raise DatabaseNotConfiguredError(
            "Database not configured. Call configure_database(path) first."
        )
    if getattr(db, "_closed", False):
        db.reopen()
    return db


class DatabaseManager:
    """
    Manages data storage and lineage persistence (both in DuckDB via SciDuck).

    Example:
        db = configure_database("experiment.duckdb", ["subject", "session"])

        RawSignal.save(np.eye(3), subject=1, session=1)
        loaded = RawSignal.load(subject=1, session=1)
    """

    def __init__(
        self,
        dataset_db_path: str | Path,
        dataset_schema_keys: list[str],
    ):
        """
        Initialize database connection.

        Args:
            dataset_db_path: Path to DuckDB database file (created if doesn't exist)
            dataset_schema_keys: List of metadata keys that define the dataset schema
                (e.g., ["subject", "visit", "channel"]). These keys identify the
                logical location of data. Any other metadata keys are treated as
                version parameters.
        """
        self.dataset_db_path = Path(dataset_db_path)

        if isinstance(dataset_schema_keys, (set, frozenset)):
            raise TypeError(
                "dataset_schema_keys must be an ordered sequence (list or tuple), "
                "not a set. Schema key order defines the dataset hierarchy."
            )
        self.dataset_schema_keys = list(dataset_schema_keys)
        self._registered_types: dict[str, Type[BaseVariable]] = {}

        # Initialize SciDuck backend for data storage and lineage (all in DuckDB)
        self._duck = SciDuck(self.dataset_db_path, dataset_schema=dataset_schema_keys)

        # Create metadata tables for type registration (in DuckDB)
        self._ensure_meta_tables()
        self._ensure_record_metadata_table()
        self._ensure_lineage_table()
        self._ensure_for_each_expected_table()
        self._ensure_schema_overrides_table()

        self._closed = False # Track connection open/closed state

    def _ensure_meta_tables(self):
        """Create internal metadata tables for type registration."""
        # Registered types table (remains in DuckDB for data type discovery)
        # Note: Only type_name is unique (PRIMARY KEY). table_name is not unique
        # to avoid DuckDB's ON CONFLICT ambiguity with multiple unique constraints.
        self._duck._execute("""
            CREATE TABLE IF NOT EXISTS _registered_types (
                type_name VARCHAR PRIMARY KEY,
                table_name VARCHAR NOT NULL,
                schema_version INTEGER NOT NULL,
                registered_at TIMESTAMP DEFAULT current_timestamp
            )
        """)

    def _ensure_record_metadata_table(self):
        """Create the _record_metadata side table for record-level metadata."""
        self._duck._execute("""
            CREATE TABLE IF NOT EXISTS _record_metadata (
                record_id VARCHAR NOT NULL,
                timestamp VARCHAR NOT NULL,
                variable_name VARCHAR NOT NULL,
                schema_id INTEGER NOT NULL,
                version_keys JSON DEFAULT '{}',
                content_hash VARCHAR,
                lineage_hash VARCHAR,
                schema_version INTEGER,
                user_id VARCHAR,
                branch_params JSON DEFAULT '{}',
                excluded BOOLEAN DEFAULT FALSE,
                PRIMARY KEY (record_id, timestamp)
            )
        """)

    def _ensure_lineage_table(self):
        """Create the _lineage table for computation provenance."""
        self._duck._execute("""
            CREATE TABLE IF NOT EXISTS _lineage (
                output_record_id VARCHAR PRIMARY KEY,
                lineage_hash     VARCHAR NOT NULL,
                target           VARCHAR NOT NULL,
                function_name    VARCHAR NOT NULL,
                function_hash    VARCHAR NOT NULL,
                inputs           JSON NOT NULL DEFAULT '[]',
                constants        JSON NOT NULL DEFAULT '[]',
                timestamp        VARCHAR NOT NULL
            )
        """)

    def _ensure_for_each_expected_table(self):
        """Create the _for_each_expected table for persisting expected combos.

        PathInput-only functions have no DB-variable inputs, so
        _get_expected_combos() cannot infer the expected set from
        _record_metadata.  scidb.for_each writes the full expected combo
        set here at runtime so that check_node_state can fall back to it.

        ``call_id`` disambiguates rows when the same function is invoked
        from multiple for_each() call sites (e.g. different inputs, where,
        or constants).  Without it, function_name alone collides and the
        second call clobbers the first's expected set.
        """
        self._duck._execute("""
            CREATE TABLE IF NOT EXISTS _for_each_expected (
                function_name VARCHAR NOT NULL,
                call_id       VARCHAR NOT NULL,
                schema_id     INTEGER NOT NULL,
                branch_params JSON DEFAULT '{}',
                PRIMARY KEY (function_name, call_id, schema_id, branch_params)
            )
        """)

    def _ensure_schema_overrides_table(self):
        """Create __scidb_schema_overrides for persistent schema-level exclusions."""
        from .exclusions import ensure_overrides_table
        ensure_overrides_table(self)

    def _create_variable_view(self, variable_class: Type[BaseVariable]):
        """Create a view joining a variable table with _schema via _record_metadata."""
        table_name = variable_class.table_name()
        view_name = variable_class.view_name()
        schema_cols = ", ".join(f's."{col}"' for col in self.dataset_schema_keys)
        self._duck._execute(f"""
            CREATE OR REPLACE VIEW "{view_name}" AS
            WITH latest_meta AS (
                SELECT record_id, schema_id, version_keys, branch_params, excluded,
                       ROW_NUMBER() OVER (PARTITION BY record_id ORDER BY timestamp DESC) AS rn
                FROM _record_metadata
                WHERE variable_name = '{view_name}'
            )
            SELECT
                t.*,
                s.schema_level, {schema_cols},
                lm.version_keys, lm.branch_params, lm.excluded
            FROM "{table_name}" t
            LEFT JOIN latest_meta lm ON t.record_id = lm.record_id AND lm.rn = 1
            LEFT JOIN _schema s ON lm.schema_id = s.schema_id
        """)

    def _split_metadata(self, flat_metadata: dict) -> dict:
        """
        Split flat metadata into nested schema/version structure.

        Keys in schema_keys go to "schema", all other keys go to "version".
        """
        schema = {}
        version = {}
        for key, value in flat_metadata.items():
            if key in self.dataset_schema_keys:
                schema[key] = value
            else:
                version[key] = value
        return {"schema": schema, "version": version}

    def _infer_schema_level(self, schema_keys: dict) -> str | None:
        """
        Infer the schema level from provided keys.

        Walks dataset_schema_keys top-down. Returns the deepest provided key.
        Keys need not be contiguous — any subset of schema keys is valid.

        Returns None if no schema keys are provided.
        """
        if not schema_keys:
            return None

        level = None
        for key in self.dataset_schema_keys:
            if key in schema_keys:
                level = key
        return level

    def _save_record_metadata(
        self,
        record_id: str,
        timestamp: str,
        variable_name: str,
        schema_id: int,
        version_keys: dict | None,
        content_hash: str | None,
        lineage_hash: str | None,
        schema_version: int,
        user_id: str | None,
        branch_params: dict | None = None,
    ) -> None:
        """Insert a new audit row into _record_metadata. Always inserts (audit trail)."""
        Log.debug(f"_save_record_metadata: {variable_name}, record_id={record_id[:12]}, schema_id={schema_id}")
        vk_json = json.dumps(version_keys or {}, sort_keys=True)
        bp_json = json.dumps(branch_params or {}, sort_keys=True)
        self._duck._execute(
            """
            INSERT INTO _record_metadata (
                record_id, timestamp, variable_name, schema_id,
                version_keys, content_hash, lineage_hash, schema_version, user_id,
                branch_params
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (record_id, timestamp) DO NOTHING
            """,
            [
                record_id, timestamp, variable_name, schema_id,
                vk_json, content_hash, lineage_hash, schema_version, user_id,
                bp_json,
            ],
        )

    def _save_columnar(
        self,
        record_id: str,
        table_name: str,
        variable_class: Type[BaseVariable],
        df: pd.DataFrame,
        schema_level: str | None,
        schema_keys: dict,
        content_hash: str,
        dict_of_arrays: bool = False,
        ndarray_keys: dict | None = None,
        struct_columns: dict | None = None,
    ) -> int:
        """
        Save a DataFrame into a columnar table identified by record_id.

        Used for custom-serialized data (to_db/from_db), native DataFrames,
        and dict-of-arrays data. The table uses record_id as the row identifier;
        multiple data rows sharing the same record_id are allowed.

        Returns schema_id.
        """
        schema_id = (
            self._duck._get_or_create_schema_id(schema_level, schema_keys)
            if schema_level is not None and schema_keys
            else 0
        )

        # Ensure table exists
        table_created = False
        if not self._duck._table_exists(table_name):
            table_created = True
            col_defs = []
            for col in df.columns:
                dtype = df[col].dtype
                if pd.api.types.is_integer_dtype(dtype):
                    ddb_type = "BIGINT"
                elif pd.api.types.is_float_dtype(dtype):
                    ddb_type = "DOUBLE"
                elif pd.api.types.is_bool_dtype(dtype):
                    ddb_type = "BOOLEAN"
                elif dtype == object:
                    first_val = next(
                        (v for v in df[col]
                         if v is not None and not (isinstance(v, float) and np.isnan(v))),
                        None,
                    )
                    if isinstance(first_val, np.ndarray) and np.issubdtype(first_val.dtype, np.number):
                        ddb_type = "DOUBLE[]"
                    elif (isinstance(first_val, list) and len(first_val) > 0
                          and all(isinstance(x, (int, float)) for x in first_val)):
                        ddb_type = "DOUBLE[]"
                    else:
                        ddb_type = "VARCHAR"
                else:
                    ddb_type = "VARCHAR"
                col_defs.append(f'"{col}" {ddb_type}')

            data_cols_sql = ", ".join(col_defs)
            self._duck._execute(f"""
                CREATE TABLE "{table_name}" (
                    record_id VARCHAR NOT NULL,
                    {data_cols_sql}
                )
            """)
            self._create_variable_view(variable_class)
            Log.debug(f"_save_columnar: created table '{table_name}'")

        # Only insert if this record_id doesn't already exist
        existing_count = self._duck._fetchall(
            f'SELECT COUNT(*) FROM "{table_name}" WHERE record_id = ?',
            [record_id],
        )[0][0]

        if existing_count == 0:
            insert_df = df.copy()
            insert_df.insert(0, "record_id", record_id)
            col_str = ", ".join(f'"{c}"' for c in insert_df.columns)
            self._duck.con.execute(
                f'INSERT INTO "{table_name}" ({col_str}) SELECT * FROM insert_df'
            )
            Log.debug(f"_save_columnar: inserted {len(df)} rows into '{table_name}', record_id={record_id[:12]}")
        else:
            Log.debug(f"_save_columnar: record_id={record_id[:12]} already exists in '{table_name}', skipped")

        # Upsert into _variables (one row per variable)
        effective_level = schema_level or self.dataset_schema_keys[-1]
        if dict_of_arrays:
            dtype_json = json.dumps({
                "custom": True,
                "dict_of_arrays": True,
                "ndarray_keys": ndarray_keys or {},
            })
        elif struct_columns:
            dtype_json = json.dumps({
                "custom": True,
                "struct_columns": struct_columns,
            })
        else:
            dtype_json = json.dumps({"custom": True})
        self._duck._execute(
            "INSERT INTO _variables (variable_name, schema_level, dtype, description) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT (variable_name) DO UPDATE SET dtype = excluded.dtype",
            [variable_class.__name__, effective_level, dtype_json, ""],
        )

        return schema_id

    def _save_native(
        self,
        record_id: str,
        table_name: str,
        variable_class: Type[BaseVariable],
        data: Any,
        content_hash: str,
        schema_level: str | None = None,
        schema_keys: dict | None = None,
    ) -> int:
        """
        Save native data as a single record using sciduck's type inference.

        Handles scalars, arrays, lists, dicts (flat & nested), and
        dict-of-arrays.  Each dict key becomes its own DuckDB column;
        vector values become DuckDB array types (e.g. DOUBLE[]).

        The table uses record_id as PRIMARY KEY so identical data is stored once.

        Returns schema_id.
        """
        if schema_level is not None and schema_keys:
            schema_id = self._duck._get_or_create_schema_id(
                schema_level, {k: _schema_str(v) for k, v in schema_keys.items()}
            )
        else:
            schema_id = 0

        data_col_types, dtype_meta = _infer_data_columns(data)
        is_dataframe = isinstance(data, pd.DataFrame)

        # Ensure table exists
        if not self._duck._table_exists(table_name):
            data_cols_sql = ", ".join(f'"{col}" {dtype}' for col, dtype in data_col_types.items())
            if is_dataframe:
                # One DuckDB row per table row: record_id is not unique per row.
                record_id_col = "record_id VARCHAR NOT NULL"
            else:
                record_id_col = "record_id VARCHAR PRIMARY KEY"
            self._duck._execute(f'''
                CREATE TABLE "{table_name}" (
                    {record_id_col},
                    {data_cols_sql}
                )
            ''')
            self._create_variable_view(variable_class)
            Log.debug(f"_save_native: created table '{table_name}'")

        if is_dataframe:
            # Idempotency: skip all inserts if this record_id already exists.
            existing_count = self._duck._fetchall(
                f'SELECT COUNT(*) FROM "{table_name}" WHERE record_id = ?',
                [record_id],
            )[0][0]
            if existing_count == 0:
                col_names = ["record_id"] + list(data_col_types.keys())
                col_str = ", ".join(f'"{c}"' for c in col_names)
                placeholders = ", ".join(["?"] * len(col_names))
                for storage_row in _dataframe_to_storage_rows(data, dtype_meta):
                    self._duck._execute(
                        f'INSERT INTO "{table_name}" ({col_str}) VALUES ({placeholders})',
                        [record_id] + storage_row,
                    )
                Log.debug(f"_save_native: inserted {len(data)} rows (dataframe) into '{table_name}', record_id={record_id[:12]}")
            else:
                Log.debug(f"_save_native: record_id={record_id[:12]} already exists in '{table_name}', skipped")
        else:
            storage_values = _value_to_storage_row(data, dtype_meta)
            col_names = ["record_id"] + list(data_col_types.keys())
            col_str = ", ".join(f'"{c}"' for c in col_names)
            placeholders = ", ".join(["?"] * len(col_names))
            self._duck._execute(
                f'INSERT INTO "{table_name}" ({col_str}) VALUES ({placeholders}) '
                f'ON CONFLICT (record_id) DO NOTHING',
                [record_id] + storage_values,
            )
            Log.debug(f"_save_native: inserted single record into '{table_name}', record_id={record_id[:12]}")

        # Upsert into _variables (one row per variable)
        effective_level = schema_level or self.dataset_schema_keys[-1]
        self._duck._execute(
            "INSERT INTO _variables (variable_name, schema_level, dtype, description) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT (variable_name) DO UPDATE SET dtype = excluded.dtype",
            [variable_class.__name__, effective_level, json.dumps(dtype_meta), ""],
        )

        return schema_id

    def save_batch(
        self,
        variable_class: Type[BaseVariable],
        data_items: list[tuple[Any, dict]],
        profile: bool = False,
    ) -> list[str]:
        """
        Bulk-save a list of (data_value, metadata_dict) pairs for a single variable type.

        Amortizes setup work (registration, table creation) and batches SQL
        operations using DataFrame-based inserts for speed.

        Data is deduplicated by record_id (same content → same record_id → stored once).
        Every call inserts a new (record_id, timestamp) row in _record_metadata for audit.

        Args:
            variable_class: The BaseVariable subclass to save as
            data_items: List of (data_value, flat_metadata_dict) tuples
            profile: If True, print phase-by-phase timing summary

        Returns:
            List of record_ids for each saved item (in input order)
        """
        if not data_items:
            return []

        timings = {}
        t0 = time.perf_counter()

        table_name = self._ensure_registered(variable_class)
        type_name = variable_class.__name__
        schema_version = variable_class.schema_version
        user_id = get_user_id()

        # --- One-time setup from first item ---
        first_data, first_meta = data_items[0]

        data_col_types, dtype_meta = _infer_data_columns(first_data)
        is_dataframe = dtype_meta.get("mode") == "dataframe"
        col_types_str = ", ".join(f"{c}: {t}" for c, t in data_col_types.items())
        Log.info(f"save_batch({type_name}): {len(data_items)} items, "
                 f"mode={dtype_meta.get('mode', 'single_column')}, "
                 f"data: {_describe_data(first_data)}, "
                 f"DuckDB columns: [{col_types_str}]")

        if not self._duck._table_exists(table_name):
            data_cols_sql = ", ".join(f'"{col}" {dtype}' for col, dtype in data_col_types.items())
            if is_dataframe:
                record_id_col = "record_id VARCHAR NOT NULL"
            else:
                record_id_col = "record_id VARCHAR PRIMARY KEY"
            self._duck._execute(f'''
                CREATE TABLE "{table_name}" (
                    {record_id_col},
                    {data_cols_sql}
                )
            ''')
            self._create_variable_view(variable_class)

        timings["1_setup"] = time.perf_counter() - t0

        # --- Detect PyArrow fast path for batch insert ---
        # The Arrow path below indexes `data_val[col]` for each column name,
        # which only works when `data_val` is a dict (i.e. multi_column mode).
        # Single-column mode stores data_val as a bare ndarray/scalar, so
        # `data_val["value"]` would raise IndexError — exclude it here and
        # let it fall through to the generic _value_to_storage_row path.
        _use_arrow = False
        pa = None
        if not is_dataframe and dtype_meta.get("mode") == "multi_column":
            try:
                import pyarrow as pa
                col_metas = dtype_meta.get("columns", {})
                _use_arrow = all(
                    m.get("python_type") == "ndarray" and m.get("ndim", 1) == 1
                    for m in col_metas.values()
                )
            except ImportError:
                pass
        if _use_arrow:
            _arrow_col_arrays: dict[str, list] = {col: [] for col in data_col_types}
            _arrow_record_ids: list[str] = []

        # --- Batch schema_id resolution ---
        t1 = time.perf_counter()
        all_nested = []
        all_branch_params = []  # Extracted before _split_metadata
        unique_schema_combos = {}  # {combo_key: schema_keys_dict}
        for data_val, flat_meta in data_items:
            # Extract __branch_params BEFORE split (it gets its own column, not part of version_keys)
            # This matches the behavior of individual save() at line 1785
            branch_params_for_item = flat_meta.get("__branch_params", {})
            all_branch_params.append(branch_params_for_item)

            # Remove __branch_params from flat_meta before splitting
            flat_meta_cleaned = {k: v for k, v in flat_meta.items() if k != "__branch_params"}
            nested = self._split_metadata(flat_meta_cleaned)
            all_nested.append(nested)
            schema_keys = nested.get("schema", {})
            schema_level = self._infer_schema_level(schema_keys)
            if schema_level is not None and schema_keys:
                key_tuple = tuple(
                    _schema_str(schema_keys.get(k, "")) for k in self.dataset_schema_keys
                    if k in schema_keys
                )
                combo_key = (schema_level, key_tuple)
                if combo_key not in unique_schema_combos:
                    unique_schema_combos[combo_key] = schema_keys

        timings["2_split_metadata"] = time.perf_counter() - t1

        # Resolve schema_ids for all unique combos (batch)
        t2 = time.perf_counter()
        schema_id_cache = self._duck.batch_get_or_create_schema_ids(
            {k: {col: _schema_str(v) for col, v in vals.items()}
             for k, vals in unique_schema_combos.items()}
        )
        timings["3_schema_resolution"] = time.perf_counter() - t2

        # --- Per-row Python computation (no SQL) ---
        t4 = time.perf_counter()
        timestamp = datetime.now().isoformat()
        record_ids = []
        data_table_rows = []   # (record_id, ...data_cols)
        metadata_rows = []     # tuples for _record_metadata

        t4_hash = 0.0
        t4_record_id = 0.0
        t4_storage = 0.0
        t4_meta = 0.0

        # Accumulate DataFrames for bulk storage-row conversion after the loop.
        # Per-row _dataframe_to_storage_rows (54 iloc calls × 7k records) was
        # the dominant cost; _bulk_df_to_storage_rows processes column-by-column.
        _df_bulk: list = []
        _df_bulk_rids: list = []

        for i, (data_val, flat_meta) in enumerate(data_items):
            nested = all_nested[i]
            schema_keys = nested.get("schema", {})
            version_keys = nested.get("version", {})
            schema_level = self._infer_schema_level(schema_keys)

            if schema_level is not None and schema_keys:
                key_tuple = tuple(
                    _schema_str(schema_keys.get(k, "")) for k in self.dataset_schema_keys
                    if k in schema_keys
                )
                schema_id = schema_id_cache[(schema_level, key_tuple)]
            else:
                schema_id = 0

            _t = time.perf_counter()
            content_hash = canonical_hash(data_val)
            t4_hash += time.perf_counter() - _t

            _t = time.perf_counter()
            record_id = generate_record_id(
                class_name=type_name,
                schema_version=schema_version,
                content_hash=content_hash,
                metadata=nested,
            )
            record_ids.append(record_id)
            t4_record_id += time.perf_counter() - _t

            # DataFrames: defer storage-row conversion to the bulk path below.
            _t = time.perf_counter()
            if _use_arrow:
                _arrow_record_ids.append(record_id)
                for col in data_col_types:
                    _arrow_col_arrays[col].append(data_val[col])
            elif is_dataframe:
                _df_bulk.append(data_val)
                _df_bulk_rids.append(record_id)
            else:
                storage_values = _value_to_storage_row(data_val, dtype_meta)
                data_table_rows.append((record_id,) + tuple(storage_values))
            t4_storage += time.perf_counter() - _t

            _t = time.perf_counter()
            vk_json = json.dumps(version_keys or {}, sort_keys=True)
            # Use pre-extracted branch_params (extracted before _split_metadata at line 1013)
            branch_params = all_branch_params[i]
            bp_json = json.dumps(branch_params, sort_keys=True)
            metadata_rows.append((
                record_id, timestamp, type_name, schema_id,
                vk_json, content_hash, None, schema_version, user_id,
                bp_json,
            ))
            t4_meta += time.perf_counter() - _t

        # --- Bulk DataFrame → storage rows (replaces 7k per-row iloc calls) ---
        if _df_bulk:
            _t = time.perf_counter()
            data_table_rows = _bulk_df_to_storage_rows(_df_bulk, _df_bulk_rids, dtype_meta)
            t4_storage += time.perf_counter() - _t

        timings["4_per_row_hashing"] = time.perf_counter() - t4
        timings["4a_canonical_hash"] = t4_hash
        timings["4b_record_id"] = t4_record_id
        timings["4c_storage_row"] = t4_storage
        timings["4d_meta_row"] = t4_meta

        # --- Find which data rows are new (dedup check) ---
        t5 = time.perf_counter()
        if _use_arrow:
            # Arrow path: ON CONFLICT DO NOTHING handles dedup in the INSERT.
            new_data_rows = _arrow_record_ids  # for count only
        elif is_dataframe:
            # No PRIMARY KEY: filter out rows whose record_id already exists.
            all_new_rids = list({row[0] for row in data_table_rows})
            if all_new_rids:
                placeholders_rids = ", ".join(["?"] * len(all_new_rids))
                existing_rids = {r[0] for r in self._duck._fetchall(
                    f'SELECT DISTINCT record_id FROM "{table_name}" '
                    f'WHERE record_id IN ({placeholders_rids})',
                    all_new_rids,
                )}
            else:
                existing_rids = set()
            new_data_rows = [row for row in data_table_rows if row[0] not in existing_rids]
        else:
            # PRIMARY KEY: ON CONFLICT DO NOTHING handles dedup in the INSERT.
            new_data_rows = data_table_rows

        timings["5_dedup_check"] = time.perf_counter() - t5

        # --- Batch inserts ---
        t6 = time.perf_counter()
        self._duck._begin()
        try:
            t6a = time.perf_counter()
            if _use_arrow and _arrow_record_ids:
                # PyArrow fast path: numpy arrays → Arrow buffers → DuckDB (no Python list conversion)
                _NUMPY_TO_ARROW = {
                    'float64': pa.float64(), 'float32': pa.float32(),
                    'int64': pa.int64(), 'int32': pa.int32(),
                    'int16': pa.int16(), 'int8': pa.int8(),
                    'uint64': pa.uint64(), 'uint32': pa.uint32(),
                    'uint16': pa.uint16(), 'uint8': pa.uint8(),
                    'bool': pa.bool_(),
                }
                arrow_data = {'record_id': pa.array(_arrow_record_ids, type=pa.string())}
                for col_name, np_list in _arrow_col_arrays.items():
                    col_meta = dtype_meta["columns"][col_name]
                    numpy_dtype = col_meta.get("numpy_dtype", "float64")
                    arrow_inner = _NUMPY_TO_ARROW.get(numpy_dtype, pa.float64())
                    arrow_data[col_name] = pa.array(np_list, type=pa.list_(arrow_inner))
                arrow_table = pa.table(arrow_data)
                all_columns = list(arrow_data.keys())
                col_str = ", ".join(f'"{c}"' for c in all_columns)
                timings["6a_data_df_create"] = time.perf_counter() - t6a

                t6b = time.perf_counter()
                self._duck.con.execute(
                    f'INSERT INTO "{table_name}" ({col_str}) SELECT * FROM arrow_table '
                    f'ON CONFLICT (record_id) DO NOTHING'
                )
                timings["6b_data_insert"] = time.perf_counter() - t6b
            elif new_data_rows:
                all_columns = ["record_id"] + list(data_col_types.keys())
                data_df = pd.DataFrame(new_data_rows, columns=all_columns)
                col_str = ", ".join(f'"{c}"' for c in all_columns)
                timings["6a_data_df_create"] = time.perf_counter() - t6a

                t6b = time.perf_counter()
                if is_dataframe:
                    self._duck.con.execute(
                        f'INSERT INTO "{table_name}" ({col_str}) SELECT * FROM data_df'
                    )
                else:
                    self._duck.con.execute(
                        f'INSERT INTO "{table_name}" ({col_str}) SELECT * FROM data_df '
                        f'ON CONFLICT (record_id) DO NOTHING'
                    )
                timings["6b_data_insert"] = time.perf_counter() - t6b
            else:
                timings["6a_data_df_create"] = time.perf_counter() - t6a
                timings["6b_data_insert"] = 0.0

            # Always insert metadata rows (audit trail — every execution logged)
            t6c = time.perf_counter()
            meta_df = pd.DataFrame(
                metadata_rows,
                columns=[
                    "record_id", "timestamp", "variable_name", "schema_id",
                    "version_keys", "content_hash", "lineage_hash",
                    "schema_version", "user_id", "branch_params",
                ],
            )
            self._duck.con.execute(
                "INSERT INTO _record_metadata ("
                "record_id, timestamp, variable_name, schema_id, "
                "version_keys, content_hash, lineage_hash, schema_version, user_id, branch_params"
                ") SELECT * FROM meta_df "
                "ON CONFLICT (record_id, timestamp) DO NOTHING"
            )
            timings["6c_meta_insert"] = time.perf_counter() - t6c

            # Upsert _variables (one row per variable)
            t6d = time.perf_counter()
            effective_level = (
                self._infer_schema_level(all_nested[0].get("schema", {}))
                or self.dataset_schema_keys[-1]
            )
            self._duck._execute(
                "INSERT INTO _variables (variable_name, schema_level, dtype, description) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT (variable_name) DO UPDATE SET dtype = excluded.dtype",
                [type_name, effective_level, json.dumps(dtype_meta), ""],
            )
            timings["6d_variables_upsert"] = time.perf_counter() - t6d

            t6e = time.perf_counter()
            self._duck._commit()
            timings["6e_commit"] = time.perf_counter() - t6e
        except Exception:
            try:
                self._duck._execute("ROLLBACK")
            except Exception:
                pass
            raise

        timings["6_batch_inserts"] = time.perf_counter() - t6
        timings["total"] = time.perf_counter() - t0

        n = len(data_items)
        n_new = len(new_data_rows)
        n_total_rows = len(_arrow_record_ids) if _use_arrow else len(data_table_rows)
        Log.info(
            f"[timing] save_batch({type_name}): {n} items ({n_new} new rows, "
            f"{n_total_rows} total storage rows), "
            f"{len(unique_schema_combos)} schemas, {timings['total']:.3f}s"
        )
        for phase, elapsed in timings.items():
            Log.debug(f"  save_batch {phase:30s} {elapsed:.3f}s")

        if profile:
            print(f"\n--- save_batch() profile ({n} items, "
                  f"{len(unique_schema_combos)} unique schemas) ---")
            for phase, elapsed in timings.items():
                print(f"  {phase:30s} {elapsed:8.3f}s")
            print()

        return record_ids

    @staticmethod
    def _has_custom_serialization(variable_class: type) -> bool:
        """Check if a BaseVariable subclass overrides to_db or from_db."""
        return "to_db" in variable_class.__dict__ or "from_db" in variable_class.__dict__

    def _sort_by_schema_keys(self, df: pd.DataFrame) -> pd.DataFrame:
        """Sort DataFrame by schema keys with numeric sorting for numeric-only columns.

        For each schema key:
        - If all values are purely numeric (convertible to float), sort numerically
        - Otherwise, sort alphabetically (lexicographically)

        This ensures "1", "2", "10" sorts as 1, 2, 10 (not "1", "10", "2").
        But "S01", "S02", "S10" or mixed "1", "S01", "10" sorts alphabetically.
        """
        if len(df) == 0:
            return df

        # Create temporary sort columns for each schema key
        sort_cols = []
        sort_ascending = []
        temp_col_names = []

        for key in self.dataset_schema_keys:
            if key not in df.columns:
                continue

            temp_col_name = f"__sort_{key}"
            temp_col_names.append(temp_col_name)

            # Get non-null values to check if column is numeric-only
            col = df[key]
            non_null_mask = col.notna()
            non_null_values = col[non_null_mask]

            # Check if all non-null values are numeric (can be converted to float)
            is_numeric = True
            if len(non_null_values) > 0:
                for val in non_null_values:
                    try:
                        float(str(val))
                    except (ValueError, TypeError):
                        is_numeric = False
                        break

            if is_numeric and len(non_null_values) > 0:
                # Numeric-only: convert to float for numeric sorting
                df[temp_col_name] = pd.to_numeric(col, errors='coerce')
            else:
                # Contains non-numeric: use string sorting
                df[temp_col_name] = col.astype(str)

            sort_cols.append(temp_col_name)
            sort_ascending.append(True)

        # Add timestamp as final tiebreaker (descending)
        if 'timestamp' in df.columns:
            sort_cols.append('timestamp')
            sort_ascending.append(False)

        # Sort by all columns
        if sort_cols:
            df = df.sort_values(sort_cols, ascending=sort_ascending)

        # Drop temporary sort columns
        df = df.drop(columns=temp_col_names, errors='ignore')

        return df

    def _find_record(
        self,
        type_name: str,
        record_id: str | None = None,
        nested_metadata: dict | None = None,
        version_id: str = "all",
        branch_params_filter: dict | None = None,
        include_excluded: bool = False,
    ) -> pd.DataFrame:
        """
        Query _record_metadata to find matching records.

        Supports two modes:
        - By record_id: direct primary key lookup (with JOINs for full row data)
        - By metadata: filter by schema keys via JOIN with _schema, optionally
          filter by version_keys JSON, order by timestamp DESC

        version_id controls which versions are returned:
        - "all" (default): no version filtering (return every version)
        - "latest": only the latest row per (variable_name, schema_id, version_keys)
        - any other string: treated as a record_id for direct lookup

        branch_params_filter: optional dict of branch_params key/value filters
        include_excluded: if False (default), skip records with excluded=TRUE

        Schema key values and version key values may be lists, interpreted as
        "match any" (SQL IN / Python in).

        Returns a DataFrame of matching rows including schema columns and version_keys.
        """
        # Build schema column SELECT list
        schema_col_select = ", ".join(
            f's."{col}"' for col in self.dataset_schema_keys
        )

        excluded_clause = "" if include_excluded else " AND COALESCE(rm.excluded, FALSE) = FALSE"

        if record_id is not None:
            sql = (
                f"SELECT rm.*, {schema_col_select} "
                f"FROM _record_metadata rm "
                f"LEFT JOIN _schema s ON rm.schema_id = s.schema_id "
                f"WHERE rm.record_id = ? AND rm.variable_name = ?{excluded_clause}"
            )
            df = self._duck._fetchdf(sql, [record_id, type_name])
            return self._sort_by_schema_keys(df)

        # Unrecognized version_id → treat as record_id lookup
        if version_id not in ("latest", "all"):
            Log.info(f"_find_record({type_name}): treating version_id={version_id!r} as record_id")
            sql = (
                f"SELECT rm.*, {schema_col_select} "
                f"FROM _record_metadata rm "
                f"LEFT JOIN _schema s ON rm.schema_id = s.schema_id "
                f"WHERE rm.record_id = ? AND rm.variable_name = ?{excluded_clause}"
            )
            df = self._duck._fetchdf(sql, [version_id, type_name])
            return self._sort_by_schema_keys(df)

        # By metadata
        schema_keys = nested_metadata.get("schema", {}) if nested_metadata else {}
        version_keys = nested_metadata.get("version", {}) if nested_metadata else {}

        conditions = ["rm.variable_name = ?"]
        params: list[Any] = [type_name]

        # Exclude excluded variants by default
        if not include_excluded:
            conditions.append("COALESCE(rm.excluded, FALSE) = FALSE")

        # Filter schema keys via _schema columns in SQL (lists → IN)
        for key, value in schema_keys.items():
            if isinstance(value, (list, tuple)):
                placeholders = ", ".join(["?"] * len(value))
                conditions.append(f's."{key}" IN ({placeholders})')
                params.extend([_schema_str(v) for v in value])
            else:
                conditions.append(f's."{key}" = ?')
                params.append(_schema_str(value))

        # branch_params_filter is handled entirely in Python (lines below).
        # We do NOT push it to SQL because:
        # 1. Keys stored in version_keys (direct user saves) would be incorrectly
        #    excluded by a branch_params SQL filter before the Python fallback runs.
        # 2. Suffix matching (e.g. "low_hz" → "bandpass.low_hz") cannot be expressed
        #    in SQL without fetching all records anyway.
        # The Python _match_row already checks version_keys first, then branch_params.
        sql_branch_params_filter = None

        where = " AND ".join(conditions)

        if version_id == "latest":
            # One row per (variable_name, schema_id, version_keys_stripped, branch_params) — latest only.
            # Strip __upstream/__output_num/__lineage_fixed_rids from version_keys to collapse
            # provenance-only variants while keeping distinct branch_params variants separate.
            # branch_params must stay in the partition to prevent merging records that differ
            # only by upstream pipeline parameters (e.g. two Intermediate records from
            # smooth(Filtered(low_hz=20)) vs smooth(Filtered(low_hz=30))).
            # Use regexp_replace to strip provenance-only keys from the JSON string.
            vk_stripped = (
                "regexp_replace("
                "regexp_replace("
                "regexp_replace("
                "rm.version_keys, "
                "'[,]?\"__upstream\":[^,}]+', '', 'g'), "
                "'[,]?\"__output_num\":[^,}]+', '', 'g'), "
                "'[,]?\"__lineage_fixed_rids\":[^,}]+', '', 'g')"
            )
            partition = f"rm.variable_name, rm.schema_id, {vk_stripped}, rm.branch_params"
        else:
            # "all": one row per distinct record_id — deduplicates re-runs of identical
            # data while still returning multiple distinct data records at the same
            # schema location (different content hash → different record_id).
            partition = "rm.record_id"

        sql = (
            f"WITH ranked AS ("
            f"SELECT rm.*, {schema_col_select}, "
            f"ROW_NUMBER() OVER ("
            f"PARTITION BY {partition} "
            f"ORDER BY rm.timestamp DESC"
            f") as rn "
            f"FROM _record_metadata rm "
            f"LEFT JOIN _schema s ON rm.schema_id = s.schema_id "
            f"WHERE {where}"
            f") SELECT * FROM ranked WHERE rn = 1"
        )
        _t_sql = time.perf_counter()
        df = self._duck._fetchdf(sql, params)
        t_sql = time.perf_counter() - _t_sql
        Log.debug(f"_find_record({type_name}): SQL returned {len(df)} records, version_id={version_id}")

        # Collapse provenance-only variants when using version_id="latest".
        # Records differing only in __upstream, __output_num, or __lineage_fixed_rids
        # are temporal updates to the same pipeline step, not distinct variants.
        t_collapse = 0.0
        rows_before_collapse = len(df)
        if version_id == "latest" and len(df) > 0:
            _t_collapse = time.perf_counter()
            from collections import defaultdict
            groups = defaultdict(list)
            # Optimized: use itertuples() instead of iterrows() (10x faster)
            for row in df.itertuples(index=True):
                vk = json.loads(row.version_keys or "{}")
                # Debug: log version_keys for investigation
                Log.debug(f"_find_record: record {row.record_id}: version_keys = {vk}")
                # Strip provenance-only keys
                vk_stripped = {k: v for k, v in vk.items()
                              if k not in ("__upstream", "__output_num", "__lineage_fixed_rids")}
                # Include branch_params in the grouping key to ensure records with
                # different upstream branch parameters are not collapsed together
                bp = getattr(row, "branch_params", "{}")
                group_key = (
                    row.variable_name,
                    row.schema_id,
                    json.dumps(vk_stripped, sort_keys=True),
                    bp  # Add branch_params to distinguish different branch variants
                )
                groups[group_key].append((row.timestamp, row.Index))

            # Keep only the latest record per group
            keep_indices = [max(group)[1] for group in groups.values()]
            collapsed_count = len(df) - len(keep_indices)
            if collapsed_count > 0:
                Log.debug(f"_find_record: collapsed {collapsed_count} provenance-only variant(s)")
            # Apply smart sorting by schema keys (numeric or alphabetic per column)
            df = self._sort_by_schema_keys(df.loc[keep_indices])
            t_collapse = time.perf_counter() - _t_collapse

        # Filter by version keys via Python-side JSON parsing (lists → in)
        # Optimized: parse JSON once per row instead of once per key per row
        t_vk_filter = 0.0
        if version_keys and len(df) > 0:
            _t_vk = time.perf_counter()
            # Parse all version_keys JSON once (vectorized)
            df['_vk_parsed'] = df["version_keys"].apply(
                lambda vk: json.loads(vk) if vk is not None and isinstance(vk, str) else {}
            )
            for key, value in version_keys.items():
                if isinstance(value, (list, tuple)):
                    mask = df['_vk_parsed'].apply(lambda vk, k=key, vals=value: vk.get(k) in vals)
                else:
                    mask = df['_vk_parsed'].apply(lambda vk, k=key, v=value: vk.get(k) == v)
                df = df[mask]
            # Clean up temporary column
            df = df.drop(columns=['_vk_parsed'])
            t_vk_filter = time.perf_counter() - _t_vk

        Log.debug(f"_find_record({type_name}): {len(df)} record(s) matched (before branch_params filter)")

        # Filter by branch_params_filter via Python-side matching.
        # Checks version_keys first (direct saves store non-schema kwargs there),
        # then falls back to branch_params suffix matching (for_each pipeline params).
        t_bp_filter = 0.0
        if branch_params_filter and len(df) > 0:
            _t_bp = time.perf_counter()
            for key, value in branch_params_filter.items():
                def _match_row(row, k=key, v=value):
                    bp = json.loads(row["branch_params"] or "{}") if row.get("branch_params") else {}
                    # Check branch_params ambiguity BEFORE version_keys shortcut:
                    # if the bare key is ambiguous across multiple pipeline steps,
                    # raise AmbiguousParamError even if the key also appears in version_keys.
                    if k not in bp:
                        suffix = f".{k}"
                        hits = [bk for bk in bp if bk.endswith(suffix)]
                        if len(hits) > 1:
                            raise AmbiguousParamError(
                                f"'{k}' matches multiple branch params: {hits}"
                            )
                    vk = json.loads(row["version_keys"] or "{}") if row.get("version_keys") else {}
                    if k in vk:
                        if isinstance(v, (list, tuple)):
                            return vk[k] in v
                        return vk[k] == v
                    return _match_branch_param(bp, k, v)
                df = df[df.apply(_match_row, axis=1)]
            t_bp_filter = time.perf_counter() - _t_bp

        # Apply smart sorting by schema keys before returning
        _t_sort = time.perf_counter()
        result = self._sort_by_schema_keys(df)
        t_sort = time.perf_counter() - _t_sort

        total = t_sql + t_collapse + t_vk_filter + t_bp_filter + t_sort
        Log.info(
            f"[timing] _find_record({type_name}, version_id={version_id!r}): "
            f"total={total:.3f}s, sql={t_sql:.3f}s ({rows_before_collapse} rows), "
            f"collapse={t_collapse:.3f}s, vk_filter={t_vk_filter:.3f}s, "
            f"bp_filter={t_bp_filter:.3f}s, sort={t_sort:.3f}s, "
            f"returned={len(result)} rows"
        )
        return result

    def _reconstruct_metadata_from_row(self, row: pd.Series) -> tuple[dict, dict]:
        """
        Reconstruct flat and nested metadata from a JOINed row.

        The row contains schema columns from _schema and version_keys from
        _variables, which together form the complete metadata.

        Returns (flat_metadata, nested_metadata).
        """
        schema = {}
        for key in self.dataset_schema_keys:
            if key in row.index:
                val = row[key]
                if val is not None and not (isinstance(val, float) and pd.isna(val)):
                    schema[key] = _from_schema_str(val)

        vk_raw = row.get("version_keys")
        version = {}
        if vk_raw is not None and isinstance(vk_raw, str):
            version = json.loads(vk_raw)

        nested_metadata = {"schema": schema, "version": version}
        flat_metadata = {}
        flat_metadata.update(schema)
        flat_metadata.update(version)
        return flat_metadata, nested_metadata

    def _deserialize_custom_subdf(
        self,
        variable_class: type[BaseVariable],
        sub_df: pd.DataFrame,
        dtype_meta: dict,
    ):
        """Deserialize a sub-DataFrame using custom dtype metadata.

        Handles four sub-paths based on dtype_meta flags:
        - dict_of_arrays: reconstruct dict of numpy arrays
        - from_db: class-level custom deserialization
        - struct_columns: unflatten dot-separated columns
        - raw: return DataFrame as-is

        The sub_df must already have internal columns
        (record_id) dropped.
        """
        if dtype_meta.get("dict_of_arrays"):
            ndarray_keys = dtype_meta.get("ndarray_keys", {})
            data = {}
            for col in sub_df.columns:
                arr = sub_df[col].values
                if col in ndarray_keys:
                    col_meta = ndarray_keys[col]
                    arr = arr.astype(np.dtype(col_meta["dtype"]))
                    orig_shape = col_meta.get("shape")
                    if orig_shape and len(orig_shape) == 2:
                        if orig_shape[0] == 1:
                            arr = arr.reshape(1, -1)
                        elif orig_shape[1] == 1:
                            arr = arr.reshape(-1, 1)
                        else:
                            try:
                                arr = arr.reshape(orig_shape)
                            except ValueError:
                                pass
                data[col] = arr
            return data
        elif self._has_custom_serialization(variable_class):
            return variable_class.from_db(sub_df)
        elif dtype_meta.get("struct_columns"):
            return _unflatten_struct_columns(sub_df, dtype_meta["struct_columns"])
        else:
            return sub_df

    def _load_by_record_row(
        self,
        variable_class: type[BaseVariable],
        row: pd.Series,
        loc: Any = None,
        iloc: Any = None,
    ) -> BaseVariable:
        """
        Load a variable instance given a row from _record_metadata.

        Determines native vs custom deserialization from _variables.dtype,
        loads data from the data table by record_id, and constructs the
        BaseVariable instance.
        """
        type_name = row["variable_name"]
        table_name = type_name + "_data"
        record_id = row["record_id"]
        content_hash = row["content_hash"]
        lineage_hash = row["lineage_hash"]
        # Normalize NaN to None (DuckDB may return NaN for NULL in some contexts)
        if lineage_hash is not None and not isinstance(lineage_hash, str):
            lineage_hash = None
        flat_metadata, nested_metadata = self._reconstruct_metadata_from_row(row)

        # Get dtype from _variables to determine deserialization path
        dtype_rows = self._duck._fetchall(
            "SELECT dtype FROM _variables WHERE variable_name = ?",
            [type_name],
        )

        if not dtype_rows:
            raise NotFoundError(
                f"No dtype found for {type_name} in _variables"
            )

        dtype_meta = json.loads(dtype_rows[0][0])
        is_custom = dtype_meta.get("custom", False)

        if is_custom:
            # Custom path: query by record_id
            df = self._duck._fetchdf(
                f'SELECT * FROM "{table_name}" WHERE record_id = ?',
                [record_id],
            )
            # Drop record_id column (internal identifier)
            df = df.drop(columns=["record_id"], errors="ignore")

            if loc is not None:
                if not isinstance(loc, (list, range, slice)):
                    loc = [loc]
                df = df.loc[loc]
            elif iloc is not None:
                if not isinstance(iloc, (list, range, slice)):
                    iloc = [iloc]
                df = df.iloc[iloc]

            data = self._deserialize_custom_subdf(variable_class, df, dtype_meta)
        else:
            # Native path: query by record_id, restore type
            row_df = self._duck._fetchdf(
                f'SELECT * FROM "{table_name}" WHERE record_id = ?',
                [record_id],
            )
            row_df = row_df.drop(columns=["record_id"], errors="ignore")

            mode = dtype_meta.get("mode", "single_column")
            columns_meta = dtype_meta.get("columns", {})

            if mode == "dataframe":
                # One DuckDB row per DataFrame row: apply _storage_to_python per cell.
                result = {}
                for c, meta in columns_meta.items():
                    if c in row_df.columns:
                        result[c] = [_storage_to_python(row_df[c].iloc[i], meta)
                                     for i in range(len(row_df))]
                df_columns = dtype_meta.get("df_columns", list(columns_meta.keys()))
                data = pd.DataFrame(result, columns=df_columns)
            else:
                row_df = self._duck._restore_types(row_df, dtype_meta)
                if len(row_df) == 1:
                    if mode == "single_column":
                        col_name = next(iter(columns_meta))
                        data = row_df[col_name].iloc[0]
                    elif mode == "multi_column":
                        result = {}
                        for c, meta in columns_meta.items():
                            result[c] = _storage_to_python(row_df[c].iloc[0], meta)
                        if dtype_meta.get("nested"):
                            data = _unflatten_dict(result, dtype_meta["path_map"])
                        else:
                            data = result
                    else:
                        data = row_df
                else:
                    data = row_df

        instance = variable_class(data)
        instance.record_id = record_id
        instance.metadata = flat_metadata
        instance.content_hash = content_hash
        instance.lineage_hash = lineage_hash
        try:
            bp_raw = row["branch_params"] if "branch_params" in row.index else None
            instance.branch_params = json.loads(bp_raw or "{}") if isinstance(bp_raw, str) else {}
        except Exception:
            instance.branch_params = {}

        return instance

    def register(self, variable_class: Type[BaseVariable]) -> None:
        """
        Register a variable type for storage.

        Args:
            variable_class: The BaseVariable subclass to register
        """
        type_name = variable_class.__name__
        table_name = variable_class.table_name()
        schema_version = variable_class.schema_version

        # Register in metadata table (skip if already registered)
        existing = self._duck._fetchall(
            "SELECT 1 FROM _registered_types WHERE type_name = ?",
            [type_name],
        )
        if not existing:
            self._duck._execute(
                """
                INSERT INTO _registered_types (type_name, table_name, schema_version)
                VALUES (?, ?, ?)
                """,
                [type_name, table_name, schema_version],
            )

        # Cache locally
        self._registered_types[type_name] = variable_class

    def _ensure_registered(
        self, variable_class: Type[BaseVariable], auto_register: bool = True
    ) -> str:
        """
        Ensure a variable type is registered.

        Returns:
            The table name for this variable type
        """
        type_name = variable_class.__name__

        if type_name in self._registered_types:
            return variable_class.table_name()

        # Check database
        rows = self._duck._fetchall(
            "SELECT table_name FROM _registered_types WHERE type_name = ?",
            [type_name],
        )

        if not rows:
            if auto_register:
                self.register(variable_class)
                return variable_class.table_name()
            else:
                raise NotRegisteredError(
                    f"Variable type '{type_name}' is not registered. "
                    f"No data has been saved for this type yet."
                )

        self._registered_types[type_name] = variable_class
        return rows[0][0]

    def save_variable(
        self,
        variable_class: Type[BaseVariable],
        data: Any,
        index: Any = None,
        **metadata,
    ) -> str:
        """
        Save data as a variable.

        Accepts a BaseVariable instance (which may carry a lineage_hash) or
        raw data. For ThunkOutput / lineage-tracked saves, use
        scihist.save_variable() which wraps this method.

        Args:
            variable_class: The BaseVariable subclass to save as
            data: The data to save (BaseVariable or raw data)
            index: Optional index to set on the DataFrame
            **metadata: Addressing metadata (e.g., subject=1, trial=1)

        Returns:
            The record_id of the saved data
        """
        type_name = variable_class.__name__
        user_keys = {k: v for k, v in metadata.items() if not k.startswith("__")}
        Log.info(f"save_variable({type_name}): metadata={user_keys}")

        lineage_hash = None
        lineage_dict = None
        pipeline_version_keys: dict = {}

        try:
            from scilineage.core import LineageFcnResult
            from scilineage.lineage import extract_lineage
            if isinstance(data, LineageFcnResult):
                # Use the invocation hash (not the result hash) so that
                # find_by_lineage(invocation) can look it up via compute_lineage_hash()
                lineage_hash = data.invoked.hash
                lineage_dict = extract_lineage(data).to_dict()

                # Build version_keys in the same format as for_each() so that
                # list_pipeline_variants() and the GUI can see this function.
                pipeline_version_keys = _build_lineage_version_keys(data)

                # Tag the result object with its variable type name.  Downstream
                # saves that receive this result as an input can then read the tag
                # to populate __inputs in their own version_keys.
                try:
                    data._scidb_variable_type = variable_class.__name__
                except (AttributeError, TypeError):
                    pass

                data = data.data
        except ImportError:
            pass

        if isinstance(data, BaseVariable):
            raw_data = data.data
            lineage_hash = data.lineage_hash
        else:
            raw_data = data

        instance = variable_class(raw_data)

        # Merge pipeline version_keys (from @lineage_fcn) into metadata so that
        # _split_metadata puts them in version_keys → _record_metadata.
        save_metadata = {**metadata, **pipeline_version_keys} if pipeline_version_keys else metadata

        record_id = self.save(
            instance, save_metadata, lineage=lineage_dict, lineage_hash=lineage_hash, index=index,
        )

        instance.record_id = record_id
        instance.metadata = metadata
        instance.lineage_hash = lineage_hash

        Log.info(f"save_variable({type_name}): saved -> record_id={record_id[:12]}")
        return record_id

    def save(
        self,
        variable: BaseVariable,
        metadata: dict,
        lineage: dict | None = None,
        lineage_hash: str | None = None,
        pipeline_lineage_hash: str | None = None,
        index: Any = None,
    ) -> str:
        """
        Save a variable to the database.

        Args:
            variable: The variable instance to save
            metadata: Addressing metadata (flat dict)
            lineage: Optional lineage dict with keys 'function_name', 'function_hash',
                'inputs', 'constants'
            lineage_hash: Optional pre-computed lineage hash (stored in DuckDB
                for input classification when this variable is reused later)
            pipeline_lineage_hash: Optional pre-computed lineage hash for cache
                lookup. If None, falls back to lineage_hash.
            index: Optional index to set on the DataFrame

        Returns:
            The record_id of the saved data
        """
        table_name = self._ensure_registered(type(variable))
        type_name = variable.__class__.__name__
        user_id = get_user_id()

        # Extract __branch_params before splitting metadata (it gets its own column)
        branch_params = None
        if isinstance(metadata, dict) and "__branch_params" in metadata:
            bp_raw = metadata["__branch_params"]
            try:
                branch_params = json.loads(bp_raw) if isinstance(bp_raw, str) else (bp_raw or {})
            except (json.JSONDecodeError, TypeError):
                branch_params = {}
            metadata = {k: v for k, v in metadata.items() if k != "__branch_params"}

        # Split metadata
        nested_metadata = self._split_metadata(metadata)

        # Warn if no metadata keys match the schema (skip internal __* keys)
        user_metadata_keys = [k for k in metadata if not k.startswith("__")]
        if user_metadata_keys and not nested_metadata.get("schema"):
            warnings.warn(
                f"None of the metadata keys {user_metadata_keys} match the "
                f"configured dataset_schema_keys {self.dataset_schema_keys}. "
                f"All keys will be treated as version parameters.",
                UserWarning,
                stacklevel=2,
            )

        # Normalize array.array values to numpy arrays (MATLAB bridge can produce these)
        import array as _array_mod
        if isinstance(variable.data, dict):
            for k, v in variable.data.items():
                if isinstance(v, _array_mod.array):
                    variable.data[k] = np.array(v)

        # Compute content hash
        content_hash = canonical_hash(variable.data)

        # Generate record_id
        record_id = generate_record_id(
            class_name=type_name,
            schema_version=variable.schema_version,
            content_hash=content_hash,
            metadata=nested_metadata,
        )

        serialization = "custom" if self._has_custom_serialization(type(variable)) else "native"
        Log.debug(f"save({type_name}): record_id={record_id[:12]}, content_hash={content_hash[:12]}, serialization={serialization}")

        # Wrap all writes in a single transaction to avoid repeated
        # WAL checkpoints (each auto-committed statement can trigger a
        # checkpoint/fsync, causing random multi-second stalls).
        self._duck._begin()

        try:
            schema_keys = nested_metadata.get("schema", {})
            version_keys = nested_metadata.get("version", {})
            schema_level = self._infer_schema_level(schema_keys)
            created_at = datetime.now().isoformat()

            if self._has_custom_serialization(type(variable)):
                # Custom serialization: user provides to_db() → DataFrame
                df = variable.to_db()

                if index is not None:
                    index_list = list(index) if not isinstance(index, list) else index
                    if len(index_list) != len(df):
                        raise ValueError(
                            f"Index length ({len(index_list)}) does not match "
                            f"DataFrame row count ({len(df)})"
                        )
                    df.index = index

                schema_id = self._save_columnar(
                    record_id, table_name, type(variable), df,
                    schema_level, schema_keys, content_hash,
                )
            else:
                # ALL other data: scalars, arrays, lists, dicts, dict-of-arrays,
                # and native DataFrames (stored as a single record with array-typed
                # columns, e.g. DOUBLE[], BIGINT[], VARCHAR[]).
                schema_id = self._save_native(
                    record_id, table_name, type(variable), variable.data, content_hash,
                    schema_level=schema_level, schema_keys=schema_keys,
                )

            self._save_record_metadata(
                record_id=record_id,
                timestamp=created_at,
                variable_name=type_name,
                schema_id=schema_id,
                version_keys=version_keys,
                content_hash=content_hash,
                lineage_hash=lineage_hash,
                schema_version=variable.schema_version,
                user_id=user_id,
                branch_params=branch_params,
            )

            # Save lineage if provided
            if lineage is not None:
                effective_plh = pipeline_lineage_hash if pipeline_lineage_hash is not None else lineage_hash
                self._save_lineage(
                    record_id, type_name, lineage, effective_plh, user_id,
                    schema_keys=nested_metadata.get("schema"),
                    output_content_hash=content_hash,
                )

            self._duck._commit()
            Log.debug(f"save({type_name}): transaction committed")

        except Exception as e:
            Log.error(f"save({type_name}): transaction rolled back: {e}")
            try:
                self._duck._rollback()
            except Exception:
                pass  # Connection may already be closed
            raise

        return record_id

    def _save_lineage(
        self,
        output_record_id: str,
        output_type: str,
        lineage: dict,
        lineage_hash: str | None = None,
        user_id: str | None = None,
        schema_keys: dict | None = None,
        output_content_hash: str | None = None,
    ) -> None:
        """Save one lineage row to DuckDB _lineage table.

        Args:
            lineage: Dict with keys 'function_name', 'function_hash',
                     'inputs', 'constants'.
        """
        Log.debug(f"_save_lineage: {output_type}, fn={lineage.get('function_name')}, lineage_hash={str(lineage_hash)[:12] if lineage_hash else 'None'}")
        lh = lineage_hash or output_record_id
        inputs_json = json.dumps(lineage.get("inputs", []), sort_keys=True)
        constants_json = json.dumps(lineage.get("constants", {}), sort_keys=True)
        timestamp = datetime.now().isoformat()

        self._duck._execute(
            "INSERT INTO _lineage "
            "(output_record_id, lineage_hash, target, function_name, function_hash, "
            " inputs, constants, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (output_record_id) DO NOTHING",
            [output_record_id, lh, output_type, lineage.get("function_name"),
             lineage.get("function_hash"), inputs_json, constants_json, timestamp],
        )

    def _load_with_where(
        self,
        variable_class: Type[BaseVariable],
        metadata: dict,
        table_name: str,
        where,
        version_id: str = "latest",
    ):
        """Load records using where= filter with version_keys-first strategy.

        When data was saved via for_each with a where= condition, the filter
        string is stored as a ``__where`` version key. This method first tries
        to match records by that version key. If no records are found (e.g. data
        was saved directly without for_each), it falls back to schema-level
        filtering via ``where.resolve()``.

        Returns:
            A pandas DataFrame of matching record rows.

        Raises:
            NotFoundError: If no records match either strategy.
        """
        type_name = variable_class.__name__

        # Strategy 1: filter by __where version key
        augmented = dict(metadata)
        # where can be a string or a Filter object
        # For RawFilter with original string, use that for consistency with save path
        from .filters import RawFilter
        if isinstance(where, str):
            augmented["__where"] = where
        elif isinstance(where, RawFilter) and hasattr(where, '_original_str'):
            augmented["__where"] = where._original_str
        elif hasattr(where, 'to_key'):
            augmented["__where"] = where.to_key()
        else:
            augmented["__where"] = str(where)

        # Optimization: fetch records WITHOUT __where filter first, then apply it in Python
        # This avoids fetching 14k+ records twice (once with __where, once without)
        nested_base = self._split_metadata(metadata)
        records_all = self._find_record(type_name, nested_metadata=nested_base, version_id=version_id)

        if len(records_all) == 0:
            raise NotFoundError(
                f"No {type_name} found matching metadata: {metadata}"
            )

        # Try filtering by __where in Python (fast dict lookup on already-loaded data)
        where_key = augmented.get("__where")
        if where_key:
            records = records_all[
                records_all["version_keys"].apply(
                    lambda vk: json.loads(vk or "{}").get("__where") == where_key
                )
            ].copy()
            if len(records) > 0:
                return records

        # Strategy 2: fallback to schema-level filtering (backward compat)
        # Reuse records_all instead of re-fetching!
        records = records_all
        if len(records) > 0:
            allowed_schema_ids = where.resolve(self, variable_class, table_name)
            records = records[records["schema_id"].isin(allowed_schema_ids)]

        if len(records) == 0:
            raise NotFoundError(
                f"No {type_name} found matching metadata: {metadata} "
                f"with the given where= filter."
            )

        return records

    def load(
        self,
        variable_class: Type[BaseVariable],
        metadata: dict,
        version: str = "latest",
        loc: Any = None,
        iloc: Any = None,
        where=None,
    ) -> BaseVariable:
        """
        Load a single variable matching the given metadata.

        Args:
            variable_class: The type to load
            metadata: Flat metadata dict
            version: "latest" for most recent, or specific record_id
            loc: Optional label-based index selection
            iloc: Optional integer position-based index selection
            where: Optional Filter for restricting which records are loaded.
                When data was saved via for_each with a where= condition, the
                filter is stored as a __where version key. At load time, this
                parameter first tries to match by version key, then falls back
                to schema-level filtering for backward compatibility.

        Returns:
            The matching variable instance
        """
        type_name = variable_class.__name__
        user_summary = {k: v for k, v in metadata.items() if not k.startswith("__")}
        Log.info(f"load({type_name}): metadata={user_summary}")
        table_name = self._ensure_registered(variable_class, auto_register=True)

        try:
            if version != "latest" and version is not None:
                # Load by specific record_id — always include excluded for direct lookup
                records = self._find_record(
                    variable_class.__name__, record_id=version, include_excluded=True,
                )
                if len(records) == 0:
                    raise NotFoundError(f"No data found with record_id '{version}'")
            elif where is not None:
                # where= specified: first try version_keys filtering (__where)
                records = self._load_with_where(
                    variable_class, metadata, table_name, where
                )
            else:
                # Load by metadata (latest version per parameter set)
                nested_metadata = self._split_metadata(metadata)
                records = self._find_record(variable_class.__name__, nested_metadata=nested_metadata, version_id="latest")
                if len(records) == 0:
                    raise NotFoundError(
                        f"No {variable_class.__name__} found matching metadata: {metadata}"
                    )

            # Take the first (latest) record
            row = records.iloc[0]
        except NotFoundError:
            Log.warn(f"load({type_name}): not found for metadata={user_summary}")
            raise
        except Exception as e:
            if "does not exist" in str(e).lower() or "not found" in str(e).lower():
                Log.warn(f"load({type_name}): not found for metadata={user_summary}")
                raise NotFoundError(
                    f"No {variable_class.__name__} found matching metadata: {metadata}"
                )
            raise

        rid = row.get("record_id", "?")
        Log.info(f"load({type_name}): found record_id={str(rid)[:12]}")
        return self._load_by_record_row(variable_class, row, loc=loc, iloc=iloc)

    # -------------------------------------------------------------------------
    # Bulk DataFrame loading engine
    # -------------------------------------------------------------------------

    def _load_as_df_via_iterator(
        self,
        variable_class: Type[BaseVariable],
        metadata: dict,
        *,
        layout: str,
        include_rid: bool,
        include_bp: bool,
        stringify_schema: bool,
        version_id: str,
        where,
        branch_params_filter: dict | None,
    ) -> pd.DataFrame:
        """Slow fallback: load via instance iterator, then assemble DataFrame.

        Mirrors the output shape of the fast path but uses ``db.load_all()`` so
        it is always correct regardless of dtype or subclass customisation.
        """
        schema_keys_set = set(self.dataset_schema_keys)
        view_name = (
            variable_class.view_name()
            if hasattr(variable_class, "view_name")
            else variable_class.__name__
        )

        loaded = list(
            self.load_all(
                variable_class, metadata,
                version_id=version_id, where=where,
                branch_params_filter=branch_params_filter,
            )
        )

        if not loaded:
            return pd.DataFrame()

        def _process_meta(var, *, spread: bool) -> dict:
            meta = dict(var.metadata) if var.metadata else {}
            if spread:
                # Drop __* keys and const-param keys (same as _stringify_meta).
                const_val = meta.get("__constants", {})
                if isinstance(const_val, str):
                    try:
                        const_val = json.loads(const_val)
                    except Exception:
                        const_val = {}
                const_keys = set(const_val.keys()) if const_val else set()
                result = {}
                for k, v in meta.items():
                    if k.startswith("__") or k in const_keys:
                        continue
                    result[k] = str(v) if (k in schema_keys_set and stringify_schema and v is not None) else v
                return result
            else:
                # Packed: include all metadata (current BaseVariable.load(as_df=True) behaviour).
                return meta

        is_spread = (layout == "spread")
        first = loaded[0]

        if hasattr(first, "data") and isinstance(first.data, pd.DataFrame):
            # DataFrame-mode variable
            if layout == "spread":
                all_data: list = []
                all_meta_rows: list = []
                for var in loaded:
                    data_df = var.data
                    meta = _process_meta(var, spread=True)
                    if include_rid:
                        meta["__record_id"] = var.record_id
                    if include_bp:
                        meta["__branch_params"] = json.dumps(var.branch_params or {})
                    nr = len(data_df)
                    for _ in range(nr):
                        all_meta_rows.append(meta)
                    all_data.append(data_df.reset_index(drop=True))
                if not all_meta_rows:
                    return pd.DataFrame()
                combined_meta = pd.DataFrame(all_meta_rows)
                combined_data = pd.concat(all_data, ignore_index=True)
                return pd.concat(
                    [combined_meta.reset_index(drop=True),
                     combined_data.reset_index(drop=True)],
                    axis=1,
                )
            else:  # packed
                rows = []
                for var in loaded:
                    row = _process_meta(var, spread=False)
                    row["data"] = var.data
                    if include_rid:
                        row["__record_id"] = var.record_id
                    if include_bp:
                        row["__branch_params"] = json.dumps(var.branch_params or {})
                    rows.append(row)
                return pd.DataFrame(rows)
        else:
            # Scalar / array / dict mode
            col_name = "data" if layout == "packed" else view_name
            rows = []
            for var in loaded:
                row = _process_meta(var, spread=is_spread)
                row[col_name] = var.data if hasattr(var, "data") else var
                if include_rid:
                    row["__record_id"] = var.record_id if hasattr(var, "record_id") else None
                if include_bp:
                    row["__branch_params"] = json.dumps(
                        var.branch_params if hasattr(var, "branch_params") else {}
                    )
                rows.append(row)
            return pd.DataFrame(rows)

    def _assemble_df_from_records_and_data(
        self,
        records: pd.DataFrame,
        data_df: pd.DataFrame,
        dtype_meta: dict,
        variable_class: Type[BaseVariable],
        *,
        layout: str,
        include_rid: bool,
        include_bp: bool,
        stringify_schema: bool,
    ) -> pd.DataFrame:
        """Assemble the output DataFrame from bulk-fetched records and data.

        Fast path — no per-record Python loops, no BaseVariable construction.
        Called only when all dispatch checks pass (native dtype, no subclass overrides).
        """
        mode = dtype_meta.get("mode", "single_column")
        columns_meta = dtype_meta.get("columns", {})
        data_cols = list(columns_meta.keys())
        schema_keys = self.dataset_schema_keys
        view_name = (
            variable_class.view_name()
            if hasattr(variable_class, "view_name")
            else variable_class.__name__
        )

        # -- Apply vectorized type restoration to data columns --
        for col, col_meta in columns_meta.items():
            if col in data_df.columns:
                data_df[col] = _storage_to_python_column(data_df[col], col_meta)

        # -- Build metadata DataFrame --
        meta_dict: dict = {}

        # Always include record_id temporarily for joining; rename/drop at end.
        meta_dict["__record_id"] = records["record_id"].values

        # Schema columns
        for key in schema_keys:
            if key in records.columns:
                col_series = records[key]
                if stringify_schema:
                    # Values come back as strings from DuckDB VARCHAR columns
                    meta_dict[key] = col_series.values
                else:
                    meta_dict[key] = col_series.apply(
                        lambda v: _from_schema_str(v)
                        if v is not None and not (isinstance(v, float) and pd.isna(v))
                        else None
                    ).values

        # Version keys: parse once per row, then expand into individual columns.
        vk_series = records["version_keys"].apply(
            lambda vk: json.loads(vk) if isinstance(vk, str) and vk else {}
        )

        # Collect which version-key column names to expose in the output.
        all_vk_col_names: dict[str, list] = {}  # name -> [value_or_None per row]
        const_keys_per_row: list[set] = []
        for vk in vk_series:
            ck_val = vk.get("__constants", {})
            if isinstance(ck_val, str):
                try:
                    ck_val = json.loads(ck_val)
                except Exception:
                    ck_val = {}
            const_keys = set(ck_val.keys()) if ck_val else set()
            const_keys_per_row.append(const_keys)

            for k in vk:
                if layout == "spread":
                    # Mirror _stringify_meta: drop __ keys and constant param names
                    if not k.startswith("__") and k not in const_keys:
                        if k not in all_vk_col_names:
                            all_vk_col_names[k] = [None] * len(records)
                else:
                    # Packed: expose all version_keys (current BaseVariable behaviour)
                    if k not in all_vk_col_names:
                        all_vk_col_names[k] = [None] * len(records)

        for i, (vk, ck) in enumerate(zip(vk_series, const_keys_per_row)):
            for col_name in all_vk_col_names:
                if layout == "spread":
                    if not col_name.startswith("__") and col_name not in ck:
                        all_vk_col_names[col_name][i] = vk.get(col_name)
                else:
                    all_vk_col_names[col_name][i] = vk.get(col_name)

        meta_dict.update(all_vk_col_names)

        # Branch params column
        if include_bp:
            meta_dict["__branch_params"] = records["branch_params"].fillna("{}").values

        meta_df = pd.DataFrame(meta_dict)

        # -- Assemble by storage mode --
        if mode == "dataframe":
            df_columns = dtype_meta.get("df_columns", data_cols)

            if layout == "spread":
                # LEFT JOIN meta to data on record_id — handles both 1-row and
                # multi-row records.  For 1-row records (the DummyMixed hot path)
                # this is a direct 1:1 merge with no groupby.
                result = meta_df.merge(
                    data_df,
                    left_on="__record_id",
                    right_on="record_id",
                    how="left",
                )
                result = result.drop(columns=["record_id"], errors="ignore")
                if not include_rid:
                    result = result.drop(columns=["__record_id"], errors="ignore")
                return result.reset_index(drop=True)
            else:  # packed
                # Group data by record_id and build a nested DataFrame per record.
                grouped = data_df.groupby("record_id", sort=False)
                packed_map: dict = {}
                for rid, group in grouped:
                    g = group.drop(columns=["record_id"], errors="ignore").reset_index(drop=True)
                    cols_present = [c for c in df_columns if c in g.columns]
                    packed_map[rid] = g[cols_present] if cols_present else g
                meta_df["data"] = meta_df["__record_id"].map(packed_map)
                if not include_rid:
                    meta_df = meta_df.drop(columns=["__record_id"], errors="ignore")
                return meta_df.reset_index(drop=True)

        elif mode == "single_column":
            # data_df: [record_id, value_col] — one row per record.
            col_name = data_cols[0] if data_cols else None
            if col_name is None:
                if not include_rid:
                    meta_df = meta_df.drop(columns=["__record_id"], errors="ignore")
                return meta_df.reset_index(drop=True)

            out_col = "data" if layout == "packed" else view_name
            data_renamed = data_df[["record_id", col_name]].rename(
                columns={"record_id": "__record_id", col_name: out_col}
            )
            result = meta_df.merge(data_renamed, on="__record_id", how="left")
            if not include_rid:
                result = result.drop(columns=["__record_id"], errors="ignore")
            return result.reset_index(drop=True)

        elif mode == "multi_column":
            # data_df: [record_id, col1, col2, …] — one row per record.
            if layout == "packed":
                data_only = data_df.drop(columns=["record_id"], errors="ignore")
                data_dicts = data_only.to_dict("records")
                data_map = dict(zip(data_df["record_id"], data_dicts))
                meta_df["data"] = meta_df["__record_id"].map(data_map)
                if not include_rid:
                    meta_df = meta_df.drop(columns=["__record_id"], errors="ignore")
                return meta_df.reset_index(drop=True)
            else:  # spread
                data_renamed = data_df.rename(columns={"record_id": "__record_id"})
                result = meta_df.merge(data_renamed, on="__record_id", how="left")
                if not include_rid:
                    result = result.drop(columns=["__record_id"], errors="ignore")
                return result.reset_index(drop=True)

        else:
            # Unknown mode — return just metadata.
            if not include_rid:
                meta_df = meta_df.drop(columns=["__record_id"], errors="ignore")
            return meta_df.reset_index(drop=True)

    def load_all_as_df(
        self,
        variable_class: Type[BaseVariable],
        metadata: dict | None = None,
        *,
        layout: str = "packed",
        include_rid: bool = False,
        include_bp: bool = False,
        stringify_schema: bool = False,
        version_id: str = "latest",
        where=None,
        branch_params_filter: dict | None = None,
    ) -> pd.DataFrame:
        """Bulk load all records of a variable type into a DataFrame.

        Shared engine for two callers:

        * ``BaseVariable.load(as_df=True)`` — ``layout="packed"``, one row per
          record, data stored in a ``"data"`` column.
        * ``foreach._convert_inputs`` — ``layout="spread"``, DataFrame-mode variables
          produce one output row per inner-table row; data columns are spread across
          top-level columns rather than nested.

        Fast path
        ---------
        Fetches records and data in bulk SQL queries and assembles the output with
        vectorised pandas operations.  Applies when all of the following hold:

        * ``variable_class.__init__`` is not overridden (standard construction).
        * ``variable_class`` does not override ``from_db`` (no custom deserialisation).
        * ``dtype_meta`` does not have ``"custom": True`` (native storage only).
        * ``dtype_meta`` does not have ``"nested": True`` (flat multi-column only).

        Fall-back
        ---------
        Any violated condition routes to ``_load_as_df_via_iterator``, which uses the
        ``db.load_all()`` iterator and assembles row-by-row.  Output shape is identical.

        Parameters
        ----------
        variable_class :
            BaseVariable subclass to load.
        metadata :
            Optional flat metadata dict for filtering (default: load all records).
        layout :
            ``"packed"`` — one output row per record; ``"spread"`` — data columns
            spread, multiple rows per record for DataFrame-mode variables.
        include_rid :
            Add ``"__record_id"`` column to the output.
        include_bp :
            Add ``"__branch_params"`` (JSON string) column to the output.
        stringify_schema :
            Keep schema key values as strings (foreach uses this; notebook users
            generally do not).
        version_id :
            ``"latest"`` or ``"all"`` — passed to ``_find_record``.
        where :
            Optional Filter for restricting records.
        branch_params_filter :
            Optional branch_params key/value filter dict.

        Returns
        -------
        pd.DataFrame
            Empty DataFrame when no matching records exist.
        """
        metadata = metadata or {}
        type_name = variable_class.__name__
        table_name = type_name + "_data"

        # Look up dtype metadata — needed for dispatch and deserialisation.
        dtype_rows = self._duck._fetchall(
            "SELECT dtype FROM _variables WHERE variable_name = ?",
            [type_name],
        )
        if not dtype_rows:
            return pd.DataFrame()
        dtype_meta = json.loads(dtype_rows[0][0])

        # -- Dispatch: fast path or iterator fallback? --
        # Class-introspection bailouts
        if variable_class.__init__ is not BaseVariable.__init__:
            return self._load_as_df_via_iterator(
                variable_class, metadata, layout=layout, include_rid=include_rid,
                include_bp=include_bp, stringify_schema=stringify_schema,
                version_id=version_id, where=where,
                branch_params_filter=branch_params_filter,
            )
        if self._has_custom_serialization(variable_class):
            return self._load_as_df_via_iterator(
                variable_class, metadata, layout=layout, include_rid=include_rid,
                include_bp=include_bp, stringify_schema=stringify_schema,
                version_id=version_id, where=where,
                branch_params_filter=branch_params_filter,
            )
        # Storage-mode bailouts
        if dtype_meta.get("custom"):
            return self._load_as_df_via_iterator(
                variable_class, metadata, layout=layout, include_rid=include_rid,
                include_bp=include_bp, stringify_schema=stringify_schema,
                version_id=version_id, where=where,
                branch_params_filter=branch_params_filter,
            )
        if dtype_meta.get("nested"):
            return self._load_as_df_via_iterator(
                variable_class, metadata, layout=layout, include_rid=include_rid,
                include_bp=include_bp, stringify_schema=stringify_schema,
                version_id=version_id, where=where,
                branch_params_filter=branch_params_filter,
            )

        # -- Fast path --
        t0 = time.perf_counter()
        if where is not None:
            try:
                records = self._load_with_where(
                    variable_class, metadata, table_name, where,
                    version_id=version_id,
                )
            except Exception:
                return pd.DataFrame()
        else:
            nested_metadata = self._split_metadata(metadata)
            records = self._find_record(
                type_name, nested_metadata=nested_metadata,
                version_id=version_id,
                branch_params_filter=branch_params_filter,
            )

        if len(records) == 0:
            return pd.DataFrame()

        # Bulk-fetch data rows in chunks to avoid very long IN clauses.
        all_record_ids = records["record_id"].tolist()
        data_cols = list(dtype_meta.get("columns", {}).keys())
        if not data_cols:
            return pd.DataFrame()

        data_select = ", ".join(f'"{c}"' for c in data_cols)
        chunk_size = 500
        chunks: list = []
        t_sql = 0.0
        for start in range(0, len(all_record_ids), chunk_size):
            chunk = all_record_ids[start : start + chunk_size]
            placeholders = ", ".join(["?"] * len(chunk))
            sql = (
                f'SELECT record_id, {data_select} FROM "{table_name}" '
                f"WHERE record_id IN ({placeholders})"
            )
            _t = time.perf_counter()
            chunk_df = self._duck._fetchdf(sql, chunk)
            t_sql += time.perf_counter() - _t
            if not chunk_df.empty:
                chunks.append(chunk_df)

        if not chunks:
            return pd.DataFrame()

        data_df = (
            pd.concat(chunks, ignore_index=True) if len(chunks) > 1 else chunks[0].copy()
        )

        result = self._assemble_df_from_records_and_data(
            records, data_df, dtype_meta, variable_class,
            layout=layout, include_rid=include_rid, include_bp=include_bp,
            stringify_schema=stringify_schema,
        )
        t_total = time.perf_counter() - t0
        Log.info(
            f"[timing] load_all_as_df({type_name}): {len(records)} records, "
            f"layout={layout!r}, sql={t_sql:.3f}s, total={t_total:.3f}s"
        )
        return result

    def load_all(
        self,
        variable_class: Type[BaseVariable],
        metadata: dict,
        version_id: str = "all",
        where=None,
        branch_params_filter: dict | None = None,
    ):
        """
        Load all variables matching the given metadata as a generator.

        Args:
            variable_class: The type to load
            metadata: Flat metadata dict
            version_id: Which versions to return:
                - "all" (default): return every version
                - "latest": return only the latest version per (schema_id, version_keys)
            where: Optional Filter for restricting which records are loaded.
                First tries version_keys filtering (__where), then falls back
                to schema-level filtering for backward compatibility.
            branch_params_filter: Optional dict of branch_params key/value filters.

        Yields:
            BaseVariable instances matching the metadata
        """
        type_name = variable_class.__name__
        user_summary = {k: v for k, v in metadata.items() if not k.startswith("__")}
        Log.info(f"load_all({type_name}): metadata={user_summary}")
        _t_load_all_total = time.perf_counter()
        table_name = self._ensure_registered(variable_class, auto_register=True)

        _t_find = time.perf_counter()
        if where is not None:
            # where= specified: first try version_keys filtering (__where)
            try:
                records = self._load_with_where(
                    variable_class, metadata, table_name, where,
                    version_id=version_id,
                )
            except NotFoundError:
                Log.info(f"load_all({type_name}): no records found")
                return
        else:
            nested_metadata = self._split_metadata(metadata)
            try:
                records = self._find_record(
                    variable_class.__name__, nested_metadata=nested_metadata,
                    version_id=version_id,
                    branch_params_filter=branch_params_filter,
                )
            except NotFoundError:
                Log.info(f"load_all({type_name}): no records found")
                return  # No data

            if len(records) == 0:
                Log.info(f"load_all({type_name}): no records found")
                return
        t_find = time.perf_counter() - _t_find

        Log.info(f"load_all({type_name}): found {len(records)} record(s)")

        # --- Bulk loading path ---

        # 1. Get dtype from _variables (one row per variable)
        _t_dtype = time.perf_counter()
        dtype_rows = self._duck._fetchall(
            "SELECT dtype FROM _variables WHERE variable_name = ?",
            [variable_class.__name__],
        )
        if not dtype_rows:
            return
        dtype_meta = json.loads(dtype_rows[0][0])
        is_custom = dtype_meta.get("custom", False)
        t_dtype = time.perf_counter() - _t_dtype

        # 2. Collect all unique record_ids to fetch
        all_record_ids = records["record_id"].tolist()
        if not all_record_ids:
            return

        # 3. Batch fetch data rows by record_id
        data_lookup: dict[str, Any] = {}  # record_id -> deserialized value

        chunk_size = 500
        t_chunk_sql = 0.0
        t_chunk_deserialize = 0.0
        _t_chunks_total = time.perf_counter()
        for start in range(0, len(all_record_ids), chunk_size):
            chunk = all_record_ids[start:start + chunk_size]
            placeholders = ", ".join(["?"] * len(chunk))

            if is_custom:
                # Custom (columnar) path: fetch all rows for this chunk
                sql = f'SELECT * FROM "{table_name}" WHERE record_id IN ({placeholders})'
                _t = time.perf_counter()
                chunk_df = self._duck._fetchdf(sql, chunk)
                t_chunk_sql += time.perf_counter() - _t

                if len(chunk_df) > 0:
                    _t = time.perf_counter()
                    grouped = chunk_df.groupby("record_id", sort=False)
                    for rid, sub_df in grouped:
                        sub_df = sub_df.drop(
                            columns=["record_id"], errors="ignore"
                        ).reset_index(drop=True)
                        data_lookup[rid] = self._deserialize_custom_subdf(
                            variable_class, sub_df, dtype_meta,
                        )
                    t_chunk_deserialize += time.perf_counter() - _t
            else:
                # Native path
                data_cols = list(dtype_meta.get("columns", {}).keys())
                data_select = ", ".join(f'"{c}"' for c in data_cols)
                sql = (
                    f'SELECT record_id, {data_select} FROM "{table_name}" '
                    f'WHERE record_id IN ({placeholders})'
                )
                _t = time.perf_counter()
                chunk_df = self._duck._fetchdf(sql, chunk)
                t_chunk_sql += time.perf_counter() - _t

                if len(chunk_df) > 0:
                    _t = time.perf_counter()
                    mode = dtype_meta.get("mode", "single_column")
                    columns_meta = dtype_meta.get("columns", {})

                    if mode == "dataframe":
                        # One DuckDB row per DataFrame row: group by record_id.
                        df_columns = dtype_meta.get("df_columns", list(columns_meta.keys()))
                        for rid, group_df in chunk_df.groupby("record_id", sort=False):
                            group_df = group_df.drop(
                                columns=["record_id"], errors="ignore"
                            ).reset_index(drop=True)
                            result = {}
                            for c, meta in columns_meta.items():
                                if c in group_df.columns:
                                    # Optimized: use tolist() instead of iloc[i] (5-10x faster)
                                    result[c] = [_storage_to_python(val, meta)
                                                 for val in group_df[c].tolist()]
                            data_lookup[rid] = pd.DataFrame(result, columns=df_columns)
                    else:
                        # Non-DataFrame: restore types, then one value per record_id row.
                        restored = chunk_df[data_cols].copy()
                        restored = self._duck._restore_types(restored, dtype_meta)

                        if mode == "single_column":
                            col_name = next(iter(columns_meta))
                            for i, rid in enumerate(chunk_df["record_id"].tolist()):
                                data_lookup[rid] = restored[col_name].iloc[i]
                        elif mode == "multi_column":
                            for i, rid in enumerate(chunk_df["record_id"].tolist()):
                                result = {}
                                for c, meta in columns_meta.items():
                                    result[c] = _storage_to_python(restored[c].iloc[i], meta)
                                if dtype_meta.get("nested"):
                                    data_lookup[rid] = _unflatten_dict(result, dtype_meta["path_map"])
                                else:
                                    data_lookup[rid] = result
                        else:
                            col_names = list(columns_meta.keys())
                            for i, rid in enumerate(chunk_df["record_id"].tolist()):
                                data_lookup[rid] = {c: restored[c].iloc[i] for c in col_names}
                    t_chunk_deserialize += time.perf_counter() - _t

        t_chunks_total = time.perf_counter() - _t_chunks_total
        n_chunks = (len(all_record_ids) + chunk_size - 1) // chunk_size
        _mode_str = 'custom' if is_custom else dtype_meta.get('mode', 'single_column')
        Log.info(
            f"[timing] load_all({type_name}): pre-yield setup: "
            f"find={t_find:.3f}s, dtype_lookup={t_dtype:.3f}s, "
            f"chunks_total={t_chunks_total:.3f}s "
            f"(sql={t_chunk_sql:.3f}s, deserialize={t_chunk_deserialize:.3f}s, "
            f"n_chunks={n_chunks}, mode={_mode_str})"
        )

        # 4. Construct instances using itertuples + inline metadata.
        # This is a generator: per-yield body cost is measured cumulatively
        # and emitted in a TOTAL summary after the last yield.
        schema_keys = self.dataset_schema_keys
        n_yielded = 0
        t_yield_body = 0.0
        for row in records.itertuples(index=False):
            _t_body = time.perf_counter()
            record_id = row.record_id

            if record_id not in data_lookup:
                t_yield_body += time.perf_counter() - _t_body
                continue

            data_value = data_lookup[record_id]
            content_hash = row.content_hash
            lineage_hash = row.lineage_hash
            if lineage_hash is not None and not isinstance(lineage_hash, str):
                lineage_hash = None

            flat_metadata = {}
            for sk in schema_keys:
                val = getattr(row, sk, None)
                if val is not None and not (isinstance(val, float) and pd.isna(val)):
                    flat_metadata[sk] = _from_schema_str(val)
            vk_raw = getattr(row, "version_keys", None)
            if vk_raw is not None and isinstance(vk_raw, str):
                flat_metadata.update(json.loads(vk_raw))

            instance = variable_class(data_value)
            instance.record_id = record_id
            instance.metadata = flat_metadata
            instance.content_hash = content_hash
            instance.lineage_hash = lineage_hash
            bp_raw = getattr(row, "branch_params", None)
            instance.branch_params = json.loads(bp_raw or "{}") if isinstance(bp_raw, str) else {}

            n_yielded += 1
            t_yield_body += time.perf_counter() - _t_body
            yield instance

        t_total = time.perf_counter() - _t_load_all_total
        _caller_overhead = t_total - t_find - t_chunks_total - t_yield_body - t_dtype
        Log.info(
            f"[timing] load_all({type_name}): TOTAL={t_total:.3f}s "
            f"(find={t_find:.3f}s, chunks={t_chunks_total:.3f}s, "
            f"yield_body={t_yield_body:.3f}s for {n_yielded} records, "
            f"caller_overhead~={_caller_overhead:.3f}s)"
        )

    def list_versions(
        self,
        variable_class: Type[BaseVariable],
        include_excluded: bool = False,
        **metadata,
    ) -> list[dict]:
        """
        List all versions at a schema location.

        Args:
            variable_class: The type to query
            include_excluded: If True, include excluded variants in results.
            **metadata: Schema metadata to match; non-schema keys are treated
                as branch_params filters.

        Returns:
            List of dicts with record_id, schema, branch_params, timestamp
            (plus "excluded" bool when include_excluded=True).
        """
        self._ensure_registered(variable_class, auto_register=True)

        schema_keys_set = set(self.dataset_schema_keys)
        schema_metadata = {k: v for k, v in metadata.items() if k in schema_keys_set}
        branch_params_filter = {k: v for k, v in metadata.items() if k not in schema_keys_set} or None

        nested_metadata = self._split_metadata(schema_metadata)

        try:
            records = self._find_record(
                variable_class.__name__,
                nested_metadata=nested_metadata,
                version_id="all",
                branch_params_filter=branch_params_filter,
                include_excluded=include_excluded,
            )
        except Exception:
            return []

        results = []
        for _, row in records.iterrows():
            _, nested = self._reconstruct_metadata_from_row(row)
            bp_raw = row.get("branch_params") if hasattr(row, 'get') else row["branch_params"]
            bp = json.loads(bp_raw or "{}") if isinstance(bp_raw, str) else {}
            entry = {
                "record_id": row["record_id"],
                "schema": nested.get("schema", {}),
                "branch_params": bp,
                "timestamp": row["timestamp"],
            }
            if include_excluded:
                exc = row.get("excluded") if hasattr(row, 'get') else row["excluded"]
                entry["excluded"] = bool(exc) if exc is not None else False
            results.append(entry)

        # Sort by timestamp descending
        results.sort(key=lambda x: x["timestamp"], reverse=True)
        return results

    def _resolve_record_id(
        self,
        record_id_or_type: "str | Type[BaseVariable]",
        **kwargs,
    ) -> str:
        """Resolve a record_id string or (variable_class, **kwargs) to a single record_id.

        Raises AmbiguousVersionError if multiple records match, NotFoundError if none.
        Always searches including excluded records.
        """
        if isinstance(record_id_or_type, str):
            return record_id_or_type

        variable_class = record_id_or_type
        schema_keys_set = set(self.dataset_schema_keys)
        schema_metadata = {k: v for k, v in kwargs.items() if k in schema_keys_set}
        branch_params_filter = {k: v for k, v in kwargs.items() if k not in schema_keys_set} or None

        nested_metadata = self._split_metadata(schema_metadata)
        records = self._find_record(
            variable_class.__name__,
            nested_metadata=nested_metadata,
            version_id="all",
            branch_params_filter=branch_params_filter,
            include_excluded=True,
        )

        if len(records) == 0:
            raise NotFoundError(
                f"No {variable_class.__name__} found matching: {kwargs}"
            )
        if len(records) > 1:
            ids = records["record_id"].tolist()
            raise AmbiguousVersionError(
                f"{len(records)} records match for {variable_class.__name__} "
                f"with {kwargs}. "
                f"Pass a record_id directly or narrow with more branch parameters. "
                f"Matching record_ids: {ids}"
            )
        return records.iloc[0]["record_id"]

    def exclude_variant(
        self,
        record_id_or_type: "str | Type[BaseVariable]",
        **kwargs,
    ) -> int:
        """Mark variant(s) as excluded from automatic inclusion in for_each and load().

        If multiple variants match the provided metadata, ALL matching variants
        are excluded (e.g., all branch_params for a given schema combo).

        Usage:
            db.exclude_variant("abc123")                                  # by record_id (1 variant)
            db.exclude_variant(DetectedSpikes, subject="S01", low_hz=20)  # specific variant
            db.exclude_variant(DetectedSpikes, subject="S01")             # all variants for S01

        Returns:
            Number of variants excluded.
        """
        if isinstance(record_id_or_type, str):
            # Direct record_id provided - exclude just that one
            self._duck._execute(
                "UPDATE _record_metadata SET excluded = TRUE WHERE record_id = ?",
                [record_id_or_type],
            )
            return 1

        # Variable class + kwargs: find and exclude ALL matching records
        variable_class = record_id_or_type
        schema_keys_set = set(self.dataset_schema_keys)
        schema_metadata = {k: v for k, v in kwargs.items() if k in schema_keys_set}
        branch_params_filter = {k: v for k, v in kwargs.items() if k not in schema_keys_set} or None

        nested_metadata = self._split_metadata(schema_metadata)
        records = self._find_record(
            variable_class.__name__,
            nested_metadata=nested_metadata,
            version_id="all",
            branch_params_filter=branch_params_filter,
            include_excluded=True,
        )

        if len(records) == 0:
            raise NotFoundError(
                f"No {variable_class.__name__} found matching: {kwargs}"
            )

        # Exclude all matching records
        record_ids = records["record_id"].tolist()
        for rid in record_ids:
            self._duck._execute(
                "UPDATE _record_metadata SET excluded = TRUE WHERE record_id = ?",
                [rid],
            )

        if len(record_ids) > 1:
            Log.info(
                f"Excluded {len(record_ids)} variant(s) of {variable_class.__name__} "
                f"matching {kwargs}"
            )
        return len(record_ids)

    def include_variant(
        self,
        record_id_or_type: "str | Type[BaseVariable]",
        **kwargs,
    ) -> int:
        """Re-include previously excluded variant(s).

        If multiple variants match the provided metadata, ALL matching variants
        are re-included.

        Usage:
            db.include_variant("abc123")                                  # by record_id (1 variant)
            db.include_variant(DetectedSpikes, subject="S01", low_hz=20)  # specific variant
            db.include_variant(DetectedSpikes, subject="S01")             # all variants for S01

        Returns:
            Number of variants re-included.
        """
        if isinstance(record_id_or_type, str):
            # Direct record_id provided - include just that one
            self._duck._execute(
                "UPDATE _record_metadata SET excluded = FALSE WHERE record_id = ?",
                [record_id_or_type],
            )
            return 1

        # Variable class + kwargs: find and include ALL matching records
        variable_class = record_id_or_type
        schema_keys_set = set(self.dataset_schema_keys)
        schema_metadata = {k: v for k, v in kwargs.items() if k in schema_keys_set}
        branch_params_filter = {k: v for k, v in kwargs.items() if k not in schema_keys_set} or None

        nested_metadata = self._split_metadata(schema_metadata)
        records = self._find_record(
            variable_class.__name__,
            nested_metadata=nested_metadata,
            version_id="all",
            branch_params_filter=branch_params_filter,
            include_excluded=True,
        )

        if len(records) == 0:
            raise NotFoundError(
                f"No {variable_class.__name__} found matching: {kwargs}"
            )

        # Re-include all matching records
        record_ids = records["record_id"].tolist()
        for rid in record_ids:
            self._duck._execute(
                "UPDATE _record_metadata SET excluded = FALSE WHERE record_id = ?",
                [rid],
            )

        if len(record_ids) > 1:
            Log.info(
                f"Re-included {len(record_ids)} variant(s) of {variable_class.__name__} "
                f"matching {kwargs}"
            )
        return len(record_ids)

    def get_provenance(
        self,
        variable_class: Type[BaseVariable] | None,
        version: str | None = None,
        **metadata,
    ) -> dict | None:
        """
        Get the provenance (lineage) of a variable.

        Returns:
            Dict with function_name, function_hash, inputs, constants
            or None if no lineage recorded
        """
        if version:
            record_id = version
        else:
            var = self.load(variable_class, metadata)
            record_id = var.record_id

        rows = self._duck._fetchall(
            "SELECT function_name, function_hash, inputs, constants "
            "FROM _lineage WHERE output_record_id = ?",
            [record_id],
        )
        if not rows:
            return None

        function_name, function_hash, inputs_json, constants_json = rows[0]
        return {
            "function_name": function_name,
            "function_hash": function_hash,
            "inputs": json.loads(inputs_json),
            "constants": json.loads(constants_json),
        }

    def get_provenance_by_schema(self, **schema_keys) -> list[dict]:
        """
        Get all provenance records at a schema location (schema-aware view).

        Args:
            **schema_keys: Schema key filters (e.g., subject="S01", session="1")

        Returns:
            List of lineage record dicts matching the schema keys
        """
        conditions = ["rm.lineage_hash IS NOT NULL"]
        params: list[Any] = []
        for key, value in schema_keys.items():
            conditions.append(f's."{key}" = ?')
            params.append(_schema_str(value))

        where = " AND ".join(conditions)
        rows = self._duck._fetchall(
            f"SELECT l.output_record_id, rm.variable_name, "
            f"l.function_name, l.function_hash, l.inputs, l.constants "
            f"FROM _lineage l "
            f"JOIN _record_metadata rm ON l.output_record_id = rm.record_id "
            f"LEFT JOIN _schema s ON rm.schema_id = s.schema_id "
            f"WHERE {where}",
            params,
        )

        results = []
        for record_id, variable_name, function_name, function_hash, inputs_json, constants_json in rows:
            results.append({
                "output_record_id": record_id,
                "output_type": variable_name,
                "function_name": function_name,
                "function_hash": function_hash,
                "inputs": json.loads(inputs_json),
                "constants": json.loads(constants_json),
            })
        return results

    def get_pipeline_structure(self) -> list[dict]:
        """
        Get the abstract pipeline structure (schema-blind view).

        Returns unique (function_name, function_hash, output_type, input_types)
        combinations, describing how variable types flow through functions
        without reference to specific data instances or schema locations.

        Returns:
            List of dicts with keys: function_name, function_hash, output_type,
            input_types (list of type names)
        """
        rows = self._duck._fetchall(
            "SELECT DISTINCT target, function_name, function_hash, inputs FROM _lineage"
        )
        seen = set()
        results = []
        for target, function_name, function_hash, inputs_json in rows:
            inputs = json.loads(inputs_json)
            input_types = tuple(sorted(
                inp.get("type", inp.get("source_function", "unknown"))
                for inp in inputs
            ))
            key = (function_name, function_hash, target, input_types)
            if key not in seen:
                seen.add(key)
                results.append({
                    "function_name": function_name,
                    "function_hash": function_hash,
                    "output_type": target,
                    "input_types": list(input_types),
                })
        return results

    def list_pipeline_variants(
        self,
        output_type: str | None = None,
    ) -> list[dict]:
        """
        List all distinct pipeline step variants recorded in the database.

        Each entry represents a unique (function, constants, output_type)
        combination — a "branch" of the pipeline. Two for_each runs on the
        same function with different constants produce two separate entries.

        Uses version_keys metadata stored by for_each; does not require the
        scilineage tracking system.

        Args:
            output_type: Optional variable type name to filter results
                         (e.g. "Filtered"). If None, all types are returned.

        Returns:
            List of dicts with keys:
                function_name (str),
                output_type   (str),
                call_id       (str: 16 hex chars; identifies the for_each call
                               site that produced this variant.  Same across
                               cosmetic source edits to the fn body),
                input_types   (dict: param_name → type_name),
                constants     (dict: param_name → value),
                output_num    (int | None: 0-based position in the fn signature;
                               None for legacy records written before __output_num
                               was added),
                record_count  (int: distinct records for this variant)
        """
        from .foreach_config import call_id_from_version_keys

        sql = "SELECT variable_name, version_keys, record_id FROM _record_metadata"
        params: list = []
        if output_type is not None:
            sql += " WHERE variable_name = ?"
            params = [output_type]

        rows = self._duck._fetchall(sql, params)

        # Group by (variable_name, version_keys_without___upstream) in Python.
        # __upstream encodes which upstream variant was used (for record_id uniqueness)
        # but should not split pipeline-level grouping — two for_each calls with the
        # same (fn, constants) are the same pipeline step regardless of upstream.
        from collections import defaultdict
        group_record_ids: dict = defaultdict(set)
        group_info: dict = {}

        for variable_name, version_keys_json, record_id in rows:
            vk = json.loads(version_keys_json or "{}") if version_keys_json else {}
            fn_name = vk.get("__fn")
            if not fn_name:
                continue  # Raw .save() record — no function, skip

            inputs_raw = vk.get("__inputs", "{}")
            constants_raw = vk.get("__constants", "{}")
            input_types = (
                json.loads(inputs_raw) if isinstance(inputs_raw, str) else (inputs_raw or {})
            )
            constants = (
                json.loads(constants_raw) if isinstance(constants_raw, str) else (constants_raw or {})
            )

            # Strip __upstream for pipeline-level grouping
            vk_for_group = {k: v for k, v in vk.items() if k != "__upstream"}
            group_key = (variable_name, json.dumps(vk_for_group, sort_keys=True))

            group_record_ids[group_key].add(record_id)
            if group_key not in group_info:
                output_num = vk.get("__output_num")
                group_info[group_key] = {
                    "function_name": fn_name,
                    "output_type": variable_name,
                    "call_id": call_id_from_version_keys(vk),
                    "input_types": input_types,
                    "constants": constants,
                    "output_num": output_num,
                }

        results = []
        for group_key, record_ids in group_record_ids.items():
            info = group_info[group_key]
            results.append({**info, "record_count": len(record_ids)})

        return results

    def get_aggregated_variants(
        self,
        fn_name: str | None = None,
        call_id: str | None = None,
    ) -> dict:
        """
        Get aggregated variant data for pipeline visualization.

        Aggregates variants by (fn_name, call_id) and collects metadata about
        functions, variables, constants, and path inputs. This provides all the
        data needed to build a pipeline graph in one query.

        Args:
            fn_name: Optional function name to filter results.
            call_id: Optional call_id to filter to a specific for_each call site.

        Returns:
            Dict with keys:

            ``"functions"`` (dict)
                Keyed by (fn_name, call_id) tuples::

                    {
                        (fn_name, call_id): {
                            "input_params": {param: var_type},
                            "outputs": [var_type1, var_type2],
                            "constants": {param: [val1, val2]},
                            "variant_count": int,
                            "variants": [variant_dicts],
                        }
                    }

            ``"variables"`` (dict)
                Variable metadata keyed by variable name::

                    {
                        var_type: {
                            "record_count": int,
                        }
                    }

            ``"constants"`` (dict)
                Constants used across functions::

                    {
                        const_name: {
                            "values": [{"value": val, "record_count": N}],
                            "functions": [(fn_name, call_id), ...],
                        }
                    }

            ``"path_inputs"`` (dict)
                PathInput parameters::

                    {
                        param_name: {
                            "template": str,
                            "root_folder": str | None,
                            "functions": [(fn_name, call_id), ...],
                        }
                    }
        """
        import re
        from collections import defaultdict

        def _parse_path_input(value: str) -> dict | None:
            """Parse PathInput from __inputs value string."""
            # New JSON format
            if value.startswith("{"):
                try:
                    parsed = json.loads(value)
                    if parsed.get("__type") == "PathInput":
                        return {
                            "template": parsed["template"],
                            "root_folder": parsed.get("root_folder"),
                        }
                except (json.JSONDecodeError, KeyError):
                    pass

            # Legacy repr format: PathInput('...', root_folder=PosixPath('...'))
            if value.startswith("PathInput("):
                m = re.match(r"PathInput\('([^']*)'", value)
                if m:
                    template = m.group(1)
                    root_match = re.search(
                        r"root_folder=(?:Posix|Windows|Pure\w*)?Path\('([^']*)'\)", value
                    )
                    root = root_match.group(1) if root_match else None
                    return {"template": template, "root_folder": root}

            return None

        # Fetch base variant data
        variants = self.list_pipeline_variants()

        # Apply filters
        if fn_name is not None:
            variants = [v for v in variants if v["function_name"] == fn_name]
        if call_id is not None:
            variants = [v for v in variants if v.get("call_id") == call_id]

        # Initialize result structure
        functions = defaultdict(lambda: {
            "input_params": {},
            "outputs": [],
            "constants": defaultdict(list),
            "variant_count": 0,
            "variants": [],
        })
        all_var_types = set()
        const_counts = defaultdict(lambda: defaultdict(int))
        const_fns = defaultdict(set)
        fn_constants_map = defaultdict(set)
        path_inputs = {}

        # Aggregate variants by (fn_name, call_id)
        for v in variants:
            fn = v["function_name"]
            cid = v.get("call_id", "")
            if not cid:
                continue  # Skip legacy variants without call_id

            fkey = (fn, cid)
            out = v["output_type"]
            inputs = v["input_types"]
            constants = v["constants"]
            count = v["record_count"]

            # Track variable types
            all_var_types.add(out)

            # Process inputs
            for param_name, type_val in inputs.items():
                # Check if it's a PathInput
                pi = _parse_path_input(type_val)
                if pi is not None:
                    if param_name not in path_inputs:
                        path_inputs[param_name] = {
                            **pi,
                            "functions": set(),
                        }
                    path_inputs[param_name]["functions"].add(fkey)
                else:
                    all_var_types.add(type_val)
                    functions[fkey]["input_params"][param_name] = type_val

            # Track outputs
            if out not in functions[fkey]["outputs"]:
                functions[fkey]["outputs"].append(out)

            # Track constants
            for k, val in constants.items():
                const_counts[k][str(val)] += count
                const_fns[k].add(fkey)
                fn_constants_map[fkey].add(k)
                if val not in functions[fkey]["constants"][k]:
                    functions[fkey]["constants"][k].append(val)

            # Track variant
            functions[fkey]["variants"].append({
                "input_types": inputs,
                "constants": constants,
                "output_type": out,
                "record_count": count,
            })
            functions[fkey]["variant_count"] += 1

        # Get variable record counts
        variables = {}
        for var_type in all_var_types:
            rows = self._duck._fetchall(
                "SELECT COUNT(DISTINCT record_id) FROM _record_metadata "
                "WHERE variable_name = ? AND excluded = FALSE",
                [var_type],
            )
            record_count = rows[0][0] if rows else 0
            variables[var_type] = {"record_count": record_count}

        # Build constants result
        constants_result = {}
        for const_name in const_counts:
            values = [
                {"value": val, "record_count": cnt}
                for val, cnt in sorted(const_counts[const_name].items())
            ]
            constants_result[const_name] = {
                "values": values,
                "functions": list(const_fns[const_name]),
            }

        # Convert functions dict to regular dict (remove defaultdict)
        functions_result = {}
        for fkey, data in functions.items():
            functions_result[fkey] = {
                "input_params": dict(data["input_params"]),
                "outputs": data["outputs"],
                "constants": {k: list(v) for k, v in data["constants"].items()},
                "variant_count": data["variant_count"],
                "variants": data["variants"],
            }

        # Convert path_inputs functions to lists
        for param_name in path_inputs:
            path_inputs[param_name]["functions"] = list(path_inputs[param_name]["functions"])

        return {
            "functions": functions_result,
            "variables": variables,
            "constants": constants_result,
            "path_inputs": path_inputs,
        }

    def filter_variants_for_execution(
        self,
        fn_name: str,
        call_id: str,
        schema_filter: dict[str, list] | None = None,
        constant_overrides: dict[str, Any] | None = None,
    ) -> list[dict]:
        """
        Filter variants for execution based on schema and constant selection.

        This method prepares variants for execution by:
        1. Getting variants for the specified function and call_id
        2. Filtering by schema_filter if provided
        3. Applying constant_overrides (replacing DB constants)
        4. Deduplicating the result

        Args:
            fn_name: Function name to filter.
            call_id: Call site identifier (16 hex chars).
            schema_filter: Optional dict of {schema_key: [selected_values]} to
                filter variants by. Only variants matching these schema values
                will be included.
            constant_overrides: Optional dict of {constant_name: value} to
                override database constants. When provided, these values replace
                the constants from the database for all matching variants.

        Returns:
            List of variant dicts ready for for_each execution::

                [
                    {
                        "input_types": {param: var_type},
                        "output_type": var_type,
                        "constants": {param: value},
                    }
                ]

            The list is deduplicated so identical variants appear only once.

        Example::

            # Get variants for a function, overriding threshold constant
            variants = db.filter_variants_for_execution(
                fn_name="process_signal",
                call_id="abc123def456789",
                schema_filter={"subject": [1, 2]},  # Only subjects 1 and 2
                constant_overrides={"threshold": 0.75},  # Override with 0.75
            )
        """
        # Get all variants for this function and call_id
        all_variants = self.list_pipeline_variants()
        fn_variants = [
            v for v in all_variants
            if v["function_name"] == fn_name and v.get("call_id") == call_id
        ]

        if not fn_variants:
            return []

        # Build result variants
        result_variants = []
        seen = set()  # For deduplication

        for variant in fn_variants:
            input_types = variant["input_types"]
            output_type = variant["output_type"]
            constants = dict(variant["constants"])  # Make a copy

            # Apply constant overrides
            if constant_overrides:
                for const_name, const_value in constant_overrides.items():
                    if const_name in constants:
                        constants[const_name] = const_value

            # Create variant dict
            result_variant = {
                "input_types": input_types,
                "output_type": output_type,
                "constants": constants,
            }

            # Deduplicate by converting to a hashable key
            key = (
                output_type,
                tuple(sorted(input_types.items())),
                tuple(sorted(constants.items())),
            )

            if key not in seen:
                seen.add(key)
                result_variants.append(result_variant)

        # Note: schema_filter is intentionally NOT applied here because
        # for_each handles schema filtering via **metadata_iterables.
        # The schema_filter parameter is kept for API compatibility with the
        # original plan, but filtering by schema happens at execution time,
        # not during variant selection.

        return result_variants

    def get_upstream_provenance(
        self,
        record_id: str,
        max_depth: int = 20,
    ) -> list[dict]:
        """
        Traverse the full upstream provenance chain for a record.

        Walks backwards through the pipeline: for each record, inspects its
        version_keys (__fn, __inputs) to determine what variable types it was
        derived from, then finds those upstream records at the same schema
        location using branch_params subset matching (the upstream record's
        branch_params must be a subset of the current record's branch_params).

        Does not require the scilineage tracking system; uses version_keys
        and branch_params metadata stored by for_each.

        Args:
            record_id: The record_id to trace backwards from.
            max_depth: Maximum number of hops to follow (guards against cycles).

        Returns:
            Flat list of provenance nodes ordered from the queried record
            outward (BFS order). Each dict has keys:
                record_id     (str),
                variable_type (str),
                schema        (dict),
                branch_params (dict),
                function_name (str | None),
                constants     (dict),
                depth         (int, 0 = queried record),
                inputs        (list of {record_id, param_name, variable_type})
        """
        schema_col_select = ", ".join(f's."{col}"' for col in self.dataset_schema_keys)

        visited: set = set()
        result: list = []
        queue: list = [(record_id, 0)]

        while queue:
            current_id, depth = queue.pop(0)
            if current_id in visited or depth > max_depth:
                continue
            visited.add(current_id)

            # Fetch this record's metadata
            rows = self._duck._fetchdf(
                f"SELECT rm.record_id, rm.variable_name, rm.version_keys, "
                f"rm.branch_params, rm.schema_id, {schema_col_select} "
                f"FROM _record_metadata rm "
                f"LEFT JOIN _schema s ON rm.schema_id = s.schema_id "
                f"WHERE rm.record_id = ? "
                f"ORDER BY rm.timestamp DESC LIMIT 1",
                [current_id],
            )
            if rows.empty:
                continue

            row = rows.iloc[0]
            vk = json.loads(row["version_keys"] or "{}") if row.get("version_keys") else {}
            bp = json.loads(row["branch_params"] or "{}") if row.get("branch_params") else {}
            fn_name = vk.get("__fn")
            # Handle both dict (new format) and JSON string (old format) for backward compatibility
            if "__inputs" in vk:
                input_types: dict = vk["__inputs"] if isinstance(vk["__inputs"], dict) else json.loads(vk["__inputs"])
            else:
                input_types = {}
            if "__constants" in vk:
                constants: dict = vk["__constants"] if isinstance(vk["__constants"], dict) else json.loads(vk["__constants"])
            else:
                constants = {}

            schema = {}
            for k in self.dataset_schema_keys:
                if k in row.index:
                    val = row[k]
                    if val is not None and not (isinstance(val, float) and pd.isna(val)):
                        schema[k] = _from_schema_str(val)

            schema_id = int(row["schema_id"])

            # For each input type, find the upstream record at the same schema
            # location whose branch_params is a subset of this record's branch_params.
            input_nodes: list = []
            for param_name, type_name in input_types.items():
                candidates = self._duck._fetchdf(
                    "SELECT DISTINCT rm.record_id, rm.branch_params "
                    "FROM _record_metadata rm "
                    "WHERE rm.variable_name = ? AND rm.schema_id = ? "
                    "AND COALESCE(rm.excluded, FALSE) = FALSE",
                    [type_name, schema_id],
                )

                matched_rid = None
                best_match_size = -1
                for _, cand in candidates.iterrows():
                    cand_bp = json.loads(cand["branch_params"] or "{}") if cand["branch_params"] else {}
                    # cand_bp must be a subset of bp (every key in cand_bp matches bp)
                    if all(bp.get(k) == v for k, v in cand_bp.items()):
                        # Prefer the most specific match (most keys)
                        if len(cand_bp) > best_match_size:
                            matched_rid = cand["record_id"]
                            best_match_size = len(cand_bp)

                if matched_rid:
                    input_nodes.append({
                        "record_id": matched_rid,
                        "param_name": param_name,
                        "variable_type": type_name,
                    })

            result.append({
                "record_id": current_id,
                "variable_type": row["variable_name"],
                "schema": schema,
                "branch_params": bp,
                "function_name": fn_name,
                "constants": constants,
                "depth": depth,
                "inputs": input_nodes,
            })

            for inp in input_nodes:
                queue.append((inp["record_id"], depth + 1))

        return result

    def has_lineage(self, record_id: str) -> bool:
        """Check if a variable has lineage information."""
        rows = self._duck._fetchall(
            "SELECT lineage_hash FROM _record_metadata "
            "WHERE record_id = ? AND lineage_hash IS NOT NULL",
            [record_id],
        )
        return len(rows) > 0 and bool(rows[0][0])

    def find_record_id(
        self,
        variable_class: type,
        metadata: dict,
        branch_params_filter: dict | None = None,
    ) -> str | None:
        """Lightweight lookup returning the record_id of the latest record for
        a variable + metadata combination, without loading any data.

        Args:
            variable_class: The BaseVariable subclass to look up.
            metadata: Flat dict of schema keys (and optionally version keys).
            branch_params_filter: Optional namespaced branch_params dict
                (e.g. ``{"bandpass_filter.low_hz": 20}``) used for variant
                disambiguation via suffix matching.  Do NOT merge these into
                ``metadata`` — they must go through the branch_params path so
                that namespaced keys like ``fn.param`` match their un-namespaced
                counterparts stored in ``version_keys``.

        Returns None if no matching record exists.
        """
        nested = self._split_metadata(metadata)
        rows = self._find_record(
            variable_class.__name__,
            nested_metadata=nested,
            version_id="latest",
            branch_params_filter=branch_params_filter or None,
        )
        if rows.empty:
            return None
        return rows.iloc[0]["record_id"]

    def get_latest_record_id_for_variant(self, used_record_id: str) -> str | None:
        """Given a record_id, find the most recently saved record that shares the
        same (variable_name, schema_id, version_keys).

        This is the "current latest" for that specific variable variant —
        the same record that load(..., version_id="latest") would return.
        Returns None if the record no longer exists.
        """
        rows = self._duck._fetchdf(
            "SELECT variable_name, schema_id, version_keys "
            "FROM _record_metadata WHERE record_id = ? LIMIT 1",
            [used_record_id],
        )
        if rows.empty:
            return None

        vn = rows.iloc[0]["variable_name"]
        sid = int(rows.iloc[0]["schema_id"])
        vk = rows.iloc[0]["version_keys"]

        latest = self._duck._fetchdf(
            "SELECT record_id FROM _record_metadata "
            "WHERE variable_name = ? AND schema_id = ? AND version_keys IS NOT DISTINCT FROM ? "
            "AND COALESCE(excluded, FALSE) = FALSE "
            "ORDER BY timestamp DESC LIMIT 1",
            [vn, sid, vk],
        )
        if latest.empty:
            return None
        return latest.iloc[0]["record_id"]

    def get_function_hash_for_record(self, record_id: str) -> str | None:
        """Return the function_hash stored in _lineage for a record, or None.

        Used by scihist.for_each's skip_computed check to detect whether the
        function that produced a record has changed since it was saved.
        """
        rows = self._duck._fetchall(
            "SELECT function_hash FROM _lineage WHERE output_record_id = ?",
            [record_id],
        )
        return rows[0][0] if rows and rows[0][0] else None

    def get_lineage_inputs(self, record_id: str) -> list[dict]:
        """Return the list of input descriptors stored in _lineage for a record.

        Each entry is a dict as written by scilineage's ClassifiedInput.to_lineage_dict().
        Entries with ``source_type == "variable"`` carry a ``record_id`` field
        that identifies the exact input record used when this output was saved.

        Returns an empty list if no lineage row exists for the record.
        """
        rows = self._duck._fetchall(
            "SELECT inputs FROM _lineage WHERE output_record_id = ?",
            [record_id],
        )
        if not rows or not rows[0][0]:
            return []
        try:
            return json.loads(rows[0][0])
        except (json.JSONDecodeError, TypeError):
            return []

    def get_lineage_constants(self, record_id: str) -> list[dict]:
        """Return the list of constant descriptors stored in _lineage for a record.

        Each entry is a dict with 'name', 'value_hash', 'value_repr', 'value_type'.

        Returns an empty list if no lineage row exists for the record.
        """
        rows = self._duck._fetchall(
            "SELECT constants FROM _lineage WHERE output_record_id = ?",
            [record_id],
        )
        if not rows or not rows[0][0]:
            return []
        try:
            result = json.loads(rows[0][0])
            return result if isinstance(result, list) else []
        except (json.JSONDecodeError, TypeError):
            return []

    def get_record_version_keys(self, record_id: str) -> dict:
        """Return the version_keys dict stored in _record_metadata for a record.

        Used by scihist.for_each's skip_computed check to compare __rid_*
        values between the current combo and the stored output record.

        Returns an empty dict if the record doesn't exist or has no version_keys.
        """
        rows = self._duck._fetchall(
            "SELECT version_keys FROM _record_metadata WHERE record_id = ? LIMIT 1",
            [record_id],
        )
        if not rows or not rows[0][0]:
            return {}
        try:
            return json.loads(rows[0][0])
        except (json.JSONDecodeError, TypeError):
            return {}

    # -------------------------------------------------------------------------
    # Export Methods
    # -------------------------------------------------------------------------

    def export_to_csv(
        self,
        variable_class: Type[BaseVariable],
        path: str,
        **metadata,
    ) -> int:
        """Export matching variables to a CSV file."""
        results = list(self.load_all(variable_class, metadata))

        if not results:
            raise NotFoundError(
                f"No {variable_class.__name__} found matching metadata: {metadata}"
            )

        all_dfs = []
        for var in results:
            df = variable_class(var.data).to_db()
            df["_record_id"] = var.record_id
            if var.metadata:
                for key, value in var.metadata.items():
                    df[f"_meta_{key}"] = value
            all_dfs.append(df)

        combined = pd.concat(all_dfs, ignore_index=True)
        combined.to_csv(path, index=False)

        return len(results)

    def find_by_lineage_hash(self, lineage_hash: str) -> list | None:
        """
        Find output values by pipeline lineage hash.

        Low-level lookup used by scihist.find_by_lineage(). Queries
        _record_metadata joined to _lineage for records matching the given hash.

        Args:
            lineage_hash: The pipeline lineage hash to look up

        Returns:
            List of output values if found, None otherwise
        """
        records = self._duck._fetchall(
            "SELECT DISTINCT rm.record_id, rm.variable_name "
            "FROM _record_metadata rm "
            "JOIN _lineage l ON rm.record_id = l.output_record_id "
            "WHERE l.lineage_hash = ?",
            [lineage_hash],
        )
        if not records:
            return None

        results = []
        has_generated = False
        for record_id, variable_name in records:
            # Track generated entries (lineage-only, no data stored)
            if record_id.startswith("generated:"):
                has_generated = True
                continue

            var_class = self._get_variable_class(variable_name)
            if var_class is None:
                return None

            try:
                # Load data from DuckDB
                var = self.load(var_class, {}, version=record_id)
                results.append(var.data)
            except (KeyError, NotFoundError):
                # Record not found
                return None

        if results:
            return results
        if has_generated:
            return [None]
        return None

    def find_by_lineage(self, invocation) -> list | None:
        """
        Find output values by a lineage invocation object.

        Computes the lineage hash from the invocation and delegates to
        find_by_lineage_hash. Accepts any invocation with a
        compute_lineage_hash() method (e.g. LineageFcnInvocation,
        MatlabLineageFcnInvocation).

        Args:
            invocation: An invocation object with compute_lineage_hash()

        Returns:
            List of output values if found, None otherwise
        """
        lineage_hash = invocation.compute_lineage_hash()
        return self.find_by_lineage_hash(lineage_hash)

    def _get_variable_class(self, type_name: str):
        """Get a variable class by name (class name, not table name)."""
        if type_name in self._registered_types:
            return self._registered_types[type_name]

        return BaseVariable.get_subclass_by_name(type_name)

    def distinct_schema_values(self, key: str) -> list:
        """Return all distinct values stored for a schema key.

        Args:
            key: A schema key name (e.g. "subject", "session")

        Returns:
            Sorted list of distinct non-null values for that key
        """
        return self._duck.distinct_schema_values(key)

    def distinct_schema_combinations(self, keys: list[str]) -> list[tuple]:
        """Return all distinct combinations for multiple schema keys.

        Args:
            keys: List of schema key names (e.g. ["subject", "session"])

        Returns:
            List of tuples of distinct non-null value combinations (strings)
        """
        return self._duck.distinct_schema_combinations(keys)

    def list_variables(self) -> "pd.DataFrame":
        """Return all variable types stored in this database.

        Queries the ``_variables`` table and returns a DataFrame with columns:
        ``variable_name``, ``schema_level``, ``created_at``, ``description``.

        Useful for discovering what variable types exist in a database file
        without needing the original Python class definitions.
        """
        return self._duck.list_variables()

    # -------------------------------------------------------------------------
    # Variable Groups
    # -------------------------------------------------------------------------

    @staticmethod
    def _resolve_var_name(v) -> str:
        """Resolve a single variable to its name string.

        Accepts a Python str, a BaseVariable subclass (class object),
        or a MATLAB BaseVariable instance (matlab.object with class name).
        """
        if isinstance(v, str):
            return v
        if isinstance(v, type) and issubclass(v, BaseVariable):
            return v.table_name()
        # MATLAB objects cross the bridge as matlab.object; try str()
        # to extract the class name (e.g. "StepLength").
        s = str(v)
        if s:
            return s
        raise TypeError(
            f"Expected a string or BaseVariable subclass, got {type(v)}"
        )

    @staticmethod
    def _resolve_var_names(variables) -> list:
        """Resolve a single or list/iterable of variables to name strings.

        Each element can be a string, a BaseVariable subclass, or a MATLAB
        object.  Accepts Python lists, MATLAB cell arrays, and MATLAB string
        arrays (any iterable).
        """
        # Scalar: single string or single class
        if isinstance(variables, (str, type)):
            return [DatabaseManager._resolve_var_name(variables)]
        # Any iterable (Python list, MATLAB cell array, MATLAB string array)
        try:
            return [DatabaseManager._resolve_var_name(v) for v in variables]
        except TypeError:
            # Not iterable — treat as a single item
            return [DatabaseManager._resolve_var_name(variables)]

    def add_to_var_group(self, group_name: str, variables):
        """Add one or more variables to a variable group.

        Args:
            group_name: Name of the group.
            variables: A BaseVariable subclass, a variable name string,
                or a list of either.
        """
        self._duck.add_to_group(group_name, self._resolve_var_names(variables))

    def remove_from_var_group(self, group_name: str, variables):
        """Remove one or more variables from a variable group.

        Args:
            group_name: Name of the group.
            variables: A BaseVariable subclass, a variable name string,
                or a list of either.
        """
        self._duck.remove_from_group(group_name, self._resolve_var_names(variables))

    def list_var_groups(self) -> list:
        """List all variable group names.

        Returns:
            Sorted list of distinct group names.
        """
        return self._duck.list_groups()

    def get_var_group(self, group_name: str) -> list:
        """Get all variable classes in a variable group.

        Args:
            group_name: Name of the group.

        Returns:
            Sorted list of BaseVariable subclasses in the group.
        """
        names = self._duck.get_group(group_name)
        classes = []
        for name in names:
            cls = BaseVariable.get_subclass_by_name(name)
            if cls is None:
                raise NotRegisteredError(
                    f"Variable '{name}' in group '{group_name}' has no "
                    f"registered BaseVariable subclass."
                )
            classes.append(cls)
        return classes

    def close(self):
        """Close the database connection."""
        self._duck.close()
        # remove global reference
        if getattr(_local, "database", None) is self:
            self._closed = True

    def reopen(self):
        # reopen DuckDB
        if self._duck is None:
            self._duck = SciDuck(self.dataset_db_path, dataset_schema=self.dataset_schema_keys)
        else:
            self._duck.reopen()
        self._closed = False

    def set_current_db(self):
        """Set this DatabaseManager as the active global database."""
        _local.database = self
        self._closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
