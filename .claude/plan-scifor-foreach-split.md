# Plan: Split MATLAB `for_each.m` into standalone + DB layers

## Context

`scifor.for_each()` in MATLAB currently contains the **entire** 2612-line implementation — both standalone features (table inputs, CsvFile, MatFile) and database features (BaseVariable, Thunk, preloading, batch save, parallel mode). This doesn't match the Python architecture where `scifor.for_each()` is a standalone core engine and `scirun.for_each()` is a thin DB wrapper that delegates to it. The goal is to mirror that clean split so `scifor` is a genuinely standalone package.

## Design

### Target architecture

```
scifor.for_each()          — standalone core engine (~1200 lines)
  Duck-typed .load()/.save(), table filtering, CsvFile/MatFile,
  constants, Fixed, Merge, distribute, dry-run, result collection.
  Extension points: _extra_save_metadata, _all_combos

scidb.for_each()           — DB wrapper (~400-500 lines)
  Pre-processing: empty-list resolve, schema propagation,
  ForEachConfig version keys, schema combo filtering.
  Optimizations: preloading via proxy, batch save via proxy, parallel branch.
  Delegates to scifor.for_each() for the core loop.
```

### Key design decision: proxy objects instead of extension-point parameters

In Python, scifor.for_each always calls `.load()` per iteration with no preloading, and `.save()` per iteration with no batching. The MATLAB preloading and batch save are performance optimizations for DB mode only.

Rather than adding `_preloaded` parameters to scifor.for_each, **scidb.for_each will wrap inputs/outputs in proxy objects**:

- **`PreloadedVariable`** — wraps a BaseVariable, preloads all data upfront, `.load()` returns from memory cache
- **`BatchSaveProxy`** — wraps an output object, `.save()` accumulates to Python lists, flushed after the loop

This means scifor.for_each needs **zero knowledge of preloading or batch save** — it just calls `.load()` and `.save()` via duck-typing. Extension points needed:
- `_extra_save_metadata` — cell array of NV pairs merged into every `.save()` call
- `_all_combos` — pre-built combo list, bypasses cartesian product

## Files to create

### `+scifor/Fixed.m` (~50 lines)
Copy of `+scidb/Fixed.m` in the `scifor` namespace. Same properties (`var_type`, `fixed_metadata`), same constructor. Standalone users write `scifor.Fixed(csv_file, session="BL")`.

### `+scifor/unwrap_input.m` (~25 lines)
Duck-typed unwrapping: if `~istable(x) && ~isnumeric(x) && ~isstruct(x) && isprop(x, 'data')`, return `x.data`. Otherwise return `x` unchanged. Replaces the scidb-specific `scidb.internal.unwrap_input`.

## Files to modify

### `+scifor/for_each.m` — rewrite as standalone core (~1200 lines)

**Remove all DB-specific code:**
- Empty-list resolve via `py.scidb.database.get_database().distinct_schema_values()` (lines 157-180) → replace with table-column scanning
- Schema combo filtering via `filter_db.distinct_schema_combinations()` (lines 276-341)
- `build_config_nv()` call (line 262-264) → config keys come from `_extra_save_metadata`
- Preloading phase (lines 361-490)
- Batch save setup/accumulation/flush (lines 519-526, 859-900)
- Parallel branch (lines 493-507, helper lines 1048-1313)
- All `py.*` calls
- All `scidb.internal.*` calls

**Rewrite for duck-typing:**
- `is_loadable()`: `istable(x) || is_fixed_like(x) || is_merge_like(x) || has_load_method(x)`
  - `is_fixed_like(x)`: checks for `.var_type` and `.fixed_metadata` properties (works with both `scifor.Fixed` and `scidb.Fixed`)
  - `has_load_method(x)`: checks `ismethod(x, 'load')` — works for CsvFile, MatFile, BaseVariable, PreloadedVariable
- Loading: call `x.load(meta_nv{:})` on any loadable object
- Unwrapping: `scifor.unwrap_input()` (duck-typed `.data` check)
- Saving: `out.save(data, save_nv{:})` on any output with `.save()`
- Thunk detection: soft `isa(fn, 'scidb.Thunk')` in try/catch, defaults to false

**Add extension points:**
- `_extra_save_metadata`: parsed in `split_options`, merged into `save_nv`
- `_all_combos`: parsed in `split_options`, bypasses `cartesian_product()`

**Keep (standalone helpers):**
- `split_options()` — add `_extra_save_metadata`, `_all_combos`
- `filter_table_for_combo()` — unchanged
- `cartesian_product()` — unchanged
- `split_for_distribute()` — unchanged
- `is_metadata_compatible()` — unchanged
- `normalize_cell_column()`, `cartesian_indices()`, `format_value()` — unchanged
- `fe_multi_result_to_table()` — rewrite with duck-typed unwrapping
- `apply_column_selection()` — rewrite with duck-typed unwrapping
- `results_to_output_table()` — rewrite with duck-typed unwrapping
- `print_dry_run_iteration()` — rewrite with duck-typed display
- `format_inputs()`, `format_outputs()` — rewrite with duck-typing
- Merge helpers (`merge_constituents`, `merge_by_schema_keys`, etc.) — adapt to use `scifor.get_schema()` instead of DB
- `build_meta_key()`, `result_meta_key()`, `combo_meta_key()` — keep

### `+scidb/for_each.m` — rewrite as DB wrapper (~400-500 lines)

Following the Python `scirun.for_each()` pattern, this function:

1. **Parses options** — extracts `parallel`, `preload`, `db`, `where` + all metadata from varargin
2. **Resolves empty metadata lists** — `py.scidb.database.get_database().distinct_schema_values()`
3. **Propagates schema** — `scifor.set_schema(db.dataset_schema_keys)`
4. **Builds ForEachConfig version keys** — `build_config_nv()` (moved here)
5. **Pre-filters schema combos** — `filter_db.distinct_schema_combinations()`, builds `_all_combos`
6. **Parallel branch** — if `parallel=true`, runs the 3-phase loop directly (moved `run_parallel` here), does NOT delegate to scifor
7. **Wraps inputs in PreloadedVariable proxies** — if `preload=true`, bulk-loads via `py.scidb_matlab.bridge.load_and_extract()`, wraps each BaseVariable in a proxy that returns from cache
8. **Wraps outputs in BatchSaveProxy** — for non-Thunk functions, wraps outputs so `.save()` accumulates
9. **Delegates** to `scifor.for_each()` with `_extra_save_metadata` and `_all_combos`
10. **Flushes batch save proxies** after scifor returns

**Moved helpers (local functions):**
- `build_config_nv()`, `serialize_loadable_inputs()`, `input_spec_to_key()`, `format_repr()`
- `run_parallel()` (full parallel execution)
- `schema_str()` (for DB combo filtering)
- `has_pathinput()` (checks `scidb.PathInput`)
- PreloadedVariable / BatchSaveProxy logic (inline or as local helper classes)

## Files NOT changed

- `+scidb/Fixed.m` — stays as-is. Duck-typing in scifor.for_each means it works with both `scifor.Fixed` and `scidb.Fixed`.
- `+scidb/Merge.m` — stays as-is, same reasoning.
- `+scifor/Col.m`, `ColFilter.m`, `CompoundFilter.m`, `NotFilter.m`, `CsvFile.m`, `MatFile.m`, `set_schema.m`, `get_schema.m` — no changes needed.

## Tests

### New: `TestSciforForEach.m` — standalone for_each tests (no database)
- Table input filtering by schema keys
- CsvFile as input + output through for_each
- MatFile as input + output through for_each
- Constants passed through unchanged
- `scifor.Fixed(table, key=val)` filtering
- `scifor.Fixed(CsvFile(...), key=val)` loading
- Distribute with table outputs
- Dry-run mode
- Empty-list resolve from table columns
- Result table structure

### Existing: `TestForEach.m` — should pass as-is
All existing DB tests call `scidb.for_each()` which now wraps scifor. No test changes expected, but we run the full suite to verify.

### Existing: `TestScifor.m` — add tests
- `scifor.Fixed` constructor and properties
- `scifor.Fixed` with table and CsvFile inputs

## Verification

1. Run existing MATLAB test suite (`TestForEach`, `TestScifor`, etc.) to verify no regressions
2. Run new `TestSciforForEach` tests to verify standalone behavior
3. Run Python tests (`scifor/tests/`, `scirun-lib/tests/`) to verify Python side is unaffected
