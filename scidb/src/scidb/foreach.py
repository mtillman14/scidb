"""DB-backed for_each wrapper — loads inputs, delegates loop to scifor, saves outputs."""

import hashlib
import json
import os
import re
import time
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path as _Path
from typing import TYPE_CHECKING, Any

from scifor.pathinput import PathInput

if TYPE_CHECKING:
    import pandas as pd

import scifor as _scifor
from scifor import for_each as _scifor_for_each

from .across_variants import AcrossVariants
from .colname import ColName
from .column_selection import ColumnSelection
from .each_of import EachOf
from .filters import Filter
from .fixed import Fixed
from .foreach_config import ForEachConfig
from .log import Log
from .merge import Merge
from .pipeline import Pipeline as _Pipeline
from .pipeline import Step, active_pipeline
from .provenance_save import GraphRecord as _GraphRecord
from .variant import Variant

# Sentinel: distinguishes "pipeline= omitted" (use the ambient active
# pipeline, if any) from an explicit pipeline=None (force eager execution).
_PIPELINE_UNSET = object()

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

    Also carries the **variable-level portion** of the merge-level where= filter
    (``variable_filter``). ``_load_with_where`` uses it for *semantic* variant
    matching — selecting the single computed variant whose consumed input
    schema_id set the filter describes — exactly as a direct ``.load(where=...)``
    would (§10 "where= redesign"). Constituents with no producing invocation
    (raw/direct-saved data) fall back to their own schema location, restricted to
    the pre-resolved ``schema_ids``.

    ``_schema_ids`` is the **row restriction**: it already encodes the full where=
    filter (variable-level AND any SchemaKey portion), applied on top of the
    variant match via the ``_restrict_to_resolved_ids`` marker so a constituent
    that matches a variant by provenance is still narrowed to the selected rows.
    """

    # Tells DatabaseManager._load_with_where to intersect the variant-matched
    # records with resolve() (the pre-resolved row set) — see class docstring.
    _restrict_to_resolved_ids = True

    def __init__(self, schema_ids: set, variable_filter: "Filter | None" = None):
        self._schema_ids = schema_ids
        self._variable_filter = variable_filter

    def to_key(self) -> str:
        vf = self._variable_filter
        return vf.to_key() if vf is not None else ""

    def resolve(
        self, db, target_variable_class, target_table_name, validate_coverage=True
    ) -> set:
        return self._schema_ids


def _merge_constituent_variable_filter(where: Any) -> "Filter | None":
    """The variable-level portion of a merge-level where= filter (or None).

    Splits off any SchemaKey portion (which selects rows, not variants) and keeps
    the variable-level portion only — the part that semantically identifies which
    computed variant to return — mirroring what ``_load_with_where`` does for a
    direct ``.load(where=...)`` so Merge constituents and direct loads select the
    same variant.
    """
    from .filters import split_schema_key_filters

    if isinstance(where, Filter):
        sk_filter, var_filter = split_schema_key_filters(where)
        if sk_filter is not None:
            return var_filter  # None when where is purely SchemaKey
    return where if isinstance(where, Filter) else None


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
    # PathOutput branch_param placeholder keys injected into combos (stripped
    # from the result table before save/return; see _for_each_save_resolved).
    path_extra_keys: Any = None  # set | None
    # Combos removed by the pre-combo hook (skip_computed): already up to
    # date, so they never reach scifor. Folded into the run-summary log line.
    skip_computed_count: int = 0


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
    track_lineage: bool = True,
    skip_computed: bool = False,
    schema_filter: "dict[str, list] | None" = None,
    schema_level: "list[str] | None" = None,
    share_limits: "dict[str, list[str]] | None" = None,
    finalized: bool = False,
    pipeline: Any = _PIPELINE_UNSET,
    _inject_combo_metadata: bool = False,
    _pre_combo_hook: "Callable[[dict], bool] | None" = None,
    _progress_fn: "Callable[[dict], None] | None" = None,
    _cancel_check: "Callable[[], bool] | None" = None,
    _lineage_fixed_rids: "dict | None" = None,
    **metadata_iterables: list[Any],
) -> "pd.DataFrame | Step | None":
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
        track_lineage: If True (default), record provenance (function hash, input
                    record_ids, constants) into the bipartite graph from the
                    inputs ``fn`` consumes. Pass False to run ``fn`` untracked.
        skip_computed: If True, skip combos whose outputs already exist and whose
                    full upstream provenance graph is unchanged (function hash,
                    input record_ids, constant hashes). Default False. Requires a
                    database and ``track_lineage``.
        schema_filter: Optional ``{schema_key: [values]}`` to build the iteration
                    set from the database instead of **metadata_iterables. Cannot
                    be combined with explicit **metadata_iterables.
        schema_level: Optional list of schema keys to iterate when using
                    schema_filter. Defaults to all schema keys.
        finalized: Endpoint (``plot_``/``stat_``) functions only. Default False
                    = DRAFT mode: nothing is written to the database — a
                    ``plot_`` figure is still rendered to its PathOutput path,
                    a ``stat_`` result is pretty-printed (and any PathOutput is
                    resolved to None so e.g. csv-stats skips its PDF report).
                    Pass True to RECORD: outputs saved with full lineage,
                    skip_computed honored; a ``stat_`` PathOutput is resolved
                    normally and its path embedded as ``report_path`` in the
                    stored JSON. Recording requires a re-run of the endpoint
                    (drafts leave no record to promote). Warned and ignored
                    for non-endpoint functions.
        _inject_combo_metadata: If True, inject current-combo metadata keys
                    as extra kwargs to fn (used by scihist for generates_file).
        pipeline: Deferred-registration control. Omitted (default): if a
                    Pipeline is active (``db.pipeline(name)``), REGISTER this
                    call as a deferred step and return a Step handle — nothing
                    executes until ``pipeline.run_all()/run_until()``; with no
                    active pipeline, execute eagerly as always. Pass ``None``
                    to force an eager call even while a pipeline is active,
                    or a Pipeline instance to register into a non-ambient
                    pipeline. Consequence: ``pipeline`` is a reserved name and
                    cannot be used as a schema key in **metadata_iterables.
        _pre_combo_hook: Internal use only. Called with each fully-expanded
                    combo dict before inputs are loaded. If it returns True
                    the combo is skipped entirely (no load, no call, no save).
                    Used by scihist.for_each to implement skip_computed.
        **metadata_iterables: Iterables of metadata values to combine.

    Returns:
        A pandas DataFrame of results, None when dry_run=True, or a Step
        handle when the call was registered into a Pipeline instead of run.
    """
    # --- Deferred pipeline registration. Must run before ANY other work —
    #     a registered call must have zero side effects, and the spec must
    #     capture the arguments exactly as passed (pristine, un-normalized)
    #     so replay through run_*() is byte-identical to an eager call. ---
    _target_pipeline = None
    if isinstance(pipeline, _Pipeline):
        _target_pipeline = pipeline
    elif pipeline is _PIPELINE_UNSET:
        _target_pipeline = active_pipeline()
    elif pipeline is not None:
        raise TypeError(
            f"pipeline= must be a Pipeline instance, None, or omitted; "
            f"got {type(pipeline).__name__}"
        )
    if _target_pipeline is not None:
        return _target_pipeline.register_call(
            fn=fn,
            inputs=inputs,
            outputs=outputs,
            metadata_iterables=dict(metadata_iterables),
            options={
                "dry_run": dry_run,
                "save": save,
                "as_table": as_table,
                "db": db,
                "distribute": distribute,
                "where": where,
                "introspect": introspect,
                "track_lineage": track_lineage,
                "skip_computed": skip_computed,
                "schema_filter": schema_filter,
                "schema_level": schema_level,
                "share_limits": share_limits,
                "finalized": finalized,
                "_inject_combo_metadata": _inject_combo_metadata,
                "_pre_combo_hook": _pre_combo_hook,
                "_progress_fn": _progress_fn,
                "_cancel_check": _cancel_check,
                "_lineage_fixed_rids": _lineage_fixed_rids,
            },
        )

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

    # --- Step 0: Resolve active database + schema_filter/schema_level (folded
    #     from scihist.for_each). Builds metadata_iterables from the DB when the
    #     caller used schema_filter/schema_level instead of explicit iterables. ---
    active_db = db
    if active_db is None and (
        skip_computed or schema_filter is not None or schema_level is not None
    ):
        try:
            from .database import get_database

            active_db = get_database()
        except Exception:
            active_db = None

    if schema_filter is not None or schema_level is not None:
        if metadata_iterables:
            raise ValueError(
                "Cannot use both schema_filter/schema_level and **metadata_iterables. "
                "Use schema_filter/schema_level for automatic iteration, or "
                "**metadata_iterables for manual control."
            )
        if active_db is None:
            raise ValueError(
                "schema_filter/schema_level require a database connection, but no db "
                "was provided and no global database is configured."
            )
        iterate_keys = (
            schema_level if schema_level is not None else active_db.dataset_schema_keys
        )
        metadata_iterables = {}
        for key in iterate_keys:
            if schema_filter and key in schema_filter:
                metadata_iterables[key] = schema_filter[key]
            else:
                metadata_iterables[key] = active_db.distinct_schema_values(key)
        # Resolved into metadata_iterables; don't re-resolve in EachOf recursion.
        schema_filter = None
        schema_level = None
        Log.debug(
            f"built metadata_iterables from schema params: {list(metadata_iterables.keys())}"
        )

    # --- Step 1: EachOf expansion: must be first, before any other logic ---
    each_of_axes = []
    for param, val in inputs.items():
        if isinstance(val, EachOf):
            each_of_axes.append(("input", param, val.alternatives))
    if isinstance(where, EachOf):
        each_of_axes.append(("where", None, where.alternatives))

    if each_of_axes:
        Log.debug(
            f"EachOf expansion detected - {len(each_of_axes)} axes, will make recursive calls"
        )
        for kind, param, alts in each_of_axes:
            if kind == "input":
                Log.debug(
                    f"  EachOf axis: input '{param}' with {len(alts)} alternatives"
                )
            else:
                Log.debug(f"  EachOf axis: where with {len(alts)} alternatives")
        from itertools import product as _eachof_product

        import pandas as pd

        results = []
        for combo in _eachof_product(*(axis[2] for axis in each_of_axes)):
            concrete_inputs = dict(inputs)
            concrete_where = where
            for (kind, param, _alts), value in zip(each_of_axes, combo, strict=False):
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
                track_lineage=track_lineage,
                skip_computed=skip_computed,
                share_limits=share_limits,
                finalized=finalized,
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
        Log.debug(f"EachOf expansion complete - concatenated {len(results)} result(s)")
        return result_df
    else:
        Log.debug("no EachOf expansion needed")

    # --- Step 1.55/1.56: Endpoint leaf detection (plot_/stat_ prefixes) ---
    # Policy (detection, PathOutput requirement, stat as_table default, draft
    # save suppression, warnings) is shared with the MATLAB bridge via
    # _endpoint_policy — one source of truth for both paths. Only the fn
    # WRAPPING is language-specific: Python wraps here; MATLAB wraps its own
    # fn in +scidb/for_each.m. See docs/claude/endpoints-viz-and-stats-design.md.
    _orig_fn_name = getattr(fn, "__name__", "")
    _endpoint_kind, _path_param, as_table, _save_suppressed = _endpoint_policy(
        _orig_fn_name, inputs, finalized, as_table
    )
    if _endpoint_kind == "plot":
        fn = _make_plot_wrapper(fn, _path_param)
        _inject_combo_metadata = True
    elif _endpoint_kind == "stat":
        fn = _make_stat_wrapper(fn, _path_param, finalized)
        _inject_combo_metadata = True
    if _save_suppressed and save:
        save = False

    # --- Step 1.6: generates_file detection + skip_computed ---
    # No function wrapping: plain functions flow straight through to scifor, which
    # spreads tuple returns natively. Provenance is built from input bindings at
    # save time (the bipartite graph); Step 16 reconstructs BaseVariable inputs.
    # ``generates_file`` is read from the @scistack marker and drives combo-
    # metadata injection + a graph-native lineage-only save (see _save_results).
    from .pipeline import GENERATES_FILE_ATTR

    _is_generates_file = bool(getattr(fn, GENERATES_FILE_ATTR, None)) or bool(
        getattr(fn, "generates_file", False)
    )
    if _is_generates_file:
        _inject_combo_metadata = True
        Log.debug("generates_file=True → combo metadata injection + lineage-only save")

    # Build the skip_computed pre-combo hook on the plain function (its
    # function_hash + input bindings are the graph identity; no wrapper needed).
    if skip_computed and not dry_run and outputs and active_db is not None:
        _pre_combo_hook = _build_skip_hook(
            fn, outputs, active_db, inputs, as_table=as_table, distribute=distribute
        )
        Log.debug(f"built skip_computed hook for {getattr(fn, '__name__', repr(fn))}")

    # --- Step 1.5: Resolve for_columns (iterate-mode ColumnSelection) inputs ---
    # Expand empty columns ([] / all) -> all data columns and validate the shared column
    # axis BEFORE version keys are built (Step 8) and before dry-run display,
    # so caching reflects the concrete column set.
    inputs = _resolve_for_columns(inputs, db)
    _has_for_columns = any(
        _iterate_column_selection(s) is not None for s in inputs.values()
    )

    # No output wrapping: scifor spreads tuple returns across outputs natively and
    # flatten/distribute consume the raw return directly. (The former LineageFcn
    # tuple-unpacking / raw-value wrappers existed only to collapse
    # LineageFcnResults, which no longer exist.)

    fn_name = getattr(fn, "__name__", repr(fn))

    # --- Pre-loop preparation. Returns None on dry_run shortcut. ---
    with Log.step(f"for_each_prepare({fn_name})"):
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

    # --- Step 16: Wrap fn to resolve PerComboLoader/PerComboLoaderMerge inputs
    #     per-combo, normalize variable inputs to raw data, and/or inject combo
    #     metadata (for generates_file functions). ---
    _per_combo = {
        k: v
        for k, v in state.loaded_inputs.items()
        if isinstance(v, (PerComboLoader, PerComboLoaderMerge))
    }
    _has_variable_inputs = any(_is_loadable(v) for v in inputs.values())
    if _per_combo or _inject_combo_metadata or _has_variable_inputs:
        wrap_reasons = []
        if _per_combo:
            wrap_reasons.append(f"{len(_per_combo)} PerComboLoader input(s)")
        if _inject_combo_metadata:
            wrap_reasons.append("generates_file metadata injection")
        if _has_variable_inputs:
            wrap_reasons.append("variable input normalization")
        Log.debug(f"wrapping function for {', '.join(wrap_reasons)}")
        _ordered_combos = state.full_combos
        _call_idx = [0]
        _orig_fn = fn
        _loaded_inputs_ref = state.loaded_inputs

        # Declared schema-key types drive PathInput spelling enforcement in
        # per-combo loads (string keys: exact only; undeclared keys that
        # need a spelling bridge: SchemaKeyTypeError).
        _kt_db = db
        if _kt_db is None:
            try:
                from scidb.database import get_database

                _kt_db = get_database()
            except Exception:
                _kt_db = None
        _schema_key_types = getattr(_kt_db, "dataset_schema_key_types", {}) or {}
        _schema_keys_for_types = list(getattr(_kt_db, "dataset_schema_keys", []) or [])

        # Get function parameters to check which metadata keys it accepts.
        _fn_params = None
        if _inject_combo_metadata:
            if hasattr(_orig_fn, "__scidb_params__"):
                _fn_params = _orig_fn.__scidb_params__
            else:
                import inspect

                try:
                    sig = inspect.signature(_orig_fn)
                    _fn_params = set(sig.parameters.keys())
                except (ValueError, TypeError):
                    # Couldn't get signature, don't inject metadata
                    _fn_params = set()

        _path_extra = state.path_extra_keys or set()

        def fn(**kwargs):  # noqa: F811 — intentional rebind
            idx = _call_idx[0]
            _call_idx[0] = idx + 1
            current_combo = _ordered_combos[idx] if idx < len(_ordered_combos) else {}
            # Exclude injected PathOutput placeholder keys: as load kwargs they
            # would act as branch_params FILTERS (with sanitized-string values)
            # and silently empty a PerComboLoader load.
            load_kw = {
                k: v
                for k, v in current_combo.items()
                if not k.startswith("__") and k not in _path_extra
            }
            resolved = {}
            for k, v in kwargs.items():
                if isinstance(v, PerComboLoader):
                    resolved[k] = _resolve_per_combo_loader(
                        v,
                        load_kw,
                        key_types=_schema_key_types,
                        schema_keys=_schema_keys_for_types,
                    )
                elif isinstance(v, PerComboLoaderMerge):
                    resolved[k] = _resolve_per_combo_merge(v, load_kw)
                else:
                    resolved[k] = v

            # Normalize variable inputs to their raw data (DataFrame → array,
            # dict structure restored) — the form the function expects.
            if _has_variable_inputs:
                resolved = _normalize_variable_inputs(
                    resolved, current_combo, inputs, _loaded_inputs_ref
                )

            if _inject_combo_metadata and _fn_params is not None:
                # Only inject metadata keys that the function signature accepts
                for k, v in load_kw.items():
                    if k not in resolved and k in _fn_params:
                        resolved[k] = v
            return _orig_fn(**resolved)
    else:
        Log.debug("no function wrapping needed")

    # Wrap _progress_fn to track final completed/failed counts for logging.
    # scifor's final "summary" event is authoritative (it also carries the
    # aggregated failure reasons); the per-combo events keep the counts live
    # for GUI consumers.
    _run_summary = {"total": 0, "completed": 0, "skipped": 0, "cancelled": False}

    def _tracking_progress_fn(info: dict):
        _run_summary["total"] = info.get("total", _run_summary["total"])
        _run_summary["completed"] = info.get("completed", _run_summary["completed"])
        _run_summary["skipped"] = info.get("skipped", _run_summary["skipped"])
        if info.get("event") == "summary":
            _run_summary["cancelled"] = bool(info.get("cancelled"))
        if _progress_fn is not None:
            _progress_fn(info)

    # Delegate the core loop to scifor
    with Log.step(f"delegate_to_scifor({fn_name}, {len(state.full_combos)} combos)"):
        result_tbl = _scifor_for_each(
            fn,
            state.loaded_inputs,
            dry_run=False,
            as_table=as_table,
            distribute=distribute,
            output_names=state.output_names,
            share_limits=share_limits,
            _all_combos=state.full_combos,
            _progress_fn=_tracking_progress_fn,
            _cancel_check=_cancel_check,
            **state.extended_metadata_iterables,
        )

    # Authoritative run summary: scifor's counts plus the combos skip_computed
    # removed before the loop (already up to date). This is the one line that
    # documents what ran, what failed, and what was skipped for the whole call.
    _summary_parts = [
        f"completed={_run_summary['completed']}",
        f"failed={_run_summary['skipped']}",
    ]
    if state.skip_computed_count:
        _summary_parts.append(
            f"skipped={state.skip_computed_count} (skip_computed, up to date)"
        )
    _summary_parts.append(f"total={_run_summary['total'] + state.skip_computed_count}")
    if _run_summary["cancelled"]:
        _summary_parts.append("cancelled")
    Log.info(f"for_each({fn_name}) run summary: {', '.join(_summary_parts)}")

    # --- Schema restore + save (+ endpoint artifact stamping) ---
    with Log.step(f"for_each_save({fn_name})"):
        result_tbl = _for_each_save_resolved(
            state=state,
            result_tbl=result_tbl,
            inputs=inputs,
            outputs=outputs,
            save=save,
            db=db,
            lineage_fixed_rids=_lineage_fixed_rids,
            generates_file=_is_generates_file,
            endpoint_kind=_endpoint_kind,
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
    # Identify __rid_* / __vsig_* columns and remove them from their current
    # positions (both are internal discriminators: per-record in full
    # iteration, per-variant-group signature in aggregation auto-split).
    rid_cols = [c for c in result_tbl.columns if c.startswith("__rid_")]
    vsig_cols = [c for c in result_tbl.columns if c.startswith("__vsig_")]
    df = result_tbl.drop(columns=rid_cols + vsig_cols)

    # Append per-input record_id + branch_params pairs in input order.
    for rid_col in rid_cols:
        param_name = rid_col[len("__rid_") :]
        record_ids = result_tbl[rid_col]
        df[f"_record_id_{param_name}"] = record_ids.values
        df[f"_branch_params_{param_name}"] = [
            state.rid_to_bp.get(rid, {}) for rid in record_ids
        ]

    # Aggregation auto-split rows have no single record_id per input; surface
    # the variant group's branch_params (parsed from the signature) instead.
    for vsig_col in vsig_cols:
        param_name = vsig_col[len("__vsig_") :]
        df[f"_branch_params_{param_name}"] = [
            json.loads(s) if isinstance(s, str) and s else {}
            for s in result_tbl[vsig_col]
        ]

    # Append call-level columns (same value on every row).
    df["_call_id"] = state.call_id
    df["_config_keys"] = json.dumps(state.config_keys)
    df["_where"] = repr(where) if where is not None else None

    return df


# ---------------------------------------------------------------------------
# PathOutput variant placeholders (per-group artifact paths; no clobbering)
# ---------------------------------------------------------------------------
# PathOutput resolution is a literal str.replace of "{key}" per combo-metadata
# key (scifor/pathoutput.py::resolve — NOT str.format, so dotted names are
# legal). Branch params therefore need no new syntax: scidb injects per-group
# values into the expanded combos under the exact placeholder text, scifor's
# generic resolver substitutes them, and scidb strips the injected keys before
# save/introspect so they never pollute records or branch_params.

_PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")
_VARIANT_TOKEN = "variant"


def _pathoutput_placeholders(inputs: dict, exclude_keys: set) -> "tuple[set, list]":
    """Placeholder names used by PathOutput inputs that are NOT combo-supplied
    (schema keys / metadata iterables / ColName), plus the PathOutput specs.
    """
    names: set = set()
    path_outputs: list = []
    for v in inputs.values():
        if isinstance(v, _scifor.PathOutput):
            path_outputs.append(v)
            names |= set(_PLACEHOLDER_RE.findall(str(v.template)))
    names.discard("ColName")
    return {n for n in names if n not in exclude_keys}, path_outputs


def _sanitize_path_value(value: Any) -> str:
    """Path-safe rendering of a branch_param value for filename substitution.

    Integral floats render WITHOUT the trailing ``.0``: MATLAB constants
    cross the bridge as doubles (``low_hz=20`` arrives as ``20.0``), and the
    artifact filename must not depend on which language ran the pipeline
    (``r_20.pdf`` from both, matching MATLAB's ``%g`` and Python-int runs).
    """
    if isinstance(value, float) and value.is_integer():
        s = str(int(value))
    else:
        s = str(value)
    for ch in (os.sep, "/", "\x00"):
        s = s.replace(ch, "-")
    return s


def _merge_group_bp(bp_dicts: "list[dict]") -> "tuple[dict, set]":
    """Merge per-record branch_params dicts; track keys with conflicting values."""
    merged: dict = {}
    conflicted: set = set()
    for bp in bp_dicts:
        for k, v in (bp or {}).items():
            if k in merged and merged[k] != v:
                conflicted.add(k)
            merged[k] = v
    return merged, conflicted


def _resolve_bp_placeholder(
    name: str, merged_bp: dict, conflicted: set, signature_text: str
) -> "str | None":
    """Resolve one PathOutput placeholder from a variant group's branch_params.

    Bare names suffix-match namespaced keys (the Variant()/branch_param()
    contract); ambiguity is a hard error naming the candidates. ``{variant}``
    is an 8-char digest of the group's canonical signature — the shorthand
    for many-param sweeps. Returns None for a key absent from the group
    (caller warns; the literal ``{name}`` stays in the path).
    """
    if name == _VARIANT_TOKEN:
        return hashlib.sha256(signature_text.encode("utf-8")).hexdigest()[:8]
    if name in merged_bp:
        matches = [name]
    else:
        matches = [k for k in merged_bp if str(k).endswith("." + name)]
    if len(matches) > 1:
        raise ValueError(
            f"PathOutput placeholder '{{{name}}}' is ambiguous: it suffix-matches "
            f"{sorted(matches)}. Use the namespaced form, e.g. "
            f"'{{{sorted(matches)[0]}}}'."
        )
    if not matches:
        return None
    key = matches[0]
    if key in conflicted:
        raise ValueError(
            f"PathOutput placeholder '{{{name}}}' matches branch_param '{key}', "
            f"which has CONFLICTING values across this call's inputs — one path "
            f"cannot represent both. Pin the inputs (Variant) or use '{{variant}}'."
        )
    return _sanitize_path_value(merged_bp[key])


def _inject_path_placeholders(
    fc: dict,
    names: set,
    merged_bp: dict,
    conflicted: set,
    signature_text: str,
    missing_out: set,
) -> None:
    """Inject resolved placeholder values into an expanded combo dict."""
    for name in names:
        val = _resolve_bp_placeholder(name, merged_bp, conflicted, signature_text)
        if val is None:
            missing_out.add(name)
        elif name not in fc:
            fc[name] = val


def _guard_pathoutput_collisions(
    path_outputs: list,
    full_combos: list,
    colname_columns: "list | None",
    rid_to_bp: dict,
    placeholder_names: set,
) -> None:
    """Hard-error when one resolved artifact path is shared by combos that
    agree on their SCHEMA/iterable identity but differ in VARIANT identity
    (``__vsig_*`` / ``__rid_*``) — silent file loss with a one-line fix to
    name. Collisions from omitted schema keys are deliberately not errors
    (pre-existing, possibly intentional overwrites); in full iteration, combos
    at different schema locations also differ in ``__rid_*``, so variant
    difference alone must NOT trigger the guard.

    ``colname_columns``: the concrete for_columns axis (resolved before
    prepare), so ``{ColName}`` templates are covered by previewing the
    combos × columns cross product. Injected placeholder keys are excluded
    from the base identity (they derive from variant identity).
    """

    def _base_identity(fc: dict) -> tuple:
        return tuple(
            sorted(
                (k, str(v))
                for k, v in fc.items()
                if not str(k).startswith("__") and k not in placeholder_names
            )
        )

    def _variant_keys(fc: dict) -> dict:
        return {k: v for k, v in fc.items() if str(k).startswith(("__vsig_", "__rid_"))}

    def _group_bp(fc: dict) -> dict:
        bp: dict = {}
        for k, v in fc.items():
            if str(k).startswith("__vsig_") and isinstance(v, str):
                try:
                    bp.update(json.loads(v))
                except (ValueError, TypeError):
                    pass
            elif str(k).startswith("__rid_"):
                bp.update(rid_to_bp.get(v, {}))
        return bp

    for po in path_outputs:
        columns = (
            colname_columns if (po.has_column_token and colname_columns) else [None]
        )
        seen: dict = {}
        for fc in full_combos:
            for col in columns:
                resolved = str(po.resolve(fc, col))
                key = (resolved, col)
                prev = seen.get(key)
                if prev is None:
                    seen[key] = fc
                    continue
                if _base_identity(prev) != _base_identity(fc):
                    continue  # schema-driven collision: user's business
                if _variant_keys(prev) == _variant_keys(fc):
                    continue  # identical combo re-reference
                bp_a, bp_b = _group_bp(prev), _group_bp(fc)
                diff_keys = sorted(
                    k for k in set(bp_a) | set(bp_b) if bp_a.get(k) != bp_b.get(k)
                )
                suggestion = (
                    "{" + str(diff_keys[0]).rsplit(".", 1)[-1] + "}"
                    if diff_keys
                    else "{variant}"
                )
                raise ValueError(
                    f"PathOutput {str(po.template)!r} resolves to the SAME path "
                    f"{resolved!r} for multiple variant groups"
                    + (f" (differing branch_params: {diff_keys})" if diff_keys else "")
                    + f" — each group's file would overwrite the previous one. "
                    f"Add a distinguishing placeholder, e.g. '...{suggestion}...' "
                    f"or '...{{variant}}...'."
                )


# ---------------------------------------------------------------------------
# skip_computed pre-combo hook (folded from scihist.for_each)
# ---------------------------------------------------------------------------


def _find_skip_gate_record(
    db,
    type_name,
    schema_combo,
    fn_name,
    target_const_hashes,
    expected_input_rids=None,
    fixed_rids=frozenset(),
):
    """Latest output record of ``type_name`` at ``schema_combo`` produced by an
    invocation of ``fn_name`` whose constants match ``target_const_hashes``
    (``{param: canonical_hash(value)}``), or None.

    Graph-precise variant lookup for the skip gate: filters by producing function
    (so a re-saved raw input at the same location is not mistaken for the output)
    and by constant hashes (so distinct constant variants are disambiguated).

    ``expected_input_rids`` (aggregation mode): the exact set of upstream
    record_ids this combo's variant group consumes. Aggregation combos carry no
    ``__rid_*`` keys for the staleness comparison, so the GATE must bind the
    group identity instead — a candidate only matches when its invocation's
    consumed variable-input rid set equals the expected set (after removing
    ``fixed_rids`` and the candidate itself, mirroring the full-iteration
    self-referential guard). Without this, a new variant group (or an
    aggregation whose underlying record set grew, e.g. a new session) would
    cross-skip against another group's / the stale record.
    """
    from . import provenance_query
    from .database import _schema_str

    schema_keys = set(db.dataset_schema_keys)
    conds = [
        "inv.function_name = ?",
        "r.type = ?",
        "COALESCE(r.excluded, FALSE) = FALSE",
    ]
    params: list = [fn_name, type_name]
    for k, v in schema_combo.items():
        if k in schema_keys:
            conds.append(f's."{k}" = ?')
            params.append(_schema_str(v))
    # LEFT JOIN _schema: a grand-aggregation output (zero iterated schema keys)
    # is saved at the ROOT level with a NULL schema_id — an inner join would
    # silently drop it from the gate, forcing eternal recompute. With no
    # schema_combo conds the record passes; with conds, NULL schema columns
    # fail the equality naturally.
    rows = db._duck._fetchall(
        "SELECT io.output_record_id FROM _invocation inv "
        "JOIN _invocation_output io ON io.invocation_id = inv.invocation_id "
        "JOIN _record r ON r.record_id = io.output_record_id "
        "JOIN _record_save rm ON rm.record_id = io.output_record_id "
        "LEFT JOIN _schema s ON r.schema_id = s.schema_id "
        f"WHERE {' AND '.join(conds)} ORDER BY rm.timestamp DESC",
        params,
    )
    _rejections: list = []
    for (rid,) in rows:
        sig = provenance_query.stored_invocation_signature(db._duck, rid)
        if sig is None:
            _rejections.append(f"{rid[:12]}: no producing invocation")
            continue
        if sig.get("const_hashes", {}) != target_const_hashes:
            _rejections.append(
                f"{rid[:12]}: const_hashes mismatch "
                f"(stored={sig.get('const_hashes', {})}, target={target_const_hashes})"
            )
            continue
        if expected_input_rids is not None:
            stored_rids = {
                str(in_rid)
                for (in_rid, _sel) in sig.get("var_inputs", {}).values()
                if in_rid is not None
            }
            stored_rids -= {str(r) for r in fixed_rids}
            stored_rids.discard(str(rid))
            if stored_rids != expected_input_rids:
                _extra = sorted(stored_rids - expected_input_rids)[:3]
                _missing = sorted(expected_input_rids - stored_rids)[:3]
                _rejections.append(
                    f"{rid[:12]}: rid-set mismatch (stored {len(stored_rids)} vs "
                    f"expected {len(expected_input_rids)}; stored-only={_extra}, "
                    f"expected-only={_missing})"
                )
                continue
        return rid
    # Gate diagnostics (NOTE 2): a silent None here is indistinguishable from a
    # legitimate first run, so record WHY each candidate was rejected.
    if _rejections:
        Log.debug(
            f"[skip-gate] {type_name} at {schema_combo or '(root)'} for "
            f"{fn_name!r}: {len(rows)} candidate(s), none matched — "
            + " | ".join(_rejections[:5])
        )
    elif expected_input_rids is not None:
        Log.debug(
            f"[skip-gate] {type_name} at {schema_combo or '(root)'} for "
            f"{fn_name!r}: NO candidate records found (query returned 0 rows)"
        )
    return None


def _build_skip_hook(
    fn,
    outputs: list,
    db,
    inputs: dict,
    as_table=None,
    distribute: bool = False,
    fn_hash: "str | None" = None,
    agg_binding_ref: "dict | None" = None,
) -> "Callable[[dict], bool]":
    """Return a pre-combo hook that returns True when a combo can be skipped.

    Rewritten over the bipartite provenance graph (the §11 "port" approach: read
    function_hash + input edges + constant records from the graph, not _lineage).
    The decision splits into:

    1. *Missing vs. variant gate* — ``find_record_id`` on (schema + constants +
       ``__fn`` name) decides whether any output for this variant exists yet.
       No record → the combo has never been run for this variant → compute
       silently (no ``[recompute]`` line), matching the legacy contract.
    2. *Staleness via edge comparison* — load the producing invocation's
       signature for that output (``stored_invocation_signature``) and compare,
       binding by binding, against the combo's *current* inputs: function hash,
       each variable input record_id (+ ColumnSelection selector), and constant
       content hashes. Any mismatch → ``[recompute]``; otherwise ``[skip]``.

    The self-referential guard (``input rid == output rid`` => stable) is what a
    pure membership test cannot express — it stops input==output pipelines
    (variant expansion feeding an output back as input) from recomputing forever.

    Binding parity with the save path holds by construction: the same
    ``full_combo`` whose ``__rid_*`` values feed this hook also feed the save
    path's graph edges, ``compute_function_hash(fn)`` equals the save-side
    ``__fn_hash``, and both sides derive selectors from ``compute_input_selectors``.

    ``fn`` is a plain pipeline function; its identity comes from
    ``compute_function_hash(fn)`` (the same hash for_each writes to the graph).

    ``fn_hash`` overrides that computation. The MATLAB-driven bridge passes a
    no-op sentinel for ``fn`` whose hash would never match what the MATLAB save
    path stored (the MATLAB-computed source hash, written as ``__fn_hash`` →
    graph ``function_hash``). Passing the same MATLAB hash here keeps the
    function-hash comparison meaningful instead of forcing eternal recompute.

    ``agg_binding_ref`` is a MUTABLE holder ``{"combo_to_rids", "keys",
    "fixed_rids"}``. The hook is built BEFORE ``_for_each_prepare`` but fires
    inside prepare's Step 14 combo filter — after Step 12 has computed the
    aggregation variant-group → consumed-rid mapping — so prepare fills the
    holder right before Step 14 via the ``_agg_binding_ref`` attribute exposed
    on the returned hook (one dict is auto-created when the caller passes
    none, which covers both the Python and MATLAB-bridge call sites). In
    aggregation mode the combo carries no ``__rid_*`` keys, so the gate binds
    the variant group by its exact consumed-rid set (see
    ``_find_skip_gate_record``) instead of per-param rid comparison.
    """
    from scilineage.hashing import compute_function_hash

    from scicanonicalhash import canonical_hash as _chash

    from . import provenance_query
    from .provenance_save import compute_input_selectors

    if agg_binding_ref is None:
        agg_binding_ref = {
            "combo_to_rids": None,
            "keys": None,
            "fixed_rids": frozenset(),
        }

    schema_keys: set = set(db.dataset_schema_keys)

    # Pre-compute scalar constant inputs (mirrors ForEachConfig._get_direct_constants
    # so skip-side and save-side constant bindings agree).
    constant_values: dict = {}
    try:
        from scifor import PathInput as _PathInput
    except ImportError:
        _PathInput = None
    try:
        from scifor import PathOutput as _PathOutput
    except ImportError:
        _PathOutput = None
    for name, value in inputs.items():
        if _is_loadable(value):
            continue
        if _PathInput is not None and isinstance(value, _PathInput):
            continue
        if _PathOutput is not None and isinstance(value, _PathOutput):
            continue
        if isinstance(value, ColName):
            continue
        constant_values[name] = value

    # Identity hash: use the caller-supplied override (MATLAB path passes its
    # source hash, since the sentinel ``fn`` has no meaningful bytecode hash);
    # otherwise compute from the plain Python function.
    fn_hash = fn_hash if fn_hash is not None else compute_function_hash(fn, truncate=16)
    # Plain function name (``.fcn`` peel kept only for any legacy wrapped input).
    fn_name = getattr(getattr(fn, "fcn", fn), "__name__", None) or repr(fn)
    selectors = compute_input_selectors(inputs)

    def _combo_str(schema_combo: dict) -> str:
        return ", ".join(f"{k}={v}" for k, v in sorted(schema_combo.items()))

    def _recompute(combo_str: str, why: str) -> bool:
        Log.debug(f"[recompute] {combo_str} — {why}")
        return False

    Log.debug(
        f"_build_skip_hook: constants={list(constant_values.keys())}, "
        f"fn_hash={fn_hash[:12]}, selectors={ {k: v for k, v in selectors.items() if v} }"
    )

    def _should_skip(combo: dict) -> bool:
        schema_combo = {k: v for k, v in combo.items() if k in schema_keys}
        combo_str = _combo_str(schema_combo)
        _vsig_bits = [
            f"{k[len('__vsig_') :]} group {v}"
            for k, v in sorted(combo.items())
            if str(k).startswith("__vsig_")
        ]
        if _vsig_bits:
            combo_str += " [" + "; ".join(_vsig_bits) + "]"

        # Aggregation mode: bind the combo's variant group to its exact
        # consumed-rid set (filled into agg_binding_ref after prepare). The
        # per-param __rid_* staleness comparison below never fires for
        # aggregation combos, so the group identity must be enforced at the
        # gate — otherwise a NEW variant group (or a grown record set) would
        # cross-skip against another group's output.
        expected_input_rids = None
        _fixed_rids: frozenset = frozenset()
        _agg = agg_binding_ref or {}
        if _agg.get("combo_to_rids") is not None:
            _key = tuple(str(combo.get(k, "")) for k in (_agg.get("keys") or []))
            _rids_by_param = _agg["combo_to_rids"].get(_key, {})
            expected_input_rids = {
                str(r) for rids in _rids_by_param.values() for r in rids
            }
            _fixed_rids = _agg.get("fixed_rids") or frozenset()

        # Gate: does an output for THIS variant already exist? Find the latest
        # output record of OutputCls at this schema location whose PRODUCING
        # invocation is ``fn`` with matching constants (graph-precise). Filtering
        # by producing function is essential for input==output (self-referential)
        # pipelines: a re-saved raw input at the same location must NOT be mistaken
        # for the fn's output (it has no producing invocation → would force a
        # spurious recompute).
        target_const_hashes = {n: _chash(v) for n, v in constant_values.items()}
        output_record_id = None
        for OutputCls in outputs:
            rid = _find_skip_gate_record(
                db,
                OutputCls.__name__,
                schema_combo,
                fn_name,
                target_const_hashes,
                expected_input_rids=expected_input_rids,
                fixed_rids=_fixed_rids,
            )
            if rid is None:
                Log.debug(
                    f"missing: {combo_str} — no output record for {OutputCls.__name__}"
                )
                return False
            output_record_id = rid

        # Staleness: compare the stored producing invocation's signature against
        # the combo's current inputs.
        sig = provenance_query.stored_invocation_signature(db._duck, output_record_id)
        if sig is None:
            return _recompute(combo_str, "no provenance record")
        if sig["function_hash"] != fn_hash:
            return _recompute(combo_str, "function hash changed")

        stored_var = sig["var_inputs"]  # param -> (record_id, selector)
        for key, rid_val in combo.items():
            if not key.startswith("__rid_") or rid_val is None:
                continue
            param = key[len("__rid_") :]
            # Self-referential: the loaded input IS the output record. Stable.
            if str(rid_val) == str(output_record_id):
                continue
            stored = stored_var.get(param)
            if stored is None:
                return _recompute(combo_str, f"no stored input {param}")
            stored_rid, stored_sel = stored
            if str(stored_rid) != str(rid_val):
                return _recompute(combo_str, f"input {param} changed")
            if (stored_sel or None) != (selectors.get(param) or None):
                return _recompute(combo_str, f"selector for {param} changed")

        # Constants: compare current value hashes to stored content hashes.
        stored_const = sig["const_hashes"]
        for name, value in constant_values.items():
            cur_hash = _chash(value)
            stored_hash = stored_const.get(name)
            if stored_hash is None:
                if stored_const:
                    return _recompute(combo_str, f"new constant {name}")
            elif stored_hash != cur_hash:
                return _recompute(combo_str, f"constant {name} changed")

        Log.debug(f"[skip] {combo_str}")
        return True

    # Exposed so _for_each_prepare can fill the aggregation binding after
    # Step 12 (variant-group → rid mapping) and before Step 14 (hook firing).
    _should_skip._agg_binding_ref = agg_binding_ref
    return _should_skip


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

    user_explicit_keys = {
        k for k, v in metadata_iterables.items() if not _is_empty_sequence(v)
    }
    Log.debug(
        f"entry: metadata_iterables keys={list(metadata_iterables.keys())}, "
        f"types={[type(v).__name__ for v in metadata_iterables.values()]}, "
        f"lens={[(len(v) if hasattr(v, '__len__') else 'N/A') for v in metadata_iterables.values()]}, "
        f"user_explicit_keys={sorted(user_explicit_keys)}"
    )

    # Step 2: Resolve empty lists to all distinct values from the database
    needs_resolve = [
        k for k, v in metadata_iterables.items() if isinstance(v, list) and len(v) == 0
    ]
    resolved_db = None
    if needs_resolve:
        Log.debug(
            f"resolving {len(needs_resolve)} empty list(s) from database: {needs_resolve}"
        )
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
                Log.warn(f"no values found for '{key}' in database, 0 iterations")
            else:
                Log.debug(f"resolved '{key}' from database: {len(values)} values")
            metadata_iterables[key] = values
    else:
        Log.debug("no empty lists to resolve from database")

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
        Log.debug("PathInput detected, running filesystem discovery")
        pi = _find_pathinput(inputs)
        if pi is not None:
            # The discovery decision (Case A / Case B, and whether discovered
            # combos drive iteration directly) is owned by PathInput so the
            # scidb and scifor layers share one implementation.  "Explicit"
            # keys are those the user passed with non-empty values — a value
            # filled from DB (Step 2) or disk is an auto-fill, not intent.
            metadata_iterables, _discovered_combos = pi.apply_discovery(
                metadata_iterables, user_explicit_keys, log=Log.debug
            )
    else:
        Log.debug("no PathInput detected, skipping filesystem discovery")

    # Step 4: Propagate schema keys to scifor so distribute and DataFrame detection work
    Log.debug("propagating schema keys to scifor")
    _propagate_schema(db, distribute)
    if db and hasattr(db, "dataset_schema_keys"):
        Log.debug(f"schema keys propagated: {db.dataset_schema_keys}")

    # Step 5: Stringify metadata_iterables values for schema keys.
    # load_all_as_df (spread layout) stringifies schema columns in loaded DataFrames
    # (DB returns typed values like np.int64); combo metadata must match to filter correctly.
    Log.debug("stringifying metadata iterable values for schema keys")
    _resolved_db_for_str = db
    if _resolved_db_for_str is None:
        try:
            from scidb.database import get_database

            _resolved_db_for_str = get_database()
        except Exception:
            _resolved_db_for_str = None
    if _resolved_db_for_str is not None and hasattr(
        _resolved_db_for_str, "dataset_schema_keys"
    ):
        from scidb.database import _canonical_numeric_value, _schema_str

        _sk_set = set(_resolved_db_for_str.dataset_schema_keys)
        _sk_types = getattr(_resolved_db_for_str, "dataset_schema_key_types", {}) or {}
        stringify_count = 0
        for key in list(metadata_iterables.keys()):
            if key in _sk_set:
                values = metadata_iterables[key]
                if _sk_types.get(key) == "numeric":
                    # Declared-numeric keys canonicalize unconditionally —
                    # every spelling of the same number ("001", 1, 1.0)
                    # collapses to one identity before stringification.
                    # dict.fromkeys dedupes spellings that collapsed.
                    values = list(
                        dict.fromkeys(_canonical_numeric_value(key, v) for v in values)
                    )
                metadata_iterables[key] = [_schema_str(v) for v in values]
                stringify_count += 1
        Log.debug(f"stringified {stringify_count} schema key iterable(s)")

        # Filesystem-discovered combos carry disk spellings ("001"); apply
        # the same declared-numeric canonicalization so discovery-driven and
        # explicit-iterable runs agree on schema-key identity.
        if _discovered_combos is not None and _sk_types:
            canon_keys = [k for k, t in _sk_types.items() if t == "numeric"]
            for combo in _discovered_combos:
                for k in canon_keys:
                    if k in combo:
                        combo[k] = _schema_str(_canonical_numeric_value(k, combo[k]))
            if canon_keys:
                # Canonicalization can collapse combos that differed only in
                # spelling (both "6MWT-1.mat" and "6MWT-001.mat" on disk) —
                # dedupe so the same identity is not iterated twice.
                seen = set()
                deduped = []
                for combo in _discovered_combos:
                    sig = tuple(sorted(combo.items()))
                    if sig not in seen:
                        seen.add(sig)
                        deduped.append(combo)
                if len(deduped) != len(_discovered_combos):
                    Log.debug(
                        f"deduped {len(_discovered_combos) - len(deduped)} "
                        f"discovered combo(s) that collapsed under "
                        f"canonicalization"
                    )
                _discovered_combos[:] = deduped
                Log.debug(
                    f"canonicalized numeric schema key(s) {canon_keys} in "
                    f"{len(_discovered_combos)} discovered combo(s)"
                )
    else:
        Log.debug("no database available for schema stringification, skipping")

    # Step 6: Build output_names for scifor
    output_names = [_output_name(o) for o in outputs] if outputs else ["result"]
    Log.debug(f"resolved {len(output_names)} output name(s): {output_names}")

    # --- Step 7: Dry-run shortcut: convert inputs for display only, call
    # scifor, return.  Also runs the same combo prefilter Step 9 applies
    # to non-dry runs so the printed iteration count reflects what would
    # actually be processed (combos missing from the DB are dropped). ---
    if dry_run:
        Log.debug(
            "dry_run=True, converting inputs for display and delegating to scifor"
        )
        display_inputs = _convert_inputs_for_display(inputs)

        # Prefilter combos to existing schema combinations (mirrors Step 9
        # for the non-dry path). Only meaningful when at least one key
        # was DB-resolved AND no PathInput is present.
        _dryrun_all_combos = None
        if needs_resolve and not _has_pathinput(inputs):
            from scidb.database import _schema_str

            filter_db = resolved_db
            if filter_db is not None and hasattr(filter_db, "dataset_schema_keys"):
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
                        dict(zip(keys, combo, strict=False))
                        for combo in raw_combos
                        if tuple(_schema_str(combo[i]) for i in schema_indices)
                        in existing_set
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
    Log.debug("building ForEachConfig version keys")
    config = ForEachConfig(
        fn=fn,
        inputs=inputs,
        where=where,
        distribute=distribute,
        as_table=as_table,
    )
    config_keys = config.to_version_keys()
    call_id = config.to_call_id()
    Log.debug(
        f"ForEachConfig: call_id={call_id}, version_keys={list(config_keys.keys())}"
    )

    # Step 9: Pre-filter to only schema combinations that actually exist in the database.
    all_combos = None
    if needs_resolve and not _has_pathinput(inputs):
        Log.debug("pre-filtering combos to only existing schema combinations")
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
                dict(zip(keys, combo, strict=False))
                for combo in raw_combos
                if tuple(_schema_str(combo[i]) for i in schema_indices) in existing_set
            ]
            removed = len(raw_combos) - len(filtered)
            if removed > 0:
                # O(1) per run and changes what will execute — INFO.
                Log.info(
                    f"filtered {removed} non-existent schema combinations "
                    f"(from {len(raw_combos)} to {len(filtered)})"
                )
            else:
                Log.debug(f"all {len(raw_combos)} combos exist in database")
            all_combos = filtered
    else:
        Log.debug(
            "skipping combo pre-filtering (no empty list resolution or PathInput detected)"
        )

    # Step 9.5: Schema exclusions — filter out excluded combos.
    # (No override-hash cache key needed: the bipartite graph invalidates
    # precisely — an aggregation's invocation_id includes its input record_ids,
    # so changing which combos are excluded changes the input set and forces a
    # recompute; unaffected outputs correctly skip.)
    _exclusion_db = db or resolved_db
    if _exclusion_db is None:
        try:
            from scidb.database import get_database

            _exclusion_db = get_database()
        except Exception:
            _exclusion_db = None

    if _exclusion_db is not None:
        from .exclusions import filter_excluded_combos

        if all_combos is not None:
            _before = len(all_combos)
            all_combos = filter_excluded_combos(
                all_combos,
                _exclusion_db.dataset_schema_keys,
                _exclusion_db,
            )
            _after = len(all_combos)
            if _before != _after:
                Log.info(
                    f"schema exclusions removed {_before - _after} combo(s) "
                    f"(from {_before} to {_after})"
                )
        else:
            Log.debug(
                "all_combos is None (explicit iterables); "
                "exclusion filtering will be skipped at combo level"
            )
    else:
        Log.debug("no database available, skipping schema exclusion filtering")

    # Step 10: Load all inputs into DataFrames (with __record_id and __branch_params)
    Log.debug(f"loading {len(inputs)} input(s) into DataFrames")
    loaded_inputs = _convert_inputs(inputs, db, where)
    df_count = sum(
        1
        for v in loaded_inputs.values()
        if isinstance(v, __import__("pandas").DataFrame)
    )
    Log.debug(
        f"loaded {df_count} DataFrame input(s), {len(loaded_inputs) - df_count} other(s)"
    )

    # --- Step 11: Variant tracking: build rid→bp mapping and __rid_{param} discriminator columns ---
    from itertools import product as _iproduct

    import pandas as pd

    Log.debug("building variant tracking (rid->branch_params mapping)")
    rid_to_bp: dict = {}  # {record_id: branch_params_dict}
    rid_keys: list = []  # __rid_{param_name} column names added to this call's schema
    fixed_rid_values: dict = {}  # {param_name: record_id} for Fixed inputs
    # ColumnSelection inputs participate in non-existent-combo PRUNING but NOT in
    # rid expansion / schema extension. Coupling them into rid_keys (as plain
    # DataFrame inputs are) would change variant semantics — it perturbs Variant
    # branch_param pinning and for_columns aggregation. So we track them
    # separately and use only their schema-location coverage to prune combos.
    colsel_params: list = []  # param_names whose input is a ColumnSelection wrapper

    for param_name, data in list(loaded_inputs.items()):
        # Extract DataFrame from a wrapper if needed. Both _scifor.Fixed and
        # _scifor.ColumnSelection expose a `.data` DataFrame, so they MUST be
        # distinguished by TYPE — a bare ``hasattr(data, 'data')`` check
        # misclassifies a ColumnSelection as Fixed.  Three distinct treatments:
        #   - plain DataFrame  -> full rid tracking (expansion + schema + pruning)
        #   - Fixed            -> single fixed record_id, no iteration rid key
        #   - ColumnSelection  -> pruning only (tracked in colsel_params), NOT
        #                         rid expansion/schema (preserves Variant /
        #                         for_columns semantics)
        df = None
        is_fixed = False
        is_colsel = False
        if isinstance(data, pd.DataFrame):
            df = data
        elif isinstance(data, _scifor.Fixed) and isinstance(data.data, pd.DataFrame):
            df = data.data
            is_fixed = True
        elif isinstance(data, _scifor.ColumnSelection) and isinstance(
            data.data, pd.DataFrame
        ):
            df = data.data
            is_colsel = True

        if df is None or "__record_id" not in df.columns:
            if df is not None:
                Log.debug(
                    f"input '{param_name}' "
                    f"({type(data).__name__}) has no __record_id column — "
                    f"rid tracking disabled for this input"
                )
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
                for rid, bp_raw in zip(valid_rids, valid_bps, strict=False):
                    rid_to_bp[rid] = (
                        json.loads(bp_raw or "{}") if isinstance(bp_raw, str) else {}
                    )
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
            Log.debug(
                f"input '{param_name}' (Fixed): rid tracked "
                f"via fixed_rid_values (no iteration rid key)"
            )
        elif is_colsel:
            # ColumnSelection: keep the renamed (now __-prefixed, hence
            # column-selection-dropped) discriminator on the wrapper's data, and
            # mark the param for existence-based combo pruning. Deliberately NOT
            # added to rid_keys: no schema extension, no rid expansion.
            data.data = df_renamed
            colsel_params.append(param_name)
            Log.debug(
                f"input '{param_name}' (ColumnSelection): "
                f"pruning-only (no rid expansion)"
            )
        else:
            # Plain DataFrame: full rid tracking (expansion + schema + pruning).
            loaded_inputs[param_name] = df_renamed
            rid_keys.append(rid_col)
            Log.debug(
                f"input '{param_name}' "
                f"({type(data).__name__}): registered rid key '{rid_col}'"
            )

    Log.debug(
        f"variant tracking: {len(rid_to_bp)} record_id(s) mapped, "
        f"{len(rid_keys)} rid key(s): {rid_keys}, "
        f"{len(fixed_rid_values)} fixed input rid(s): {list(fixed_rid_values.keys())}"
    )

    # Strip __branch_params from all DataFrames (now tracked via rid_to_bp)
    for param_name, data in list(loaded_inputs.items()):
        if isinstance(data, pd.DataFrame) and "__branch_params" in data.columns:
            loaded_inputs[param_name] = data.drop(columns=["__branch_params"])

    # --- Step 12: Build full combos: base_combos × valid rid-combos per schema location ---
    Log.debug("expanding combos with record-ID variants")
    current_schema_keys = list(_scifor.get_schema() or [])

    base_combos = all_combos
    Log.debug(
        f"all_combos={'None' if all_combos is None else len(all_combos)}, "
        f"_discovered_combos={'None' if _discovered_combos is None else len(_discovered_combos)}"
    )
    if base_combos is None and _discovered_combos is not None:
        # Use filesystem-discovered combos directly (avoids non-existent Cartesian combos)
        base_combos = _discovered_combos
        Log.debug(f"using {len(base_combos)} filesystem-discovered combos")
    if base_combos is None:
        keys = list(metadata_iterables.keys())
        value_lists = [metadata_iterables[k] for k in keys]
        base_combos = [
            dict(zip(keys, combo, strict=False)) for combo in _iproduct(*value_lists)
        ]
        Log.debug(f"built {len(base_combos)} base combos from metadata iterables")

    # Detect aggregation mode: not all schema keys are being iterated, so
    # lower-level records should be aggregated into multi-row DataFrames
    # rather than being separated into individual combos via rid expansion.
    _iterated_schema_keys = set(metadata_iterables.keys()) & set(current_schema_keys)
    _aggregation_mode = len(current_schema_keys) > 0 and len(
        _iterated_schema_keys
    ) < len(current_schema_keys)
    if _aggregation_mode:
        Log.debug(
            f"aggregation mode detected: iterating {len(_iterated_schema_keys)}/{len(current_schema_keys)} schema keys"
        )
    else:
        Log.debug("full iteration mode: all schema keys being iterated")

    # Lookup keys for rid disambiguation: schema keys + any non-schema metadata
    # iterable keys.  Using only schema keys misses non-schema iterables (e.g.
    # "session") that ARE present in the loaded DataFrame and should distinguish
    # which record belongs to which combo.
    _lookup_keys = list(
        dict.fromkeys(
            current_schema_keys
            + [k for k in metadata_iterables if k not in set(current_schema_keys)]
        )
    )

    # PathOutput variant placeholders: names referenced by templates that are
    # NOT combo-supplied — these resolve from each expanded combo's variant
    # group branch_params and are injected below (then stripped before save).
    _path_placeholder_names, _path_outputs = _pathoutput_placeholders(
        inputs, set(current_schema_keys) | set(metadata_iterables)
    )
    _path_missing_placeholders: set = set()
    if _path_placeholder_names:
        Log.debug(
            f"PathOutput branch_param placeholder(s) detected: "
            f"{sorted(_path_placeholder_names)}"
        )

    # For each rid_key, map combo_tuple → [rid_values at that combo]
    rid_per_combo: dict = {}
    for rid_col in rid_keys:
        param_name = rid_col[len("__rid_") :]
        data = loaded_inputs.get(param_name)

        # Extract DataFrame from Fixed wrapper if needed
        df = None
        if isinstance(data, pd.DataFrame):
            df = data
        elif hasattr(data, "data") and isinstance(data.data, pd.DataFrame):
            df = data.data

        if df is None or rid_col not in df.columns:
            continue
        # Group only by the schema keys this input actually POPULATES. A variable
        # stored at a coarser level than the dataset schema (e.g. a subject/session/
        # speed/trial variable in a schema that also has 'cycle') carries the finer
        # keys as all-NaN columns. Including an all-NaN column here is catastrophic:
        # pandas groupby drops NaN-key groups by default, so EVERY row is dropped →
        # empty mapping → no rids tracked → no __upstream → no _invocation_input
        # edges (severed input provenance, the precondition for the orphan cascade).
        # The mapping key is still built over the full _lookup_keys (missing keys
        # filled with ""), so downstream combo matching is unaffected.
        schema_cols_in_df = [
            k for k in _lookup_keys if k in df.columns and not df[k].isna().all()
        ]
        mapping: dict = {}
        # Dedupe rids per group so DataFrame-mode inputs (one DuckDB row
        # per inner-table row, all sharing a single record_id) don't
        # produce N duplicate combos. We preserve insertion order via
        # dict.fromkeys.
        if schema_cols_in_df:
            for combo_vals, group in df.groupby(schema_cols_in_df, sort=False):
                raw_key = combo_vals if isinstance(combo_vals, tuple) else (combo_vals,)
                # Expand to ALL _lookup_keys, filling missing cols with ""
                col_val = {
                    sk: ("" if v is None else str(v))
                    for sk, v in zip(schema_cols_in_df, raw_key, strict=False)
                }
                key = tuple(col_val.get(sk, "") for sk in _lookup_keys)
                mapping[key] = list(dict.fromkeys(group[rid_col].tolist()))
        else:
            # No lookup cols in df — use all-empty key
            mapping[tuple("" for _ in _lookup_keys)] = list(
                dict.fromkeys(df[rid_col].tolist())
            )
        rid_per_combo[rid_col] = mapping

    # Existence coverage for ColumnSelection inputs: the set of schema-location
    # keys (over _lookup_keys) each one actually has data for. Used purely to
    # PRUNE non-existent Cartesian combos — no rid expansion, no schema change.
    # Keyed identically to rid_per_combo so the same combo_key tuple compares.
    colsel_existence: dict = {}  # param_name -> set[tuple]
    for param_name in colsel_params:
        data = loaded_inputs.get(param_name)
        df = (
            data.data
            if (hasattr(data, "data") and isinstance(data.data, pd.DataFrame))
            else None
        )
        if df is None:
            continue
        # Same all-NaN exclusion as rid_per_combo above: a coarser-level
        # ColumnSelection input carries finer schema keys as all-NaN columns;
        # grouping by them would drop every row (pandas dropna), yielding EMPTY
        # coverage → the prune step would then drop ALL combos and nothing runs.
        schema_cols_in_df = [
            k for k in _lookup_keys if k in df.columns and not df[k].isna().all()
        ]
        present: set = set()
        if schema_cols_in_df:
            for combo_vals, _group in df.groupby(schema_cols_in_df, sort=False):
                raw_key = combo_vals if isinstance(combo_vals, tuple) else (combo_vals,)
                col_val = {
                    sk: ("" if v is None else str(v))
                    for sk, v in zip(schema_cols_in_df, raw_key, strict=False)
                }
                present.add(tuple(col_val.get(sk, "") for sk in _lookup_keys))
        else:
            present.add(tuple("" for _ in _lookup_keys))
        colsel_existence[param_name] = present
        Log.debug(
            f"ColumnSelection '{param_name}' covers "
            f"{len(present)} schema location(s) for combo pruning"
        )

    # Precompute, per ColumnSelection input, the index positions it actually
    # populates (a coarser input's finer keys are "" everywhere). Computed once,
    # not per combo, since it depends only on the coverage set.
    _colsel_coverage = []  # list[(present_set, populated_idx_tuple)]
    for _param, present in colsel_existence.items():
        if not present:
            continue
        populated_idx = tuple(
            i for i in range(len(_lookup_keys)) if any(key[i] != "" for key in present)
        )
        _colsel_coverage.append((present, populated_idx))

    def _colsel_combo_present(schema_vals: tuple) -> bool:
        """True if every ColumnSelection input has data at this combo location.

        ``schema_vals`` is the combo key over ``_lookup_keys``. Compared only on
        the keys each input actually populates, so a ColumnSelection stored at a
        coarser level (finer keys absent from its frame) still matches.
        """
        n = len(_lookup_keys)
        for present, populated_idx in _colsel_coverage:
            probe = tuple(
                schema_vals[i] if i in populated_idx else "" for i in range(n)
            )
            if probe not in present:
                return False
        return True

    # --- Step 12 diagnostic: record/row multiplicity per schema location ---
    # When a per-combo call receives MORE rows than expected, the cause is almost
    # always >1 record_id at one schema location (distinct branch_param/version
    # VARIANTS, both kept by "latest version PER PARAMETER SET"), or one record
    # whose stored table has multiple rows. This pass makes the distinction
    # explicit so it's obvious which is happening and what the variants are.
    _diag_inputs = []
    for _pn, _data in loaded_inputs.items():
        _d = (
            _data
            if isinstance(_data, pd.DataFrame)
            else (
                _data.data
                if (
                    hasattr(_data, "data")
                    and isinstance(getattr(_data, "data", None), pd.DataFrame)
                )
                else None
            )
        )
        if _d is not None:
            _diag_inputs.append((_pn, _d))
    for _pn, _d in _diag_inputs:
        _rid_cols = [c for c in _d.columns if c.startswith("__rid_")]
        if not _rid_cols:
            continue
        _rc = _rid_cols[0]
        _scols = [k for k in _lookup_keys if k in _d.columns]
        if not _scols:
            continue
        _multi = 0
        _samples = []
        for _vals, _grp in _d.groupby(_scols, sort=False):
            _rids = list(dict.fromkeys(_grp[_rc].tolist()))
            if len(_rids) > 1 or len(_grp) > 1:
                _loc = dict(
                    zip(
                        _scols,
                        _vals if isinstance(_vals, tuple) else (_vals,),
                        strict=False,
                    )
                )
                if len(_rids) > 1:
                    _multi += 1
                if len(_samples) < 5:
                    _bps = [rid_to_bp.get(r, {}) for r in _rids]
                    _samples.append(
                        f"{_loc}: {len(_grp)} row(s), {len(_rids)} record_id(s) "
                        f"branch_params={_bps}"
                    )
        if _multi:
            Log.warn(
                f"diagnostic: input '{_pn}' has {_multi} schema "
                f"location(s) with MORE THAN ONE record_id (distinct "
                f"branch_param/version variants). Full iteration expands these "
                f"into separate combos; aggregation auto-splits into one call "
                f"per branch_param signature (pooled only if the input is "
                f"wrapped in AcrossVariants). Examples: " + "; ".join(_samples)
            )
        elif _samples:
            Log.debug(
                f"diagnostic: input '{_pn}' — single record_id but "
                f"multi-row stored table at some locations. Examples: "
                + "; ".join(_samples)
            )

    if _aggregation_mode:
        # Aggregation mode: skip per-record rid expansion, but AUTO-SPLIT by
        # upstream branch_param signature (decision D1,
        # endpoints-viz-and-stats-design.md): one call per distinct variant
        # group, as if the user had written EachOf(Variant(...), Variant(...)) —
        # implemented here at signature granularity so nothing is reloaded.
        # Pooling distinct variants into one table double-counts aggregates and
        # destroys variant identity; AcrossVariants inputs opt out explicitly
        # (multiverse analysis) and pool with branch_params attached as columns.
        # __rid_* columns are stripped so the user's function doesn't see
        # internal tracking columns.
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
            i for i, k in enumerate(current_schema_keys) if k in _iterated_schema_keys
        ]
        if iterated_indices:
            below_iterated_keys = set(current_schema_keys[max(iterated_indices) + 1 :])
        else:
            # No schema keys iterated — every schema key is "below"
            # (this is the no-iteration case; aggregate across everything).
            below_iterated_keys = set(current_schema_keys)

        # --- D1 auto-split bookkeeping (before __rid_* columns are stripped) ---
        _across_params = {
            name for name, spec in inputs.items() if isinstance(spec, AcrossVariants)
        }
        _sig_cache: dict = {}

        def _sig_of(rid) -> str:
            """Canonical signature of a record's upstream branch_params group."""
            try:
                if rid in _sig_cache:
                    return _sig_cache[rid]
            except TypeError:
                rid = str(rid)
                if rid in _sig_cache:
                    return _sig_cache[rid]
            sig = json.dumps(rid_to_bp.get(rid, {}), sort_keys=True, default=str)
            _sig_cache[rid] = sig
            return sig

        _EMPTY_SIG = json.dumps({})
        _iterated_keys_ordered = [k for k in _lookup_keys if k in _iterated_schema_keys]
        _iter_idx = [_lookup_keys.index(k) for k in _iterated_keys_ordered]

        vsig_cols: list = []  # __vsig_{param} discriminators for split inputs
        _vsig_values: dict = {}  # vsig_col -> ordered unique signature values
        # vsig_col -> {iterated_combo_key -> {sig -> [rids]}}
        _sig_rids_by_combo: dict = {}

        for rid_col in rid_keys:
            param_name = rid_col[len("__rid_") :]
            data = loaded_inputs.get(param_name)
            _df = data if isinstance(data, pd.DataFrame) else None
            if _df is None or rid_col not in _df.columns:
                continue

            if param_name in _across_params:
                # Opt-out: pool all variants, attaching each namespaced
                # branch_param key as an ordinary column so the function can
                # group by specification (variant identity is preserved).
                bp_keys = sorted(
                    {
                        k
                        for rid in _df[rid_col].dropna().unique()
                        for k in rid_to_bp.get(rid, {})
                    }
                )
                _attached, _collided = [], []
                for k in bp_keys:
                    if k in _df.columns:
                        _collided.append(k)
                        continue
                    _df[k] = _df[rid_col].map(
                        lambda r, _k=k: rid_to_bp.get(r, {}).get(_k)
                    )
                    _attached.append(k)
                if _collided:
                    _msg = (
                        f"AcrossVariants('{param_name}'): branch_param "
                        f"column(s) {_collided} collide with existing data "
                        f"columns — not attached."
                    )
                    warnings.warn(_msg, UserWarning, stacklevel=2)
                    Log.warn(_msg)
                _n_sigs = len({_sig_of(r) for r in _df[rid_col].dropna().unique()})
                Log.debug(
                    f"AcrossVariants('{param_name}'): pooling "
                    f"{_n_sigs} variant group(s); attached branch_param "
                    f"column(s): {_attached}"
                )
                continue

            # Split input: one __vsig_{param} discriminator column per row.
            # scifor treats __-prefixed schema keys as internal (filters by
            # them, hides them from the user function) — same seam as __rid_*.
            vsig_col = f"__vsig_{param_name}"
            vsig_cols.append(vsig_col)
            _df[vsig_col] = _df[rid_col].map(_sig_of)

            # Per-iterated-combo signature bookkeeping from rid_per_combo
            # (built above over the full _lookup_keys) for combo expansion,
            # save-path provenance, and the ragged-group warning.
            per_combo_rids: dict = {}
            per_combo_locs: dict = {}
            for full_key, rids in rid_per_combo.get(rid_col, {}).items():
                ck = tuple(full_key[i] for i in _iter_idx)
                for rid in rids:
                    sig = _sig_of(rid)
                    per_combo_rids.setdefault(ck, {}).setdefault(sig, []).append(rid)
                    per_combo_locs.setdefault(ck, {}).setdefault(sig, set()).add(
                        full_key
                    )
            _sig_rids_by_combo[vsig_col] = per_combo_rids
            _vsig_values[vsig_col] = list(
                dict.fromkeys(
                    sig for sig_map in per_combo_rids.values() for sig in sig_map
                )
            )

            # Ragged variant groups: a group missing schema locations that other
            # groups cover aggregates a PARTIAL set of rows. Decided policy
            # (D1): warn and proceed.
            _ragged_examples: list = []
            for ck, sig_map in per_combo_locs.items():
                if len(sig_map) <= 1:
                    continue
                union_locs = set().union(*sig_map.values())
                for sig, locs in sig_map.items():
                    missing = union_locs - locs
                    if missing and len(_ragged_examples) < 5:
                        combo_disp = (
                            dict(zip(_iterated_keys_ordered, ck, strict=False))
                            or "(grand aggregation)"
                        )
                        miss_disp = [
                            {
                                k: v
                                for k, v in zip(_lookup_keys, m, strict=False)
                                if v != ""
                            }
                            for m in sorted(missing)[:3]
                        ]
                        _ragged_examples.append(
                            f"combo {combo_disp}: group {json.loads(sig)} missing "
                            f"{len(missing)} location(s), e.g. {miss_disp}"
                        )
            if _ragged_examples:
                _msg = (
                    f"aggregation auto-split: input '{param_name}' has "
                    f"RAGGED variant groups — some branch_param groups cover "
                    f"fewer schema locations than others; each group aggregates "
                    f"only the rows it has. Pin one group with Variant(...) or "
                    f"pool explicitly with AcrossVariants(...) if this is not "
                    f"intended. " + " | ".join(_ragged_examples)
                )
                warnings.warn(_msg, UserWarning, stacklevel=2)
                Log.warn(_msg)

        for param_name, data in list(loaded_inputs.items()):
            # Resolve the underlying frame for plain DataFrame OR ColumnSelection
            # wrapper inputs (the latter now carries a renamed __rid_* column too,
            # since Step 11 registers a rid key for it).
            if isinstance(data, pd.DataFrame):
                _df = data
            elif isinstance(data, _scifor.ColumnSelection) and isinstance(
                data.data, pd.DataFrame
            ):
                _df = data.data
            else:
                continue
            rid_cols_in_df = [c for c in _df.columns if c.startswith("__rid_")]
            empty_schema_cols = [
                c
                for c in _df.columns
                if c in below_iterated_keys and _df[c].isna().all()
            ]
            drop_cols = rid_cols_in_df + empty_schema_cols
            if drop_cols:
                _stripped = _df.drop(columns=drop_cols)
                if isinstance(data, pd.DataFrame):
                    loaded_inputs[param_name] = _stripped
                else:
                    data.data = _stripped
            if empty_schema_cols:
                Log.debug(
                    f"aggregation: dropped all-null schema "
                    f"column(s) {empty_schema_cols} from loaded input "
                    f"'{param_name}' (below iterated schema level)"
                )

        # Expand combos over the observed signature combinations per combo —
        # one call per variant group (auto-split), Cartesian across split
        # inputs (mirroring full-iteration rid expansion at signature
        # granularity). A split input with NO data at a combo expands with the
        # empty signature so the combo still flows through and skips
        # gracefully, matching pre-split behavior for empty locations.
        #
        # _combo_to_rids is keyed by the iterated keys PLUS the __vsig_* values
        # (the same recipe the save path applies to result rows, which carry
        # the __vsig_* columns) so each output saves with only ITS group's
        # contributing rids: the branch_params merge becomes conflict-free by
        # construction and __upstream gives each group a distinct identity.
        _combo_key_cols = _iterated_keys_ordered + vsig_cols

        def _sig_conflicts_with_combo(sig: str, combo: dict) -> bool:
            """True when a ``__save__.<key>`` signature entry contradicts the
            combo's own value for ``<key>``.

            Save-time non-schema kwargs are BOTH a branch-param discriminator
            (``__save__.<key>``) and a loaded data column scifor row-filters
            by when ``<key>`` is iterated. Pairing a combo with a variant
            group whose ``__save__.<key>`` differs from the combo's value
            would call fn on rows the combo's own filter excludes (an empty
            or wrong-group input), so such pairings are dropped — align, not
            cross-product. Only ``__save__.*`` keys participate: function
            branch_params (``fn.param``) have no corresponding data column.
            """
            if sig == _EMPTY_SIG:
                return False
            for k, v in json.loads(sig).items():
                if not str(k).startswith("__save__."):
                    continue
                bare = k[len("__save__.") :]
                if bare in combo and str(combo[bare]) != str(v):
                    return True
            return False

        full_combos = []
        _combo_to_rids = {}
        for combo in base_combos:
            ck = tuple(str(combo.get(k, "")) for k in _iterated_keys_ordered)
            sig_options = []
            for c in vsig_cols:
                sigs = sorted(_sig_rids_by_combo.get(c, {}).get(ck, {}).keys()) or [
                    _EMPTY_SIG
                ]
                aligned = [s for s in sigs if not _sig_conflicts_with_combo(s, combo)]
                if len(aligned) < len(sigs):
                    Log.debug(
                        f"aggregation auto-split: input "
                        f"'{c[len('__vsig_') :]}' at combo {combo}: aligned "
                        f"__save__.* signature(s) to iterated value(s) — "
                        f"kept {len(aligned)}/{len(sigs)} group(s)"
                    )
                # All groups conflicting = no matching data at this combo:
                # flow through with the empty signature and skip gracefully,
                # same as a combo with no data at all.
                sig_options.append(aligned or [_EMPTY_SIG])
            # Pooled rids at this combo for inputs that do NOT split
            # (AcrossVariants opt-outs and any rid-tracked input without a
            # __vsig column) — identical for every group of this combo.
            pooled_by_param = {}
            for rid_col, mapping in rid_per_combo.items():
                if f"__vsig_{rid_col[len('__rid_') :]}" in vsig_cols:
                    continue
                param_rids = []
                for full_key, rids in mapping.items():
                    if tuple(full_key[i] for i in _iter_idx) == ck:
                        param_rids.extend(rids)
                if param_rids:
                    pooled_by_param[rid_col] = param_rids
            for sig_combo in _iproduct(*sig_options) if sig_options else [()]:
                fc = dict(combo)
                rids_by_param = dict(pooled_by_param)
                for c, s in zip(vsig_cols, sig_combo, strict=False):
                    fc[c] = s
                    group_rids = _sig_rids_by_combo.get(c, {}).get(ck, {}).get(s, [])
                    if group_rids:
                        rids_by_param["__rid_" + c[len("__vsig_") :]] = group_rids
                if _path_placeholder_names:
                    # Group bp = the parsed split-input signatures + any Fixed
                    # inputs' bp; {variant} digests the signature tuple itself.
                    _bp_dicts = [json.loads(s) for s in sig_combo]
                    _bp_dicts += [
                        rid_to_bp.get(r, {}) for r in fixed_rid_values.values() if r
                    ]
                    _merged, _confl = _merge_group_bp(_bp_dicts)
                    _inject_path_placeholders(
                        fc,
                        _path_placeholder_names,
                        _merged,
                        _confl,
                        "|".join(sig_combo),
                        _path_missing_placeholders,
                    )
                full_combos.append(fc)
                _combo_to_rids[tuple(str(fc.get(k, "")) for k in _combo_key_cols)] = (
                    rids_by_param
                )

        # The __vsig_* keys extend the scifor schema (Step 15) so each call's
        # rows are filtered to its variant group; the save path keys
        # combo_to_rids lookups by iterated keys + __vsig_* values.
        _iterated_keys_ordered = _combo_key_cols
        rid_keys_for_schema = list(vsig_cols)

        total_rids = sum(
            len(rids)
            for rids_by_param in _combo_to_rids.values()
            for rids in rids_by_param.values()
        )
        Log.debug(
            f"aggregation mode (auto-split by branch_param signature): "
            f"iterating {sorted(_iterated_schema_keys) or '(none)'} "
            f"of schema {current_schema_keys}, "
            f"{len(base_combos)} base combo(s) -> {len(full_combos)} call(s), "
            f"variant groups per split input: "
            f"{ {c[len('__vsig_') :]: len(_vsig_values.get(c, [])) for c in vsig_cols} }, "
            f"pooled (AcrossVariants) inputs: {sorted(_across_params) or 'none'}, "
            f"{total_rids} contributing rids"
        )
    else:
        # Full iteration mode: expand combos with rid variants.
        _combo_to_rids = None
        _iterated_keys_ordered = None
        rid_keys_for_schema = rid_keys

        # AcrossVariants only changes aggregation-mode behavior: in full
        # iteration every combo sees exactly one variant row (rid expansion),
        # so pooling is a no-op and the input behaves as if unwrapped.
        _across_noop = sorted(
            name for name, spec in inputs.items() if isinstance(spec, AcrossVariants)
        )
        if _across_noop:
            _msg = (
                f"AcrossVariants input(s) {_across_noop} in FULL "
                f"iteration mode: every combo sees exactly one variant, so "
                f"pooling is a no-op — the input(s) behave as if unwrapped "
                f"(variants expand into separate combos). AcrossVariants only "
                f"affects aggregation-mode for_each calls."
            )
            warnings.warn(_msg, UserWarning, stacklevel=2)
            Log.warn(_msg)

        # Expand each base combo with all valid rid-combos for that schema location
        Log.debug(
            f"expanding combos: {len(base_combos)} base combos, "
            f"{len(rid_per_combo)} rid dimensions"
        )
        full_combos: list = []
        _pruned_colsel = 0
        for combo in base_combos:
            schema_vals = tuple(str(combo.get(k, "")) for k in _lookup_keys)

            # Prune Cartesian combos that no ColumnSelection input has data for.
            # (Plain DataFrame inputs prune via the rid-validity check below;
            # ColumnSelection inputs deliberately don't expand, so they prune
            # here instead — without this, non-existent grid points leak through
            # as empty per-combo calls.)
            if colsel_existence and not _colsel_combo_present(schema_vals):
                _pruned_colsel += 1
                continue

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
                    for rc_name, rc_val in zip(rid_col_names, rid_combo, strict=False):
                        full_combo[rc_name] = rc_val
                    # Add Fixed input record_ids to combo
                    for fixed_param, fixed_rid in fixed_rid_values.items():
                        full_combo[f"__rid_{fixed_param}"] = fixed_rid
                    if _path_placeholder_names:
                        _bp_dicts = [
                            rid_to_bp.get(full_combo[k], {})
                            for k in full_combo
                            if str(k).startswith("__rid_")
                        ]
                        _merged, _confl = _merge_group_bp(_bp_dicts)
                        _inject_path_placeholders(
                            full_combo,
                            _path_placeholder_names,
                            _merged,
                            _confl,
                            json.dumps(_merged, sort_keys=True, default=str),
                            _path_missing_placeholders,
                        )
                    full_combos.append(full_combo)
            else:
                full_combo = {**combo}
                # Add Fixed input record_ids to combo
                for fixed_param, fixed_rid in fixed_rid_values.items():
                    full_combo[f"__rid_{fixed_param}"] = fixed_rid
                if _path_placeholder_names:
                    _bp_dicts = [
                        rid_to_bp.get(full_combo[k], {})
                        for k in full_combo
                        if str(k).startswith("__rid_")
                    ]
                    _merged, _confl = _merge_group_bp(_bp_dicts)
                    _inject_path_placeholders(
                        full_combo,
                        _path_placeholder_names,
                        _merged,
                        _confl,
                        json.dumps(_merged, sort_keys=True, default=str),
                        _path_missing_placeholders,
                    )
                full_combos.append(full_combo)

        if _pruned_colsel:
            Log.debug(
                f"pruned {_pruned_colsel} non-existent combo(s) "
                f"via ColumnSelection coverage"
            )
        if len(full_combos) != len(base_combos):
            Log.debug(
                f"expanded {len(base_combos)} base combos -> "
                f"{len(full_combos)} full combos (rid variants / pruning)"
            )
        else:
            Log.debug(f"{len(full_combos)} combos (no rid expansion needed)")

        # Existence-pruning health check. In full iteration mode the rid-validity
        # skip and the ColumnSelection coverage prune are the ONLY things that
        # drop Cartesian combos with no backing data. If there are DataFrame-backed
        # inputs but NEITHER pruning mechanism is active, the entire Cartesian
        # product leaks through — every non-existent location becomes an empty
        # per-combo call. This is exactly the failure mode when an input wrapper
        # fails to register either a rid key or ColumnSelection coverage.
        _has_df_inputs = any(
            isinstance(v, pd.DataFrame)
            or (
                isinstance(v, (_scifor.ColumnSelection, _scifor.Fixed))
                and isinstance(getattr(v, "data", None), pd.DataFrame)
            )
            for v in loaded_inputs.values()
        )
        if (
            _has_df_inputs
            and not rid_per_combo
            and not colsel_existence
            and len(full_combos) == len(base_combos)
        ):
            Log.warn(
                "expand_combos: full iteration over all schema keys kept the "
                f"ENTIRE Cartesian product ({len(full_combos)} combos) with no "
                "pruning — DataFrame-backed inputs registered neither a rid key nor "
                "ColumnSelection coverage, so non-existent schema locations will be "
                "passed to the function as EMPTY tables. This usually means an "
                "input's __record_id was lost before variant tracking. "
                "Check the per-input logs above."
            )

    # PathOutput placeholders: warn once per unresolved name (the literal
    # ``{name}`` stays in the path), then guard against variant-group path
    # collisions BEFORE anything renders — a shared path means each group's
    # file silently overwrites the previous one.
    if _path_missing_placeholders:
        _msg = (
            f"PathOutput placeholder(s) "
            f"{sorted('{' + n + '}' for n in _path_missing_placeholders)} did not "
            f"match any branch_param of this call's variant group(s) — the "
            f"literal placeholder text stays in the resolved path. Available "
            f"branch_param keys come from upstream constants (e.g. "
            f"'bandpass.low_hz', bare-name '{{low_hz}}')."
        )
        warnings.warn(_msg, UserWarning, stacklevel=2)
        Log.warn(_msg)
    if _path_outputs and full_combos:
        _colname_columns = None
        for _spec in inputs.values():
            _cs = _iterate_column_selection(_spec)
            if _cs is not None and _cs.columns:
                _colname_columns = list(_cs.columns)
                break
        _guard_pathoutput_collisions(
            _path_outputs,
            full_combos,
            _colname_columns,
            rid_to_bp,
            _path_placeholder_names,
        )

    # Step 14: Apply pre-combo hook (e.g. skip_computed from scihist): filter out any
    # combos where the hook returns True.
    _skip_computed_count = 0
    if _pre_combo_hook is not None:
        # Aggregation mode: hand the skip hook the variant-group → consumed-rid
        # mapping Step 12 just built (via the mutable holder _build_skip_hook
        # exposes). Aggregation combos carry no __rid_* keys, so the hook's
        # gate binds each group by its exact rid set — without this, a new
        # variant group (or a grown record set) would cross-skip against
        # another group's output. Works for both the Python and MATLAB-bridge
        # call sites, which both build the hook before calling prepare.
        _hook_agg_ref = getattr(_pre_combo_hook, "_agg_binding_ref", None)
        if _hook_agg_ref is not None and _aggregation_mode:
            _hook_agg_ref["combo_to_rids"] = _combo_to_rids
            _hook_agg_ref["keys"] = _iterated_keys_ordered
            _hook_agg_ref["fixed_rids"] = frozenset(
                str(v) for v in fixed_rid_values.values() if v is not None
            )
        Log.debug("applying pre-combo hook (skip_computed)")
        pre_hook_count = len(full_combos)
        full_combos = [c for c in full_combos if not _pre_combo_hook(c)]
        skipped = pre_hook_count - len(full_combos)
        _skip_computed_count = skipped
        if skipped > 0:
            # O(1) per run and part of the "what ran / what was skipped" story.
            Log.info(f"skip_computed: {skipped}/{pre_hook_count} combos skipped")
        else:
            Log.debug(
                f"skip_computed: 0/{pre_hook_count} combos skipped (all will be computed)"
            )
    else:
        Log.debug("no pre-combo hook provided, skipping")

    # Step 15: Temporarily extend scifor's schema with the discriminator keys so
    # _filter_df_for_combo treats them as schema columns (not data columns):
    # __rid_* record ids in full iteration (single-row filtered DFs), __vsig_*
    # branch-param signatures in aggregation (per-variant-group multi-row DFs).
    if rid_keys_for_schema:
        extended_schema = current_schema_keys + rid_keys_for_schema
        Log.debug(
            f"extending scifor schema from {len(current_schema_keys)} to {len(extended_schema)} keys (added {len(rid_keys_for_schema)} {'variant-signature' if _aggregation_mode else 'rid'} keys)"
        )
        _scifor.set_schema(extended_schema)
    else:
        Log.debug("not extending scifor schema (no discriminator keys)")

    # Collect all values per extension key so scifor's metadata_iterables are
    # complete. Full iteration extends with __rid_* record ids; aggregation
    # extends with __vsig_* branch-param signatures (collected from the
    # expanded combos so empty-signature placeholders are included).
    extended_metadata_iterables = dict(metadata_iterables)
    if rid_keys_for_schema:
        if _aggregation_mode:
            for vsig_col in rid_keys_for_schema:
                extended_metadata_iterables[vsig_col] = list(
                    dict.fromkeys(
                        str(fc[vsig_col]) for fc in full_combos if vsig_col in fc
                    )
                )
        else:
            for rid_col, mapping in rid_per_combo.items():
                all_rids: list = []
                for rids in mapping.values():
                    all_rids.extend(rids)
                extended_metadata_iterables[rid_col] = list(
                    dict.fromkeys(all_rids)
                )  # preserve order, dedupe

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
        path_extra_keys=_path_placeholder_names or None,
        skip_computed_count=_skip_computed_count,
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
    generates_file: bool = False,
    endpoint_kind: "str | None" = None,
):
    """Run scidb.for_each's Step 18 (schema restore) and Step 19 (save).

    Returns ``result_tbl`` unchanged after performing the save side effect.
    For endpoint runs (``endpoint_kind`` in {"plot", "stat"}), artifacts get a
    provenance stamp (D4): record mode stamps inside ``_save_results`` (where
    the record_id is known); draft mode stamps here with the same blob minus
    the record_id.
    """
    # Step 18: Restore scifor's schema
    if state.rid_keys_for_schema:
        Log.debug(
            f"restoring scifor schema to {len(state.current_schema_keys)} keys (removing {len(state.rid_keys_for_schema)} rid keys)"
        )
        _scifor.set_schema(state.current_schema_keys)
    else:
        Log.debug("no schema restoration needed (wasn't extended)")

    if result_tbl is None:
        return None

    # Strip PathOutput placeholder columns injected at combo expansion: they
    # exist only so scifor's path resolution can substitute them. Left in,
    # they would surface in the user-facing table and — worse — be picked up
    # as dynamic-discriminator branch_params on save (the group's REAL
    # namespaced bp already inherits via combo_to_rids).
    if state.path_extra_keys:
        _extra_cols = [c for c in result_tbl.columns if c in state.path_extra_keys]
        if _extra_cols:
            result_tbl = result_tbl.drop(columns=_extra_cols)
            Log.debug(
                f"stripped {len(_extra_cols)} PathOutput placeholder "
                f"column(s) from results: {_extra_cols}"
            )

    # Step 19: Save results
    if save and outputs and not result_tbl.empty:
        Log.debug(
            f"saving {len(result_tbl)} result row(s) for {len(outputs)} output(s)"
        )
        # Compute Fixed input rids for the bipartite graph edges if not provided
        # (Fixed inputs contribute __graph_var_bindings just like variable inputs).
        fixed_rids_for_save = lineage_fixed_rids
        if fixed_rids_for_save is None:
            fixed_rids_for_save = _compute_fixed_input_rids(inputs, db)
            if fixed_rids_for_save:
                Log.debug(
                    f"computed {len(fixed_rids_for_save)} Fixed input rid(s) for graph: {list(fixed_rids_for_save.keys())}"
                )

        # Per-param identity selectors (ColumnSelection columns, etc.) for the
        # bipartite graph edges. Computed once from the inputs spec.
        from .provenance_save import compute_input_selectors

        input_selectors = compute_input_selectors(inputs)

        save_t0 = time.perf_counter()
        _save_results(
            result_tbl,
            outputs,
            state.output_names,
            state.config_keys,
            db,
            rid_to_bp=state.rid_to_bp,
            rid_keys=[] if state.aggregation_mode else state.rid_keys,
            lineage_fixed_rids=fixed_rids_for_save,
            combo_to_rids=state.combo_to_rids,
            combo_to_rids_keys=state.iterated_keys_ordered,
            input_selectors=input_selectors,
            generates_file=generates_file,
            endpoint_kind=endpoint_kind,
            stamp_param_names=[rc[len("__rid_") :] for rc in (state.rid_keys or [])],
        )
        save_elapsed = time.perf_counter() - save_t0
        Log.debug(
            f"save_results complete: saved {len(result_tbl)} result(s) in {save_elapsed:.3f}s"
        )
    elif not save:
        Log.debug("skipping save (save=False)")
    elif not outputs:
        Log.debug("skipping save (no outputs specified)")
    elif result_tbl.empty:
        Log.debug("skipping save (result table is empty)")

    # Endpoint DRAFT stamping (D4): the save was suppressed (finalized=False,
    # or explicit save=False), but draft artifacts get the same provenance
    # blob a finalized run would embed — draft:true in place of a record_id.
    if endpoint_kind and not (save and outputs) and not result_tbl.empty:
        _stamp_draft_endpoint_artifacts(endpoint_kind, result_tbl, state, db)

    return result_tbl


def _normalize_variable_inputs(
    resolved: dict,
    current_combo: dict,
    inputs: dict,
    loaded_inputs: "dict | None" = None,
) -> dict:
    """Normalize variable inputs to the raw data the function expects.

    scifor extracts data from the spread DataFrames; this normalizes each
    variable param to its clean raw value — pulling the data column out of a
    1-row DataFrame and restoring the dict structure for multi-column
    (dict-of-arrays) variables (scifor's _extract_data strips the dict wrapper
    when there is exactly one data column). Non-variable params pass through.

    This is the value the function previously received as ``BaseVariable.data``
    after LineageFcn unwrapped its reconstructed input — now produced directly.

    Args:
        resolved: Dict of param_name → raw_data from scifor
        current_combo: Combo dict with __rid_* → record_id + schema keys
        inputs: Original inputs dict with param_name → variable_class or Fixed()
        loaded_inputs: The spread DataFrames from _for_each_prepare (state.loaded_inputs).

    Returns:
        Dict with normalized raw data for variable inputs, pass-through for others
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
        elif hasattr(input_spec, "var_type") and isinstance(input_spec.var_type, type):
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
                schema_keys_in_combo = {
                    k for k in current_combo if not k.startswith("__")
                }
                data_cols = [
                    c
                    for c in df_input.columns
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

        # Pass the normalized raw data (DataFrame → array, dict structure
        # restored for multi-column variables) — exactly the value the function
        # used to receive as ``BaseVariable.data`` after LineageFcn unwrapped it.
        reconstructed[param_name] = data_value

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


def _log_loaded_input(
    param_name: str, var_spec: Any, loaded: Any, elapsed: float
) -> None:
    """Log details about a loaded input."""
    import pandas as pd

    type_name = _input_type_name(var_spec)

    if isinstance(loaded, pd.DataFrame):
        Log.debug(
            f"input '{param_name}': loaded {type_name} -> "
            f"{len(loaded)} rows, {len(loaded.columns)} cols in {elapsed:.3f}s"
        )
    elif isinstance(loaded, (PerComboLoader, PerComboLoaderMerge)):
        Log.debug(
            f"input '{param_name}': {type_name} (per-combo loader, will load during iteration)"
        )
    else:
        Log.debug(f"input '{param_name}': loaded {type_name} in {elapsed:.3f}s")


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
        bp_str = ", ".join(
            f"{k}={v}" for k, v in sorted(var_spec.branch_params.items())
        )
        return f"Variant({inner_name}, {bp_str})"
    if isinstance(var_spec, AcrossVariants):
        return f"AcrossVariants({_input_type_name(var_spec.var_type)})"
    if isinstance(var_spec, ColumnSelection):
        inner_name = _input_type_name(var_spec.var_type)
        return f"ColumnSelection({inner_name}, {var_spec.columns})"
    if isinstance(var_spec, type):
        return var_spec.__name__
    if hasattr(var_spec, "__name__"):
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
        elif isinstance(var_spec, Fixed) and isinstance(
            var_spec.var_type, ColumnSelection
        ):
            inner = var_spec.var_type
            dummy = pd.DataFrame(columns=inner.columns or [])
            dummy_cs = _scifor.ColumnSelection(
                dummy, inner.columns, iterate=inner.iterate
            )
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

    var_name = (
        var_type.__name__ if isinstance(var_type, type) else type(var_type).__name__
    )
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
        if hasattr(var_type, "view_name"):
            return var_type.view_name()
        return var_name

    dtype_meta = json.loads(row[0])
    mode = dtype_meta.get("mode", "single_column")

    if mode == "single_column":
        # Single-column variables always have exactly one data column
        col_names = list(dtype_meta.get("columns", {}).keys())
        if col_names:
            return col_names[0]
        if hasattr(var_type, "view_name"):
            return var_type.view_name()
        return var_name

    if mode == "dataframe":
        # DataFrame variables: subtract schema keys from df_columns
        df_columns = dtype_meta.get(
            "df_columns", list(dtype_meta.get("columns", {}).keys())
        )
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
    if hasattr(var_type, "view_name"):
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

    # AcrossVariants: a pooling MARKER, not a load-time filter — loading is
    # identical to the bare input (all variants load). Its effect happens in
    # foreach Step 12 (skip the aggregation auto-split, attach branch_param
    # columns), keyed off the original ``inputs`` spec, so here we just unwrap.
    if isinstance(var_spec, AcrossVariants):
        return _load_input(
            var_spec.var_type, db, where, branch_params_filter=branch_params_filter
        )

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
            f"[Variant] {var_spec.__name__}: injecting branch_params_filter={merged}"
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
        _schema_keys = set(
            getattr(_merge_db, "dataset_schema_keys", [])
            if _merge_db is not None
            else []
        )

        if where is not None:
            merge_effective_ids = _compute_merge_effective_ids(_merge_db, var_spec)
            _check_merge_filter_coverage(_merge_db, where, merge_effective_ids)
            # Variable-level portion of the filter, shared by every constituent.
            # Carrying it lets the constituent loader semantically select the single
            # computed variant the filter describes (by its consumed input schema_id
            # set) instead of returning every variant that shares the same schema keys.
            merge_var_filter = _merge_constituent_variable_filter(where)
            Log.debug(
                f"[Merge] {var_spec.__name__}: variant filter={merge_var_filter!r}"
            )

        for sub_spec in var_spec.var_specs:
            if where is not None:
                cls = _get_loadable_class_from_spec(sub_spec)
                matching_ids = where.resolve(
                    _merge_db,
                    cls,
                    cls.table_name(),
                    validate_coverage=False,  # coverage validated once above
                )
                constituent_where = _PreresolvedFilter(
                    matching_ids, variable_filter=merge_var_filter
                )
            else:
                constituent_where = None
            # Per-constituent Variant injects its own branch_params_filter inside
            # this recursion; the inherited filter (normally None — Variant(Merge)
            # is rejected at construction) is threaded for safety.
            loaded = _load_input(
                sub_spec,
                db,
                where=constituent_where,
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
                drop_cols = [
                    c for c in loaded.columns if c in _SCIDB_META or c.startswith("__")
                ]
                all_null_sk = [
                    c
                    for c in loaded.columns
                    if c in _schema_keys and loaded[c].isna().all()
                ]
                drop_cols = list(dict.fromkeys(drop_cols + all_null_sk))
                if drop_cols:
                    loaded = loaded.drop(columns=drop_cols)
            elif hasattr(loaded, "data") and isinstance(loaded.data, pd.DataFrame):
                # _scifor.Fixed wrapping a DataFrame
                drop_cols = [
                    c
                    for c in loaded.data.columns
                    if c in _SCIDB_META or c.startswith("__")
                ]
                all_null_sk = [
                    c
                    for c in loaded.data.columns
                    if c in _schema_keys and loaded.data[c].isna().all()
                ]
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
            var_spec.var_type,
            db,
            where,
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
                k: _schema_str(v) if k in _sk else v for k, v in fixed_meta.items()
            }
        return _scifor.Fixed(inner_loaded, **fixed_meta)

    # ColumnSelection: load inner var_type if possible, else per-combo
    if isinstance(var_spec, ColumnSelection):
        if hasattr(var_spec.var_type, "load"):
            loaded_df = _load_var_type_as_spread(
                var_spec.var_type,
                db,
                where,
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
    if isinstance(var_spec, type) or hasattr(var_spec, "load"):
        if hasattr(var_spec, "load"):
            _check_db = db
            if _check_db is None:
                try:
                    from scidb.database import get_database

                    _check_db = get_database()
                except Exception:
                    pass
            if _check_db is not None and hasattr(_check_db, "load_all_as_df"):
                return _load_var_type_as_spread(
                    var_spec,
                    db,
                    where,
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
        if not hasattr(value, "fixed_metadata"):
            continue

        # Unwrap to get inner variable type
        inner = value.var_type if hasattr(value, "var_type") else value

        # Unwrap ColumnSelection if present
        if hasattr(inner, "var_type"):
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
    from .filters import (
        _expand_coarse_to_fine_schema_ids,
        _get_all_schema_ids_for_variable,
    )

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
            expanded = _expand_coarse_to_fine_schema_ids(
                db, schema_ids, fine_table_name
            )
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
        ColumnFilter,
        CompoundFilter,
        InFilter,
        NotFilter,
        VariableFilter,
        _get_all_schema_ids_for_variable,
        _validate_filter_coverage,
    )

    if where is None or not merge_effective_ids:
        return

    if isinstance(where, (VariableFilter, ColumnFilter, InFilter)):
        filter_table_name = where.variable_class.table_name()
        filter_ids = _get_all_schema_ids_for_variable(db, filter_table_name)
        filter_level_idx = _get_schema_level_idx(db, filter_ids)
        target_level_idx = _get_schema_level_idx(db, merge_effective_ids)

        _validate_filter_coverage(
            db,
            where.variable_class,
            None,
            filter_table_name,
            None,
            filter_level_idx,
            target_level_idx,
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
        if cls is not None and not hasattr(cls, "load"):
            return True
    return False


def _get_loadable_class_from_spec(spec: Any) -> Any:
    """Extract the innermost loadable class from a spec (class, Variant, AcrossVariants, Fixed, ColumnSelection)."""
    if isinstance(spec, AcrossVariants):
        spec = spec.var_type
    if isinstance(spec, Variant):
        spec = spec.var_type
    if isinstance(spec, Fixed):
        spec = spec.var_type
    if isinstance(spec, Variant):
        spec = spec.var_type
    if isinstance(spec, ColumnSelection):
        spec = spec.var_type
    if isinstance(spec, type) or hasattr(spec, "load"):
        return spec
    return None


def _make_plot_wrapper(fn: Any, path_param: str) -> Any:
    """Wrap a plotting (``plot_``) function so it saves its Figure and returns a path.

    The wrapped function receives the same kwargs as ``fn`` — including the
    PathOutput-resolved destination under ``path_param`` (scifor resolves
    PathOutput per combo before calling). It calls ``fn``; if the return value
    is a matplotlib Figure, it is saved to that path and closed (to bound memory
    across many combos), and the path string is returned. If ``fn`` already
    returns a str/Path (it saved the figure itself), that is passed through.

    ``functools.wraps`` preserves the original name, signature, and
    ``__wrapped__`` so combo-metadata injection and function hashing
    (skip_computed / lineage) all resolve to the user's function.
    """
    import functools

    @functools.wraps(fn)
    def wrapped(**kwargs):
        result = fn(**kwargs)
        path = kwargs.get(path_param)
        # Already a path-like return: the function saved it itself.
        if isinstance(result, (str, _Path)):
            return str(result)
        # Treat as a matplotlib Figure (duck-typed: has savefig).
        if hasattr(result, "savefig"):
            if path is None:
                raise ValueError(
                    f"Plotting function '{getattr(fn, '__name__', 'plot_fn')}' "
                    f"returned a Figure but no path was resolved for input "
                    f"'{path_param}'."
                )
            result.savefig(str(path))
            try:
                import matplotlib.pyplot as _plt

                _plt.close(result)
            except Exception:
                pass  # closing is best-effort memory hygiene
            return str(path)
        raise TypeError(
            f"Plotting function '{getattr(fn, '__name__', 'plot_fn')}' must return "
            f"a matplotlib Figure or a path; got {type(result).__name__}."
        )

    return wrapped


def _endpoint_kind(fn_name: str) -> "str | None":
    """Endpoint detection only — "plot" | "stat" | None by name prefix.

    Side-effect-free subset of :func:`_endpoint_policy` for callers that
    need classification without the contract checks (Pipeline.endpoints()).
    """
    return (
        "plot"
        if fn_name.startswith("plot_")
        else "stat"
        if fn_name.startswith("stat_")
        else None
    )


def _endpoint_policy(fn_name: str, inputs: dict, finalized: bool, as_table):
    """Endpoint (plot_/stat_) policy shared by scidb.for_each AND the MATLAB
    bridge's for_each_prepare — one source of truth for detection, the
    plot-requires-PathOutput contract, the stat_ as_table default, draft
    save-suppression, and the finalized warnings. Callers do their own
    language-specific fn wrapping.

    Returns ``(endpoint_kind, path_param, as_table, save_suppressed)`` where
    endpoint_kind is "plot" | "stat" | None and path_param names the (first)
    PathOutput input, if any.
    """
    from scifor import PathOutput

    endpoint_kind = _endpoint_kind(fn_name)
    path_param = None
    if endpoint_kind is not None:
        path_param = next(
            (name for name, v in inputs.items() if isinstance(v, PathOutput)), None
        )
    if endpoint_kind == "plot":
        if path_param is None:
            raise ValueError(
                f"Plotting function '{fn_name}' (plot_ prefix) requires a "
                f"PathOutput input naming where to save the figure, e.g. "
                f"inputs={{..., 'filename': PathOutput('plots/{{subject}}.png')}}."
            )
        Log.info(
            f"'{fn_name}' detected as plotting function; "
            f"figure saved to PathOutput input '{path_param}'"
            + (", path stored as record" if finalized else " (draft: not recorded)")
        )
    elif endpoint_kind == "stat":
        # Statistics run on the long-format table: group/repeated-measures
        # columns (the schema keys) must reach the function — exactly
        # csv-stats' input contract. Without as_table, a single-data-column
        # aggregate is delivered as a bare ndarray with the schema columns
        # stripped. Default it ON for stat_ functions; an explicit user
        # as_table (including False) is respected.
        if as_table is None:
            as_table = True
            Log.debug(
                "as_table defaulted to True for stat_ function "
                "(schema columns delivered for grouping)"
            )
        Log.info(
            f"'{fn_name}' detected as statistics function; "
            + (
                "result JSON stored as record"
                if finalized
                else "draft: result printed, not recorded"
            )
            + (
                f"; PathOutput input '{path_param}'"
                + (" resolved normally" if finalized else " resolved to None")
                if path_param
                else ""
            )
        )

    save_suppressed = endpoint_kind is not None and not finalized
    if save_suppressed:
        # DRAFT mode (D3): suppress the entire save phase — no records, no
        # lineage, no graph. The in-memory result table is still returned.
        # Recording later requires a re-run with finalized=True (drafts leave
        # no record to promote; endpoints are cheap to re-run by construction).
        _draft_msg = (
            f"[draft] {fn_name}: finalized=False — "
            f"{'figures rendered' if endpoint_kind == 'plot' else 'results printed'} "
            f"but NOT recorded. Pass finalized=True to save with lineage."
        )
        Log.info(_draft_msg)
    elif finalized and endpoint_kind is None:
        _msg = (
            f"finalized=True ignored for '{fn_name}': the flag "
            f"only applies to endpoint functions (plot_/stat_ prefixes); "
            f"processing functions always record."
        )
        warnings.warn(_msg, UserWarning, stacklevel=2)
        Log.warn(_msg)

    return endpoint_kind, path_param, as_table, save_suppressed


def _jsonify_stat(obj: Any) -> Any:
    """Recursively convert a stat-result structure to JSON-native types.

    numpy scalars and arrays convert via ``tolist()`` (same recipe as
    csv-stats' ``convert_types``); dict keys are stringified. Anything still
    non-serializable is caught by ``json.dumps(default=str)`` at the caller.
    """
    if isinstance(obj, dict):
        return {str(k): _jsonify_stat(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonify_stat(v) for v in obj]
    tolist = getattr(obj, "tolist", None)
    if callable(tolist):
        try:
            return _jsonify_stat(tolist())
        except Exception:
            return str(obj)
    return obj


def _make_stat_wrapper(fn: Any, path_param: "str | None", finalized: bool) -> Any:
    """Wrap a statistics (``stat_``) function so its result dict becomes a
    canonical JSON string (the stored record data in record mode).

    Contract (see docs/claude/endpoints-viz-and-stats-design.md, D3/D5):

    - ``fn`` must return a **dict** (csv-stats' native return) or a ready
      JSON **string**; anything else raises TypeError.
    - The top-level ``"date"`` key is STRIPPED: csv-stats stamps a wall-clock
      timestamp inside every result, which would make identical reruns store
      different bytes. The database's own save timestamp is the time
      authority.
    - Draft (``finalized=False``): any PathOutput input is resolved to None
      before calling ``fn`` — handing it straight to csv-stats'
      ``filename=None`` disables the PDF side effect — and the result is
      pretty-printed for interactive exploration.
    - Record (``finalized=True``): the PathOutput path (if any) passes
      through for the fn's report writer, and is embedded as
      ``"report_path"`` in the stored JSON so the artifact is discoverable
      from the record.

    ``functools.wraps`` preserves the original name, signature, and
    ``__wrapped__`` so combo-metadata injection and function hashing
    (skip_computed / lineage) all resolve to the user's function.
    """
    import functools

    @functools.wraps(fn)
    def wrapped(**kwargs):
        if path_param is not None and not finalized:
            kwargs[path_param] = None
        result = fn(**kwargs)

        report_path = (
            str(kwargs[path_param])
            if finalized
            and path_param is not None
            and kwargs.get(path_param) is not None
            else None
        )
        payload = normalize_stat_payload(
            result, report_path, finalized, fn_name=getattr(fn, "__name__", "stat_fn")
        )
        if not finalized:
            pretty = json.dumps(json.loads(payload), indent=2, sort_keys=True)
            print(f"[stat draft] {getattr(fn, '__name__', 'stat_fn')}:\n{pretty}")
        return payload

    return wrapped


def normalize_stat_payload(
    result: Any, report_path: "str | None", finalized: bool, fn_name: str = "stat_fn"
) -> str:
    """Canonicalize a stat_ result into the stored JSON payload string.

    Shared by the Python stat_ wrapper and the MATLAB bridge
    (``scimatlab.bridge.normalize_stat_result``) so both paths store
    byte-identical payloads for the same result — skip_computed's content
    identity and reproducibility depend on this living in ONE place (MATLAB's
    ``jsonencode`` differs from ``json.dumps`` in key order and float
    formatting, so MATLAB results are re-canonicalized here).

    Contract: ``result`` is a dict or a JSON string (anything else raises
    TypeError); numpy values are converted; the top-level wall-clock ``date``
    key is STRIPPED (the DB save timestamp is the time authority);
    ``report_path`` (record mode only) is embedded for artifact discovery.
    """
    if isinstance(result, str):
        try:
            parsed = json.loads(result)
        except (TypeError, ValueError) as exc:
            raise TypeError(
                f"Statistics function '{fn_name}' "
                f"returned a string that is not valid JSON: {exc}"
            ) from exc
    elif isinstance(result, dict):
        parsed = result
    else:
        raise TypeError(
            f"Statistics function '{fn_name}' must "
            f"return a dict (e.g. a csv-stats result) or a JSON string; got "
            f"{type(result).__name__}."
        )

    parsed = _jsonify_stat(parsed)
    if isinstance(parsed, dict):
        parsed.pop("date", None)
        if finalized and report_path:
            parsed["report_path"] = str(report_path)

    return json.dumps(parsed, sort_keys=True, default=str)


# ---------------------------------------------------------------------------
# Endpoint artifact provenance stamping (D4)
# ---------------------------------------------------------------------------


def _endpoint_artifact_path(
    endpoint_kind: "str | None", data_value: Any
) -> "str | None":
    """The artifact file a result row points at, or None.

    plot_: the output value IS the path string. stat_: the output value is the
    result JSON; its ``report_path`` (present only in record mode with a
    PathOutput) names the PDF report. Drafts of stat_ resolve PathOutput to
    None, so they yield no path — nothing to stamp.
    """
    if endpoint_kind == "plot":
        return data_value if isinstance(data_value, str) and data_value else None
    if endpoint_kind == "stat" and isinstance(data_value, str):
        try:
            parsed = json.loads(data_value)
        except (ValueError, TypeError):
            return None
        rp = parsed.get("report_path") if isinstance(parsed, dict) else None
        return rp if isinstance(rp, str) and rp else None
    return None


def _stamp_db_name(db: Any) -> "str | None":
    """Basename of the active database file for the stamp blob."""
    if db is None:
        try:
            from .database import get_database

            db = get_database()
        except Exception:
            return None
    p = getattr(db, "dataset_db_path", None)
    return _Path(p).name if p is not None else None


def _collapse_upstream_param(key: str, param_names: "list[str]") -> str:
    """Map an ``__upstream`` key back to its input param name.

    Aggregation stores multiple rids per param as indexed keys
    (``__rid_df_0``, ``__rid_df_1``, …); the blob groups them under ``df``.
    """
    k = key[len("__rid_") :] if str(key).startswith("__rid_") else str(key)
    if k in param_names:
        return k
    for p in sorted(param_names, key=len, reverse=True):
        if k.startswith(p + "_") and k[len(p) + 1 :].isdigit():
            return p
    return k


def _build_stamp_blob(
    *, fn_name: str, inputs_map: dict, schema: dict, db: Any, record_id: "str | None"
) -> dict:
    """The provenance blob embedded in endpoint artifacts (D4).

    ``record_id`` is the primary key (the bipartite graph reaches everything
    else from it); the rest is human-readable redundancy that survives DB
    loss. Drafts carry the FULL blob with ``draft: true`` in place of the
    record_id — a draft figure is fully traceable to its exact input records.
    """
    blob = {
        "scidb_stamp": 1,
        "function": fn_name,
        "inputs": inputs_map,
        "schema": schema,
        "database": _stamp_db_name(db),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if record_id is not None:
        blob["record_id"] = str(record_id)
    else:
        blob["draft"] = True
    return blob


def _stamp_inputs_from_meta(meta: dict, param_names: "list[str]") -> dict:
    """Consumed input rids per param, from save metadata (record mode)."""
    inputs_map: dict = {}
    gvb = meta.get("__graph_var_bindings")
    if gvb:
        for entry in gvb:
            param, rid = entry[0], entry[1]
            if rid is not None:
                inputs_map.setdefault(str(param), []).append(str(rid))
        return inputs_map
    upstream = meta.get("__upstream") or {}
    if isinstance(upstream, str):
        try:
            upstream = json.loads(upstream)
        except (ValueError, TypeError):
            upstream = {}
    for key, rid in upstream.items():
        if rid is None:
            continue
        inputs_map.setdefault(_collapse_upstream_param(key, param_names), []).append(
            str(rid)
        )
    return inputs_map


def _stamp_draft_endpoint_artifacts(
    endpoint_kind: str, result_tbl, state: "_ForEachState", db: Any
) -> None:
    """Draft-mode stamping pass: the save phase is suppressed, but draft
    artifacts get the SAME blob a finalized run would embed (decided
    2026-07-06), with ``draft: true`` in place of the record_id. Runs from
    ``_for_each_save_resolved``, which executes in both modes.
    """
    import pandas as pd

    from .artifact_stamp import stamp_artifact

    if not state.output_names:
        return
    out_name = state.output_names[0]
    param_names = [rc[len("__rid_") :] for rc in (state.rid_keys or [])]
    schema_keys = list(state.current_schema_keys or [])
    stamped = 0
    for row in result_tbl.to_dict("records"):
        apath = _endpoint_artifact_path(endpoint_kind, row.get(out_name))
        if not apath:
            continue
        inputs_map: dict = {}
        for col, val in row.items():
            if not str(col).startswith("__rid_"):
                continue
            if val is None or (isinstance(val, float) and pd.isna(val)):
                continue
            inputs_map.setdefault(col[len("__rid_") :], []).append(str(val))
        if (
            not inputs_map
            and state.combo_to_rids is not None
            and state.iterated_keys_ordered is not None
        ):
            key = tuple(str(row.get(k, "")) for k in state.iterated_keys_ordered)
            for rid_col, rids in state.combo_to_rids.get(key, {}).items():
                param = _collapse_upstream_param(rid_col, param_names)
                inputs_map[param] = [str(r) for r in rids]
        schema = {
            k: row[k]
            for k in schema_keys
            if k in row
            and row[k] is not None
            and not (isinstance(row[k], float) and pd.isna(row[k]))
        }
        blob = _build_stamp_blob(
            fn_name=state.fn_name,
            inputs_map=inputs_map,
            schema=schema,
            db=db,
            record_id=None,
        )
        stamp_artifact(apath, blob)
        stamped += 1
    if stamped:
        Log.info(
            f"[artifact-stamp] draft: stamped {stamped} artifact(s) "
            f"for {state.fn_name} (full provenance, no record)"
        )


def _iterate_column_selection(spec: Any) -> "ColumnSelection | None":
    """Return the iterate-mode ColumnSelection inside a spec (bare or Fixed), else None."""
    if isinstance(spec, ColumnSelection) and spec.iterate:
        return spec
    if (
        isinstance(spec, Fixed)
        and isinstance(spec.var_type, ColumnSelection)
        and spec.var_type.iterate
    ):
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
        c
        for c in loaded.columns
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
        name: cs
        for name, spec in inputs.items()
        if (cs := _iterate_column_selection(spec)) is not None
    }
    if not iterate_params:
        return inputs

    Log.debug(f"resolving for_columns iteration for input(s) {list(iterate_params)}")

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
            Log.debug(
                f"for_columns: resolved '{name}' to all {len(cols)} column(s): {cols}"
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

    _vt_name = getattr(var_type, "__name__", type(var_type).__name__)
    _t0 = time.perf_counter()

    # Resolve the database instance.
    resolved_db = db
    if resolved_db is None:
        try:
            from scidb.database import get_database

            resolved_db = get_database()
        except Exception:
            pass

    if resolved_db is not None and hasattr(resolved_db, "load_all_as_df"):
        # Fast path: bulk engine with spread layout.
        where_kw = {"where": where} if where is not None else {}
        bp_kw = (
            {"branch_params_filter": branch_params_filter}
            if branch_params_filter
            else {}
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
    if resolved_db is not None and hasattr(resolved_db, "dataset_schema_keys"):
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
        return {
            k: str(v) if k in _schema_keys and v is not None else v
            for k, v in meta.items()
            if not k.startswith("__") and k not in const_keys
        }

    first = loaded[0]
    all_have_data = all(hasattr(v, "data") for v in loaded)

    if all_have_data and isinstance(first.data, pd.DataFrame):
        all_data = []
        all_meta_rows = []
        for var in loaded:
            data_df = var.data
            meta = _stringify_meta(
                dict(var.metadata) if hasattr(var, "metadata") and var.metadata else {}
            )
            meta["__record_id"] = getattr(var, "record_id", None)
            meta["__branch_params"] = json.dumps(
                getattr(var, "branch_params", None) or {}
            )
            nr = len(data_df)
            for _ in range(nr):
                all_meta_rows.append(meta)
            all_data.append(data_df.reset_index(drop=True))

        if all_meta_rows:
            combined_meta_df = pd.DataFrame(all_meta_rows)
            combined_data_df = pd.concat(all_data, ignore_index=True)
            result = pd.concat(
                [
                    combined_meta_df.reset_index(drop=True),
                    combined_data_df.reset_index(drop=True),
                ],
                axis=1,
            )
        else:
            result = pd.DataFrame()
    elif all_have_data:
        view_name = (
            var_type.view_name()
            if hasattr(var_type, "view_name")
            else getattr(var_type, "__name__", type(var_type).__name__)
        )
        all_data = []
        all_meta_rows = []
        for var in loaded:
            # Use _to_dataframe so scalars/arrays/lists expand into proper rows
            # (consistent with PerComboLoaderMerge and the DataFrame branch above)
            part_df = _to_dataframe(var.data, view_name)
            meta = _stringify_meta(
                dict(var.metadata) if hasattr(var, "metadata") and var.metadata else {}
            )
            meta["__record_id"] = getattr(var, "record_id", None)
            meta["__branch_params"] = json.dumps(
                getattr(var, "branch_params", None) or {}
            )
            nr = len(part_df)
            for _ in range(nr):
                all_meta_rows.append(dict(meta))
            all_data.append(part_df.reset_index(drop=True))
        if all_meta_rows:
            combined_meta_df = pd.DataFrame(all_meta_rows)
            combined_data_df = pd.concat(all_data, ignore_index=True)
            result = pd.concat(
                [
                    combined_meta_df.reset_index(drop=True),
                    combined_data_df.reset_index(drop=True),
                ],
                axis=1,
            )
        else:
            result = pd.DataFrame()
    else:
        var_name = getattr(var_type, "__name__", type(var_type).__name__)
        rows = []
        for var in loaded:
            rows.append(
                {
                    var_name: var,
                    "__record_id": getattr(var, "record_id", None),
                    "__branch_params": "{}",
                }
            )
        result = pd.DataFrame(rows)

    Log.info(
        f"[timing] _load_var_type_as_spread({_vt_name}): "
        f"{len(result)} rows (slow fallback) in {time.perf_counter() - _t0:.3f}s"
    )
    return result


# ---------------------------------------------------------------------------
# Per-combo resolution helpers
# ---------------------------------------------------------------------------


def _load_pathinput_checked(
    pi: "PathInput",
    load_kw: dict,
    key_types: dict,
    schema_keys: "list | set",
):
    """Per-combo PathInput load enforcing declared schema-key types.

    - ``"string"``-declared keys are excluded from the numeric-equivalence
      fallback entirely: spelling is identity, so "1" never matches "001".
    - ``"numeric"``-declared keys may resolve freely (their stored identity
      is already canonical; only the filename lookup bridges spellings).
    - An UNDECLARED schema key whose spelling had to be bridged raises
      SchemaKeyTypeError: the dataset has proven the spelling ambiguous, so
      the user must declare the key's type once.  Non-schema keys keep the
      silent fallback (their spelling does not define dataset identity).
    """
    from .exceptions import SchemaKeyTypeError

    key_types = key_types or {}
    string_keys = {k for k, t in key_types.items() if t == "string"}
    eligible = {k for k in load_kw if k not in string_keys}
    path, resolutions = pi.load_with_captures(load_kw, numeric_match=eligible)
    if resolutions:
        numeric_keys = {k for k, t in key_types.items() if t == "numeric"}
        offending = {
            k: spelling
            for k, spelling in resolutions.items()
            if k in set(schema_keys or []) and k not in numeric_keys
        }
        if offending:
            key, spelling = next(iter(offending.items()))
            raise SchemaKeyTypeError(
                f"PathInput resolved {key}={load_kw[key]!r} to '{spelling}' "
                f"on disk (template {pi.path_template!r}) — the spelling of "
                f"schema key '{key}' is ambiguous (zero-padded filenames). "
                f"Declare its type once to fix its identity: "
                f"configure_database(..., schema_key_types={{'{key}': "
                f"'numeric'}}) to treat values as numbers (canonical, no "
                f"leading zeros), or 'string' to make spelling significant "
                f"(exact matches only)."
            )
        Log.debug(f"pathinput resolved spellings (declared numeric): {resolutions}")
    return path


def _resolve_per_combo_loader(
    pcl: "PerComboLoader",
    load_kw: dict,
    key_types: "dict | None" = None,
    schema_keys: "list | None" = None,
) -> Any:
    """Resolve a PerComboLoader per-combo by calling spec.load(**effective_kw)."""
    spec = pcl.spec

    if isinstance(spec, Fixed):
        effective_kw = {**load_kw, **spec.fixed_metadata}
        inner = spec.var_type
        columns = None
        if isinstance(inner, ColumnSelection):
            columns = inner.columns
            inner = inner.var_type
        if isinstance(inner, PathInput):
            return _load_pathinput_checked(
                inner, effective_kw, key_types or {}, schema_keys or []
            )
        lv = inner.load(**effective_kw)
        raw = lv.data if hasattr(lv, "data") else lv
        if columns:
            cls_name = getattr(inner, "__name__", type(inner).__name__)
            raw = _apply_per_combo_col_selection(raw, columns, cls_name)
        return raw

    if isinstance(spec, ColumnSelection):
        lv = spec.var_type.load(**load_kw)
        raw = lv.data if hasattr(lv, "data") else lv
        cls_name = getattr(spec.var_type, "__name__", type(spec.var_type).__name__)
        return _apply_per_combo_col_selection(raw, spec.columns, cls_name)

    if isinstance(spec, PathInput):
        return _load_pathinput_checked(
            spec, load_kw, key_types or {}, schema_keys or []
        )

    # Plain class
    lv = spec.load(**load_kw)
    return lv.data if hasattr(lv, "data") else lv


def _resolve_per_combo_merge(
    pcl_merge: "PerComboLoaderMerge", load_kw: dict
) -> "pd.DataFrame":
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
        cls_name = getattr(actual_spec, "__name__", type(actual_spec).__name__)
        if isinstance(lv, list):
            raise ValueError(
                f"{cls_name}.load() returned multiple results (list), expected exactly 1."
            )
        raw = lv.data if hasattr(lv, "data") else lv

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
    import numpy as np
    import pandas as pd

    if isinstance(data, pd.DataFrame):
        return data.reset_index(drop=True)
    if isinstance(data, np.ndarray):
        if data.ndim == 1:
            return pd.DataFrame({cls_name: data})
        elif data.ndim == 2:
            cols = [f"{cls_name}_{i}" for i in range(data.shape[1])]
            return pd.DataFrame(data, columns=cols)
        else:
            raise ValueError(
                f"Cannot convert {data.ndim}D array from {cls_name} to DataFrame"
            )
    if isinstance(data, (list, tuple)):
        return pd.DataFrame({cls_name: list(data)})
    # Scalar
    return pd.DataFrame({cls_name: [data]})


def _apply_per_combo_col_selection(raw: Any, columns: list, cls_name: str) -> Any:
    """Apply column selection to raw data, returning array (1 col) or DataFrame (multi-col)."""
    df = _to_dataframe(raw, cls_name)
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise KeyError(
            f"Columns {missing} not found in {cls_name}. Available: {list(df.columns)}"
        )
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
    input_selectors: "dict | None" = None,
    generates_file: bool = False,
    endpoint_kind: "str | None" = None,
    stamp_param_names: "list | None" = None,
) -> None:
    """Save results from the result table to output variable types using batch operations.

    This function preserves all the config_keys and branch_params tracking from the
    original implementation while using save_batch for efficiency when saving multiple rows.

    The for_each save path adds config_keys and branch_params tracking on top of the
    direct save, as documented in scidb-identity-and-data-flow.md.
    """
    import pandas as pd

    batch_start_time = time.perf_counter()

    # Get schema keys for dynamic discriminator detection
    schema_keys_set: set = set()
    if db is not None and hasattr(db, "dataset_schema_keys"):
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

    # Input-provenance diagnostic. Each saved row's _invocation_input edges are
    # built ONLY from its __rid_* columns (full iteration), combo_to_rids
    # (aggregation), or lineage_fixed_rids (Fixed). If NONE of these is present,
    # the output records are saved with NO consumed-input edges → broken lineage
    # AND the precondition for the re-run orphan/duplicate cascade (records can't
    # be tied to the input version they consumed). Cheap: inspects columns once.
    _rid_cols_present = [c for c in result_tbl.columns if c.startswith("__rid_")]
    # combo_to_rids may be a non-empty dict of EMPTY rid-maps (aggregation
    # bookkeeping with no actual upstream records) — that still yields no input
    # edges, so check for real rids rather than mere presence.
    _combo_has_rids = bool(combo_to_rids) and any(
        rids
        for rids_by_param in combo_to_rids.values()
        for rids in (rids_by_param.values() if isinstance(rids_by_param, dict) else [])
    )
    Log.debug(
        f"[batch_save] input-provenance sources for {fn_name!r}: "
        f"rid_keys={list(rid_keys or [])}, "
        f"__rid_* cols in result_tbl={_rid_cols_present}, "
        f"combo_to_rids={'has-rids' if _combo_has_rids else ('empty' if combo_to_rids else 'None')}, "
        f"fixed_rids={list((lineage_fixed_rids or {}).keys())}"
    )
    if not _rid_cols_present and not _combo_has_rids and not lineage_fixed_rids:
        Log.warn(
            f"[batch_save] {fn_name!r}: NO variable input-binding source (no __rid_* "
            f"columns in the result table, no upstream rids in combo_to_rids, no "
            f"fixed rids) — saved records will have NO _invocation_input edges. "
            f"EXPECTED when the only inputs are files (PathInput) or constants; a "
            f"BUG if a scidb-variable input was consumed (severs lineage and is the "
            f"precondition for the re-run orphan/duplicate cascade — the __rid_* "
            f"discriminators were likely dropped before save, e.g. distribute "
            f"fan-out or the result round-trip)."
        )

    # ===========================================================================
    # PHASE 1: Collect all (data, metadata) items for batch saving
    # ===========================================================================
    # Structure: {(output_idx, save_path): [(data, metadata), ...]}
    # save_path is one of: 'normal', 'flatten'
    batch_items = {}
    # generates_file outputs: lineage-only (no data row). Collected as
    # (output_obj, output_idx, save_metadata) and written graph-natively below.
    generated_items: list = []

    # Bipartite provenance graph: saved output records awaiting graph insertion
    # (see provenance_save.record_run). Populated as each save path completes.
    graph_records: list = []

    prep_start = time.perf_counter()
    Log.info(f"[batch_save] Preparing {len(result_tbl)} result row(s) for batch save")

    # Convert DataFrame to list of dicts for 10-100x faster iteration than iterrows()
    rows = result_tbl.to_dict("records")
    for _row_idx, row in enumerate(rows):
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
                                    UserWarning,
                                    stacklevel=4,
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
                                UserWarning,
                                stacklevel=4,
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
                    UserWarning,
                    stacklevel=4,
                )
            merged_bp[col] = val

        # Build save metadata: non-__ cols (schema keys etc.) + config_keys + __branch_params
        # Exclude __rid_* and other internal __ columns from version keys.
        save_metadata = {col: row[col] for col in meta_cols if not col.startswith("__")}
        save_metadata.update(config_keys)

        # Unpack constants as direct keys so downstream consumers (e.g. scihist's
        # _save_with_lineage) see them in the metadata dict.  They are also stored
        # as __constants (JSON) in config_keys, so _stringify_meta can strip them
        # when loading back — preventing them from polluting input DataFrames.
        for k, v in direct_constants.items():
            if k not in save_metadata:
                save_metadata[k] = v

        save_metadata["__branch_params"] = merged_bp

        # Build the COMPLETE bipartite input edge set for this row: every
        # consumed input record (variable, Fixed, Variant, Merge constituent)
        # with its ColumnSelection selector. Sourced from all __rid_* columns in
        # the row plus Fixed rids (which may not appear as __rid_* columns), so
        # the graph and skip_computed see the same bindings. Aggregation rows
        # carry no __rid_* columns → leave unset and let record_run fall back to
        # the indexed __upstream it builds below.
        _sel = input_selectors or {}
        _row_bindings: dict = {}
        for _col, _val in row.items():
            if not _col.startswith("__rid_"):
                continue
            if _val is None or (isinstance(_val, float) and pd.isna(_val)):
                continue
            _param = _col[len("__rid_") :]
            _row_bindings[_param] = str(_val)
        if lineage_fixed_rids:
            for _k, _v in lineage_fixed_rids.items():
                if _v is None:
                    continue
                _param = _k[len("__rid_") :] if _k.startswith("__rid_") else _k
                _row_bindings.setdefault(_param, str(_v))
        if _row_bindings:
            save_metadata["__graph_var_bindings"] = [
                (p, r, _sel.get(p)) for p, r in _row_bindings.items()
            ]

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
                    if rid_val is not None and not (
                        isinstance(rid_val, float) and pd.isna(rid_val)
                    ):
                        upstream[rid_col] = rid_val
            if upstream:
                save_metadata["__upstream"] = upstream

        for output_idx, (output_obj, output_name) in enumerate(
            zip(outputs, output_names, strict=False)
        ):
            if output_name not in row:
                # Flatten/distribute mode: fn returned a DataFrame whose columns are
                # spread directly in result_tbl (scifor all_dataframes flatten mode).
                # Build a 1-row DataFrame from non-schema, non-__ data columns.
                data_cols = [
                    c
                    for c in meta_cols
                    if not c.startswith("__") and c not in schema_keys_set
                ]
                if not data_cols:
                    continue
                output_value = pd.DataFrame({c: [row[c]] for c in data_cols})
                save_meta_for_output = {
                    k: v for k, v in save_metadata.items() if k not in set(data_cols)
                }

                # Collect for batch save - need deep copy to avoid shared dict references
                key = (output_idx, "flatten")
                if key not in batch_items:
                    batch_items[key] = []
                # Deep copy metadata to avoid sharing __branch_params dict across rows
                meta_copy = dict(save_meta_for_output)
                if "__branch_params" in meta_copy:
                    meta_copy["__branch_params"] = dict(meta_copy["__branch_params"])
                if "__upstream" in meta_copy and isinstance(
                    meta_copy["__upstream"], dict
                ):
                    meta_copy["__upstream"] = dict(meta_copy["__upstream"])
                batch_items[key].append((output_value, meta_copy))
                continue

            output_value = row[output_name]

            # generates_file output: side-effect function (writes a file, returns
            # no storable data). Save lineage-only — graph + metadata, no data
            # row — keyed generated:{invocation_id}. The function's return value
            # is intentionally discarded.
            if generates_file:
                gen_meta = dict(save_metadata)
                if "__branch_params" in gen_meta:
                    gen_meta["__branch_params"] = dict(gen_meta["__branch_params"])
                if "__upstream" in gen_meta and isinstance(
                    gen_meta["__upstream"], dict
                ):
                    gen_meta["__upstream"] = dict(gen_meta["__upstream"])
                generated_items.append((output_obj, output_idx, gen_meta))
                continue

            # Normal save path - collect for batch save - need deep copy to avoid shared dict references
            key = (output_idx, "normal")
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
    Log.info(
        f"[batch_save] Preparation complete in {prep_elapsed:.3f}s: "
        f"{len(batch_items)} batch group(s), {len(generated_items)} generates_file item(s)"
    )

    # ===========================================================================
    # PHASE 2: Execute batch saves
    # ===========================================================================
    time.perf_counter()
    total_saved = 0

    for (output_idx, save_path), items in batch_items.items():
        output_obj = outputs[output_idx]

        if len(items) == 0:
            continue

        Log.info(
            f"[batch_save] Saving {len(items)} record(s) for {_output_name(output_obj)} ({save_path} path)"
        )

        try:
            save_t0 = time.perf_counter()

            # Use save_batch for efficiency
            if db is not None:
                record_ids = db.save_batch(
                    type(output_obj)
                    if not isinstance(output_obj, type)
                    else output_obj,
                    items,
                    profile=False,
                )
            else:
                from .database import get_database

                _db = get_database()
                record_ids = _db.save_batch(
                    type(output_obj)
                    if not isinstance(output_obj, type)
                    else output_obj,
                    items,
                    profile=False,
                )

            save_elapsed = time.perf_counter() - save_t0
            # save_batch returns None in the slot of any record it skipped
            # (schema-incompatible); count only the records actually persisted.
            _n_saved = sum(1 for _r in record_ids if isinstance(_r, str))
            _n_skipped = len(items) - _n_saved
            total_saved += _n_saved
            if _n_skipped:
                _skip_msg = (
                    f"[batch_save] {_output_name(output_obj)}: {_n_skipped} of "
                    f"{len(items)} record(s) SKIPPED (schema-incompatible, e.g. "
                    f"empty/missing-key results); the rest were saved. See the "
                    f"per-record SKIPPED warning(s) in the log for details."
                )
                Log.warn(_skip_msg)

            # Collect for the bipartite provenance graph. output_idx is the
            # output slot (output_num); items align with record_ids in order.
            _out_cls = (
                type(output_obj) if not isinstance(output_obj, type) else output_obj
            )
            _out_sv = getattr(_out_cls, "schema_version", 1)
            for (_data, _meta), _rid in zip(items, record_ids, strict=False):
                if isinstance(_rid, str):
                    graph_records.append(
                        _GraphRecord(
                            _out_cls.__name__,
                            _out_sv,
                            output_idx,
                            _rid,
                            _meta,
                        )
                    )
                    # Endpoint artifact stamping (D4, record mode): the one
                    # point where the artifact path (in _data), the consumed
                    # rids (in _meta), and the saved record_id all coexist.
                    if endpoint_kind:
                        _apath = _endpoint_artifact_path(endpoint_kind, _data)
                        if _apath:
                            from .artifact_stamp import stamp_artifact

                            _blob = _build_stamp_blob(
                                fn_name=fn_name,
                                inputs_map=_stamp_inputs_from_meta(
                                    _meta, stamp_param_names or []
                                ),
                                schema={
                                    k: v
                                    for k, v in _meta.items()
                                    if k in schema_keys_set
                                    and v is not None
                                    and not str(k).startswith("__")
                                },
                                db=db,
                                record_id=_rid,
                            )
                            stamp_artifact(_apath, _blob)

            # Log summary (first few records)
            for _i, ((data, meta), rid) in enumerate(
                zip(items[:3], record_ids[:3], strict=False)
            ):
                meta_str = ", ".join(
                    f"{k}={v}" for k, v in meta.items() if not k.startswith("__")
                )
                data_desc = _describe_save_data(data)
                rid_short = rid[:12] if isinstance(rid, str) else str(rid)
                suffix = " [flatten]" if save_path == "flatten" else ""
                msg = f"[save] {meta_str}: {_output_name(output_obj)} -> record_id={rid_short} ({data_desc}){suffix}"
                Log.info(msg)

            if len(items) > 3:
                Log.info(f"[save] ... and {len(items) - 3} more record(s)")

            Log.info(
                f"[batch_save] Completed {len(items)} save(s) for {_output_name(output_obj)} in {save_elapsed:.3f}s "
                f"({len(items) / save_elapsed:.1f} records/s)"
            )

        except Exception as e:
            import traceback

            Log.error(
                f"[batch_save] Failed to save batch for "
                f"{_output_name(output_obj)} ({len(items)} record(s)): "
                f"{type(e).__name__}: {e}"
            )
            # Full traceback pinpoints the failing operation; the per-record
            # cause (if it is one record) is best surfaced by the schema
            # validation in save_batch, which skips bad records individually.
            Log.error("[batch_save] traceback:\n" + traceback.format_exc())
            # NOTE: these are the FIRST rows of the batch for context — NOT
            # necessarily the row that raised. A batch insert fails atomically,
            # so the offending record is not identifiable from the exception
            # alone; rely on the SKIPPED warnings above to find bad records.
            Log.error(
                f"failed to save {_output_name(output_obj)}: {type(e).__name__}: {e}"
            )
            for data, meta in items[:3]:
                meta_str = ", ".join(
                    f"{k}={v}" for k, v in meta.items() if not k.startswith("__")
                )
                Log.error(
                    f"[error] (first batch rows, not necessarily the "
                    f"culprit) {meta_str}: {_output_name(output_obj)}"
                )

    # ===========================================================================
    # PHASE 3: generates_file outputs — lineage-only save (graph + metadata, no
    # data row), keyed ``generated:{invocation_id}``. Built entirely from each
    # row's save_metadata bindings; the function's return value is discarded.
    # ===========================================================================
    if generated_items:
        from datetime import datetime

        from .database import get_user_id
        from .provenance import insert_record_entity
        from .provenance_save import invocation_id_for_meta

        _db = db
        if _db is None:
            from .database import get_database

            _db = get_database()
        _user = get_user_id()
        Log.info(
            f"[batch_save] Saving {len(generated_items)} generates_file item(s) (lineage-only)"
        )
        for output_obj, output_idx, gen_meta in generated_items:
            try:
                cls = output_obj if isinstance(output_obj, type) else type(output_obj)
                out_name = cls.__name__
                sv = getattr(cls, "schema_version", 1)
                generated_id = f"generated:{invocation_id_for_meta(gen_meta)}"
                schema_keys = {
                    k: v for k, v in gen_meta.items() if k in schema_keys_set
                }
                schema_level = _db._infer_schema_level(schema_keys)
                schema_id = (
                    _db._duck._get_or_create_schema_id(schema_level, schema_keys)
                    if schema_level is not None and schema_keys
                    else 0
                )
                ts = datetime.now().isoformat()
                # The generated record's producing invocation (written by record_run
                # in PHASE 4) carries the function identity, so the graph-based
                # skip_computed gate finds it — no version_keys needed.
                _db._save_record_event(
                    record_id=generated_id,
                    timestamp=ts,
                    user_id=_user,
                )
                insert_record_entity(
                    _db._duck,
                    record_id=generated_id,
                    created_at=ts,
                    type_name=out_name,
                    schema_id=schema_id,
                    content_hash=None,
                    schema_version=sv,
                )
                graph_records.append(
                    _GraphRecord(out_name, sv, output_idx, generated_id, gen_meta)
                )
                total_saved += 1
                meta_str = ", ".join(
                    f"{k}={v}" for k, v in gen_meta.items() if not k.startswith("__")
                )
                Log.info(
                    f"[save] {meta_str}: {out_name} -> {generated_id[:20]} [generates_file]"
                )
            except Exception as e:
                Log.error(
                    f"[error] failed generates_file save for {_output_name(output_obj)}: {e}"
                )

    # ===========================================================================
    # PHASE 4: Write the bipartite provenance graph + append-only _run audit.
    #
    # Runs additively alongside the legacy _lineage writes above (Phase 3 of the
    # lineage-simplification migration). Idempotent for the graph; a fresh _run
    # row is appended per execution.
    # ===========================================================================
    if graph_records:
        try:
            from .database import get_user_id
            from .provenance_save import record_run

            active_db = db
            if active_db is None:
                from .database import get_database

                active_db = get_database()
            where_clause = config_keys.get("__where")
            run_id = record_run(
                active_db,
                graph_records,
                function_name=fn_name,
                where_clause=where_clause,
                user_id=get_user_id(),
            )
            Log.info(
                f"[provenance] recorded run_id={run_id} for {len(graph_records)} "
                f"record(s) of fn={fn_name}"
            )
        except Exception as e:
            # Provenance graph is additive during migration — never fail the save.
            Log.error(f"[provenance] record_run failed for fn={fn_name}: {e}")

    # ===========================================================================
    # Summary
    # ===========================================================================
    batch_total_elapsed = time.perf_counter() - batch_start_time
    Log.info(
        f"[batch_save] Total: saved {total_saved} record(s) in {batch_total_elapsed:.3f}s "
        f"({total_saved / batch_total_elapsed:.1f} records/s)"
    )


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
    return isinstance(
        var_spec,
        (type, Fixed, Variant, AcrossVariants, ColumnSelection, Merge, PathInput),
    ) or hasattr(var_spec, "load")


def _get_schema_keys(db: Any | None) -> set:
    """Return the set of dataset_schema_keys from db or the global database."""
    if db is not None and hasattr(db, "dataset_schema_keys"):
        return set(db.dataset_schema_keys)
    try:
        from .database import get_database

        _db = get_database()
        if hasattr(_db, "dataset_schema_keys"):
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
    import numpy as np
    import pandas as pd

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
    if hasattr(output_obj, "view_name"):
        return output_obj.view_name()
    if isinstance(output_obj, type):
        return output_obj.__name__
    return getattr(output_obj, "__name__", type(output_obj).__name__)


def _propagate_schema(db, distribute: bool) -> None:
    """Propagate dataset_schema_keys from the db into scifor.set_schema()."""
    # If a db was passed explicitly and has schema keys, use them.
    if db is not None and hasattr(db, "dataset_schema_keys"):
        _scifor.set_schema(list(db.dataset_schema_keys))
        return

    # No explicit db: try the global database.
    _global_db = None
    try:
        from scidb.database import get_database

        _global_db = get_database()
    except Exception:
        pass

    if _global_db is not None and hasattr(_global_db, "dataset_schema_keys"):
        _scifor.set_schema(list(_global_db.dataset_schema_keys))
    elif distribute:
        raise ValueError(
            "distribute=True requires access to dataset_schema_keys, "
            "but no database is available. Either pass db= to for_each or "
            "call configure_database() first."
        )
