"""DB-backed for_each wrapper — loads inputs, delegates loop to scifor, saves outputs."""

import json
import time
import warnings
from dataclasses import dataclass, field
from typing import Any, Callable

from .log import Log

import scifor as _scifor
from scifor import for_each as _scifor_for_each
from scifor.pathinput import PathInput

# Conditional import for lineage support (optional dependency)
try:
    from scilineage import LineageFcnResult
    HAS_LINEAGE = True
except ImportError:
    LineageFcnResult = None
    HAS_LINEAGE = False

from .colname import ColName
from .column_selection import ColumnSelection
from .fixed import Fixed
from .variant import Variant
from .each_of import EachOf
from .foreach_config import ForEachConfig
from .filters import Filter
from .merge import Merge


# ---------------------------------------------------------------------------
# Sentinel classes for per-combo loading
# ---------------------------------------------------------------------------

class PerComboLoader:
    """Sentinel for inputs that need per-combo loading (class lacks bulk load support).

    ``spec`` can be:
    - A plain class (has .load())
    - A ``Fixed`` wrapping a plain class (load with overridden metadata)
    - A ``ColumnSelection`` wrapping a plain class (load, then select cols)
    - A ``Fixed`` wrapping a ``ColumnSelection`` (both overrides)

    ``for_each`` wraps fn so these are resolved per-combo via cls.load(**combo).
    """
    __slots__ = ("spec",)

    def __init__(self, spec: Any):
        self.spec = spec


class PerComboLoaderMerge:
    """Sentinel for Merge where some/all constituents lack bulk load support.

    Holds the original ``scidb.Merge`` spec; ``for_each`` wraps fn to
    resolve each constituent per-combo via cls.load(**combo_metadata).
    """
    __slots__ = ("merge_spec",)

    def __init__(self, merge_spec: "Merge"):
        self.merge_spec = merge_spec


class _DryRunMerge(_scifor.Merge):
    """scifor.Merge subclass used only for dry_run display.

    Has the correct ``__name__`` from the scidb.Merge spec so scifor
    prints ``Merge(GaitData, ForceData)`` instead of a repr string.
    """

    def __init__(self, scidb_merge):
        # Do NOT call super().__init__ — bypass validation for display only
        import pandas as pd
        self._dry_name = scidb_merge.__name__
        # scifor loops over self.tables in _print_dry_run_iteration
        self.tables = [pd.DataFrame() for _ in scidb_merge.var_specs]

    @property
    def __name__(self) -> str:  # type: ignore[override]
        return self._dry_name


class _PreresolvedFilter(Filter):
    """Wraps a pre-computed set of schema_ids for constituent loading.

    Used in the Merge path so each constituent receives already-resolved,
    already-validated schema_ids directly — no second DB query or coverage
    check needed.

    Also carries the ``__where`` provenance key derived from the merge-level
    where= filter (``where_key``). This lets a constituent that was computed by
    for_each (and therefore has a stored ``__where`` version key) be matched by
    provenance in ``_load_with_where`` Strategy 1 — selecting the single variant
    the filter describes — exactly as a direct ``.load(where=...)`` would. Without
    it, constituents fall through to schema-id filtering (Strategy 2), which
    cannot distinguish multiple variants that share the same schema keys.
    Constituents with no stored ``__where`` (e.g. raw-saved data) simply miss
    Strategy 1 and fall back to the pre-resolved ``schema_ids`` in Strategy 2.

    ``_schema_ids`` is authoritative in *both* strategies: it already encodes the
    full where= filter (variable-level AND any SchemaKey portion).  The
    ``_restrict_to_resolved_ids`` marker tells ``_load_with_where`` to apply it as
    a schema-id row selector even when Strategy 1 matches by provenance — without
    it, a constituent that *does* have a stored ``__where`` would return every
    schema_id sharing that variant, ignoring the SchemaKey restriction.
    """

    # Tells DatabaseManager._load_with_where (Strategy 1) to intersect the
    # provenance-matched records with resolve() — see class docstring.
    _restrict_to_resolved_ids = True

    def __init__(self, schema_ids: set, where_key: str = ""):
        self._schema_ids = schema_ids
        self._where_key = where_key or ""

    def to_key(self) -> str:
        # Drives augmented["__where"] in _load_with_where: empty → Strategy 1
        # skipped (schema-id fallback only); non-empty → provenance match.
        return self._where_key

    def resolve(self, db, target_variable_class, target_table_name, validate_coverage=True) -> set:
        return self._schema_ids


def _merge_constituent_where_key(where: Any) -> str:
    """Derive the ``__where`` provenance key for a merge-level where= filter.

    Splits off any SchemaKey portion (which selects rows, not variants) and
    keys on the variable-level portion only — mirroring exactly what
    ``DatabaseManager._load_with_where`` does for a direct ``.load(where=...)``,
    via the shared ``_where_key_from_filter`` helper, so Merge constituents and
    direct loads resolve to the same stored variant.
    """
    from .filters import split_schema_key_filters
    from .database import _where_key_from_filter

    where_for_key = where
    if isinstance(where, Filter):
        sk_filter, var_filter = split_schema_key_filters(where)
        if sk_filter is not None:
            where_for_key = var_filter  # None when where is purely SchemaKey
    return _where_key_from_filter(where_for_key) or ""


# ---------------------------------------------------------------------------
# Prepared state shared between the prepare / loop / save phases
# ---------------------------------------------------------------------------


@dataclass
class _ForEachState:
    """Everything ``_for_each_prepare`` computes that the inner loop and
    ``_for_each_save_resolved`` consume. Holding it in one place lets the
    same prepare code service both the Python-driven path (the existing
    ``for_each`` orchestration) and the MATLAB-driven bridge entry that
    runs the loop in MATLAB's ``scifor.for_each``.

    Fields are populated by ``_for_each_prepare`` in the order they appear
    in the pre-loop steps; consumers should treat the dataclass as
    read-only once returned.
    """

    fn_name: str
    config_keys: dict
    call_id: str
    output_names: list
    loaded_inputs: dict
    full_combos: list
    extended_metadata_iterables: dict
    rid_to_bp: dict
    rid_keys: list
    rid_keys_for_schema: list
    aggregation_mode: bool
    combo_to_rids: Any  # dict | None
    iterated_keys_ordered: Any  # list | None
    fixed_rid_values: dict
    current_schema_keys: list


# ---------------------------------------------------------------------------
# Main for_each entry point
# ---------------------------------------------------------------------------

def for_each(
    fn: Callable,
    inputs: dict[str, Any],
    outputs: list[type],
    dry_run: bool = False,
    save: bool = True,
    as_table: list[str] | bool | None = None,
    db=None,
    distribute: bool = False,
    where=None,
    introspect: bool = False,
    _inject_combo_metadata: bool = False,
    _pre_combo_hook: "Callable[[dict], bool] | None" = None,
    _progress_fn: "Callable[[dict], None] | None" = None,
    _cancel_check: "Callable[[], bool] | None" = None,
    _lineage_fixed_rids: "dict | None" = None,
    **metadata_iterables: list[Any],
) -> "pd.DataFrame | None":
    """
    Execute a function for all combinations of metadata, loading inputs
    and saving outputs automatically.

    This is the DB-backed wrapper. It:
    1. Resolves empty lists ``[]`` via ``db.distinct_schema_values()``
    2. Pre-filters schema combos via ``db.distinct_schema_combinations()``
    3. Builds ``ForEachConfig`` version keys
    4. Loads all input variables into DataFrames
    5. Converts scidb wrappers → scifor wrappers
    6. Delegates the core loop to ``scifor.for_each``
    7. Saves results from the returned table

    Args:
        fn: The function to execute (plain function handle; for_each handles
            lineage tracking internally).
        inputs: Dict mapping parameter names to variable types, Fixed wrappers,
                Merge wrappers, ColumnSelection wrappers, PathInput, or constants.
        outputs: List of output types/objects with ``.save()``.
        dry_run: If True, only print what would happen without executing.
        save: If True (default), save each function run's output.
        as_table: Controls which inputs are passed as full DataFrames.
        db: Optional database instance.
        distribute: If True, split outputs and save each piece at the schema
                    level below the deepest iterated key.
        where: Optional filter; passed to .load() calls on DB-backed inputs.
        introspect: If True, append introspection columns to the right of the
                    result DataFrame: _record_id_{param} and _branch_params_{param}
                    per DB-backed input, plus _call_id, _config_keys, _where on
                    every row. Does not affect saved outputs.
        _inject_combo_metadata: If True, inject current-combo metadata keys
                    as extra kwargs to fn (used by scihist for generates_file).
        _pre_combo_hook: Internal use only. Called with each fully-expanded
                    combo dict before inputs are loaded. If it returns True
                    the combo is skipped entirely (no load, no call, no save).
                    Used by scihist.for_each to implement skip_computed.
        **metadata_iterables: Iterables of metadata values to combine.

    Returns:
        A pandas DataFrame of results, or None when dry_run=True.
    """
    # --- Normalize where clause: convert string to RawFilter ---
    # (but not if it's an EachOf wrapper - those will be normalized in recursive calls)
    if isinstance(where, str):
        from .filters import raw_sql
        # Preserve original string for version_keys
        original_where_str = where
        # Convert Python-style == to SQL =
        where_sql = where.replace("==", "=")
        where = raw_sql(where_sql)
        # Store original for version_keys serialization
        where._original_str = original_where_str

    # --- Step 1: EachOf expansion: must be first, before any other logic ---
    each_of_axes = []
    for param, val in inputs.items():
        if isinstance(val, EachOf):
            each_of_axes.append(("input", param, val.alternatives))
    if isinstance(where, EachOf):
        each_of_axes.append(("where", None, where.alternatives))

    if each_of_axes:
        Log.info(f"[scidb] Step 1: EachOf expansion detected - {len(each_of_axes)} axes, will make recursive calls")
        for kind, param, alts in each_of_axes:
            if kind == "input":
                Log.info(f"  EachOf axis: input '{param}' with {len(alts)} alternatives")
            else:
                Log.info(f"  EachOf axis: where with {len(alts)} alternatives")
        import pandas as pd
        from itertools import product as _eachof_product

        results = []
        for combo in _eachof_product(*(axis[2] for axis in each_of_axes)):
            concrete_inputs = dict(inputs)
            concrete_where = where
            for (kind, param, _alts), value in zip(each_of_axes, combo):
                if kind == "input":
                    concrete_inputs[param] = value
                elif kind == "where":
                    concrete_where = value
            result = for_each(
                fn,
                concrete_inputs,
                outputs,
                dry_run=dry_run,
                save=save,
                as_table=as_table,
                db=db,
                distribute=distribute,
                where=concrete_where,
                introspect=introspect,
                _inject_combo_metadata=_inject_combo_metadata,
                _pre_combo_hook=_pre_combo_hook,
                _progress_fn=_progress_fn,
                _cancel_check=_cancel_check,
                **metadata_iterables,
            )
            if result is not None:
                results.append(result)
            # Cooperative cancel: stop iterating across EachOf alternatives
            # as soon as the user cancels — don't start the next concrete run.
            if _cancel_check is not None and _cancel_check():
                break
        result_df = pd.concat(results, ignore_index=True) if results else None
        Log.info(f"[scidb] Step 1: EachOf expansion complete - concatenated {len(results)} result(s)")
        return result_df
    else:
        Log.info("[scidb] Step 1: no EachOf expansion needed")

    # --- Step 1.5: Resolve for_columns (iterate-mode ColumnSelection) inputs ---
    # Expand empty columns ([] / all) -> all data columns and validate the shared column
    # axis BEFORE version keys are built (Step 8) and before dry-run display,
    # so caching reflects the concrete column set.
    inputs = _resolve_for_columns(inputs, db)
    _has_for_columns = any(
        _iterate_column_selection(s) is not None for s in inputs.values()
    )

    # Wrap lineage functions to unpack tuple returns when needed.
    # Skip if already wrapped (scihist.for_each pre-wraps before delegating here).
    if HAS_LINEAGE and not getattr(fn, '__lineage_wrapper__', False):
        if _has_for_columns:
            # for_columns reassembles per-column results into one wide output;
            # per-column lineage objects cannot live in that DataFrame, so
            # collapse LineageFcnResult returns to raw values (combined-call
            # lineage — upstream provenance is still recorded at save time from
            # the input record_ids).
            fn = _make_raw_value_wrapper(fn)
            Log.info("[scidb] wrapped function in raw-value wrapper for for_columns")
        else:
            try:
                from scilineage import make_tuple_unpacking_wrapper
                fn = make_tuple_unpacking_wrapper(fn)
                Log.info("[scidb] wrapped function in tuple unpacking wrapper for lineage support")
            except ImportError:
                pass  # scilineage not available

    fn_name = getattr(fn, "__name__", repr(fn))
    Log.info(f"===== for_each({fn_name}) start =====")

    # --- Steps 2-15: pre-loop preparation. Returns None on dry_run shortcut. ---
    state = _for_each_prepare(
        fn=fn,
        fn_name=fn_name,
        inputs=inputs,
        outputs=outputs,
        dry_run=dry_run,
        as_table=as_table,
        db=db,
        distribute=distribute,
        where=where,
        _pre_combo_hook=_pre_combo_hook,
        _cancel_check=_cancel_check,
        metadata_iterables=metadata_iterables,
    )
    if state is None:
        return None

    # --- Step 16: Wrap fn to resolve PerComboLoader/PerComboLoaderMerge inputs per-combo,
    #     inject combo metadata (for generates_file functions), and/or
    #     reconstruct BaseVariable objects (for LineageFcn). ---
    _per_combo = {k: v for k, v in state.loaded_inputs.items()
                  if isinstance(v, (PerComboLoader, PerComboLoaderMerge))}
    _is_lineage_wrapper = getattr(fn, '__lineage_wrapper__', False)
    if _per_combo or _inject_combo_metadata or _is_lineage_wrapper:
        wrap_reasons = []
        if _per_combo:
            wrap_reasons.append(f"{len(_per_combo)} PerComboLoader input(s)")
        if _inject_combo_metadata:
            wrap_reasons.append("generates_file metadata injection")
        if _is_lineage_wrapper:
            wrap_reasons.append("LineageFcn variable reconstruction")
        Log.info(f"[scidb] Step 16: wrapping function for {', '.join(wrap_reasons)}")
        _ordered_combos = state.full_combos
        _call_idx = [0]
        _orig_fn = fn
        _loaded_inputs_ref = state.loaded_inputs

        # Get function parameters to check which metadata keys it accepts.
        # For scihist functions, the wrapper stores the original function's
        # parameters in __scidb_params__. Otherwise try to get the signature.
        _fn_params = None
        if _inject_combo_metadata:
            if hasattr(_orig_fn, '__scidb_params__'):
                _fn_params = _orig_fn.__scidb_params__
            else:
                import inspect
                try:
                    sig = inspect.signature(_orig_fn)
                    _fn_params = set(sig.parameters.keys())
                except (ValueError, TypeError):
                    # Couldn't get signature, don't inject metadata
                    _fn_params = set()

        def fn(**kwargs):  # noqa: F811 — intentional rebind
            idx = _call_idx[0]
            _call_idx[0] = idx + 1
            current_combo = _ordered_combos[idx] if idx < len(_ordered_combos) else {}
            load_kw = {k: v for k, v in current_combo.items() if not k.startswith("__")}
            resolved = {}
            for k, v in kwargs.items():
                if isinstance(v, PerComboLoader):
                    resolved[k] = _resolve_per_combo_loader(v, load_kw)
                elif isinstance(v, PerComboLoaderMerge):
                    resolved[k] = _resolve_per_combo_merge(v, load_kw)
                else:
                    resolved[k] = v

            # Reconstruct BaseVariable objects for LineageFcn
            if getattr(_orig_fn, '__lineage_wrapper__', False):
                resolved = _reconstruct_variable_inputs(
                    resolved, current_combo, inputs, _loaded_inputs_ref
                )

            if _inject_combo_metadata and _fn_params is not None:
                # Only inject metadata keys that the function signature accepts
                for k, v in load_kw.items():
                    if k not in resolved and k in _fn_params:
                        resolved[k] = v
            return _orig_fn(**resolved)
    else:
        Log.info("[scidb] Step 16: no function wrapping needed")

    # Wrap _progress_fn to track final completed/skipped counts for logging.
    _run_summary = {"total": 0, "completed": 0, "skipped": 0}

    def _tracking_progress_fn(info: dict):
        _run_summary["total"] = info.get("total", _run_summary["total"])
        _run_summary["completed"] = info.get("completed", _run_summary["completed"])
        _run_summary["skipped"] = info.get("skipped", _run_summary["skipped"])
        if _progress_fn is not None:
            _progress_fn(info)

    # Step 17: Delegate core loop to scifor
    Log.info(f"[scidb] Step 17: delegating to scifor.for_each with {len(state.full_combos)} combo(s)")
    result_tbl = _scifor_for_each(
        fn,
        state.loaded_inputs,
        dry_run=False,
        as_table=as_table,
        distribute=distribute,
        output_names=state.output_names,
        _all_combos=state.full_combos,
        _log_fn=Log.info,
        _progress_fn=_tracking_progress_fn,
        _cancel_check=_cancel_check,
        **state.extended_metadata_iterables,
    )
    Log.info(f"[scidb] scifor.for_each completed: {_run_summary['completed']} completed, {_run_summary['skipped']} skipped")

    # Log run summary with failed repetition count.
    if _run_summary["total"] > 0:
        Log.debug(f"for_each({fn_name}): completed={_run_summary['completed']}, "
                  f"failed={_run_summary['skipped']}, total={_run_summary['total']}")

    # --- Steps 18-19: schema restore + save ---
    result_tbl = _for_each_save_resolved(
        state=state,
        result_tbl=result_tbl,
        inputs=inputs,
        outputs=outputs,
        save=save,
        db=db,
        lineage_fixed_rids=_lineage_fixed_rids,
    )

    if introspect and result_tbl is not None and not result_tbl.empty:
        result_tbl = _apply_introspect(result_tbl, state, where)

    return result_tbl


# ---------------------------------------------------------------------------
# Introspect helper
# ---------------------------------------------------------------------------

def _apply_introspect(result_tbl, state, where):
    """Append introspection columns to the for_each result DataFrame.

    Column order: existing non-__rid columns (schema + outputs) →
    _record_id_* / _branch_params_* pairs (one per DB-backed input) →
    _call_id, _config_keys, _where.
    """
    # Identify __rid_* columns and remove them from their current positions.
    rid_cols = [c for c in result_tbl.columns if c.startswith("__rid_")]
    df = result_tbl.drop(columns=rid_cols)

    # Append per-input record_id + branch_params pairs in input order.
    for rid_col in rid_cols:
        param_name = rid_col[len("__rid_"):]
        record_ids = result_tbl[rid_col]
        df[f"_record_id_{param_name}"] = record_ids.values
        df[f"_branch_params_{param_name}"] = [
            state.rid_to_bp.get(rid, {}) for rid in record_ids
        ]

    # Append call-level columns (same value on every row).
    df["_call_id"] = state.call_id
    df["_config_keys"] = json.dumps(state.config_keys)
    df["_where"] = repr(where) if where is not None else None

    return df


# ---------------------------------------------------------------------------
# Prepare / save seam functions
#
# These factor the Python-driven body of ``for_each`` so that:
#   - Python pipelines (the ``for_each`` orchestration above) call them
#     in sequence with a Python ``for`` loop in between (delegated to
#     ``scifor.for_each``).
#   - MATLAB pipelines (the ``scimatlab.bridge.for_each_prepare`` /
#     ``for_each_save`` bridge entries) call them in sequence with the
#     MATLAB-side ``+scifor/for_each.m`` running the inner loop in
#     between.
#
# Both callers get identical correctness (variant expansion,
# branch_params, ``__upstream``, lineage save) because they share the
# same prepare and save code.
# ---------------------------------------------------------------------------


def _for_each_prepare(
    *,
    fn: Callable,
    fn_name: str,
    inputs: dict,
    outputs: list,
    dry_run: bool,
    as_table,
    db,
    distribute: bool,
    where,
    _pre_combo_hook,
    _cancel_check,
    metadata_iterables: dict,
) -> "_ForEachState | None":
    """Run scidb.for_each's pre-loop work (Steps 2-15).

    On ``dry_run=True`` runs the dry-run shortcut (Step 7) and returns
    ``None`` to signal the caller to stop. Otherwise returns the prepared
    state object the loop and save phases consume.
    """
    # Track which keys the user passed with explicit (non-empty) values.
    # Keys passed as an empty sequence ([], (), empty numpy array) are
    # about to be resolved from the DB (Step 2) or the filesystem
    # (Step 3) — those should not count as "user explicit" in Step 3's
    # discovery branch, since the user delegated their values to
    # resolution rather than asserting intent.
    #
    # Defensively accept any sized non-string sequence so that callers
    # that pass numpy arrays / tuples (in addition to the usual lists)
    # are classified the same way the MATLAB bridge's [] normalization
    # produces.
    def _is_empty_sequence(v):
        if isinstance(v, str):
            return False  # strings are scalar values, never "empty iterables"
        try:
            return len(v) == 0
        except TypeError:
            return False
    user_explicit_keys = {k for k, v in metadata_iterables.items()
                           if not _is_empty_sequence(v)}
    Log.info(
        f"[scidb] entry: metadata_iterables keys={list(metadata_iterables.keys())}, "
        f"types={[type(v).__name__ for v in metadata_iterables.values()]}, "
        f"lens={[(len(v) if hasattr(v, '__len__') else 'N/A') for v in metadata_iterables.values()]}, "
        f"user_explicit_keys={sorted(user_explicit_keys)}"
    )

    # Step 2: Resolve empty lists to all distinct values from the database
    needs_resolve = [k for k, v in metadata_iterables.items()
                     if isinstance(v, list) and len(v) == 0]
    resolved_db = None
    if needs_resolve:
        Log.info(f"[scidb] Step 2: resolving {len(needs_resolve)} empty list(s) from database: {needs_resolve}")
        resolved_db = db
        if resolved_db is None:
            try:
                from scidb.database import get_database
                resolved_db = get_database()
            except Exception:
                raise ValueError(
                    f"Empty list [] was passed for {needs_resolve}, which means "
                    f"'use all levels', but no database is available. Either pass "
                    f"db= to for_each or call configure_database() first."
                )
        for key in needs_resolve:
            values = resolved_db.distinct_schema_values(key)
            if not values:
                msg = f"no values found for '{key}' in database, 0 iterations"
                print(f"[warn] {msg}")
                Log.warn(msg)
            else:
                Log.info(f"[scidb] resolved '{key}' from database: {len(values)} values")
            metadata_iterables[key] = values
    else:
        Log.info("[scidb] Step 2: no empty lists to resolve from database")

    # --- Step 3: PathInput discovery.  Discovery runs whenever a PathInput
    # is present; its role depends on what the caller supplied:
    #
    #   * No metadata_iterables at all → adopt every discovered key/value.
    #   * All template keys passed as [] → fill from disk and use the
    #     discovered combos directly. This avoids Cartesian-product
    #     "invention" of combos that have no file on disk (regression
    #     covered by tests/matlab/scidb/TestForEachSchemaFiltering).
    #   * Any template key has explicit user values → user intent is
    #     authoritative. Empty-list keys still get filled from disk, but
    #     no filtering happens; the Cartesian product of metadata_iterables
    #     drives base_combos. Combos with missing files fail at runtime
    #     and are surfaced as "missing" by check_node_state. ---
    _discovered_combos = None
    if _has_pathinput(inputs):
        Log.info("[scidb] Step 3: PathInput detected, running filesystem discovery")
        pi = _find_pathinput(inputs)
        if pi is not None:
            combos = pi.discover()
            Log.debug(f"PathInput discovery: template={pi.path_template!r}, "
                      f"root_folder={pi.root_folder!r}, "
                      f"matching_files={len(combos)}")
            if combos:
                combo_keys = list(combos[0].keys())

                # Case A: No metadata keys passed at all → adopt every
                # discovered key with all its discovered values.
                if not metadata_iterables:
                    for key in combo_keys:
                        metadata_iterables[key] = list(dict.fromkeys(c[key] for c in combos))
                        Log.info(f"discovered {key} -> {len(metadata_iterables[key])} values from filesystem")
                    _discovered_combos = combos
                else:
                    # Case B: Keys provided (some may be []). For each
                    # template key, fill empty lists from disk; explicit
                    # user-provided values are left alone.
                    #
                    # "Explicit" means the user passed a non-empty list at
                    # the call site (captured in user_explicit_keys before
                    # Step 2).  A key whose value came from DB resolution
                    # (Step 2) or filesystem discovery (here) is NOT
                    # considered explicit — those are auto-fills, not
                    # user assertions of intent.
                    user_filter_seen = False
                    for key in combo_keys:
                        if key not in metadata_iterables:
                            continue
                        user_vals = metadata_iterables[key]
                        if not user_vals:
                            metadata_iterables[key] = list(dict.fromkeys(
                                c[key] for c in combos
                            ))
                            Log.info(f"discovered {key} -> {len(metadata_iterables[key])} values from filesystem")
                        elif key in user_explicit_keys:
                            user_filter_seen = True

                    if user_filter_seen:
                        # User supplied explicit values for at least one
                        # template key — those define the intended combo
                        # set. Leave _discovered_combos=None so Step 12
                        # falls through to the Cartesian product of
                        # metadata_iterables. Combos whose files are
                        # missing on disk will be attempted and fail
                        # with FileNotFoundError, which scifor catches
                        # per-combo and records as a skip — surfacing as
                        # "missing" in check_node_state rather than
                        # being silently dropped here.
                        Log.info(
                            "[scidb] explicit user values for template keys; "
                            "skipping discovery filter — Cartesian product "
                            "of user-provided iterables will drive base_combos"
                        )
                    else:
                        # All template keys filled from disk discovery —
                        # use discovered combos directly to avoid
                        # inventing non-existent combos via Cartesian
                        # product (e.g. {sub1,sub2} × {sessA,sessB}
                        # producing {sub2,sessB} when only 3 of 4 files
                        # exist).
                        _discovered_combos = combos
                        Log.info(
                            f"[scidb] no user-explicit template keys; "
                            f"_discovered_combos set to {len(combos)} disk combos"
                        )
    else:
        Log.info("[scidb] Step 3: no PathInput detected, skipping filesystem discovery")

    # Step 4: Propagate schema keys to scifor so distribute and DataFrame detection work
    Log.info("[scidb] Step 4: propagating schema keys to scifor")
    _propagate_schema(db, distribute)
    if db and hasattr(db, 'dataset_schema_keys'):
        Log.info(f"[scidb] schema keys propagated: {db.dataset_schema_keys}")

    # Step 5: Stringify metadata_iterables values for schema keys.
    # load_all_as_df (spread layout) stringifies schema columns in loaded DataFrames
    # (DB returns typed values like np.int64); combo metadata must match to filter correctly.
    Log.info("[scidb] Step 5: stringifying metadata iterable values for schema keys")
    _resolved_db_for_str = db
    if _resolved_db_for_str is None:
        try:
            from scidb.database import get_database
            _resolved_db_for_str = get_database()
        except Exception:
            _resolved_db_for_str = None
    if _resolved_db_for_str is not None and hasattr(_resolved_db_for_str, 'dataset_schema_keys'):
        from scidb.database import _schema_str
        _sk_set = set(_resolved_db_for_str.dataset_schema_keys)
        stringify_count = 0
        for key in list(metadata_iterables.keys()):
            if key in _sk_set:
                metadata_iterables[key] = [
                    _schema_str(v) for v in metadata_iterables[key]
                ]
                stringify_count += 1
        Log.info(f"[scidb] stringified {stringify_count} schema key iterable(s)")
    else:
        Log.info("[scidb] Step 5: no database available for schema stringification, skipping")

    # Step 6: Build output_names for scifor
    output_names = [_output_name(o) for o in outputs] if outputs else ["result"]
    Log.info(f"[scidb] Step 6: resolved {len(output_names)} output name(s): {output_names}")

    # --- Step 7: Dry-run shortcut: convert inputs for display only, call
    # scifor, return.  Also runs the same combo prefilter Step 9 applies
    # to non-dry runs so the printed iteration count reflects what would
    # actually be processed (combos missing from the DB are dropped). ---
    if dry_run:
        Log.info("[scidb] Step 7: dry_run=True, converting inputs for display and delegating to scifor")
        display_inputs = _convert_inputs_for_display(inputs)

        # Prefilter combos to existing schema combinations (mirrors Step 9
        # for the non-dry path). Only meaningful when at least one key
        # was DB-resolved AND no PathInput is present.
        _dryrun_all_combos = None
        if needs_resolve and not _has_pathinput(inputs):
            from scidb.database import _schema_str
            filter_db = resolved_db
            if filter_db is not None and hasattr(filter_db, 'dataset_schema_keys'):
                schema_keys_set = set(filter_db.dataset_schema_keys)
                keys = list(metadata_iterables.keys())
                schema_indices = [i for i, k in enumerate(keys) if k in schema_keys_set]
                filter_keys = [keys[i] for i in schema_indices]
                if filter_keys:
                    from itertools import product
                    value_lists = [metadata_iterables[k] for k in keys]
                    raw_combos = list(product(*value_lists))
                    existing = filter_db.distinct_schema_combinations(filter_keys)
                    existing_set = set(existing)
                    _dryrun_all_combos = [
                        dict(zip(keys, combo))
                        for combo in raw_combos
                        if tuple(_schema_str(combo[i]) for i in schema_indices) in existing_set
                    ]

        # Apply schema exclusions to dry-run combos (mirrors Step 9.5)
        if _dryrun_all_combos is not None:
            _dry_excl_db = db or resolved_db
            if _dry_excl_db is not None:
                from .exclusions import filter_excluded_combos
                _dryrun_all_combos = filter_excluded_combos(
                    _dryrun_all_combos,
                    _dry_excl_db.dataset_schema_keys,
                    _dry_excl_db,
                )

        scifor_kwargs = dict(metadata_iterables)
        if _dryrun_all_combos is not None:
            scifor_kwargs["_all_combos"] = _dryrun_all_combos
        _scifor_for_each(
            fn,
            display_inputs,
            dry_run=True,
            as_table=as_table,
            distribute=distribute,
            output_names=output_names,
            _cancel_check=_cancel_check,
            **scifor_kwargs,
        )
        return None

    # Step 8: Build ForEachConfig version keys (DB-specific; not part of scifor)
    Log.info("[scidb] Step 8: building ForEachConfig version keys")
    config = ForEachConfig(
        fn=fn,
        inputs=inputs,
        where=where,
        distribute=distribute,
        as_table=as_table,
    )
    config_keys = config.to_version_keys()
    call_id = config.to_call_id()
    Log.info(f"[scidb] ForEachConfig: call_id={call_id}, version_keys={list(config_keys.keys())}")

    # Step 9: Pre-filter to only schema combinations that actually exist in the database.
    all_combos = None
    if needs_resolve and not _has_pathinput(inputs):
        Log.info("[scidb] Step 9: pre-filtering combos to only existing schema combinations")
        from scidb.database import _schema_str
        filter_db = resolved_db
        schema_keys_set = set(filter_db.dataset_schema_keys)
        keys = list(metadata_iterables.keys())
        schema_indices = [i for i, k in enumerate(keys) if k in schema_keys_set]
        filter_keys = [keys[i] for i in schema_indices]

        if filter_keys:
            from itertools import product
            value_lists = [metadata_iterables[k] for k in keys]
            raw_combos = list(product(*value_lists))

            existing = filter_db.distinct_schema_combinations(filter_keys)
            existing_set = set(existing)

            filtered = [
                dict(zip(keys, combo))
                for combo in raw_combos
                if tuple(_schema_str(combo[i]) for i in schema_indices) in existing_set
            ]
            removed = len(raw_combos) - len(filtered)
            if removed > 0:
                msg = (f"filtered {removed} non-existent schema combinations "
                       f"(from {len(raw_combos)} to {len(filtered)})")
                print(f"[info] {msg}")
                Log.info(f"[scidb] {msg}")
            else:
                Log.info(f"[scidb] all {len(raw_combos)} combos exist in database")
            all_combos = filtered
    else:
        Log.info("[scidb] Step 9: skipping combo pre-filtering (no empty list resolution or PathInput detected)")

    # Step 9.5: Schema exclusions — add override hash to version_keys and filter combos.
    _exclusion_db = db or resolved_db
    if _exclusion_db is None:
        try:
            from scidb.database import get_database
            _exclusion_db = get_database()
        except Exception:
            _exclusion_db = None

    if _exclusion_db is not None:
        from .exclusions import get_schema_overrides_hash, filter_excluded_combos
        _overrides_hash = get_schema_overrides_hash(_exclusion_db)
        config_keys["__schema_overrides_hash"] = _overrides_hash
        Log.info(f"[scidb] Step 9.5: schema overrides hash = {_overrides_hash}")

        if all_combos is not None:
            _before = len(all_combos)
            all_combos = filter_excluded_combos(
                all_combos,
                _exclusion_db.dataset_schema_keys,
                _exclusion_db,
            )
            _after = len(all_combos)
            if _before != _after:
                msg = (f"schema exclusions removed {_before - _after} combo(s) "
                       f"(from {_before} to {_after})")
                print(f"[info] {msg}")
        else:
            Log.info("[scidb] Step 9.5: all_combos is None (explicit iterables); "
                     "exclusion filtering will be skipped at combo level")
    else:
        Log.info("[scidb] Step 9.5: no database available, skipping schema exclusion filtering")

    # Step 10: Load all inputs into DataFrames (with __record_id and __branch_params)
    Log.info(f"[scidb] Step 10: loading {len(inputs)} input(s) into DataFrames")
    loaded_inputs = _convert_inputs(inputs, db, where)
    df_count = sum(1 for v in loaded_inputs.values() if isinstance(v, __import__('pandas').DataFrame))
    Log.info(f"[scidb] loaded {df_count} DataFrame input(s), {len(loaded_inputs) - df_count} other(s)")

    # --- Step 11: Variant tracking: build rid→bp mapping and __rid_{param} discriminator columns ---
    import pandas as pd
    from itertools import product as _iproduct

    Log.info("[scidb] Step 11: building variant tracking (rid->branch_params mapping)")
    rid_to_bp: dict = {}   # {record_id: branch_params_dict}
    rid_keys: list = []    # __rid_{param_name} column names added to this call's schema
    fixed_rid_values: dict = {}  # {param_name: record_id} for Fixed inputs

    for param_name, data in list(loaded_inputs.items()):
        # Extract DataFrame from Fixed wrapper if needed
        df = None
        is_fixed = False
        if isinstance(data, pd.DataFrame):
            df = data
        elif hasattr(data, 'data') and isinstance(data.data, pd.DataFrame):
            # scifor.Fixed wrapper
            df = data.data
            is_fixed = True

        if df is None or "__record_id" not in df.columns:
            continue

        # Build rid→bp from this input's DataFrame (vectorized for performance)
        bp_col = "__branch_params" if "__branch_params" in df.columns else None
        # Filter out None record_ids using vectorized operation
        valid_mask = df["__record_id"].notna()
        if valid_mask.any():
            valid_rids = df.loc[valid_mask, "__record_id"]
            if bp_col:
                valid_bps = df.loc[valid_mask, bp_col]
                # Use zip over columns instead of iterrows() - 10-100x faster
                for rid, bp_raw in zip(valid_rids, valid_bps):
                    rid_to_bp[rid] = json.loads(bp_raw or "{}") if isinstance(bp_raw, str) else {}
            else:
                for rid in valid_rids:
                    rid_to_bp[rid] = {}

        # Rename __record_id → __rid_{param_name} so per-param tracking is unambiguous
        rid_col = f"__rid_{param_name}"
        df_renamed = df.rename(columns={"__record_id": rid_col})

        # Update loaded_inputs with renamed DataFrame (or rewrap in Fixed)
        if is_fixed:
            # For Fixed inputs, extract the single record_id and store it
            # (Fixed inputs should have exactly one row after filtering)
            if len(df) == 1:
                fixed_rid_values[param_name] = str(df.iloc[0]["__record_id"])
            data.data = df_renamed
        else:
            loaded_inputs[param_name] = df_renamed
            rid_keys.append(rid_col)

    Log.info(f"[scidb] variant tracking: {len(rid_to_bp)} record_id(s) mapped, "
              f"{len(rid_keys)} rid key(s): {rid_keys}, "
              f"{len(fixed_rid_values)} fixed input rid(s): {list(fixed_rid_values.keys())}")

    # Strip __branch_params from all DataFrames (now tracked via rid_to_bp)
    for param_name, data in list(loaded_inputs.items()):
        if isinstance(data, pd.DataFrame) and "__branch_params" in data.columns:
            loaded_inputs[param_name] = data.drop(columns=["__branch_params"])

    # --- Step 12: Build full combos: base_combos × valid rid-combos per schema location ---
    Log.info("[scidb] Step 12: expanding combos with record-ID variants")
    current_schema_keys = list(_scifor.get_schema() or [])

    base_combos = all_combos
    Log.info(
        f"[scidb] Step 12: all_combos={'None' if all_combos is None else len(all_combos)}, "
        f"_discovered_combos={'None' if _discovered_combos is None else len(_discovered_combos)}"
    )
    if base_combos is None and _discovered_combos is not None:
        # Use filesystem-discovered combos directly (avoids non-existent Cartesian combos)
        base_combos = _discovered_combos
        Log.info(f"[scidb] using {len(base_combos)} filesystem-discovered combos")
    if base_combos is None:
        keys = list(metadata_iterables.keys())
        value_lists = [metadata_iterables[k] for k in keys]
        base_combos = [dict(zip(keys, combo)) for combo in _iproduct(*value_lists)]
        Log.info(f"[scidb] built {len(base_combos)} base combos from metadata iterables")

    # Detect aggregation mode: not all schema keys are being iterated, so
    # lower-level records should be aggregated into multi-row DataFrames
    # rather than being separated into individual combos via rid expansion.
    _iterated_schema_keys = set(metadata_iterables.keys()) & set(current_schema_keys)
    _aggregation_mode = len(current_schema_keys) > 0 and len(_iterated_schema_keys) < len(current_schema_keys)
    if _aggregation_mode:
        Log.info(f"[scidb] aggregation mode detected: iterating {len(_iterated_schema_keys)}/{len(current_schema_keys)} schema keys")
    else:
        Log.info("[scidb] full iteration mode: all schema keys being iterated")

    # Lookup keys for rid disambiguation: schema keys + any non-schema metadata
    # iterable keys.  Using only schema keys misses non-schema iterables (e.g.
    # "session") that ARE present in the loaded DataFrame and should distinguish
    # which record belongs to which combo.
    _lookup_keys = list(dict.fromkeys(
        current_schema_keys +
        [k for k in metadata_iterables if k not in set(current_schema_keys)]
    ))

    # For each rid_key, map combo_tuple → [rid_values at that combo]
    rid_per_combo: dict = {}
    for rid_col in rid_keys:
        param_name = rid_col[len("__rid_"):]
        data = loaded_inputs.get(param_name)

        # Extract DataFrame from Fixed wrapper if needed
        df = None
        if isinstance(data, pd.DataFrame):
            df = data
        elif hasattr(data, 'data') and isinstance(data.data, pd.DataFrame):
            df = data.data

        if df is None or rid_col not in df.columns:
            continue
        schema_cols_in_df = [k for k in _lookup_keys if k in df.columns]
        mapping: dict = {}
        # Dedupe rids per group so DataFrame-mode inputs (one DuckDB row
        # per inner-table row, all sharing a single record_id) don't
        # produce N duplicate combos. We preserve insertion order via
        # dict.fromkeys.
        if schema_cols_in_df:
            for combo_vals, group in df.groupby(schema_cols_in_df, sort=False):
                raw_key = combo_vals if isinstance(combo_vals, tuple) else (combo_vals,)
                # Expand to ALL _lookup_keys, filling missing cols with ""
                col_val = {sk: ("" if v is None else str(v))
                           for sk, v in zip(schema_cols_in_df, raw_key)}
                key = tuple(col_val.get(sk, "") for sk in _lookup_keys)
                mapping[key] = list(dict.fromkeys(group[rid_col].tolist()))
        else:
            # No lookup cols in df — use all-empty key
            mapping[tuple("" for _ in _lookup_keys)] = list(
                dict.fromkeys(df[rid_col].tolist())
            )
        rid_per_combo[rid_col] = mapping

    if _aggregation_mode:
        # Aggregation mode: skip rid expansion.  Strip __rid_* columns from
        # loaded DataFrames so the user's function doesn't see internal
        # tracking columns, and pass base_combos straight through.
        #
        # Also drop schema columns BELOW the lowest iterated level when
        # they are entirely NULL.  Loaded DataFrames carry one column per
        # dataset_schema_key; for a variable stored at a higher schema
        # level, columns for finer-grained keys come back all-NULL.  In
        # aggregation mode those un-iterated schema keys carry no per-row
        # meaning — leaving them in clutters the user-facing table and,
        # on the MATLAB bridge, surfaces as an empty cell column the
        # caller has to special-case.
        iterated_indices = [
            i for i, k in enumerate(current_schema_keys)
            if k in _iterated_schema_keys
        ]
        if iterated_indices:
            below_iterated_keys = set(
                current_schema_keys[max(iterated_indices) + 1:]
            )
        else:
            # No schema keys iterated — every schema key is "below"
            # (this is the no-iteration case; aggregate across everything).
            below_iterated_keys = set(current_schema_keys)
        for param_name, data in list(loaded_inputs.items()):
            if isinstance(data, pd.DataFrame):
                rid_cols_in_df = [c for c in data.columns if c.startswith("__rid_")]
                empty_schema_cols = [
                    c for c in data.columns
                    if c in below_iterated_keys and data[c].isna().all()
                ]
                drop_cols = rid_cols_in_df + empty_schema_cols
                if drop_cols:
                    loaded_inputs[param_name] = data.drop(columns=drop_cols)
                if empty_schema_cols:
                    Log.info(
                        f"[scidb] aggregation: dropped all-null schema "
                        f"column(s) {empty_schema_cols} from loaded input "
                        f"'{param_name}' (below iterated schema level)"
                    )

        # Don't expand combos — aggregation keeps multiple records per combo
        full_combos = list(base_combos)

        # Pre-compute contributing rids per combo for save path (branch_params merge + provenance)
        # Structure: combo_key → {rid_col: [rids]} to preserve parameter information
        _iterated_keys_ordered = [k for k in _lookup_keys if k in _iterated_schema_keys]
        _combo_to_rids = {}
        for combo in base_combos:
            combo_key = tuple(str(combo.get(k, "")) for k in _iterated_keys_ordered)
            rids_by_param = {}
            for rid_col, mapping in rid_per_combo.items():
                param_rids = []
                for full_key, rids in mapping.items():
                    iterated_vals = tuple(
                        full_key[_lookup_keys.index(k)] for k in _iterated_keys_ordered
                    )
                    if iterated_vals == combo_key:
                        param_rids.extend(rids)
                if param_rids:
                    rids_by_param[rid_col] = param_rids
            _combo_to_rids[combo_key] = rids_by_param

        # Don't extend scifor schema or metadata_iterables with rid keys
        rid_keys_for_schema = []

        total_rids = sum(len(rids) for rids_by_param in _combo_to_rids.values()
                         for rids in rids_by_param.values())
        Log.info(f"aggregation mode: skipped rid expansion, "
                 f"iterating {list(_iterated_schema_keys) or '(none)'} "
                 f"of schema {current_schema_keys}, "
                 f"{len(full_combos)} combo(s), "
                 f"{total_rids} contributing rids")
    else:
        # Full iteration mode: expand combos with rid variants.
        _combo_to_rids = None
        _iterated_keys_ordered = None
        rid_keys_for_schema = rid_keys

        # Expand each base combo with all valid rid-combos for that schema location
        Log.debug(f"expanding combos: {len(base_combos)} base combos, "
                  f"{len(rid_per_combo)} rid dimensions")
        full_combos: list = []
        for combo in base_combos:
            schema_vals = tuple(str(combo.get(k, "")) for k in _lookup_keys)

            rid_lists: list = []
            rid_col_names: list = []
            valid = True
            for rid_col, mapping in rid_per_combo.items():
                rids = mapping.get(schema_vals, [])
                if not rids:
                    valid = False
                    break
                rid_lists.append(rids)
                rid_col_names.append(rid_col)

            if not valid:
                continue

            if rid_lists:
                for rid_combo in _iproduct(*rid_lists):
                    full_combo = {**combo}
                    for rc_name, rc_val in zip(rid_col_names, rid_combo):
                        full_combo[rc_name] = rc_val
                    # Add Fixed input record_ids to combo
                    for fixed_param, fixed_rid in fixed_rid_values.items():
                        full_combo[f"__rid_{fixed_param}"] = fixed_rid
                    full_combos.append(full_combo)
            else:
                full_combo = {**combo}
                # Add Fixed input record_ids to combo
                for fixed_param, fixed_rid in fixed_rid_values.items():
                    full_combo[f"__rid_{fixed_param}"] = fixed_rid
                full_combos.append(full_combo)

        if len(full_combos) != len(base_combos):
            Log.info(f"expanded {len(base_combos)} base combos -> "
                     f"{len(full_combos)} full combos (rid variants)")
        else:
            Log.debug(f"{len(full_combos)} combos (no rid expansion needed)")

    # Step 13: Persist the full expected combo set BEFORE skip_computed filtering,
    # so check_node_state knows all combos that should exist (including
    # ones that failed or were skipped).  Only needed when we actually
    # have outputs and are not in dry_run mode.
    if not dry_run and outputs:
        Log.info(f"[scidb] Step 13: persisting {len(full_combos)} expected combo(s) to _for_each_expected table")
        _persist_expected_combos(db, fn_name, call_id, full_combos)
    else:
        Log.info("[scidb] Step 13: skipping expected combos persistence (dry_run or no outputs)")

    # Step 14: Apply pre-combo hook (e.g. skip_computed from scihist): filter out any
    # combos where the hook returns True.
    if _pre_combo_hook is not None:
        Log.info("[scidb] Step 14: applying pre-combo hook (skip_computed)")
        pre_hook_count = len(full_combos)
        full_combos = [c for c in full_combos if not _pre_combo_hook(c)]
        skipped = pre_hook_count - len(full_combos)
        if skipped > 0:
            msg = f"skip_computed: {skipped}/{pre_hook_count} combos skipped"
            print(f"[info] {msg}")
            Log.info(f"[scidb] {msg}")
        else:
            Log.info(f"[scidb] skip_computed: 0/{pre_hook_count} combos skipped (all will be computed)")
    else:
        Log.info("[scidb] Step 14: no pre-combo hook provided, skipping")

    # Step 15: Temporarily extend scifor's schema to include __rid_* keys so _filter_df_for_combo
    # treats them as schema columns (not data columns), giving single-row filtered DFs.
    # In aggregation mode, rid_keys_for_schema is empty so schema isn't extended.
    if rid_keys_for_schema:
        extended_schema = current_schema_keys + rid_keys_for_schema
        Log.info(f"[scidb] Step 15: extending scifor schema from {len(current_schema_keys)} to {len(extended_schema)} keys (added {len(rid_keys_for_schema)} rid keys)")
        _scifor.set_schema(extended_schema)
    else:
        Log.info("[scidb] Step 15: not extending scifor schema (aggregation mode or no rid keys)")

    # Collect all rid values per key so scifor's metadata_iterables are complete.
    # In aggregation mode, rid_keys_for_schema is empty so this loop is skipped.
    extended_metadata_iterables = dict(metadata_iterables)
    if rid_keys_for_schema:
        for rid_col, mapping in rid_per_combo.items():
            all_rids: list = []
            for rids in mapping.values():
                all_rids.extend(rids)
            extended_metadata_iterables[rid_col] = list(dict.fromkeys(all_rids))  # preserve order, dedupe

    return _ForEachState(
        fn_name=fn_name,
        config_keys=config_keys,
        call_id=call_id,
        output_names=output_names,
        loaded_inputs=loaded_inputs,
        full_combos=full_combos,
        extended_metadata_iterables=extended_metadata_iterables,
        rid_to_bp=rid_to_bp,
        rid_keys=rid_keys,
        rid_keys_for_schema=rid_keys_for_schema,
        aggregation_mode=_aggregation_mode,
        combo_to_rids=_combo_to_rids,
        iterated_keys_ordered=_iterated_keys_ordered,
        fixed_rid_values=fixed_rid_values,
        current_schema_keys=current_schema_keys,
    )


def _for_each_save_resolved(
    *,
    state: "_ForEachState",
    result_tbl,
    inputs: dict,
    outputs: list,
    save: bool,
    db,
    lineage_fixed_rids,
):
    """Run scidb.for_each's Step 18 (schema restore) and Step 19 (save).

    Returns ``result_tbl`` unchanged after performing the save side effect.
    """
    # Step 18: Restore scifor's schema
    if state.rid_keys_for_schema:
        Log.info(f"[scidb] Step 18: restoring scifor schema to {len(state.current_schema_keys)} keys (removing {len(state.rid_keys_for_schema)} rid keys)")
        _scifor.set_schema(state.current_schema_keys)
    else:
        Log.info("[scidb] Step 18: no schema restoration needed (wasn't extended)")

    if result_tbl is None:
        return None

    # Step 19: Save results
    if save and outputs and not result_tbl.empty:
        Log.info(f"[scidb] Step 19: saving {len(result_tbl)} result row(s) for {len(outputs)} output(s)")
        # Compute Fixed input rids for lineage tracking if not provided
        fixed_rids_for_save = lineage_fixed_rids
        if fixed_rids_for_save is None and HAS_LINEAGE:
            # Only compute if we might save LineageFcnResult objects
            fixed_rids_for_save = _compute_fixed_input_rids(inputs, db)
            if fixed_rids_for_save:
                Log.info(f"[scidb] computed {len(fixed_rids_for_save)} Fixed input rid(s) for lineage: {list(fixed_rids_for_save.keys())}")

        save_t0 = time.perf_counter()
        _save_results(
            result_tbl, outputs, state.output_names, state.config_keys, db,
            rid_to_bp=state.rid_to_bp,
            rid_keys=[] if state.aggregation_mode else state.rid_keys,
            lineage_fixed_rids=fixed_rids_for_save,
            combo_to_rids=state.combo_to_rids,
            combo_to_rids_keys=state.iterated_keys_ordered,
        )
        save_elapsed = time.perf_counter() - save_t0
        Log.info(f"[scidb] Step 19 complete: saved {len(result_tbl)} result(s) in {save_elapsed:.3f}s")
    elif not save:
        Log.info("[scidb] Step 19: skipping save (save=False)")
    elif not outputs:
        Log.info("[scidb] Step 19: skipping save (no outputs specified)")
    elif result_tbl.empty:
        Log.info("[scidb] Step 19: skipping save (result table is empty)")

    return result_tbl


def _reconstruct_variable_inputs(
    resolved: dict,
    current_combo: dict,
    inputs: dict,
    loaded_inputs: "dict | None" = None,
) -> dict:
    """Reconstruct BaseVariable objects for variable inputs.

    After scifor extracts raw data, reconstruct BaseVariable objects
    with metadata so LineageFcn can classify them correctly.

    Args:
        resolved: Dict of param_name → raw_data from scifor
        current_combo: Combo dict with __rid_* → record_id + schema keys
        inputs: Original inputs dict with param_name → variable_class or Fixed()
        loaded_inputs: The spread DataFrames from _for_each_prepare (state.loaded_inputs).
            Used to restore dict structure for multi-column (dict-of-arrays) variables:
            scifor's _extract_data strips the dict wrapper when there is exactly one data
            column, so we re-read the row from the spread DataFrame directly.

    Returns:
        Dict with BaseVariable objects for variable inputs, raw data for others
    """
    import pandas as pd
    reconstructed = {}

    for param_name, raw_value in resolved.items():
        # Check if this param is a variable input (has __rid_* entry)
        rid_key = f"__rid_{param_name}"
        if rid_key not in current_combo:
            # Not a variable - pass through as-is
            reconstructed[param_name] = raw_value
            continue

        # Get variable class from inputs
        input_spec = inputs.get(param_name)
        variable_class = None

        if isinstance(input_spec, type):
            # Simple variable type
            variable_class = input_spec
        elif hasattr(input_spec, 'var_type') and isinstance(input_spec.var_type, type):
            # Fixed wrapper - extract the variable class
            variable_class = input_spec.var_type

        if variable_class is None:
            # Not a simple variable type - pass through
            reconstructed[param_name] = raw_value
            continue

        # Extract raw data from DataFrame if needed
        data_value = raw_value
        if isinstance(raw_value, pd.DataFrame):
            # Extract the data column (variable name column)
            var_name = variable_class.__name__
            if var_name in raw_value.columns:
                # Get the single value from the data column
                data_value = raw_value[var_name].iloc[0]
            else:
                # Fallback: pass through as-is
                data_value = raw_value
        elif loaded_inputs is not None and not isinstance(raw_value, dict):
            # Check whether the original variable stored a dict (multi-column mode).
            # scifor's _extract_data strips the dict wrapper when there is a single
            # data column (e.g. {"vals": array} → just array).  Detect this by
            # comparing the spread DataFrame's data column name(s) against the
            # variable's view_name: single-column variables rename their column to
            # view_name, so if any data column differs from view_name the original
            # data was a dict.
            df_input = loaded_inputs.get(param_name)
            if isinstance(df_input, pd.DataFrame):
                rid_col = f"__rid_{param_name}"
                # Columns that are NOT data: internal __ columns + schema/combo keys
                schema_keys_in_combo = {k for k in current_combo if not k.startswith("__")}
                data_cols = [
                    c for c in df_input.columns
                    if not c.startswith("__") and c not in schema_keys_in_combo
                ]
                view_name = (
                    variable_class.view_name()
                    if hasattr(variable_class, "view_name")
                    else variable_class.__name__
                )
                # Multi-column dict: data columns differ from the view_name
                is_dict_type = len(data_cols) > 1 or (
                    len(data_cols) == 1 and data_cols[0] != view_name
                )
                if is_dict_type and rid_col in df_input.columns:
                    rid_val = str(current_combo[rid_col])
                    mask = df_input[rid_col].astype(str) == rid_val
                    if mask.any():
                        row = df_input[mask].iloc[0]
                        data_value = {col: row[col] for col in data_cols}

        # Reconstruct BaseVariable
        var = variable_class(data_value)
        var.record_id = str(current_combo[rid_key])

        # Set metadata from combo (schema keys only)
        var.metadata = {k: v for k, v in current_combo.items() if not k.startswith("__")}

        reconstructed[param_name] = var

    return reconstructed


# ---------------------------------------------------------------------------
# Input loading and conversion
# ---------------------------------------------------------------------------

def _convert_inputs(
    inputs: dict[str, Any],
    db: Any | None,
    where: Any | None,
) -> dict[str, Any]:
    """Convert all inputs: load var types into DataFrames, convert wrappers.

    Returns a dict suitable for scifor.for_each (DataFrames + constants).
    """
    result = {}
    total_t0 = time.perf_counter()
    for param_name, var_spec in inputs.items():
        if isinstance(var_spec, ColName):
            if var_spec.is_deferred:
                # No-arg ColName() resolves to the current for_columns column;
                # hand the scifor engine a deferred marker so it substitutes the
                # column name per-iteration (validated there against the
                # presence of an iterate input).
                from scifor import ColName as SciforColName
                result[param_name] = SciforColName()
                Log.debug(f"input '{param_name}': deferred ColName() -> scifor marker")
            else:
                result[param_name] = _resolve_colname_from_db(var_spec, db)
        elif _is_loadable(var_spec):
            t0 = time.perf_counter()
            loaded = _load_input(var_spec, db, where)
            elapsed = time.perf_counter() - t0
            result[param_name] = loaded
            _log_loaded_input(param_name, var_spec, loaded, elapsed)
        else:
            # Constant — pass through unchanged
            result[param_name] = var_spec
            Log.debug(f"input '{param_name}': constant {type(var_spec).__name__}")
    total_elapsed = time.perf_counter() - total_t0
    Log.info(f"loaded {len(result)} inputs in {total_elapsed:.3f}s")
    return result


def _log_loaded_input(param_name: str, var_spec: Any, loaded: Any, elapsed: float) -> None:
    """Log details about a loaded input."""
    import pandas as pd

    type_name = _input_type_name(var_spec)

    if isinstance(loaded, pd.DataFrame):
        Log.info(f"input '{param_name}': loaded {type_name} -> "
                 f"{len(loaded)} rows, {len(loaded.columns)} cols in {elapsed:.3f}s")
    elif isinstance(loaded, (PerComboLoader, PerComboLoaderMerge)):
        Log.info(f"input '{param_name}': {type_name} (per-combo loader, will load during iteration)")
    else:
        Log.info(f"input '{param_name}': loaded {type_name} in {elapsed:.3f}s")


def _input_type_name(var_spec: Any) -> str:
    """Get a human-readable type name for a var_spec."""
    if isinstance(var_spec, Merge):
        return var_spec.__name__
    if isinstance(var_spec, Fixed):
        inner = var_spec.var_type
        inner_name = _input_type_name(inner)
        fixed_str = ", ".join(f"{k}={v}" for k, v in var_spec.fixed_metadata.items())
        return f"Fixed({inner_name}, {fixed_str})"
    if isinstance(var_spec, Variant):
        inner_name = _input_type_name(var_spec.var_type)
        bp_str = ", ".join(f"{k}={v}" for k, v in sorted(var_spec.branch_params.items()))
        return f"Variant({inner_name}, {bp_str})"
    if isinstance(var_spec, ColumnSelection):
        inner_name = _input_type_name(var_spec.var_type)
        return f"ColumnSelection({inner_name}, {var_spec.columns})"
    if isinstance(var_spec, type):
        return var_spec.__name__
    if hasattr(var_spec, '__name__'):
        return var_spec.__name__
    return type(var_spec).__name__


def _convert_inputs_for_display(inputs: dict[str, Any]) -> dict[str, Any]:
    """Convert inputs for dry_run display without actually loading any data.

    scidb-specific types (Merge, Fixed, ColumnSelection, classes) are converted
    to scifor-compatible display forms or left as constants.
    """
    import pandas as pd

    result = {}
    for param_name, var_spec in inputs.items():
        # Variant is a load-time filter; for display, unwrap to its inner spec.
        if isinstance(var_spec, Variant):
            var_spec = var_spec.var_type
        if isinstance(var_spec, Merge):
            # Use _DryRunMerge so scifor prints "merge {param_name}:" and class names
            result[param_name] = _DryRunMerge(var_spec)
        elif isinstance(var_spec, ColumnSelection):
            dummy = pd.DataFrame(columns=var_spec.columns or [])
            result[param_name] = _scifor.ColumnSelection(
                dummy, var_spec.columns, iterate=var_spec.iterate
            )
        elif isinstance(var_spec, Fixed) and isinstance(var_spec.var_type, ColumnSelection):
            inner = var_spec.var_type
            dummy = pd.DataFrame(columns=inner.columns or [])
            dummy_cs = _scifor.ColumnSelection(dummy, inner.columns, iterate=inner.iterate)
            result[param_name] = _scifor.Fixed(dummy_cs, **var_spec.fixed_metadata)
        elif isinstance(var_spec, Fixed) and not isinstance(var_spec.var_type, Merge):
            dummy = pd.DataFrame()
            result[param_name] = _scifor.Fixed(dummy, **var_spec.fixed_metadata)
        else:
            # Constants, plain classes, etc. — pass through (shown as constants by scifor)
            result[param_name] = var_spec
    return result


def _resolve_colname_from_db(colname: "ColName", db: Any | None) -> str:
    """Resolve a ColName wrapper to the single data column name string.

    Uses the variable's dtype metadata from the database to determine
    what data columns exist, then subtracts schema keys.
    """
    import json

    var_type = colname.var_type

    # Get the database
    resolved_db = db
    if resolved_db is None:
        try:
            from scidb.database import get_database
            resolved_db = get_database()
        except Exception:
            raise ValueError(
                "ColName requires a database to resolve column names. "
                "Either pass db= to for_each or call configure_database() first."
            )

    var_name = var_type.__name__ if isinstance(var_type, type) else type(var_type).__name__
    schema_keys = list(resolved_db.dataset_schema_keys)

    # Query the _variables table for dtype metadata
    try:
        row = resolved_db._execute(
            "SELECT dtype FROM _variables WHERE variable_name = ?",
            [var_name],
        ).fetchone()
    except Exception:
        row = None

    if row is None:
        # Variable not yet saved — try using view_name for single-column mode
        if hasattr(var_type, 'view_name'):
            return var_type.view_name()
        return var_name

    dtype_meta = json.loads(row[0])
    mode = dtype_meta.get("mode", "single_column")

    if mode == "single_column":
        # Single-column variables always have exactly one data column
        col_names = list(dtype_meta.get("columns", {}).keys())
        if col_names:
            return col_names[0]
        if hasattr(var_type, 'view_name'):
            return var_type.view_name()
        return var_name

    if mode == "dataframe":
        # DataFrame variables: subtract schema keys from df_columns
        df_columns = dtype_meta.get("df_columns", list(dtype_meta.get("columns", {}).keys()))
        data_cols = [c for c in df_columns if c not in schema_keys]
        if len(data_cols) == 1:
            return data_cols[0]
        elif len(data_cols) == 0:
            raise ValueError(
                f"ColName({var_name}): variable has no data columns "
                f"(all columns are schema keys). "
                f"Columns: {df_columns}, schema keys: {schema_keys}"
            )
        else:
            raise ValueError(
                f"ColName({var_name}): variable has {len(data_cols)} "
                f"data columns ({data_cols}), expected exactly 1. "
                f"Schema keys: {schema_keys}"
            )

    if mode == "multi_column":
        raise ValueError(
            f"ColName({var_name}): not supported for dict-type (multi_column) variables. "
            f"ColName only works with single-column or single-data-column DataFrame variables."
        )

    # Unknown mode — fall back to view_name
    if hasattr(var_type, 'view_name'):
        return var_type.view_name()
    return var_name


def _load_input(
    var_spec: Any,
    db: Any | None,
    where: Any | None,
    branch_params_filter: dict | None = None,
) -> Any:
    """Load a single input and return a scifor-compatible wrapper or sentinel.

    ``branch_params_filter`` is an orthogonal, load-time filter threaded through
    the recursion exactly like ``where``.  A ``Variant`` wrapper *injects* it into
    its subtree; the other wrappers pass it through; the leaf load applies it via
    ``load_all_as_df(branch_params_filter=…)``.
    """
    import pandas as pd

    # Already a DataFrame — pass through
    if isinstance(var_spec, pd.DataFrame):
        return var_spec

    # Variant: inject/merge its branch_params into the inherited filter (error on
    # conflicting values) and recurse into the inner spec.  Composition with the
    # other wrappers is order-agnostic because the filter is threaded, not
    # wrapper-aware.
    if isinstance(var_spec, Variant):
        merged = dict(branch_params_filter or {})
        for k, v in var_spec.branch_params.items():
            if k in merged and merged[k] != v:
                raise ValueError(
                    f"Conflicting branch_param '{k}' for Variant input: "
                    f"{merged[k]!r} vs {v!r}."
                )
            merged[k] = v
        Log.debug(
            f"[Variant] {var_spec.__name__}: injecting branch_params_filter="
            f"{merged}"
        )
        return _load_input(var_spec.var_type, db, where, branch_params_filter=merged)

    # Merge: check if any constituent needs per-combo loading
    if isinstance(var_spec, Merge):
        _merge_db = db
        if _merge_db is None:
            try:
                from scidb.database import get_database
                _merge_db = get_database()
            except Exception:
                pass
        if _merge_needs_per_combo(var_spec) or _merge_db is None:
            # Use per-combo when a constituent lacks bulk-load support, or when
            # there is genuinely no database — without one, the bulk loader
            # cannot filter each constituent by schema keys.
            return PerComboLoaderMerge(var_spec)
        # All constituents can be pre-loaded.
        # All filter types (VariableFilter, ColumnFilter, InFilter, SchemaKey, Raw)
        # are now propagated to Merge constituents.  Coverage is validated once
        # against the actual Merge inner-join result rather than per-constituent
        # to avoid false-positive errors when a constituent has "extra" rows that
        # the Merge would eliminate anyway.
        loaded_tables = []
        _SCIDB_META = {"__record_id", "__branch_params", "version"}
        _schema_keys = set(getattr(_merge_db, 'dataset_schema_keys', []) if _merge_db is not None else [])

        if where is not None:
            merge_effective_ids = _compute_merge_effective_ids(_merge_db, var_spec)
            _check_merge_filter_coverage(_merge_db, where, merge_effective_ids)
            # Provenance key for the variable-level portion of the filter, shared
            # by every constituent.  A constituent computed by for_each with this
            # where= stored it as its __where version key; carrying it lets the
            # constituent loader match that single variant (Strategy 1) instead of
            # returning every variant that happens to share the same schema keys.
            merge_where_key = _merge_constituent_where_key(where)
            Log.debug(
                f"[Merge] {var_spec.__name__}: where provenance key="
                f"{merge_where_key!r}"
            )

        for sub_spec in var_spec.var_specs:
            if where is not None:
                cls = _get_loadable_class_from_spec(sub_spec)
                matching_ids = where.resolve(
                    _merge_db, cls, cls.table_name(),
                    validate_coverage=False,  # coverage validated once above
                )
                constituent_where = _PreresolvedFilter(
                    matching_ids, where_key=merge_where_key
                )
            else:
                constituent_where = None
            # Per-constituent Variant injects its own branch_params_filter inside
            # this recursion; the inherited filter (normally None — Variant(Merge)
            # is rejected at construction) is threaded for safety.
            loaded = _load_input(
                sub_spec, db, where=constituent_where,
                branch_params_filter=branch_params_filter,
            )
            # Strip scidb metadata columns that would conflict when merged column-wise.
            # __record_id/__branch_params/version appear in every constituent but carry
            # no per-row meaning after merge; scifor's _prepare_merge doesn't track them.
            #
            # Also drop schema key columns that are entirely null: when a variable was
            # saved at a coarser granularity (e.g. subject-level only), the spread layout
            # includes ALL schema key columns but fills unused ones with NaN.  Keeping
            # these all-null columns causes MATLAB's filter_table_for_combo to receive
            # cell arrays of empty doubles and crash when it attempts string conversion.
            # Dropping them lets the constituent broadcast across the missing dimension.
            if isinstance(loaded, pd.DataFrame):
                drop_cols = [c for c in loaded.columns
                             if c in _SCIDB_META or c.startswith("__")]
                all_null_sk = [c for c in loaded.columns
                               if c in _schema_keys and loaded[c].isna().all()]
                drop_cols = list(dict.fromkeys(drop_cols + all_null_sk))
                if drop_cols:
                    loaded = loaded.drop(columns=drop_cols)
            elif hasattr(loaded, 'data') and isinstance(loaded.data, pd.DataFrame):
                # _scifor.Fixed wrapping a DataFrame
                drop_cols = [c for c in loaded.data.columns
                             if c in _SCIDB_META or c.startswith("__")]
                all_null_sk = [c for c in loaded.data.columns
                               if c in _schema_keys and loaded.data[c].isna().all()]
                drop_cols = list(dict.fromkeys(drop_cols + all_null_sk))
                if drop_cols:
                    loaded.data = loaded.data.drop(columns=drop_cols)
            loaded_tables.append(loaded)
        return _scifor.Merge(*loaded_tables)

    # Fixed: check for Fixed(Merge(...)) error, then load inner
    if isinstance(var_spec, Fixed):
        if isinstance(var_spec.var_type, Merge):
            raise TypeError(
                "Fixed cannot wrap a Merge. Use Fixed on individual "
                "constituents inside the Merge instead: "
                "Merge(Fixed(df1, ...), df2)"
            )
        inner_loaded = _load_input(
            var_spec.var_type, db, where,
            branch_params_filter=branch_params_filter,
        )
        if isinstance(inner_loaded, PerComboLoader):
            # Inner needs per-combo loading; wrap the whole Fixed spec
            return PerComboLoader(var_spec)
        # Keep __record_id for variant tracking (needed for BaseVariable reconstruction)
        # but strip __branch_params which is redundant for Fixed inputs.
        import pandas as pd
        if isinstance(inner_loaded, pd.DataFrame):
            if "__branch_params" in inner_loaded.columns:
                inner_loaded = inner_loaded.drop(columns=["__branch_params"])
        # Stringify fixed_metadata schema keys to match the stringified
        # DataFrame columns produced by load_all_as_df (spread layout).
        fixed_meta = dict(var_spec.fixed_metadata)
        _sk = _get_schema_keys(db)
        if _sk:
            from .database import _schema_str
            fixed_meta = {
                k: _schema_str(v) if k in _sk else v
                for k, v in fixed_meta.items()
            }
        return _scifor.Fixed(inner_loaded, **fixed_meta)

    # ColumnSelection: load inner var_type if possible, else per-combo
    if isinstance(var_spec, ColumnSelection):
        if hasattr(var_spec.var_type, 'load'):
            loaded_df = _load_var_type_as_spread(
                var_spec.var_type, db, where,
                branch_params_filter=branch_params_filter,
            )
            return _scifor.ColumnSelection(
                loaded_df, var_spec.columns, iterate=var_spec.iterate
            )
        return PerComboLoader(var_spec)

    # PathInput: needs per-combo resolution via load(**combo); wrap in PerComboLoader
    if isinstance(var_spec, PathInput):
        return PerComboLoader(var_spec)

    # Variable type (class with .load()): bulk load or per-combo.
    # Use bulk loading only when the DB provides load_all_as_df; without it
    # the slow-path cannot build a properly-keyed spread DataFrame (it only
    # calls load() once with version/db kwargs, not per combo metadata), so
    # fall back to per-combo loading — same logic as Merge above.
    if isinstance(var_spec, type) or hasattr(var_spec, 'load'):
        if hasattr(var_spec, 'load'):
            _check_db = db
            if _check_db is None:
                try:
                    from scidb.database import get_database
                    _check_db = get_database()
                except Exception:
                    pass
            if _check_db is not None and hasattr(_check_db, 'load_all_as_df'):
                return _load_var_type_as_spread(
                    var_spec, db, where,
                    branch_params_filter=branch_params_filter,
                )
            return PerComboLoader(var_spec)
        return PerComboLoader(var_spec)

    # Unknown — return as-is
    return var_spec


def _compute_fixed_input_rids(inputs: dict, db) -> dict:
    """Compute record_ids for Fixed inputs for lineage tracking.

    Fixed inputs have __record_id stripped during variant expansion (line 826-829),
    but lineage tracking needs to know which specific record was used for staleness
    checking. This function computes those record_ids.

    Args:
        inputs: The inputs dict passed to for_each (may contain Fixed wrappers)
        db: Database instance

    Returns:
        Dict mapping "__rid_{param_name}" to record_id for each Fixed input
    """
    fixed_rids = {}

    # If db is None, we can't look up record_ids
    if db is None:
        return fixed_rids

    for name, value in inputs.items():
        # Detect Fixed wrapper
        if not hasattr(value, 'fixed_metadata'):
            continue

        # Unwrap to get inner variable type
        inner = value.var_type if hasattr(value, 'var_type') else value

        # Unwrap ColumnSelection if present
        if hasattr(inner, 'var_type'):
            inner = inner.var_type

        # Must be a variable type (class)
        if not isinstance(inner, type):
            continue

        # Look up record_id for this Fixed input
        try:
            rid = db.find_record_id(inner, value.fixed_metadata)
            if rid:
                fixed_rids[f"__rid_{name}"] = rid
        except Exception:
            # If lookup fails, skip this Fixed input
            pass

    return fixed_rids


def _get_schema_level_idx(db, schema_ids: set) -> int:
    """Return the deepest populated schema key index for the given schema_ids, or -1."""
    schema_keys = db.dataset_schema_keys
    if not schema_ids:
        return -1
    placeholders = ", ".join(["?"] * len(schema_ids))
    rows = db._duck._fetchdf(
        f"SELECT * FROM _schema WHERE schema_id IN ({placeholders})",
        list(schema_ids),
    )
    if len(rows) == 0:
        return -1
    level_idx = -1
    for i, key in enumerate(schema_keys):
        if key in rows.columns and rows[key].notna().any():
            level_idx = i
    return level_idx


def _compute_merge_effective_ids(db, merge_spec: "Merge") -> set:
    """Compute the schema_ids that the Merge inner join will produce.

    For each constituent, expand coarser schema_ids to the finest level, then
    intersect all fine-level sets.  The result is the set of schema_ids that
    would survive the Merge inner join — used to validate filter coverage once
    against the right target rather than per-constituent.
    """
    from .filters import _get_all_schema_ids_for_variable, _expand_coarse_to_fine_schema_ids

    # Collect (table_name, schema_ids) for each constituent
    constituent_data = []
    for sub_spec in merge_spec.var_specs:
        cls = _get_loadable_class_from_spec(sub_spec)
        if cls is None:
            continue
        table_name = cls.table_name()
        schema_ids = _get_all_schema_ids_for_variable(db, table_name)
        constituent_data.append((table_name, schema_ids))

    if not constituent_data:
        return set()

    # Determine level index for each constituent
    levels = [
        (_get_schema_level_idx(db, ids), table_name, ids)
        for table_name, ids in constituent_data
    ]

    max_level = max(lv for lv, _, _ in levels)
    if max_level < 0:
        return set()

    # Pick the first fine-level constituent's table as expansion target
    fine_table_name = next(tn for lv, tn, _ in levels if lv == max_level)

    # Compute each constituent's contribution at the finest level
    effective_sets = []
    for lv, table_name, schema_ids in levels:
        if lv == max_level:
            effective_sets.append(schema_ids)
        else:
            expanded = _expand_coarse_to_fine_schema_ids(db, schema_ids, fine_table_name)
            effective_sets.append(expanded)

    # Intersection = Merge inner join result
    result = effective_sets[0]
    for s in effective_sets[1:]:
        result = result & s
    return result


def _check_merge_filter_coverage(db, where, merge_effective_ids: set) -> None:
    """Validate that the filter covers all schema_ids the Merge inner join will produce.

    Recurses through the filter tree.  VariableFilter/ColumnFilter/InFilter are
    validated against merge_effective_ids via _validate_filter_coverage with the
    override parameter.  SchemaKey and Raw filters have no coverage concept and
    are skipped.

    Raises:
        ValueError: If the filter variable is missing data for a schema_id that
            genuinely survives the Merge inner join.
    """
    from .filters import (
        VariableFilter, ColumnFilter, InFilter,
        CompoundFilter, NotFilter,
        _validate_filter_coverage, _get_all_schema_ids_for_variable,
    )

    if where is None or not merge_effective_ids:
        return

    if isinstance(where, (VariableFilter, ColumnFilter, InFilter)):
        filter_table_name = where.variable_class.table_name()
        filter_ids = _get_all_schema_ids_for_variable(db, filter_table_name)
        filter_level_idx = _get_schema_level_idx(db, filter_ids)
        target_level_idx = _get_schema_level_idx(db, merge_effective_ids)

        _validate_filter_coverage(
            db, where.variable_class, None,
            filter_table_name, None,
            filter_level_idx, target_level_idx,
            target_schema_ids_override=merge_effective_ids,
        )

    elif isinstance(where, CompoundFilter):
        _check_merge_filter_coverage(db, where.left, merge_effective_ids)
        _check_merge_filter_coverage(db, where.right, merge_effective_ids)

    elif isinstance(where, NotFilter):
        _check_merge_filter_coverage(db, where.inner, merge_effective_ids)

    # SchemaKeyInFilter, SchemaKeyCompareFilter, RawFilter: no coverage concept; no-op


def _merge_needs_per_combo(merge_spec: "Merge") -> bool:
    """Return True if any Merge constituent lacks load."""
    for spec in merge_spec.var_specs:
        cls = _get_loadable_class_from_spec(spec)
        if cls is not None and not hasattr(cls, 'load'):
            return True
    return False


def _get_loadable_class_from_spec(spec: Any) -> Any:
    """Extract the innermost loadable class from a spec (class, Variant, Fixed, ColumnSelection)."""
    if isinstance(spec, Variant):
        spec = spec.var_type
    if isinstance(spec, Fixed):
        spec = spec.var_type
    if isinstance(spec, Variant):
        spec = spec.var_type
    if isinstance(spec, ColumnSelection):
        spec = spec.var_type
    if isinstance(spec, type) or hasattr(spec, 'load'):
        return spec
    return None


def _make_raw_value_wrapper(fn: Any) -> Any:
    """Wrap fn so LineageFcnResult returns collapse to their raw value.

    Used for for_columns iteration: per-column results are reassembled into one
    wide DataFrame, which cannot hold per-column lineage objects. Upstream
    provenance for the combined output is still recorded at save time from the
    input record_ids.
    """
    try:
        from scilineage.lineage import get_raw_value
        from scilineage.core import LineageFcnResult
    except Exception:
        get_raw_value = None
        LineageFcnResult = ()

    def wrapped(*args, **kwargs):
        result = fn(*args, **kwargs)
        if get_raw_value is not None and isinstance(result, LineageFcnResult):
            return get_raw_value(result)
        return result

    wrapped.__name__ = getattr(fn, "__name__", "for_columns_fn")
    return wrapped


def _iterate_column_selection(spec: Any) -> "ColumnSelection | None":
    """Return the iterate-mode ColumnSelection inside a spec (bare or Fixed), else None."""
    if isinstance(spec, ColumnSelection) and spec.iterate:
        return spec
    if isinstance(spec, Fixed) and isinstance(spec.var_type, ColumnSelection) \
            and spec.var_type.iterate:
        return spec.var_type
    return None


def _resolve_all_columns(var_type: Any, db: Any | None) -> list[str]:
    """Resolve ``for_columns()`` (all columns) to the variable's data column names.

    Loads the variable's stored table and returns its columns minus schema keys
    and internal ``__*`` columns. Used so that an empty ``columns`` becomes a
    concrete list before version keys are computed.
    """
    import pandas as pd

    loaded = _load_var_type_as_spread(var_type, db, None)
    var_name = getattr(var_type, "__name__", repr(var_type))
    if not isinstance(loaded, pd.DataFrame):
        raise ValueError(
            f"for_columns(): could not load '{var_name}' to resolve its columns "
            f"(no DataFrame returned). Pass an explicit column list instead."
        )
    schema_keys = _get_schema_keys(db)
    cols = [
        c for c in loaded.columns
        if c not in schema_keys and not str(c).startswith("__")
    ]
    if not cols:
        raise ValueError(
            f"for_columns(): no data columns found for '{var_name}' "
            f"(columns were {list(loaded.columns)})."
        )
    return cols


def _resolve_for_columns(inputs: dict, db: Any | None) -> dict:
    """Resolve iterate-mode ColumnSelection inputs (``for_columns``).

    Expands empty ``columns`` ([] / all) to all data columns and validates that every
    iterate input shares the same column set (zipped by name). Returns a new
    inputs dict with concrete ColumnSelections; raises ValueError on mismatch.
    Inputs without any iterate selection are returned unchanged.
    """
    iterate_params = {
        name: cs for name, spec in inputs.items()
        if (cs := _iterate_column_selection(spec)) is not None
    }
    if not iterate_params:
        return inputs

    Log.info(
        f"[scidb] Step 1.5: resolving for_columns iteration for input(s) "
        f"{list(iterate_params)}"
    )

    resolved_db = db
    if resolved_db is None:
        try:
            from scidb.database import get_database
            resolved_db = get_database()
        except Exception:
            resolved_db = None

    resolved_cols: dict[str, list[str]] = {}
    for name, cs in iterate_params.items():
        if not cs.columns:  # empty [] (or legacy None) -> all data columns
            cols = _resolve_all_columns(cs.var_type, resolved_db)
            Log.info(
                f"[scidb] for_columns: resolved '{name}' to all {len(cols)} "
                f"column(s): {cols}"
            )
        else:
            cols = list(cs.columns)
        resolved_cols[name] = cols

    # Zip-by-name: every iterate input must cover the same column set.
    ref_name = next(iter(resolved_cols))
    ref_set = set(resolved_cols[ref_name])
    for name, cols in resolved_cols.items():
        if set(cols) != ref_set:
            raise ValueError(
                f"for_columns inputs must iterate over the same columns "
                f"(zipped by name). '{ref_name}' resolves to "
                f"{sorted(ref_set)} but '{name}' resolves to {sorted(cols)}."
            )

    # Rebuild inputs with concrete, iterate-mode ColumnSelections.
    new_inputs = dict(inputs)
    for name, cs in iterate_params.items():
        new_cs = ColumnSelection(cs.var_type, resolved_cols[name], iterate=True)
        spec = inputs[name]
        if isinstance(spec, Fixed):
            new_inputs[name] = Fixed(new_cs, **spec.fixed_metadata)
        else:
            new_inputs[name] = new_cs
    return new_inputs


def _load_var_type_as_spread(
    var_type: Any,
    db: Any | None,
    where: Any | None,
    branch_params_filter: dict | None = None,
) -> "pd.DataFrame":
    """Bulk load all records for a variable type into a spread DataFrame.

    Routes to ``db.load_all_as_df`` (the fast bulk engine) when a database is
    available.  Falls back to the iterator-based slow path for types that the
    fast engine cannot handle (custom serialisation, subclass overrides, etc.).

    The returned DataFrame has ``__record_id`` and ``__branch_params`` columns
    plus one column per schema/version key and per data column (spread layout).
    """
    import pandas as pd

    _vt_name = getattr(var_type, '__name__', type(var_type).__name__)
    _t0 = time.perf_counter()

    # Resolve the database instance.
    resolved_db = db
    if resolved_db is None:
        try:
            from scidb.database import get_database
            resolved_db = get_database()
        except Exception:
            pass

    if resolved_db is not None and hasattr(resolved_db, 'load_all_as_df'):
        # Fast path: bulk engine with spread layout.
        where_kw = {"where": where} if where is not None else {}
        bp_kw = (
            {"branch_params_filter": branch_params_filter}
            if branch_params_filter else {}
        )
        if branch_params_filter:
            Log.debug(
                f"[Variant] _load_var_type_as_spread({_vt_name}): applying "
                f"branch_params_filter={branch_params_filter}"
            )
        result = resolved_db.load_all_as_df(
            var_type,
            layout="spread",
            include_rid=True,
            include_bp=True,
            stringify_schema=True,
            version_id="latest",
            **where_kw,
            **bp_kw,
        )
        Log.info(
            f"[timing] _load_var_type_as_spread({_vt_name}): "
            f"{len(result)} rows x {len(result.columns) if not result.empty else 0} cols "
            f"in {time.perf_counter() - _t0:.3f}s (fast path)"
        )
        return result

    # Slow fallback: use iterator (no database or database lacks load_all_as_df).
    # BaseVariable.load derives branch_params_filter from its non-schema metadata
    # kwargs (version="latest" path), so pass the pinned branch_params as kwargs.
    db_kwargs = {"db": db} if db is not None else {}
    where_kwargs = {"where": where} if where is not None else {}
    bp_kwargs = dict(branch_params_filter) if branch_params_filter else {}

    _raw = var_type.load(version="latest", **db_kwargs, **where_kwargs, **bp_kwargs)
    loaded = _raw if isinstance(_raw, list) else [_raw]

    if not loaded:
        return pd.DataFrame()

    _schema_keys: set = set()
    if resolved_db is not None and hasattr(resolved_db, 'dataset_schema_keys'):
        _schema_keys = set(resolved_db.dataset_schema_keys)

    def _stringify_meta(meta: dict) -> dict:
        const_keys: set = set()
        constants_val = meta.get("__constants")
        if constants_val:
            try:
                if isinstance(constants_val, dict):
                    const_keys = set(constants_val.keys())
                else:
                    const_keys = set(json.loads(constants_val).keys())
            except Exception:
                pass
        return {k: str(v) if k in _schema_keys and v is not None else v
                for k, v in meta.items()
                if not k.startswith("__") and k not in const_keys}

    first = loaded[0]
    all_have_data = all(hasattr(v, 'data') for v in loaded)

    if all_have_data and isinstance(first.data, pd.DataFrame):
        all_data = []
        all_meta_rows = []
        for var in loaded:
            data_df = var.data
            meta = _stringify_meta(dict(var.metadata) if hasattr(var, 'metadata') and var.metadata else {})
            meta["__record_id"] = getattr(var, 'record_id', None)
            meta["__branch_params"] = json.dumps(getattr(var, 'branch_params', None) or {})
            nr = len(data_df)
            for _ in range(nr):
                all_meta_rows.append(meta)
            all_data.append(data_df.reset_index(drop=True))

        if all_meta_rows:
            combined_meta_df = pd.DataFrame(all_meta_rows)
            combined_data_df = pd.concat(all_data, ignore_index=True)
            result = pd.concat([combined_meta_df.reset_index(drop=True),
                                combined_data_df.reset_index(drop=True)], axis=1)
        else:
            result = pd.DataFrame()
    elif all_have_data:
        view_name = var_type.view_name() if hasattr(var_type, 'view_name') else getattr(var_type, '__name__', type(var_type).__name__)
        all_data = []
        all_meta_rows = []
        for var in loaded:
            # Use _to_dataframe so scalars/arrays/lists expand into proper rows
            # (consistent with PerComboLoaderMerge and the DataFrame branch above)
            part_df = _to_dataframe(var.data, view_name)
            meta = _stringify_meta(dict(var.metadata) if hasattr(var, 'metadata') and var.metadata else {})
            meta["__record_id"] = getattr(var, 'record_id', None)
            meta["__branch_params"] = json.dumps(getattr(var, 'branch_params', None) or {})
            nr = len(part_df)
            for _ in range(nr):
                all_meta_rows.append(dict(meta))
            all_data.append(part_df.reset_index(drop=True))
        if all_meta_rows:
            combined_meta_df = pd.DataFrame(all_meta_rows)
            combined_data_df = pd.concat(all_data, ignore_index=True)
            result = pd.concat([combined_meta_df.reset_index(drop=True),
                                combined_data_df.reset_index(drop=True)], axis=1)
        else:
            result = pd.DataFrame()
    else:
        var_name = getattr(var_type, '__name__', type(var_type).__name__)
        rows = []
        for var in loaded:
            rows.append({var_name: var, "__record_id": getattr(var, 'record_id', None), "__branch_params": "{}"})
        result = pd.DataFrame(rows)

    Log.info(
        f"[timing] _load_var_type_as_spread({_vt_name}): "
        f"{len(result)} rows (slow fallback) in {time.perf_counter() - _t0:.3f}s"
    )
    return result


# ---------------------------------------------------------------------------
# Per-combo resolution helpers
# ---------------------------------------------------------------------------

def _resolve_per_combo_loader(pcl: "PerComboLoader", load_kw: dict) -> Any:
    """Resolve a PerComboLoader per-combo by calling spec.load(**effective_kw)."""
    spec = pcl.spec

    if isinstance(spec, Fixed):
        effective_kw = {**load_kw, **spec.fixed_metadata}
        inner = spec.var_type
        columns = None
        if isinstance(inner, ColumnSelection):
            columns = inner.columns
            inner = inner.var_type
        lv = inner.load(**effective_kw)
        raw = lv.data if hasattr(lv, 'data') else lv
        if columns:
            cls_name = getattr(inner, '__name__', type(inner).__name__)
            raw = _apply_per_combo_col_selection(raw, columns, cls_name)
        return raw

    if isinstance(spec, ColumnSelection):
        lv = spec.var_type.load(**load_kw)
        raw = lv.data if hasattr(lv, 'data') else lv
        cls_name = getattr(spec.var_type, '__name__', type(spec.var_type).__name__)
        return _apply_per_combo_col_selection(raw, spec.columns, cls_name)

    # Plain class
    lv = spec.load(**load_kw)
    return lv.data if hasattr(lv, 'data') else lv


def _resolve_per_combo_merge(pcl_merge: "PerComboLoaderMerge", load_kw: dict) -> "pd.DataFrame":
    """Resolve a PerComboLoaderMerge per-combo by loading each constituent."""
    from scifor.foreach import _merge_parts as _scifor_merge_parts

    parts = []
    for spec in pcl_merge.merge_spec.var_specs:
        effective_kw = dict(load_kw)
        columns = None
        actual_spec = spec

        # Unwrap Fixed
        if isinstance(actual_spec, Fixed):
            effective_kw = {**load_kw, **actual_spec.fixed_metadata}
            actual_spec = actual_spec.var_type

        # Unwrap ColumnSelection
        if isinstance(actual_spec, ColumnSelection):
            columns = actual_spec.columns
            actual_spec = actual_spec.var_type

        # Load the variable
        lv = actual_spec.load(**effective_kw)
        cls_name = getattr(actual_spec, '__name__', type(actual_spec).__name__)
        if isinstance(lv, list):
            raise ValueError(
                f"{cls_name}.load() returned multiple results (list), expected exactly 1."
            )
        raw = lv.data if hasattr(lv, 'data') else lv

        # Convert to DataFrame
        part_df = _to_dataframe(raw, cls_name)

        # Apply column selection
        if columns:
            missing = [c for c in columns if c not in part_df.columns]
            if missing:
                raise KeyError(
                    f"Columns {missing} not found in {cls_name}. "
                    f"Available: {list(part_df.columns)}"
                )
            if len(columns) == 1:
                part_df = part_df[[columns[0]]]
            else:
                part_df = part_df[columns]

        parts.append(part_df)

    return _scifor_merge_parts(parts)


def _to_dataframe(data: Any, cls_name: str) -> "pd.DataFrame":
    """Convert raw data (scalar, array, list, DataFrame) to a named DataFrame."""
    import pandas as pd
    import numpy as np

    if isinstance(data, pd.DataFrame):
        return data.reset_index(drop=True)
    if isinstance(data, np.ndarray):
        if data.ndim == 1:
            return pd.DataFrame({cls_name: data})
        elif data.ndim == 2:
            cols = [f"{cls_name}_{i}" for i in range(data.shape[1])]
            return pd.DataFrame(data, columns=cols)
        else:
            raise ValueError(f"Cannot convert {data.ndim}D array from {cls_name} to DataFrame")
    if isinstance(data, (list, tuple)):
        return pd.DataFrame({cls_name: list(data)})
    # Scalar
    return pd.DataFrame({cls_name: [data]})


def _apply_per_combo_col_selection(raw: Any, columns: list, cls_name: str) -> Any:
    """Apply column selection to raw data, returning array (1 col) or DataFrame (multi-col)."""
    import pandas as pd
    df = _to_dataframe(raw, cls_name)
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise KeyError(f"Columns {missing} not found in {cls_name}. Available: {list(df.columns)}")
    if len(columns) == 1:
        return df[columns[0]].values
    return df[columns]


# ---------------------------------------------------------------------------
# Saving results
# ---------------------------------------------------------------------------

def _save_results(
    result_tbl: "pd.DataFrame",
    outputs: list[Any],
    output_names: list[str],
    config_keys: dict,
    db: Any | None,
    rid_to_bp: "dict | None" = None,
    rid_keys: "list | None" = None,
    lineage_fixed_rids: "dict | None" = None,
    combo_to_rids: "dict | None" = None,
    combo_to_rids_keys: "list | None" = None,
) -> None:
    """Save results from the result table to output variable types using batch operations.

    This function preserves all the config_keys and branch_params tracking from the
    original implementation while using save_batch for efficiency when saving multiple rows.

    The for_each save path adds config_keys and branch_params tracking on top of the
    direct save, as documented in scidb-identity-and-data-flow.md.
    """
    import pandas as pd

    batch_start_time = time.perf_counter()
    db_kwargs = {"db": db} if db is not None else {}

    # Get schema keys for dynamic discriminator detection
    schema_keys_set: set = set()
    if db is not None and hasattr(db, 'dataset_schema_keys'):
        schema_keys_set = set(db.dataset_schema_keys)
    else:
        try:
            schema_keys_set = set(_scifor.get_schema() or [])
        except Exception:
            pass

    # Determine which columns are metadata (not output names)
    meta_cols = [c for c in result_tbl.columns if c not in output_names]

    fn_name = config_keys.get("__fn", "")
    # Handle both dict (new format) and JSON string (old format) for backward compatibility
    constants_val = config_keys.get("__constants", {})
    if isinstance(constants_val, str):
        direct_constants = json.loads(constants_val or "{}")
    else:
        direct_constants = constants_val or {}

    # ===========================================================================
    # PHASE 1: Collect all (data, metadata) items for batch saving
    # ===========================================================================
    # Structure: {(output_idx, save_path): [(data, metadata), ...]}
    # save_path is one of: 'normal', 'flatten', 'lineage'
    batch_items = {}
    lineage_items = []  # LineageFcnResult items saved sequentially (special handling)

    prep_start = time.perf_counter()
    Log.info(f"[batch_save] Preparing {len(result_tbl)} result row(s) for batch save")

    # Convert DataFrame to list of dicts for 10-100x faster iteration than iterrows()
    rows = result_tbl.to_dict('records')
    for row_idx, row in enumerate(rows):
        # 1. Collect upstream branch_params via __rid_* columns → rid_to_bp lookup
        merged_bp: dict = {}
        if combo_to_rids is not None and combo_to_rids_keys is not None:
            # Aggregation mode: merge branch_params from all contributing rids
            combo_key = tuple(str(row.get(k, "")) for k in combo_to_rids_keys)
            rids_by_param = combo_to_rids.get(combo_key, {})
            # Flatten all rids from all parameters
            for rid_col, rids in rids_by_param.items():
                for rid in rids:
                    if rid in rid_to_bp:
                        for k, v in rid_to_bp[rid].items():
                            if k in merged_bp and merged_bp[k] != v:
                                warnings.warn(
                                    f"branch_params key '{k}' overwritten: "
                                    f"{merged_bp[k]!r} → {v!r}. "
                                    f"Use version= for precise selection.",
                                    UserWarning, stacklevel=4,
                                )
                            merged_bp[k] = v
        elif rid_to_bp and rid_keys:
            # Full iteration mode: existing per-row rid lookup
            for rid_col in rid_keys:
                if rid_col not in row:
                    continue
                rid = row[rid_col]
                if rid and rid in rid_to_bp:
                    for k, v in rid_to_bp[rid].items():
                        if k in merged_bp and merged_bp[k] != v:
                            warnings.warn(
                                f"branch_params key '{k}' overwritten: "
                                f"{merged_bp[k]!r} → {v!r}. "
                                f"Use version= for precise selection.",
                                UserWarning, stacklevel=4,
                            )
                        merged_bp[k] = v

        # 2. Add constants namespaced by function name (for branch_params tracking)
        for k, v in direct_constants.items():
            merged_bp[f"{fn_name}.{k}"] = v

        # 3. Add dynamic discriminators (non-schema, non-__ meta columns with scalar values)
        _scalar_types = (bool, int, float, str)
        for col in meta_cols:
            if col.startswith("__"):
                continue
            if col in schema_keys_set:
                continue
            val = row.get(col)
            if val is None:
                continue
            if isinstance(val, float) and pd.isna(val):
                continue
            if not isinstance(val, _scalar_types):
                continue  # Skip numpy arrays and other complex types
            if col in merged_bp and merged_bp[col] != val:
                warnings.warn(
                    f"branch_params key '{col}' overwritten: "
                    f"{merged_bp[col]!r} → {val!r}. "
                    f"Use version= for precise selection.",
                    UserWarning, stacklevel=4,
                )
            merged_bp[col] = val

        # Build save metadata: non-__ cols (schema keys etc.) + config_keys + __branch_params
        # Exclude __rid_* and other internal __ columns from version keys.
        save_metadata = {
            col: row[col] for col in meta_cols if not col.startswith("__")
        }
        save_metadata.update(config_keys)

        # Unpack constants as direct keys so downstream consumers (e.g. scihist's
        # _save_with_lineage) see them in the metadata dict.  They are also stored
        # as __constants (JSON) in config_keys, so _stringify_meta can strip them
        # when loading back — preventing them from polluting input DataFrames.
        for k, v in direct_constants.items():
            if k not in save_metadata:
                save_metadata[k] = v

        save_metadata["__branch_params"] = merged_bp

        # Add upstream record_ids to version_keys so that records from different
        # upstream variants get distinct record_ids even when content is identical.
        if combo_to_rids is not None and combo_to_rids_keys is not None:
            # Aggregation mode: collect all contributing upstream rids per parameter
            combo_key = tuple(str(row.get(k, "")) for k in combo_to_rids_keys)
            rids_by_param = combo_to_rids.get(combo_key, {})
            if rids_by_param:
                # Build __upstream from contributing rids
                # Since aggregation has multiple upstream records per parameter,
                # we store them as individual indexed entries for provenance compatibility:
                # __rid_signal_0, __rid_signal_1, etc.
                upstream = {}
                for rid_col, rids in rids_by_param.items():
                    if rids:
                        if len(rids) == 1:
                            # Single rid: store normally
                            upstream[rid_col] = rids[0]
                        else:
                            # Multiple rids: store as indexed entries
                            for idx, rid in enumerate(rids):
                                upstream[f"{rid_col}_{idx}"] = rid
                if upstream:
                    save_metadata["__upstream"] = upstream
        elif rid_keys:
            # Full iteration mode: per-row rid lookup
            upstream = {}
            for rid_col in rid_keys:
                if rid_col in row:
                    rid_val = row[rid_col]
                    if rid_val is not None and not (isinstance(rid_val, float) and pd.isna(rid_val)):
                        upstream[rid_col] = rid_val
            if upstream:
                save_metadata["__upstream"] = upstream

        for output_idx, (output_obj, output_name) in enumerate(zip(outputs, output_names)):
            if output_name not in row:
                # Flatten/distribute mode: fn returned a DataFrame whose columns are
                # spread directly in result_tbl (scifor all_dataframes flatten mode).
                # Build a 1-row DataFrame from non-schema, non-__ data columns.
                data_cols = [c for c in meta_cols
                             if not c.startswith("__") and c not in schema_keys_set]
                if not data_cols:
                    continue
                output_value = pd.DataFrame({c: [row[c]] for c in data_cols})
                save_meta_for_output = {k: v for k, v in save_metadata.items()
                                        if k not in set(data_cols)}

                # Collect for batch save - need deep copy to avoid shared dict references
                key = (output_idx, 'flatten')
                if key not in batch_items:
                    batch_items[key] = []
                # Deep copy metadata to avoid sharing __branch_params dict across rows
                meta_copy = dict(save_meta_for_output)
                if "__branch_params" in meta_copy:
                    meta_copy["__branch_params"] = dict(meta_copy["__branch_params"])
                if "__upstream" in meta_copy and isinstance(meta_copy["__upstream"], dict):
                    meta_copy["__upstream"] = dict(meta_copy["__upstream"])
                batch_items[key].append((output_value, meta_copy))
                continue

            output_value = row[output_name]

            # Detect LineageFcnResult and handle separately (cannot batch these)
            if HAS_LINEAGE and isinstance(output_value, LineageFcnResult):
                lineage_metadata = dict(save_metadata)
                # Deep copy nested dicts
                if "__branch_params" in lineage_metadata:
                    lineage_metadata["__branch_params"] = dict(lineage_metadata["__branch_params"])
                if "__upstream" in lineage_metadata and isinstance(lineage_metadata["__upstream"], dict):
                    lineage_metadata["__upstream"] = dict(lineage_metadata["__upstream"])
                if lineage_fixed_rids:
                    lineage_metadata["__lineage_fixed_rids"] = lineage_fixed_rids
                lineage_items.append((output_obj, output_value, lineage_metadata, row_idx))
                continue

            # Normal save path - collect for batch save - need deep copy to avoid shared dict references
            key = (output_idx, 'normal')
            if key not in batch_items:
                batch_items[key] = []
            # Deep copy metadata to avoid sharing __branch_params dict across rows
            meta_copy = dict(save_metadata)
            if "__branch_params" in meta_copy:
                meta_copy["__branch_params"] = dict(meta_copy["__branch_params"])
            if "__upstream" in meta_copy and isinstance(meta_copy["__upstream"], dict):
                meta_copy["__upstream"] = dict(meta_copy["__upstream"])
            batch_items[key].append((output_value, meta_copy))

    prep_elapsed = time.perf_counter() - prep_start
    Log.info(f"[batch_save] Preparation complete in {prep_elapsed:.3f}s: "
             f"{len(batch_items)} batch group(s), {len(lineage_items)} lineage item(s)")

    # ===========================================================================
    # PHASE 2: Execute batch saves
    # ===========================================================================
    batch_save_start = time.perf_counter()
    total_saved = 0

    for (output_idx, save_path), items in batch_items.items():
        output_obj = outputs[output_idx]

        if len(items) == 0:
            continue

        Log.info(f"[batch_save] Saving {len(items)} record(s) for {_output_name(output_obj)} ({save_path} path)")

        try:
            save_t0 = time.perf_counter()

            # Use save_batch for efficiency
            if db is not None:
                record_ids = db.save_batch(type(output_obj) if not isinstance(output_obj, type) else output_obj,
                                          items,
                                          profile=False)
            else:
                from .database import get_database
                _db = get_database()
                record_ids = _db.save_batch(
                    type(output_obj) if not isinstance(output_obj, type) else output_obj,
                    items,
                    profile=False,
                )

            save_elapsed = time.perf_counter() - save_t0
            total_saved += len(items)

            # Log summary (first few records)
            for i, ((data, meta), rid) in enumerate(zip(items[:3], record_ids[:3])):
                meta_str = ", ".join(f"{k}={v}" for k, v in meta.items()
                                     if not k.startswith("__"))
                data_desc = _describe_save_data(data)
                rid_short = rid[:12] if isinstance(rid, str) else str(rid)
                suffix = " [flatten]" if save_path == 'flatten' else ""
                msg = f"[save] {meta_str}: {_output_name(output_obj)} -> record_id={rid_short} ({data_desc}){suffix}"
                if i == 0:
                    print(msg)  # Print first one
                Log.info(msg)

            if len(items) > 3:
                Log.info(f"[save] ... and {len(items) - 3} more record(s)")
                print(f"[save] ... and {len(items) - 3} more record(s) for {_output_name(output_obj)}")

            Log.info(f"[batch_save] Completed {len(items)} save(s) for {_output_name(output_obj)} in {save_elapsed:.3f}s "
                     f"({len(items)/save_elapsed:.1f} records/s)")

        except Exception as e:
            Log.error(f"[batch_save] Failed to save batch for {_output_name(output_obj)}: {e}")
            # Log first few failed items
            for data, meta in items[:3]:
                meta_str = ", ".join(f"{k}={v}" for k, v in meta.items()
                                     if not k.startswith("__"))
                msg = f"[error] {meta_str}: failed to save {_output_name(output_obj)}: {e}"
                print(msg)
                Log.error(msg)

    # ===========================================================================
    # PHASE 3: Handle lineage items sequentially (cannot be batched)
    # ===========================================================================
    if lineage_items:
        Log.info(f"[batch_save] Saving {len(lineage_items)} lineage item(s) sequentially")
        from scihist.foreach import save_lineage_result

        for output_obj, output_value, lineage_metadata, row_idx in lineage_items:
            try:
                save_t0 = time.perf_counter()
                rid = save_lineage_result(output_obj, output_value, lineage_metadata, db)
                save_elapsed = time.perf_counter() - save_t0
                total_saved += 1

                meta_str = ", ".join(f"{k}={v}" for k, v in lineage_metadata.items()
                                     if not k.startswith("__"))
                data_desc = _describe_save_data(output_value)
                rid_short = rid[:12] if isinstance(rid, str) else str(rid)
                msg = f"[save] {meta_str}: {_output_name(output_obj)} -> record_id={rid_short} ({data_desc}) [lineage] in {save_elapsed:.3f}s"
                print(msg)
                Log.info(msg)
            except Exception as e:
                meta_str = ", ".join(f"{k}={v}" for k, v in lineage_metadata.items()
                                     if not k.startswith("__"))
                msg = f"[error] {meta_str}: failed to save {_output_name(output_obj)} [lineage]: {e}"
                print(msg)
                Log.error(msg)

    # ===========================================================================
    # Summary
    # ===========================================================================
    batch_total_elapsed = time.perf_counter() - batch_start_time
    Log.info(f"[batch_save] Total: saved {total_saved} record(s) in {batch_total_elapsed:.3f}s "
             f"({total_saved/batch_total_elapsed:.1f} records/s)")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_loadable(var_spec: Any) -> bool:
    """Check if an input spec is loadable (var type, Fixed, Merge, ColumnSelection, etc.)."""
    try:
        import pandas as pd
        if isinstance(var_spec, pd.DataFrame):
            return True
    except ImportError:
        pass
    return isinstance(var_spec, (type, Fixed, Variant, ColumnSelection, Merge, PathInput)) or hasattr(var_spec, 'load')


def _get_schema_keys(db: Any | None) -> set:
    """Return the set of dataset_schema_keys from db or the global database."""
    if db is not None and hasattr(db, 'dataset_schema_keys'):
        return set(db.dataset_schema_keys)
    try:
        from .database import get_database
        _db = get_database()
        if hasattr(_db, 'dataset_schema_keys'):
            return set(_db.dataset_schema_keys)
    except Exception:
        pass
    return set()


def _has_pathinput(inputs: dict) -> bool:
    """Check if any input is a PathInput, directly or wrapped in Fixed."""
    for v in inputs.values():
        if isinstance(v, PathInput):
            return True
        if isinstance(v, Fixed) and isinstance(v.var_type, PathInput):
            return True
    return False


def _find_pathinput(inputs: dict) -> PathInput | None:
    """Find the first PathInput in inputs, unwrapping Fixed if needed."""
    for v in inputs.values():
        if isinstance(v, PathInput):
            return v
        if isinstance(v, Fixed) and isinstance(v.var_type, PathInput):
            return v.var_type
    return None


def _describe_save_data(val) -> str:
    """Compact description of data being saved."""
    import pandas as pd
    import numpy as np
    if isinstance(val, pd.DataFrame):
        return f"DataFrame {val.shape[0]}x{val.shape[1]}"
    if isinstance(val, np.ndarray):
        return f"ndarray shape={val.shape}"
    if isinstance(val, dict):
        return f"dict, {len(val)} keys"
    if isinstance(val, (list, tuple)):
        return f"{type(val).__name__} len={len(val)}"
    return type(val).__name__


def _output_name(output_obj: Any) -> str:
    """Get display name for an output object."""
    if hasattr(output_obj, 'view_name'):
        return output_obj.view_name()
    if isinstance(output_obj, type):
        return output_obj.__name__
    return getattr(output_obj, '__name__', type(output_obj).__name__)


def _propagate_schema(db, distribute: bool) -> None:
    """Propagate dataset_schema_keys from the db into scifor.set_schema()."""
    # If a db was passed explicitly and has schema keys, use them.
    if db is not None and hasattr(db, 'dataset_schema_keys'):
        _scifor.set_schema(list(db.dataset_schema_keys))
        return

    # No explicit db: try the global database.
    _global_db = None
    try:
        from scidb.database import get_database
        _global_db = get_database()
    except Exception:
        pass

    if _global_db is not None and hasattr(_global_db, 'dataset_schema_keys'):
        _scifor.set_schema(list(_global_db.dataset_schema_keys))
    elif distribute:
        raise ValueError(
            "distribute=True requires access to dataset_schema_keys, "
            "but no database is available. Either pass db= to for_each or "
            "call configure_database() first."
        )


def _persist_expected_combos(
    db, fn_name: str, call_id: str, full_combos: list[dict]
) -> None:
    """Persist the full expected combo set for a for_each call into _for_each_expected.

    Called during for_each BEFORE skip_computed filtering, so we capture ALL
    combos (including ones that will be skipped).  This lets check_node_state
    know how many combos are expected for PathInput-only functions where no
    DB-variable inputs exist to infer the expected set.

    Rows are scoped by (function_name, call_id) so that multiple for_each()
    call sites that reuse the same function don't clobber each other.  The
    DELETE only removes rows for *this* call site; rows for other call sites
    of the same function are left intact.
    """
    if not full_combos:
        return

    try:
        if db is None:
            from .database import get_database
            db = get_database()
    except Exception:
        Log.debug("_persist_expected_combos: no database available, skipping")
        return

    try:
        sk_set = set(db.dataset_schema_keys)
        rows_to_insert = []

        for combo in full_combos:
            # Extract only schema keys from the combo (ignore __rid_*, etc.)
            schema_keys = {k: v for k, v in combo.items() if k in sk_set}
            if not schema_keys:
                continue

            level = db._infer_schema_level(schema_keys)
            if level is None:
                continue

            schema_id = db._duck._get_or_create_schema_id(level, schema_keys)
            rows_to_insert.append((fn_name, call_id, schema_id, "{}"))

        if not rows_to_insert:
            return

        # Deduplicate (multiple combos can map to the same schema_id)
        rows_to_insert = list(set(rows_to_insert))

        # Replace old entries for THIS call site only.  Other call sites of
        # the same function (different call_id) are untouched.
        deleted = db._duck._fetchall(
            "SELECT COUNT(*) FROM _for_each_expected "
            "WHERE function_name = ? AND call_id = ?",
            [fn_name, call_id],
        )
        prev_count = deleted[0][0] if deleted else 0
        db._duck._execute(
            "DELETE FROM _for_each_expected WHERE function_name = ? AND call_id = ?",
            [fn_name, call_id],
        )
        for fn, cid, sid, bp in rows_to_insert:
            db._duck._execute(
                "INSERT INTO _for_each_expected "
                "(function_name, call_id, schema_id, branch_params) "
                "VALUES (?, ?, ?, ?)",
                [fn, cid, sid, bp],
            )

        Log.debug(
            f"_persist_expected_combos({fn_name}, call_id={call_id}): "
            f"replaced {prev_count} -> wrote {len(rows_to_insert)} expected combos"
        )
    except Exception as exc:
        Log.debug(
            f"_persist_expected_combos({fn_name}, call_id={call_id}): failed — {exc}"
        )
