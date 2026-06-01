# for_columns — Column-Wise Iteration + Reassembly

## Purpose

Iterate a `for_each()` function over each column of a wide-table variable,
feeding one column at a time to the function, and reassemble the per-column
results into a **single** output variable whose data — per schema combo — is a
one-row table with the **same column names** as the source.

This replaces the pattern of one `for_each()` call (and one output variable)
per column.

## Syntax

```python
# All columns (resolved at for_each time)
for_each(col_mean, inputs={"value": GaitData.for_columns()},
         outputs=[DeltaGait], subject=[], session=[])

# Explicit subset
for_each(col_mean, inputs={"value": GaitData.for_columns(["StepLength", "Cadence"])},
         outputs=[DeltaGait], subject=[], session=[])

# Two iterate inputs, zipped by column name (baseline + value)
for_each(mean_change,
         inputs={"baseline": Fixed(GaitData.for_columns(), session="BL"),
                 "value":    GaitData.for_columns()},
         outputs=[DeltaGait], subject=[], session=["FV"])
```

`MyVar.for_columns(cols=None)` returns a `ColumnSelection` with `iterate=True`.
It reuses the existing `ColumnSelection` abstraction — there is **no** new
wrapper type. `MyVar[[...]]` (bracket syntax) remains `iterate=False` and means
"pass the columns as one argument," unchanged.

## Semantics

- The function runs once **per column** per schema combo and must take the
  iterated column as a single-column argument (a numpy array, same as
  `MyVar["col"]`).
- It returns a scalar per column; the per-column scalars become the columns of
  a one-row DataFrame (`1 × N`), saved as the single output variable's data for
  that combo.
- When multiple inputs use `for_columns`, they are **zipped by column name** and
  must resolve to the same column set (else `ValueError`). The same column drives
  every iterate input in lockstep (e.g. `baseline[c]` and `value[c]` together).
- **Column drift is a hard error**: the iterate column set is fixed up front, so
  a combo missing one of those columns raises (it does not silently skip).

## Why not EachOf

`EachOf` was considered but mismatches on two axes:
1. It fans **out** into separately-saved variant records; `for_columns` fans
   **in** to one reassembled record/variable.
2. Its axes are a **cartesian product**; `for_columns` is a single **shared,
   zipped** axis across inputs.

## Why wrap-the-function (not expand-and-remerge)

`for_each` already saves whatever `fn` returns as the output's `.data` per combo,
and scifor's flatten path + scidb's flatten save path (`foreach.py` ~2348)
already persist a wide-DataFrame return to **one** table variable. So the
implementation wraps the per-combo work to loop over columns and return the
assembled `1 × N` row — the existing save path does the rest. No bespoke merge or
`save=False` inner passes.

## Implementation map

| Layer | File | Change |
|-------|------|--------|
| scifor | `scifor/column_selection.py` | `ColumnSelection.iterate` flag |
| scifor | `scifor/foreach.py` | Step 6.5 detect iterate inputs + shared column set; per-combo `_run_column_iteration` (loop fn per column → 1×N DataFrame); `_prepare_iterate_df`, `_unwrap_column_selection`; hard drift error |
| scidb | `scidb/column_selection.py` | `iterate` flag, `columns=None`, `to_key`/`__hash__`/`__name__` |
| scidb | `scidb/variable.py` | `BaseVariable.for_columns()` classmethod |
| scidb | `scidb/foreach.py` | Step 1.5 `_resolve_for_columns` (None→all columns + zip-by-name validation, **before** version keys); pass `iterate` through `_load_input`; `_make_raw_value_wrapper` (lineage); dry-run display |

Resolution happens at **Step 1.5** (top of `for_each`) so the concrete column
set is reflected in version keys (Step 8) and dry-run display (Step 7).

## Lineage

Per the design decision, `for_columns` uses **combined-call lineage**: per-column
results are collapsed to raw values (`_make_raw_value_wrapper`) because per-column
`LineageFcnResult` objects cannot live in the reassembled wide DataFrame. Upstream
provenance for the combined output is still recorded at save time from the input
record_ids. There is no per-column function-hash lineage.

## Caching

`ColumnSelection.to_key()` includes `iterate` and the resolved column list, so
changing the iterated column set (including the `None`→all resolution) creates a
new record; an identical re-run is a cache hit.

## Saving: branch_params contains the reassembled column values

`_save_results` feeds every non-schema, non-`__` column through the
dynamic-discriminator loop, so a for_columns output's reassembled column values
(e.g. `{StepLength: 2.0, Cadence: 20.0}`) land in `branch_params`. **This is
intentional, load-bearing flatten behavior** — do NOT "fix" it by excluding the
data columns. For multi-row flatten outputs (a function returning an N-row
DataFrame), scifor spreads the N rows into N result rows and the per-row data
value is the *only* thing distinguishing them, so each row saves as a distinct
record. Excluding the data columns collapses those N records into one (verified by
`test_variant_pinning.py::test_variant_wraps_column_selection`, which checks a
3-row flatten output round-trips as 3 values summing to 120).

For for_columns specifically the output is a single 1×N row per combo, so the
values-in-branch_params is harmless: there is one deterministic record per schema
combo (no variant ambiguity), and an identical re-run still hits cache.

## Known limitations / future work

- **All-columns resolution loads the variable once** (via `_load_var_type_as_spread`)
  just to read column names, in addition to the loop's own load. Acceptable for
  v1; could be optimized with a metadata-only column query.
- **Output column set is fixed by the first save.** A table variable's physical
  columns are created on first write, so re-running the same output variable with a
  *different* column set fails at save (DuckDB binder error). Use a distinct output
  variable per column set, or keep the set stable. (Changing the *function* over the
  same columns is fine — same physical schema, new version key.)
- **MATLAB parity is not yet implemented.** The MATLAB path runs its own
  `+scifor/for_each.m` loop and a `for_each_prepare` bridge, so parity requires
  porting `_run_column_iteration` + the Step 1.5 resolution there. See task list.
- **scihist + for_columns** (function pre-wrapped as a lineage wrapper) is not
  specially handled in v1.
```
