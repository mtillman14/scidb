"""Pure for_each loop — works with DataFrames only, no I/O."""

import sys
import time
import traceback
from itertools import product
from typing import Any, Callable

from .colname import ColName
from .column_selection import ColumnSelection
from .fixed import Fixed
from .merge import Merge
from .pathoutput import PathOutput
from .schema import get_schema


def for_each(
    fn: Callable,
    inputs: dict[str, Any],
    dry_run: bool = False,
    as_table: list[str] | bool | None = None,
    distribute: bool = False,
    where=None,
    output_names: list[str] | int | None = None,
    share_limits: "dict[str, list[str]] | None" = None,
    _all_combos: list[dict] | None = None,
    _log_fn: "Callable[[str], None] | None" = None,
    _progress_fn: "Callable[[dict], None] | None" = None,
    _cancel_check: "Callable[[], bool] | None" = None,
    **metadata_iterables: list[Any],
) -> "pd.DataFrame | None":
    """
    Execute a function for all combinations of metadata, filtering
    DataFrame inputs per iteration.

    This is a pure loop orchestrator — no I/O, no .load(), no .save().
    All inputs must be DataFrames or constants.

    Args:
        fn: The function to execute.
        inputs: Dict mapping parameter names to DataFrames, Fixed wrappers,
                Merge wrappers, ColumnSelection wrappers, or constant values.
        dry_run: If True, only print what would happen without executing.
        as_table: Controls which DataFrame inputs keep schema key columns.
                  True = all; list of names = selected; False/None = none.
        distribute: If True, split outputs by element/row and expand them
                    into the result table at the schema level below the
                    deepest iterated key.
        where: Optional scifor.ColFilter/CompoundFilter to filter DataFrame
               rows after combo filtering.
        output_names: Names for result columns. list[str] names them;
                      int N auto-names (output_1, ..., output_N);
                      None defaults to ["output"] (single output).
        share_limits: Optional ``{input_name: [schema_keys_to_hold_fixed]}``.
                      For each named input, computes the global numeric
                      ``(min, max)`` extent of that input's data within each
                      group defined by the held-fixed schema keys (spanning all
                      other iterated keys), and injects it as a
                      ``{input_name}_limits`` keyword argument on each call —
                      but only if the function's signature accepts that name
                      (or ``**kwargs``). Used so e.g. every per-trial plot within
                      a subject shares one y-axis range
                      (``share_limits={"signal": ["subject"]}``).
        _all_combos: Pre-built list of metadata dicts; skips itertools.product().
                     Used by DB wrappers that pre-filter schema combinations.
        **metadata_iterables: Iterables of metadata values to combine.

    Returns:
        A pandas DataFrame of results, or None when dry_run=True.
    """
    schema_keys = get_schema()

    # Step 0: Forgive a bare ColName class passed without parentheses.
    # `scifor.ColName` (uninstantiated) can only mean the no-arg deferred form,
    # since there is no DataFrame to attach. Normalize it to ColName() so all
    # downstream isinstance(v, ColName) checks treat it uniformly. We remember
    # which inputs arrived this way to give a clearer error if they turn out to
    # lack a for_columns input to resolve against.
    bare_colname_params = [
        name for name, v in inputs.items()
        if isinstance(v, type) and issubclass(v, ColName)
    ]
    if bare_colname_params:
        inputs = {
            name: (v() if (isinstance(v, type) and issubclass(v, ColName)) else v)
            for name, v in inputs.items()
        }

    # Step 1: Resolve output_names
    if output_names is None:
        resolved_output_names = ["output"]
    elif isinstance(output_names, int):
        resolved_output_names = [f"output_{i+1}" for i in range(output_names)]
    else:
        resolved_output_names = list(output_names)
    n_outputs = len(resolved_output_names)
    if _log_fn:
        _log_fn(f"[scifor] Step 1: resolved {n_outputs} output name(s): {resolved_output_names}")

    # Step 2: Resolve empty lists [] in standalone mode (scan DataFrame inputs)
    if _all_combos is None:
        needs_resolve = [k for k, v in metadata_iterables.items()
                         if isinstance(v, list) and len(v) == 0]
        if needs_resolve:
            if _log_fn:
                _log_fn(f"[scifor] Step 2: resolving empty lists for {needs_resolve} from DataFrame inputs")
            for key in needs_resolve:
                values = _distinct_values_from_inputs(inputs, key)
                if not values:
                    print(f"[warn] no values found for '{key}' in input DataFrames, 0 iterations")
                    if _log_fn:
                        _log_fn(f"[warn] no values found for '{key}' in input DataFrames")
                else:
                    if _log_fn:
                        _log_fn(f"[scifor] resolved '{key}' to {len(values)} values: {values}")
                metadata_iterables[key] = values
        elif _log_fn:
            _log_fn("[scifor] Step 2: no empty lists to resolve (using pre-built combos or explicit values)")

    # Step 3: Validate distribute parameter and resolve target key.
    # Internal discriminator keys (scidb's __rid_* record-id and __vsig_*
    # variant-signature schema extensions) are not experimental LEVELS — they
    # must be invisible to distribute resolution, or an aggregation over a
    # variant-tracked input would see the discriminator as the deepest key
    # and refuse to distribute.
    distribute_key = None
    if distribute:
        if _log_fn:
            _log_fn("[scifor] Step 3: validating distribute parameter")
        real_schema_keys = [
            k for k in schema_keys
            if "__rid_" not in str(k) and "__vsig_" not in str(k)
        ]
        iter_keys_in_schema = [k for k in real_schema_keys if k in metadata_iterables]
        if not iter_keys_in_schema:
            raise ValueError(
                "distribute=True requires at least one metadata_iterable "
                "that is a schema key. Call set_schema() or configure_database() first."
            )
        deepest_iterated = iter_keys_in_schema[-1]
        deepest_idx = real_schema_keys.index(deepest_iterated)

        if deepest_idx + 1 >= len(real_schema_keys):
            raise ValueError(
                f"distribute=True but '{deepest_iterated}' is the deepest schema key. "
                f"There is no lower level to distribute to. "
                f"Schema order: {real_schema_keys}"
            )
        distribute_key = real_schema_keys[deepest_idx + 1]
        if _log_fn:
            _log_fn(f"[scifor] distribute target resolved: '{distribute_key}' (one level below '{deepest_iterated}')")
    elif _log_fn:
        _log_fn("[scifor] Step 3: distribute=False, skipping validation")

    # Step 4: Resolve static ColName(df) wrappers before the data/constant split.
    # Deferred ColName() markers (no DataFrame) are left in place — they resolve
    # per-column inside the for_columns iteration loop (validated at Step 6.5).
    if _log_fn:
        static_count = sum(
            1 for v in inputs.values() if isinstance(v, ColName) and not v.is_deferred
        )
        deferred_count = sum(
            1 for v in inputs.values() if isinstance(v, ColName) and v.is_deferred
        )
        if static_count or deferred_count:
            _log_fn(
                f"[scifor] Step 4: resolving {static_count} static ColName(df) "
                f"wrapper(s); deferring {deferred_count} no-arg ColName() marker(s) "
                f"to for_columns iteration"
            )
        else:
            _log_fn("[scifor] Step 4: no ColName wrappers to resolve")
    inputs = _resolve_colnames(inputs, schema_keys)

    # Step 5: Separate data inputs from constants
    data_inputs = {}
    constant_inputs = {}
    for param_name, var_spec in inputs.items():
        if _is_data_input(var_spec):
            data_inputs[param_name] = var_spec
        else:
            constant_inputs[param_name] = var_spec
    if _log_fn:
        _log_fn(f"[scifor] Step 5: classified {len(data_inputs)} data input(s), {len(constant_inputs)} constant(s)")

    # Check distribute doesn't conflict with a constant input name
    if distribute_key is not None and distribute_key in constant_inputs:
        raise ValueError(
            f"distribute target '{distribute_key}' conflicts with a constant input named '{distribute_key}'."
        )

    # Step 6: Build set of input names to keep as full DataFrames (with schema cols)
    if as_table is True:
        as_table_set = set(data_inputs.keys())
    elif as_table:
        as_table_set = set(as_table)
    else:
        as_table_set = set()
    if _log_fn:
        if as_table_set:
            _log_fn(f"[scifor] Step 6: as_table inputs: {sorted(as_table_set)}")
        else:
            _log_fn("[scifor] Step 6: as_table=False, all data inputs will have schema columns stripped")

    # Step 6.5: Detect iterate-mode ColumnSelection inputs (for_columns).
    # These fan out column-wise: fn runs once per column and the per-column
    # results are reassembled into one wide row per combo. All iterate inputs
    # share a single column axis (zipped by name).
    iterate_params = [
        name for name, spec in data_inputs.items()
        if getattr(_unwrap_column_selection(spec), "iterate", False)
    ]

    # Deferred ColName() markers resolve to the current iterated column, so they
    # require at least one for_columns input. (Static ColName(df) was already
    # resolved to a string at Step 4, so only no-arg markers remain here.)
    deferred_colname_params = [
        name for name, v in constant_inputs.items()
        if isinstance(v, ColName) and v.is_deferred
    ]
    if deferred_colname_params and not iterate_params:
        bare_here = [p for p in deferred_colname_params if p in bare_colname_params]
        if bare_here:
            hint = (
                f"Input(s) {bare_here} were given the bare ColName class "
                f"(no parentheses), which is treated as the deferred ColName() form. "
                f"If you meant the static single-column form, instantiate it with a "
                f"DataFrame: ColName(df). Otherwise add a for_columns input to "
                f"iterate over."
            )
        else:
            hint = "Use ColName(df) for the static single-column form instead."
        raise ValueError(
            f"ColName() with no argument resolves to the current for_columns "
            f"column, so it requires at least one iterate input "
            f"(for_columns() / ColumnSelection(..., iterate=True)). "
            f"Deferred ColName() input(s): {deferred_colname_params}. "
            f"{hint}"
        )

    # A PathOutput template using {ColName} resolves per-column, so it likewise
    # needs an iterate input. (Metadata-only PathOutput templates are fine
    # without one — they resolve per-combo.)
    path_output_column_params = [
        name for name, v in constant_inputs.items()
        if isinstance(v, PathOutput) and v.has_column_token
    ]
    if path_output_column_params and not iterate_params:
        raise ValueError(
            f"PathOutput template uses the {{ColName}} token, which resolves to "
            f"the current for_columns column, so it requires at least one iterate "
            f"input (for_columns() / ColumnSelection(..., iterate=True)). "
            f"PathOutput input(s): {path_output_column_params}."
        )

    iterate_columns: list[str] | None = None
    if iterate_params:
        col_sets = {
            name: _resolve_iterate_columns(data_inputs[name], schema_keys)
            for name in iterate_params
        }
        iterate_columns = col_sets[iterate_params[0]]
        for name in iterate_params[1:]:
            if set(col_sets[name]) != set(iterate_columns):
                raise ValueError(
                    f"for_columns inputs must iterate over the same columns "
                    f"(zipped by name). '{iterate_params[0]}' has "
                    f"{iterate_columns} but '{name}' has {col_sets[name]}."
                )
        if n_outputs != 1:
            raise ValueError(
                f"for_columns supports exactly one output; got {n_outputs} "
                f"({resolved_output_names})."
            )
        if distribute_key is not None:
            raise ValueError("for_columns cannot be combined with distribute=True.")
        if _log_fn:
            _log_fn(
                f"[scifor] Step 6.5: column iteration over {len(iterate_columns)} "
                f"column(s) {iterate_columns} for input(s) {iterate_params}"
            )

    # Step 7: Build combo list
    if _all_combos is not None:
        all_combos = _all_combos
        keys = list(metadata_iterables.keys())
        if _log_fn:
            _log_fn(f"[scifor] Step 7: using {len(all_combos)} pre-built combos (from DB wrapper)")
    else:
        keys = list(metadata_iterables.keys())
        value_lists = [metadata_iterables[k] for k in keys]
        all_combos = [dict(zip(keys, combo)) for combo in product(*value_lists)]
        if _log_fn:
            _log_fn(f"[scifor] Step 7: built {len(all_combos)} combos from Cartesian product of {keys}")

    total = len(all_combos)
    fn_name = getattr(fn, "__name__", repr(fn))

    # Step 7.5: share_limits prepass — compute per-group numeric extents so all
    # combos in a group (e.g. all trials within a subject) can share axis limits.
    shared_limits_map: dict = {}
    if share_limits:
        shared_limits_map = _compute_shared_limits(
            share_limits, data_inputs, schema_keys
        )
        # Param names the function will accept the *_limits kwargs under.
        _limits_accepted = _accepted_param_names(fn)
        if _log_fn:
            _log_fn(
                f"[scifor] Step 7.5: computed shared limits for "
                f"{list(shared_limits_map.keys())} (fn accepts: "
                f"{sorted(_limits_accepted) if _limits_accepted is not None else 'any (**kwargs)'})"
            )
    else:
        _limits_accepted = None

    # Step 8: Print summary banner
    if _log_fn:
        _log_fn(f"[scifor] Step 8: printing summary banner for {total} iterations")
    display_keys = [k for k in keys if not k.startswith("__")]
    meta_summary = ", ".join(
        f"{k}=[{len(metadata_iterables[k])} values]"
        for k in display_keys
    ) if display_keys else "no metadata"
    print(f"\n{'=' * 64}")
    print(f"  for_each({fn_name}) — {total} iteration{'s' if total != 1 else ''}")
    print(f"  {meta_summary}")
    print(f"{'=' * 64}")
    if _log_fn is not None:
        _log_fn("=" * 64)
        _log_fn(f"for_each({fn_name}) — {total} iteration{'s' if total != 1 else ''}")
        _log_fn(meta_summary)
        _log_fn("=" * 64)

    # Detailed config: inputs
    _inputs_str = _format_inputs(inputs)
    print(f"  inputs: {_inputs_str}")
    if _log_fn is not None:
        _log_fn(f"inputs: {_inputs_str}")

    # Detailed config: metadata actual values
    for k in display_keys:
        vals = metadata_iterables[k]
        formatted = ", ".join(repr(v) for v in vals)
        print(f"  {k}=[{formatted}]")
        if _log_fn is not None:
            _log_fn(f"{k}=[{formatted}]")

    # Detailed config: non-default options
    _opts_parts = []
    if dry_run:
        _opts_parts.append("dry_run=True")
    if distribute:
        _opts_parts.append("distribute=True")
    if as_table:
        _opts_parts.append(f"as_table={as_table!r}")
    if where is not None:
        _opts_parts.append(f"where={where!r}")
    if _opts_parts:
        _opts_str = ", ".join(_opts_parts)
        print(f"  options: {_opts_str}")
        if _log_fn is not None:
            _log_fn(f"options: {_opts_str}")

    if dry_run:
        print(f"[dry-run] for_each({fn_name})")
        print(f"[dry-run] {total} iterations over: {keys}")
        print(f"[dry-run] inputs: {_format_inputs(inputs)}")
        if distribute_key is not None:
            print(f"[dry-run] distribute: '{distribute_key}' (split outputs by element/row, 1-based)")
        print()

    completed = 0
    skipped = 0
    collected_rows: list[tuple[dict, tuple]] = []
    was_cancelled = False

    # Step 9: Main loop
    if _log_fn:
        _log_fn(f"[scifor] Step 9: starting main loop over {total} combo(s)")

    for combo_idx, metadata in enumerate(all_combos):
        # Cooperative cancel: check between combos (before any work for this combo).
        if _cancel_check is not None and _cancel_check():
            was_cancelled = True
            cancel_msg = (
                f"[cancelled] for_each({fn_name}) at combo {combo_idx + 1}/{total} "
                f"(completed={completed}, skipped={skipped})"
            )
            print(cancel_msg)
            if _log_fn is not None:
                _log_fn(cancel_msg)
            if _progress_fn is not None:
                _progress_fn({
                    "event": "cancelled",
                    "current": combo_idx + 1,
                    "total": total,
                    "completed": completed,
                    "skipped": skipped,
                })
            break

        metadata_str = ", ".join(f"{k}={v}" for k, v in metadata.items())

        if _progress_fn is not None:
            _progress_fn({
                "event": "combo_start",
                "current": combo_idx + 1,
                "total": total,
                "completed": completed,
                "skipped": skipped,
                "metadata": metadata,
            })

        if dry_run:
            _print_dry_run_iteration(inputs, metadata, constant_inputs, distribute_key)
            completed += 1
            continue

        # Filter/prepare inputs for this combo
        filtered_inputs = {}
        iterate_dfs: dict[str, Any] = {}
        filter_failed = False

        for param_name, var_spec in data_inputs.items():
            try:
                if param_name in iterate_params:
                    # Keep the full per-combo DataFrame; slice per column below.
                    iterate_dfs[param_name] = _prepare_iterate_df(
                        var_spec, metadata, schema_keys, where
                    )
                    continue
                wants_table = param_name in as_table_set
                filtered_inputs[param_name] = _prepare_input(
                    var_spec, metadata, schema_keys, wants_table, where
                )
            except Exception as e:
                msg = f"[skip] {metadata_str}: failed to filter {param_name}: {e}"
                print(msg)
                if _log_fn is not None:
                    _log_fn(msg)
                # DIAG: log filter error to file
                import sys as _sys
                with open("/tmp/scihist_diag.log", "a") as _f:
                    _f.write(f"[DIAG] FILTER ERROR for {param_name}: {e}\n")
                    import traceback as _tb
                    _tb.print_exc(file=_f)
                traceback.print_exc()
                filter_failed = True
                break

        if filter_failed:
            skipped += 1
            if _progress_fn is not None:
                _progress_fn({
                    "event": "combo_skip",
                    "current": combo_idx + 1,
                    "total": total,
                    "completed": completed,
                    "skipped": skipped,
                    "metadata": metadata,
                    "error": "filter failed",
                })
            continue

        # Column drift is a hard error (not a per-combo skip): the iterate
        # column set is fixed up front, so a combo missing one of those
        # columns means the stored data is inconsistent and must be surfaced.
        if iterate_params:
            for name in iterate_params:
                missing = [c for c in iterate_columns if c not in iterate_dfs[name].columns]
                if missing:
                    raise ValueError(
                        f"for_columns column drift: column(s) {missing} missing from "
                        f"input '{name}' for combo {metadata_str}. The iterate column "
                        f"set {iterate_columns} must be present in every combo."
                    )

        # Surface empty per-combo inputs explicitly. After upstream existence
        # filtering an empty input usually means this combo has no backing data
        # for that input — the function is still called (it may handle empties),
        # but the emptiness must never be silent.
        _empty_inputs = [
            name for name, val in
            (list(filtered_inputs.items()) + list(iterate_dfs.items()))
            if _input_is_empty(val)
        ]
        if _empty_inputs:
            empty_msg = (
                f"[empty-combo] {metadata_str}: input(s) "
                f"{', '.join(_empty_inputs)} had 0 rows"
            )
            print(empty_msg)
            if _log_fn is not None:
                _log_fn(empty_msg)

        # Call the function
        all_param_names = (
            list(filtered_inputs.keys())
            + list(iterate_params)
            + list(constant_inputs.keys())
        )
        if iterate_params:
            msg = (f"[run] {metadata_str}: {fn_name} x {len(iterate_columns)} column(s) "
                   f"({', '.join(all_param_names)})")
        else:
            msg = f"[run] {metadata_str}: {fn_name}({', '.join(all_param_names)})"
        print(msg)
        if _log_fn is not None:
            _log_fn(msg)

        # Merge constants into function arguments
        filtered_inputs.update(constant_inputs)

        # Inject shared axis limits for this combo's group (share_limits).
        if shared_limits_map:
            for input_name, (group_keys, limits) in shared_limits_map.items():
                param = f"{input_name}_limits"
                if _limits_accepted is not None and param not in _limits_accepted:
                    continue  # fn signature doesn't accept it and has no **kwargs
                gkey = tuple(str(metadata.get(k, "")) for k in group_keys)
                if gkey in limits:
                    filtered_inputs[param] = limits[gkey]

        try:
            fn_t0 = time.perf_counter()
            if iterate_params:
                result = (_run_column_iteration(
                    fn, filtered_inputs, iterate_dfs, iterate_columns,
                    schema_keys, as_table_set, metadata,
                ),)
            else:
                # PathOutput constants resolve to a finished path from this
                # combo's metadata (no column outside for_columns).
                call_inputs = _resolve_path_outputs(filtered_inputs, metadata, None)
                result = _call_fn(fn, call_inputs, n_outputs)
            fn_elapsed = time.perf_counter() - fn_t0
            done_msg = f"[done] {metadata_str}: {fn_name} completed in {fn_elapsed:.3f}s"
            print(done_msg)
            if _log_fn is not None:
                _log_fn(done_msg)
        except ColumnFunctionError as e:
            # The function failed on specific columns. This is deterministic
            # across combos (a bad column is bad everywhere), so surface it as a
            # hard error naming every offending column — to stderr and the log —
            # rather than silently skipping the whole combo.
            full = f"[error] {metadata_str}: {e}"
            print(full, file=sys.stderr)
            if _log_fn is not None:
                _log_fn(full)
            with open("/tmp/scihist_diag.log", "a") as _f:
                _f.write(f"[DIAG] COLUMN FUNCTION ERROR:\n{full}\n")
            raise
        except ForColumnsError:
            # Structural for_columns errors are deterministic across combos and
            # indicate a return-contract bug — surface immediately, don't skip.
            raise
        except Exception as e:
            msg = f"[skip] {metadata_str}: {fn_name} raised: {e}"
            print(msg)
            if _log_fn is not None:
                _log_fn(msg)
            # DIAG: log function error to file
            with open("/tmp/scihist_diag.log", "a") as _f:
                _f.write(f"[DIAG] FUNCTION ERROR: {e}\n")
                import traceback as _tb
                _tb.print_exc(file=_f)
            traceback.print_exc()
            skipped += 1
            if _progress_fn is not None:
                _progress_fn({
                    "event": "combo_skip",
                    "current": combo_idx + 1,
                    "total": total,
                    "completed": completed,
                    "skipped": skipped,
                    "metadata": metadata,
                    "error": str(e),
                })
            continue

        # Normalize single output to tuple
        if not isinstance(result, tuple):
            result = (result,)

        # Handle distribute: expand result into multiple rows
        if distribute_key is not None:
            for output_value in result:
                try:
                    pieces = _split_for_distribute(output_value)
                except TypeError as e:
                    msg = f"[error] {metadata_str}: cannot distribute: {e}"
                    print(msg)
                    if _log_fn is not None:
                        _log_fn(msg)
                    continue

                for i, piece in enumerate(pieces):
                    dist_metadata = {**metadata, distribute_key: i + 1}
                    collected_rows.append((dist_metadata, (piece,)))
        else:
            collected_rows.append((metadata, result))

        completed += 1
        if _progress_fn is not None:
            _progress_fn({
                "event": "combo_done",
                "current": combo_idx + 1,
                "total": total,
                "completed": completed,
                "skipped": skipped,
                "metadata": metadata,
            })

    # Summary
    print(f"{'─' * 64}")
    if dry_run:
        print(f"  [dry-run] would process {total} iterations")
        print(f"{'=' * 64}\n")
        return None
    else:
        cancelled_suffix = ", cancelled" if was_cancelled else ""
        done_msg = (
            f"for_each({fn_name}) done: completed={completed}, "
            f"skipped={skipped}, total={total}{cancelled_suffix}"
        )
        print(f"  done: completed={completed}, skipped={skipped}, total={total}{cancelled_suffix}")
        print(f"{'=' * 64}\n")
        if _log_fn is not None:
            _log_fn("─" * 64)
            _log_fn(done_msg)
            _log_fn("=" * 64)
        # Step 10: Build output DataFrame
        if _log_fn:
            _log_fn(f"[scifor] Step 10: building output DataFrame from {len(collected_rows)} result row(s)")
        return _results_to_output_dataframe(collected_rows, resolved_output_names, _log_fn)


def _call_fn(fn, kwargs, n_outputs):
    """Call fn with the right number of output captures."""
    return fn(**kwargs)


def _resolve_path_outputs(kwargs: dict, metadata: dict, column: "str | None") -> dict:
    """Return a copy of kwargs with any PathOutput resolved to a finished path.

    Substitutes the combo metadata and (inside for_columns) the current column.
    Non-PathOutput entries pass through untouched.
    """
    if not any(isinstance(v, PathOutput) for v in kwargs.values()):
        return kwargs
    return {
        name: (v.resolve(metadata, column) if isinstance(v, PathOutput) else v)
        for name, v in kwargs.items()
    }


class ForColumnsError(ValueError):
    """A structural error in for_columns reassembly (e.g. a colliding output
    column or a non-collapsible return). These are deterministic across combos
    and indicate a function/return-contract bug, so they propagate as hard
    errors rather than being swallowed as a per-combo ``[skip]``."""


class ColumnFunctionError(ValueError):
    """The for_columns function raised on one or more iterated columns.

    Rather than skipping the whole combo on the first column that fails, the
    column loop runs every column, collects each failure, and raises this once
    with the complete list. A per-column failure is almost always deterministic
    across combos (e.g. a non-numeric column the function can't process), so the
    full list is the actionable signal: it names exactly which columns to drop
    from the selection or fix upstream. The failing ``(column, message)`` pairs
    are available on the ``failures`` attribute."""

    def __init__(self, message: str, failures: "list[tuple[str, str]]"):
        super().__init__(message)
        self.failures = failures


# Separator joining a source column name to a per-column output key when a
# for_columns function returns multiple named values (dict / Series / 1-row
# DataFrame) instead of a single scalar.
FOR_COLUMNS_OUTPUT_SEP = "__"


def _run_column_iteration(
    fn, base_kwargs, iterate_dfs, iterate_columns, schema_keys, as_table_set,
    metadata,
):
    """Run fn once per column and reassemble into a single one-row DataFrame.

    For each column, every iterate input is sliced to that column and passed to
    fn; non-iterate inputs/constants in ``base_kwargs`` pass through unchanged.
    An iterate input named in ``as_table_set`` is sliced to a DataFrame holding
    all schema key columns plus that one column (mirroring the non-iterate
    ColumnSelection as_table behavior at ``_prepare_input``); otherwise it is
    sliced to a bare single-column numpy array (the default).

    The per-column return is expanded into output columns by
    ``_expand_column_result``: a scalar yields one column named after the source
    column; a dict / pandas Series / 1-row DataFrame yields one column per key,
    named ``"<col><sep><key>"``. Different source columns may return different
    numbers (and names) of outputs — the reassembled row is the ordered
    concatenation of every produced column, so a single for_each call supports
    an arbitrary, per-column-varying number of outputs.
    """
    import pandas as pd

    ordered: list[tuple[str, Any]] = []
    # Per-column failures, collected across the whole loop so we can report
    # every offending column at once instead of dying on the first one.
    failures: list[tuple[str, str]] = []
    # Constant inputs that are deferred ColName() markers resolve to the name of
    # the column currently being iterated (recomputed each pass below).
    deferred_colname_params = [
        name for name, v in base_kwargs.items()
        if isinstance(v, ColName) and v.is_deferred
    ]
    # PathOutput constants resolve per-column (current combo metadata + column).
    path_output_params = [
        name for name, v in base_kwargs.items() if isinstance(v, PathOutput)
    ]
    for col in iterate_columns:
        call_kwargs = dict(base_kwargs)
        for name in deferred_colname_params:
            call_kwargs[name] = col
        for name in path_output_params:
            # PathOutput resolves to a finished path using this combo's metadata
            # and the current column ({ColName}).
            call_kwargs[name] = base_kwargs[name].resolve(metadata, col)
        for name, df in iterate_dfs.items():
            if name in as_table_set:
                # Keep real schema keys + the current column, but never surface
                # internal tracking columns (e.g. scidb's ``__rid_*`` record-id
                # discriminators, which DB wrappers add to the schema for per-combo
                # filtering). They've already done their filtering job upstream.
                keep = [
                    c for c in df.columns
                    if c in schema_keys and not c.startswith("__")
                ] + [col]
                call_kwargs[name] = df[keep]
            else:
                call_kwargs[name] = df[col].values
        try:
            res = fn(**call_kwargs)
        except Exception as e:
            # Record and keep going so the raised error names every bad column.
            failures.append((col, f"{type(e).__name__}: {e}"))
            continue
        if isinstance(res, tuple):
            # for_columns is a single (reassembled) output; a tuple return is
            # collapsed to its first element. Return a dict/Series/1-row frame
            # to emit multiple named values per column.
            res = res[0]
        ordered.extend(_expand_column_result(col, res))

    if failures:
        fn_name = getattr(fn, "__name__", repr(fn))
        detail = "\n".join(f"  - {col}: {msg}" for col, msg in failures)
        message = (
            f"for_columns: {fn_name} raised on {len(failures)} of "
            f"{len(iterate_columns)} iterated column(s). These columns could not "
            f"be processed:\n{detail}\n"
            f"Hint: schema keys are already excluded; restrict the selection to "
            f"data columns (e.g. ColumnSelection(df, columns=[...])) or ensure "
            f"these columns are numeric."
        )
        raise ColumnFunctionError(message, failures)

    # Assemble a one-row DataFrame, preserving encounter order and rejecting
    # collisions (two produced names mapping to the same output column).
    data: dict[str, list] = {}
    for out_name, value in ordered:
        if out_name in data:
            raise ForColumnsError(
                f"for_columns produced a duplicate output column '{out_name}'. "
                f"Per-column output keys must be unique after prefixing with the "
                f"source column name (separator '{FOR_COLUMNS_OUTPUT_SEP}')."
            )
        data[out_name] = [value]
    return pd.DataFrame(data)


def _expand_column_result(col: str, res: Any) -> "list[tuple[str, Any]]":
    """Expand one source column's return into (output_name, value) pairs.

    - scalar (or any non-mapping / non-frame value) -> ``[(col, res)]``
    - dict / pandas Series -> one pair per item, named ``"<col><sep><key>"``
    - 1-row pandas DataFrame -> one pair per column, ``"<col><sep><column>"``

    A multi-row DataFrame is rejected: for_columns reassembles to a single row
    per combo, so each source column must collapse to scalar output value(s).
    """
    import pandas as pd

    sep = FOR_COLUMNS_OUTPUT_SEP
    if isinstance(res, dict):
        return [(f"{col}{sep}{k}", v) for k, v in res.items()]
    if isinstance(res, pd.Series):
        return [(f"{col}{sep}{k}", v) for k, v in res.items()]
    if isinstance(res, pd.DataFrame):
        if len(res) != 1:
            raise ForColumnsError(
                f"for_columns function returned a {len(res)}-row DataFrame for "
                f"column '{col}'; expected a single row (one value per output "
                f"key). Return a scalar, dict, pandas Series, or 1-row DataFrame."
            )
        return [(f"{col}{sep}{c}", res[c].iloc[0]) for c in res.columns]
    return [(col, res)]


def _describe_result(val) -> str:
    """Compact description of a function result value."""
    try:
        import pandas as pd
        if isinstance(val, pd.DataFrame):
            return f"DataFrame {val.shape[0]}x{val.shape[1]}"
    except ImportError:
        pass
    try:
        import numpy as np
        if isinstance(val, np.ndarray):
            return f"ndarray shape={val.shape}"
    except ImportError:
        pass
    if isinstance(val, dict):
        return f"dict ({len(val)} keys)"
    if isinstance(val, (list, tuple)):
        return f"{type(val).__name__} len={len(val)}"
    return type(val).__name__


# ---------------------------------------------------------------------------
# Input classification
# ---------------------------------------------------------------------------

def _is_data_input(var_spec: Any) -> bool:
    """Check if an input is a data input (DataFrame, Fixed, Merge, ColumnSelection)."""
    if _is_dataframe(var_spec):
        return True
    if isinstance(var_spec, (Fixed, Merge, ColumnSelection)):
        return True
    return False


def _is_dataframe(value: Any) -> bool:
    """Return True if value is a pandas DataFrame."""
    try:
        import pandas as pd
        return isinstance(value, pd.DataFrame)
    except ImportError:
        return False


def _input_is_empty(value: Any) -> bool:
    """Return True if a prepared per-combo input carries zero rows.

    Used only for logging — a DataFrame with no rows, or a sized container
    (array/list/Series) of length 0. Scalars and unsized values are never
    considered empty.
    """
    if _is_dataframe(value):
        return value.empty
    if value is None:
        return False
    try:
        return len(value) == 0
    except TypeError:
        return False


# ---------------------------------------------------------------------------
# ColName resolution
# ---------------------------------------------------------------------------

def _resolve_colnames(inputs: dict[str, Any], schema_keys: list[str]) -> dict[str, Any]:
    """Replace static ColName(df) wrappers with the resolved column name string.

    For each static ColName(df) in inputs:
    1. Get the inner DataFrame
    2. Compute data_cols = columns not in schema_keys
    3. If exactly 1 data column -> replace with the string name
    4. Otherwise -> raise ValueError

    Deferred (no-arg) ColName() markers are passed through unchanged — they are
    resolved per-column during for_columns iteration (_run_column_iteration).
    """
    resolved = {}
    for param_name, var_spec in inputs.items():
        if isinstance(var_spec, ColName) and var_spec.is_deferred:
            # No-arg ColName() — leave in place; resolved per-column during
            # for_columns iteration (see _run_column_iteration).
            resolved[param_name] = var_spec
        elif isinstance(var_spec, ColName):
            df = var_spec.data
            if not _is_dataframe(df):
                raise TypeError(
                    f"ColName({param_name}) expected a DataFrame, "
                    f"got {type(df).__name__}"
                )
            data_cols = [c for c in df.columns if c not in schema_keys]
            if len(data_cols) == 1:
                resolved[param_name] = data_cols[0]
            elif len(data_cols) == 0:
                raise ValueError(
                    f"ColName({param_name}): DataFrame has no data columns "
                    f"(all columns are schema keys). "
                    f"Columns: {list(df.columns)}, schema keys: {schema_keys}"
                )
            else:
                raise ValueError(
                    f"ColName({param_name}): DataFrame has {len(data_cols)} "
                    f"data columns ({data_cols}), expected exactly 1. "
                    f"Schema keys: {schema_keys}"
                )
        else:
            resolved[param_name] = var_spec
    return resolved


# ---------------------------------------------------------------------------
# DataFrame filtering
# ---------------------------------------------------------------------------

def _is_per_combo_df(df: "pd.DataFrame", schema_keys: list[str]) -> bool:
    """True if df has at least one column that is a schema key."""
    return bool(set(df.columns) & set(schema_keys))


def _accepted_param_names(fn) -> "set[str] | None":
    """Return the set of keyword names ``fn`` accepts, or None if it takes **kwargs.

    None means "inject anything" (the function has a ``**kwargs`` catch-all).
    Falls back to ``__scidb_params__`` (set by scidb/scilineage wrappers) when
    the signature can't be introspected.
    """
    import inspect
    try:
        sig = inspect.signature(fn)
    except (ValueError, TypeError):
        params = getattr(fn, "__scidb_params__", None)
        return set(params) if params is not None else set()
    names = set()
    for p in sig.parameters.values():
        if p.kind == inspect.Parameter.VAR_KEYWORD:
            return None  # **kwargs — accepts any keyword
        if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD,
                      inspect.Parameter.KEYWORD_ONLY):
            names.add(p.name)
    return names


def _numeric_extent(df: "pd.DataFrame") -> "tuple[float, float] | tuple[None, None]":
    """Return (min, max) over all numeric values in df, flattening array cells.

    Handles both scalar-valued cells and ndarray/list-valued cells (timeseries).
    Returns (None, None) when no finite numeric values are present.
    """
    import numpy as np
    lo = None
    hi = None
    for col in df.columns:
        for val in df[col].to_numpy():
            arr = np.asarray(val, dtype="float64").ravel() if not np.isscalar(val) \
                else np.asarray([val], dtype="float64")
            arr = arr[np.isfinite(arr)]
            if arr.size == 0:
                continue
            cmn = float(arr.min())
            cmx = float(arr.max())
            lo = cmn if lo is None else min(lo, cmn)
            hi = cmx if hi is None else max(hi, cmx)
    if lo is None:
        return (None, None)
    return (lo, hi)


def _compute_shared_limits(
    share_limits: dict, data_inputs: dict, schema_keys: list[str]
) -> dict:
    """Compute per-group numeric extents for each input named in share_limits.

    Returns ``{input_name: (group_keys_present, {group_key_tuple: (min, max)})}``
    where ``group_keys_present`` is the subset of the requested held-fixed schema
    keys actually present in the input's DataFrame, and each group spans all rows
    sharing those key values (i.e. across every other iterated key).
    """
    import pandas as pd

    result: dict = {}
    for input_name, group_keys in share_limits.items():
        var_spec = data_inputs.get(input_name)
        if var_spec is None:
            continue
        df, _eff_meta, column_selection = _resolve_data_spec(var_spec, {})
        if not isinstance(df, pd.DataFrame):
            continue
        data_cols = [
            c for c in df.columns
            if c not in schema_keys and not str(c).startswith("__")
        ]
        if column_selection:
            data_cols = [c for c in data_cols if c in column_selection]
        if not data_cols:
            continue

        present_group_keys = [k for k in group_keys if k in df.columns]
        limits: dict = {}
        if present_group_keys:
            for gvals, gdf in df.groupby(present_group_keys, sort=False):
                key = gvals if isinstance(gvals, tuple) else (gvals,)
                gkey = tuple(str(v) for v in key)
                mn, mx = _numeric_extent(gdf[data_cols])
                if mn is not None:
                    limits[gkey] = (mn, mx)
        else:
            mn, mx = _numeric_extent(df[data_cols])
            if mn is not None:
                limits[()] = (mn, mx)
        result[input_name] = (present_group_keys, limits)
    return result


def _filter_df_for_combo(
    df: "pd.DataFrame", metadata: dict, schema_keys: list[str]
) -> "pd.DataFrame":
    """Filter df rows to match combo metadata for schema key columns present in df."""
    import pandas as pd
    mask = pd.Series([True] * len(df), index=df.index)
    for key in schema_keys:
        if key in df.columns and key in metadata:
            col_vals = df[key]
            meta_val = metadata[key]
            mask = mask & (col_vals == meta_val)
    return df[mask].reset_index(drop=True)


def _apply_where_filter(df: "pd.DataFrame", where) -> "pd.DataFrame":
    """Apply a scifor Col filter to a DataFrame."""
    if where is None:
        return df
    mask = where.apply(df)
    return df[mask].reset_index(drop=True)


def _extract_data(
    df: "pd.DataFrame",
    schema_keys: list[str],
    as_table: bool,
) -> Any:
    """Extract data from a filtered DataFrame.

    If as_table: return full DataFrame (real schema columns + data columns, but
    not internal ``__``-prefixed schema columns such as scidb's ``__rid_*``
    record-id discriminators).
    Otherwise: drop schema key columns; if 1 row + 1 data col -> extract scalar.
    """
    if as_table:
        internal = [c for c in df.columns if c in schema_keys and c.startswith("__")]
        return df.drop(columns=internal) if internal else df

    data_cols = [c for c in df.columns if c not in schema_keys]
    if len(df) == 1 and len(data_cols) == 1:
        return df[data_cols[0]].iloc[0]
    if len(data_cols) == 1:
        # Single data column, multiple rows → 2D numpy column vector
        return df[data_cols].reset_index(drop=True).values
    if data_cols and set(data_cols) != set(df.columns):
        return df[data_cols].reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Input preparation per combo
# ---------------------------------------------------------------------------

def _prepare_input(
    var_spec: Any,
    metadata: dict,
    schema_keys: list[str],
    as_table: bool,
    where=None,
) -> Any:
    """Prepare a single data input for the current combo."""
    if isinstance(var_spec, Merge):
        return _prepare_merge(var_spec, metadata, schema_keys, where)

    if isinstance(var_spec, Fixed) and isinstance(var_spec.data, Merge):
        raise TypeError(
            "Fixed cannot wrap a Merge. Use Fixed on individual "
            "constituents inside the Merge instead: "
            "Merge(Fixed(df1, ...), df2)"
        )

    # Resolve the raw DataFrame and effective metadata
    df, effective_metadata, column_selection = _resolve_data_spec(var_spec, metadata)

    excl = _excluded_columns(var_spec)

    if not _is_per_combo_df(df, schema_keys):
        # Constant DataFrame — pass unchanged every iteration
        if column_selection is not None:
            # An empty selection means "all data columns".
            cols = column_selection or _all_data_columns(df, schema_keys)
            cols = _apply_exclusions(cols, excl)
            return _apply_column_selection(df, cols)
        return df

    filtered = _filter_df_for_combo(df, effective_metadata, schema_keys)
    filtered = _apply_where_filter(filtered, where)

    if column_selection is not None:
        # An empty selection means "all data columns".
        cols = column_selection or _all_data_columns(filtered, schema_keys)
        cols = _apply_exclusions(cols, excl)
        if as_table:
            # Keep real schema columns alongside selected data columns, but never
            # surface internal tracking columns (e.g. scidb's ``__rid_*`` record-id
            # discriminators added to the schema for per-combo filtering).
            keep = [
                c for c in filtered.columns
                if c in schema_keys and not c.startswith("__")
            ] + cols
            return filtered[keep]
        return _apply_column_selection(filtered, cols)

    return _extract_data(filtered, schema_keys, as_table)


def _resolve_data_spec(
    var_spec: Any, metadata: dict
) -> tuple["pd.DataFrame", dict, list[str] | None]:
    """Resolve a var_spec into (DataFrame, effective_metadata, column_selection)."""
    column_selection = None

    if isinstance(var_spec, Fixed):
        effective_metadata = {**metadata, **var_spec.fixed_metadata}
        inner = var_spec.data
        if isinstance(inner, ColumnSelection):
            column_selection = inner.columns
            df = inner.data
        else:
            df = inner
    elif isinstance(var_spec, ColumnSelection):
        effective_metadata = metadata
        column_selection = var_spec.columns
        df = var_spec.data
    else:
        # Plain DataFrame
        effective_metadata = metadata
        df = var_spec

    return df, effective_metadata, column_selection


def _unwrap_column_selection(var_spec: Any) -> Any:
    """Return the ColumnSelection inside a spec (bare or Fixed-wrapped), else the spec."""
    if isinstance(var_spec, Fixed) and isinstance(var_spec.data, ColumnSelection):
        return var_spec.data
    return var_spec


def _excluded_columns(var_spec: Any) -> list[str]:
    """Return the ColumnSelection's ``excl_columns`` (bare or Fixed-wrapped)."""
    cs = _unwrap_column_selection(var_spec)
    if isinstance(cs, ColumnSelection):
        return cs.excl_columns
    return []


def _apply_exclusions(cols: list[str], excl: list[str]) -> list[str]:
    """Drop ``excl`` names from ``cols``, preserving order. No-op if ``excl`` empty."""
    if not excl:
        return cols
    excl_set = set(excl)
    return [c for c in cols if c not in excl_set]


def _all_data_columns(df: "pd.DataFrame", schema_keys: list[str]) -> list[str]:
    """Return a DataFrame's data columns: everything that is not a schema key
    or an internal ``__*`` column. Used to expand an empty (all-columns)
    ColumnSelection to a concrete list."""
    return [
        c for c in df.columns
        if c not in schema_keys and not str(c).startswith("__")
    ]


def _resolve_iterate_columns(var_spec: Any, schema_keys: list[str]) -> list[str]:
    """Resolve an iterate-mode ColumnSelection's column list.

    An explicit list is returned as-is; an empty list (the all-columns
    sentinel) is expanded to every data column of the underlying DataFrame.
    Any ``excl_columns`` are removed from whichever list is produced.
    """
    cs = _unwrap_column_selection(var_spec)
    excl = _excluded_columns(var_spec)
    cols = list(cs.columns)
    if cols:
        return _apply_exclusions(cols, excl)
    df = cs.data if isinstance(cs, ColumnSelection) else None
    if df is None or not _is_dataframe(df):
        raise ValueError(
            "for_columns(): cannot resolve all columns — the input is not a "
            "DataFrame-backed ColumnSelection. Pass an explicit column list."
        )
    resolved = _apply_exclusions(_all_data_columns(df, schema_keys), excl)
    if not resolved:
        raise ValueError(
            f"for_columns(): no data columns found to iterate over "
            f"(columns were {list(df.columns)}, schema keys {schema_keys}, "
            f"excluded {excl})."
        )
    return resolved


def _prepare_iterate_df(
    var_spec: Any, metadata: dict, schema_keys: list[str], where=None
) -> "pd.DataFrame":
    """Prepare the per-combo DataFrame for an iterate-mode ColumnSelection.

    Returns the combo-filtered DataFrame retaining the iterate columns so the
    caller can slice one column at a time. Unlike ``_prepare_input`` it does
    not collapse to a single column.
    """
    df, effective_metadata, _column_selection = _resolve_data_spec(var_spec, metadata)
    if not _is_per_combo_df(df, schema_keys):
        return df
    filtered = _filter_df_for_combo(df, effective_metadata, schema_keys)
    return _apply_where_filter(filtered, where)


def _apply_column_selection(df: "pd.DataFrame", columns: list[str]) -> Any:
    """Extract selected columns from a DataFrame."""
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise KeyError(
            f"Column(s) {missing} not found. "
            f"Available columns: {list(df.columns)}"
        )
    if len(columns) == 1:
        return df[columns[0]].values
    return df[columns]


# ---------------------------------------------------------------------------
# Merge handling
# ---------------------------------------------------------------------------

def _prepare_merge(
    merge_spec: Merge,
    metadata: dict,
    schema_keys: list[str],
    where=None,
) -> "pd.DataFrame":
    """Filter each constituent of a Merge and combine into a single DataFrame."""
    import pandas as pd

    parts = []

    for i, spec in enumerate(merge_spec.tables):
        label = f"merge[{i}]"

        df, effective_metadata, column_selection = _resolve_data_spec(spec, metadata)

        if _is_per_combo_df(df, schema_keys):
            filtered = _filter_df_for_combo(df, effective_metadata, schema_keys)
            filtered = _apply_where_filter(filtered, where)
            # Drop schema key columns for merge
            data_cols = [c for c in filtered.columns if c not in schema_keys]
            if data_cols and set(data_cols) != set(filtered.columns):
                part_df = filtered[data_cols].reset_index(drop=True)
            else:
                part_df = filtered.reset_index(drop=True)
        else:
            part_df = df.reset_index(drop=True)

        if column_selection is not None:
            missing = [c for c in column_selection if c not in part_df.columns]
            if missing:
                raise KeyError(
                    f"Column(s) {missing} not found in {label}. "
                    f"Available: {list(part_df.columns)}"
                )
            if len(column_selection) == 1:
                part_df = pd.DataFrame({column_selection[0]: part_df[column_selection[0]]})
            else:
                part_df = part_df[column_selection]

        parts.append(part_df)

    return _merge_parts(parts)


def _merge_parts(parts: list["pd.DataFrame"]) -> "pd.DataFrame":
    """Merge multiple DataFrames column-wise."""
    import pandas as pd

    if not parts:
        raise ValueError("Merge has no constituents.")

    # Check for column name conflicts
    seen_columns: set[str] = set()
    for df in parts:
        for col in df.columns:
            if col in seen_columns:
                raise KeyError(
                    f"Column name conflict in Merge: "
                    f"column '{col}' appears in multiple constituents."
                )
            seen_columns.add(col)

    # Check row count compatibility
    row_counts = [(len(df), df) for df in parts if len(df) > 1]
    if row_counts:
        unique_counts = set(n for n, _ in row_counts)
        if len(unique_counts) > 1:
            detail = ", ".join(str(n) for n, _ in row_counts)
            raise ValueError(
                f"Cannot merge constituents with different row counts: {detail}."
            )
        target_len = row_counts[0][0]
    else:
        target_len = 1

    expanded = []
    for df in parts:
        if len(df) == 1 and target_len > 1:
            df = pd.concat([df] * target_len, ignore_index=True)
        expanded.append(df)

    return pd.concat(expanded, axis=1)


# ---------------------------------------------------------------------------
# Empty-list resolution from DataFrame inputs
# ---------------------------------------------------------------------------

def _distinct_values_from_inputs(inputs: dict, key: str) -> list:
    """Find distinct values for `key` by scanning DataFrame inputs."""
    all_values = set()
    for _param_name, var_spec in inputs.items():
        df = _get_raw_df(var_spec)
        if df is not None and key in df.columns:
            all_values.update(df[key].dropna().unique().tolist())
    if not all_values:
        raise ValueError(
            f"Empty list [] was passed for '{key}', but no input DataFrame has "
            f"that column. Either provide values explicitly or ensure a DataFrame "
            f"input contains a '{key}' column."
        )
    try:
        return sorted(all_values)
    except TypeError:
        return list(all_values)


def _get_raw_df(var_spec: Any) -> "pd.DataFrame | None":
    """Extract the DataFrame from a var_spec, if it contains one."""
    if _is_dataframe(var_spec):
        return var_spec
    if isinstance(var_spec, Fixed) and _is_dataframe(var_spec.data):
        return var_spec.data
    if isinstance(var_spec, ColumnSelection) and _is_dataframe(var_spec.data):
        return var_spec.data
    return None


# ---------------------------------------------------------------------------
# Result collection
# ---------------------------------------------------------------------------

def _results_to_output_dataframe(
    collected_rows: list[tuple[dict, tuple]],
    output_names: list[str],
    _log_fn: "Callable[[str], None] | None" = None,
) -> "pd.DataFrame":
    """Build a combined DataFrame from all for_each results."""
    import pandas as pd

    if _log_fn:
        _log_fn(f"[scifor] _results_to_output_dataframe: processing {len(collected_rows)} row(s)")

    if not collected_rows:
        return pd.DataFrame()

    # Check if all outputs are DataFrames (flatten mode)
    all_dataframes = all(
        isinstance(value, pd.DataFrame)
        for _, result_tuple in collected_rows
        for value in result_tuple
    )

    if all_dataframes:
        if _log_fn:
            _log_fn("[scifor] using flatten mode (all outputs are DataFrames)")
        parts = []
        for metadata, result_tuple in collected_rows:
            combined_data = pd.concat(
                [df.reset_index(drop=True) for df in result_tuple], axis=1
            )
            nr = len(combined_data)
            meta_df = pd.DataFrame({k: [v] * nr for k, v in metadata.items()})
            parts.append(pd.concat(
                [meta_df.reset_index(drop=True), combined_data], axis=1
            ))
        result = pd.concat(parts, ignore_index=True)
        if _log_fn:
            _log_fn(f"[scifor] flatten mode: built DataFrame with {len(result)} row(s), {len(result.columns)} column(s)")
        return result
    else:
        if _log_fn:
            _log_fn("[scifor] using scalar mode (at least one output is not a DataFrame)")
        rows = []
        for metadata, result_tuple in collected_rows:
            row = dict(metadata)
            for name, value in zip(output_names, result_tuple):
                row[name] = value
            rows.append(row)
        result = pd.DataFrame(rows)
        if _log_fn:
            _log_fn(f"[scifor] scalar mode: built DataFrame with {len(result)} row(s), {len(result.columns)} column(s)")
        return result


# ---------------------------------------------------------------------------
# Distribute
# ---------------------------------------------------------------------------

def _split_for_distribute(data: Any) -> list[Any]:
    """Split data into elements for distribute-style expansion."""
    try:
        import pandas as pd
        if isinstance(data, pd.DataFrame):
            return [data.iloc[[i]] for i in range(len(data))]
    except ImportError:
        pass

    try:
        import numpy as np
        if isinstance(data, np.ndarray):
            if data.ndim == 1:
                return [data[i] for i in range(len(data))]
            elif data.ndim == 2:
                return [data[i, :] for i in range(data.shape[0])]
            else:
                raise TypeError(
                    f"distribute does not support numpy arrays with {data.ndim} dimensions. "
                    f"Only 1D (split by element) and 2D (split by row) are supported."
                )
    except ImportError:
        pass

    if isinstance(data, list):
        return list(data)

    raise TypeError(
        f"distribute does not support type {type(data).__name__}. "
        f"Supported types: numpy 1D/2D array, list, pandas DataFrame."
    )


# ---------------------------------------------------------------------------
# Display / dry-run
# ---------------------------------------------------------------------------

def _format_inputs(inputs: dict[str, Any]) -> str:
    """Format inputs dict for display."""
    parts = []
    for name, var_spec in inputs.items():
        if isinstance(var_spec, Merge):
            parts.append(f"{name}: {var_spec.__name__}")
        elif isinstance(var_spec, Fixed):
            fixed_str = ", ".join(f"{k}={v}" for k, v in var_spec.fixed_metadata.items())
            inner = var_spec.data
            if isinstance(inner, ColumnSelection):
                inner_name = inner.__name__
            elif _is_dataframe(inner):
                inner_name = f"DataFrame{list(inner.columns)}"
            else:
                inner_name = repr(inner)
            parts.append(f"{name}: Fixed({inner_name}, {fixed_str})")
        elif isinstance(var_spec, ColumnSelection):
            parts.append(f"{name}: {var_spec.__name__}")
        elif _is_dataframe(var_spec):
            parts.append(f"{name}: DataFrame{list(var_spec.columns)}")
        elif _is_data_input(var_spec):
            parts.append(f"{name}: {repr(var_spec)}")
        else:
            parts.append(f"{name}: {var_spec!r}")
    return "{" + ", ".join(parts) + "}"


def _print_dry_run_iteration(
    inputs: dict[str, Any],
    metadata: dict[str, Any],
    constant_inputs: dict[str, Any],
    distribute: str | None = None,
) -> None:
    """Print what would happen for one iteration in dry-run mode."""
    metadata_str = ", ".join(f"{k}={v}" for k, v in metadata.items())
    print(f"[dry-run] {metadata_str}:")

    for param_name, var_spec in inputs.items():
        if isinstance(var_spec, Merge):
            print(f"  merge {param_name}:")
            for i, sub_spec in enumerate(var_spec.tables):
                _print_constituent_filter(sub_spec, metadata, i)
        elif isinstance(var_spec, Fixed):
            filter_metadata = {**metadata, **var_spec.fixed_metadata}
            inner = var_spec.data
            if isinstance(inner, ColumnSelection):
                col_str = ", ".join(inner.columns)
                print(f"  filter {param_name} with {filter_metadata} -> columns: [{col_str}]")
            elif _is_dataframe(inner):
                print(f"  filter {param_name} = DataFrame with {filter_metadata}")
            else:
                print(f"  filter {param_name} with {filter_metadata}")
        elif isinstance(var_spec, ColumnSelection):
            col_str = ", ".join(var_spec.columns)
            print(f"  filter {param_name} with {metadata} -> columns: [{col_str}]")
        elif _is_dataframe(var_spec):
            print(f"  filter {param_name} = DataFrame with {metadata}")
        elif _is_data_input(var_spec):
            print(f"  filter {param_name} with {metadata}")
        else:
            print(f"  constant {param_name} = {var_spec!r}")

    if distribute is not None:
        print(f"  distribute by '{distribute}' (1-based indexing)")


def _print_constituent_filter(spec: Any, metadata: dict[str, Any], index: int) -> None:
    """Print a single Merge constituent's filter line for dry-run display."""
    if isinstance(spec, Fixed):
        filter_metadata = {**metadata, **spec.fixed_metadata}
        inner = spec.data
        if isinstance(inner, ColumnSelection):
            col_str = ", ".join(inner.columns)
            print(f"    [{index}] filter with {filter_metadata} -> columns: [{col_str}]")
        else:
            print(f"    [{index}] filter with {filter_metadata}")
    elif isinstance(spec, ColumnSelection):
        col_str = ", ".join(spec.columns)
        print(f"    [{index}] filter with {metadata} -> columns: [{col_str}]")
    else:
        print(f"    [{index}] filter with {metadata}")
