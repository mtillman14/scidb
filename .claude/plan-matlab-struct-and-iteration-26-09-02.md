# Plan: struct Parameters, missing schema iteration, and dict-record round-trip

**Date:** 2026-09-02
**Trigger:** MATLAB pipeline run in the GUI (`loadDelsysEMGOneFile` -> `filterDelsys`).
Evidence: `/workspace/scidb.log` lines 2151-2184, 6461-6490.

Three defects, two layers. All three are needed for `filterDelsys` to run at all.

---

## Defect 1 — a dict-valued Parameter reaches MATLAB as a char array

**Layer: scistack-gui.**

`scidb.log:6485`:

```
config: '{'FILTER': {'BANDPASS_ORDER': 4, ...}}'
```

`scistack_gui/api/matlab_command.py::_format_matlab_value` handles
`bool/int/float/str/list` and falls through to `f"'{str(val)}'"`. A dict hits
that fallback, so `_format_sweep` emits `scidb.Parameter('{...}')` — a MATLAB
char row vector holding a Python repr.

The list branch is wrong too: `['HAM', 'RF']` renders as `['HAM', 'RF']`, which
MATLAB concatenates into the single char array `'HAMRF'`.

The entities bridge path is already correct (`+scidb/entities.m` ->
`pylist_to_cell` -> `pydict_to_struct` -> `from_python` recurses). Only the
GUI's inlined-literal generator is broken.

### Fix

Rewrite `_format_matlab_value` to mirror what `from_python.m` produces, so a
value reaching MATLAB as an inlined literal is identical to the same value
reaching it through `scidb.entities()`:

| Python value | MATLAB literal | Mirrors |
|---|---|---|
| `dict` | `struct('k', v, ...)` | `pydict_to_struct` |
| all-string list | `["a", "b"]` (string array) | `from_python.m:273` |
| all-numeric/bool list | `[1, 2]` | ndarray branch |
| mixed / nested list | `{...}` (cell) | list fallback |
| `None` | `[]` | `py.NoneType` branch |

Traps:
- `struct('a', {1,2})` builds a **1x2 struct array**, not a scalar struct with a
  cell field. Every cell-valued field must be double-wrapped: `struct('a', {{1,2}})`.
- Field names go through a `matlab.lang.makeValidName` equivalent, matching
  `pydict_to_struct`.
- `struct()` with zero fields for an empty dict.

---

## Defect 2 — first run of a MATLAB function emits no schema iteration

**Layer: scistack-gui.**

`scidb.log:6461` `variants=0`, `:6462` `fn_variants=0`, `:6482`
`full_combos=1`, `:6485` `loaded_data: <table 3x12>`.

`generate_matlab_command` has two branches:

- **has variants** (line ~747): emits `_format_schema_kwargs(iterate_keys, ...)`
  with `iterate_keys = schema_level or schema_keys`.
- **no variants** (line 510, the never-run template): emits
  `scihist.for_each(@fn, inputs, outputs);` — **no schema kwargs at all**.

With no iterables, `for_each_prepare` returns one combo and the whole 3-row
`RawEMG` table goes into a single call.

`loadDelsysEMGOneFile` took the same branch and survived only because its
PathInput template contains `{pass}`, so PathInput discovery supplied the
iterable (`:2169` `full_combos=3, keys=['pass']`). `filterDelsys` has no
PathInput, so nothing supplied `pass`.

### Fix

The template branch emits the same schema kwargs the variants branch does.
Schema keys are known from the dataset regardless of whether history exists —
that is exactly why the never-run case needs them *more*, not less.

---

## Defect 3 — a dict-saved record does not come back as a dict/struct

**Layer: scifor (extraction rule) + scidb (supplies the fact).**

`scidb.log:2182-2184`: `RawEMG -> record_id=... (dict, 10 keys)` — sciduckdb
`multi_column` mode, one DuckDB column per struct field.

`for_each` loads it through the **spread** layout (`:6472` `3 rows x 14 cols`).
`+scifor/for_each.m::extract_data` (and Python's `scifor/foreach.py::_extract_data`)
only unwrap to a scalar at **1 row AND 1 data column**. With 10 data columns
they return a table/DataFrame. Hence `loaded_data.(muscle_name)` yields a
`1x1 cell` and `isnan` fails — and it would still fail after Defect 2 is fixed,
just with a 1x10 table instead of 3x12.

Two facts make this a real inconsistency rather than a design choice:

1. `sciduckdb.py:1497-1509` **does** reassemble a single-row `multi_column`
   record into a dict (and unflattens nested ones). `RawEMG().load(pass=1)`
   returns a struct. Only the batched spread path skips that.
2. `database.py::_load_as_df_via_iterator` — the fallback used for `nested`
   dicts — puts the whole dict in **one** column, so nested dict variables
   already round-trip correctly. Only the flat fast path spreads and loses it.

### Why the fix cannot live at load time

The spread N-column layout is load-bearing for `Type("col")` column selection,
`ColName`, `Merge`, `as_table=True`, `share_limits` and `for_columns`.
Collapsing at load would break all of them. Reassembly must happen **per combo,
after column selection has had its chance** — i.e. in `_extract_data`.

### Why scifor cannot infer it

"1 row, N data columns -> dict" would also convert a genuine DataFrame-mode
variable's single row into a dict. scifor must be *told*; scidb is the layer
that knows the storage mode.

### Fix

- **scidb** `DatabaseManager.get_dtype_meta(name)` accessor (three sites already
  inline this query; new code uses the accessor).
- **scidb** `_mapping_data_columns(var_spec, db)` -> the dict keys when the type
  stores `multi_column` and is not `nested`, else `None`. `_convert_inputs`
  builds `{input_name: [cols]}` and it is threaded to scifor as the private
  `_mapping_inputs=` kwarg (same convention as `_all_combos`,
  `_path_input_resolver`).
- **scifor** `for_each(..., _mapping_inputs=None)`; `_prepare_input` forwards to
  `_extract_data`, which returns `{col: value}` for a single row when the input
  is marked, `as_table` is off and no column selection applies.
- **scimatlab** `for_each_prepare` returns `mapping_inputs`;
  `+scidb/for_each.m` forwards it as `'_mapping_inputs'`;
  `+scifor/for_each.m::extract_data` builds a scalar struct.

Multi-row slices keep returning a table (a coarser iteration level genuinely has
no single struct to give). `as_table=true` keeps returning the table.

---

## Logging and tests (CLAUDE.md NOTE 2)

- `_convert_inputs` logs which inputs were marked mapping-valued and their column
  count, at INFO — the missing observability that made this take a log dive.
- `extract_data` (both languages) logs at DEBUG when it reassembles a struct.
- The GUI generator logs when a Parameter value renders as a struct literal.
- Tests: dict/list/nested-dict/empty-dict/`None` -> MATLAB literal; cell-field
  double-wrap guard; never-run branch emits schema kwargs; `_extract_data`
  returns a dict for a marked single row and a frame for a marked multi-row
  slice.

## Out of scope

- `generate_matlab_pipeline_command` still **skips** a step with no variants
  ("no runnable target derived"). Pre-existing, deliberate, untouched here.
- `+toml` (MATLAB TOML reader) is not used — user is removing it; only Python
  reads/writes TOML.
