# Column Selection for BaseVariable

## Purpose

When a `BaseVariable` stores a wide table (e.g. 50+ columns loaded from
Excel), loading the entire table to extract one column is wasteful. Column
selection lets users request specific columns at the point where the
variable is used as a `for_each()` input, without changing how data is
stored or loaded from the database.

## Python Syntax

```python
# Single column → function receives numpy array
for_each(fn, inputs={"x": MyVar["col_a"]}, outputs=[Result], subject=[1, 2, 3])

# Multiple columns → function receives DataFrame subset
for_each(fn, inputs={"x": MyVar[["col_a", "col_b"]]}, outputs=[Result], subject=[1])

# Works inside Fixed too
for_each(fn, inputs={"x": Fixed(MyVar["col_a"], session="BL")}, outputs=[Result], subject=[1])
```

`MyVar["col"]` uses `BaseVariable.__class_getitem__` (`scidb/src/scidb/variable.py`)
to construct a `ColumnSelection`.

**As of the scifor/scidb modifier-class unification**
(`docs/claude/scifor-scidb-modifier-unification.md`), `ColumnSelection`'s
container (`.data`, `.columns`, `.iterate`, `.excl_columns`, `to_key()`,
`__hash__`, `__name__`) is defined once in
`scifor/src/scifor/column_selection.py` and wraps either a DataFrame
(standalone scifor use) or a variable type (scidb use) — the same class
either way. `scidb/src/scidb/column_selection.py` is a thin **subclass**
adding only the DB-only surface with no scifor equivalent: comparison
operators (`MyVar["col"] == value` → `scidb.filters.ColumnFilter`),
`.load()`, `.to_csv()`. `MyVar["col"]` always constructs scidb's subclass;
scidb's internal isinstance checks use the scifor **base** class so a bare
`scifor.ColumnSelection(some_dataframe, [...])` passed directly into
`scidb.for_each()` is recognized too (new capability — previously
impossible to even construct, since scidb's old `ColumnSelection` only ever
wrapped a variable type).

## MATLAB Syntax

```matlab
% Single column → function receives array
scidb.for_each(@fn, struct('x', MyVar("col_a")), {Result()}, subject=[1 2 3]);

% Multiple columns → function receives subtable
scidb.for_each(@fn, struct('x', MyVar(["col_a", "col_b"])), {Result()}, subject=[1]);
```

Unlike Python, MATLAB has no separate `ColumnSelection` wrapper class — the
column names are passed to the `BaseVariable` constructor and stored
directly on the instance in the `selected_columns` property
(`+scidb/BaseVariable.m`), alongside an `iterate` flag for `for_columns()`.

## Return Behavior

| Selection | Python return type | MATLAB return type |
|-----------|-------------------|-------------------|
| Single column | `numpy.ndarray` (`.values` of the column) | numeric/cell array (table column) |
| Multiple columns | `pandas.DataFrame` (subset of columns) | MATLAB `table` (subtable) |

## How It Works (Python)

1. `MyVar["col"]` creates `ColumnSelection(MyVar, ["col"])` (scidb's subclass).
2. `_is_loadable()` in `scidb/src/scidb/foreach.py` recognizes `ColumnSelection`
   (checked against the scifor base class) as loadable.
3. `_load_input` dispatches on what's inside: a plain DataFrame passes
   through unchanged (as-is, no loading needed); something with `.load()`
   goes through `_load_var_type_as_spread` (bulk) and gets re-wrapped as a
   `scifor.ColumnSelection` around the loaded DataFrame; anything else
   (can't bulk-load) is wrapped in `PerComboLoader`, resolved per-combo by
   `_resolve_per_combo_loader` calling `spec.data.load(**load_kw)`.
4. Either way, the per-combo *extraction* (dropping to a numpy array for one
   column, or a DataFrame subset for several) is scifor's job —
   `scifor/src/scifor/foreach.py`'s `prepare_input`/column-selection
   handling, unchanged by which package constructed the wrapper.

## How It Works (MATLAB)

1. `MyVar("col_a")` stores `"col_a"` in the `selected_columns` property on
   the `BaseVariable` instance itself (no separate wrapper object).
2. For `for_each()`, MATLAB's bridge (`scimatlab/src/scimatlab/bridge.py`,
   `describe_input_for_python` on the MATLAB side in `+scidb/for_each.m`)
   serializes a non-empty `selected_columns` (or `iterate`) into a
   `{"kind": "column_selection", "type_name": ..., "columns": ..., "iterate":
   ...}` spec, which Python's `_reconstruct_input_for_keys` rebuilds into a
   real `scidb.column_selection.ColumnSelection` — from there it's the same
   Python machinery described above.
3. For direct calls that don't go through `for_each` (e.g. `.to_csv()`),
   MATLAB constructs `py.scidb.column_selection.ColumnSelection(py_class,
   py.list(cols))` directly via the bridge and calls its instance methods —
   MATLAB never re-implements the extraction itself.

## Key Files

| File | Role |
|------|------|
| `scifor/src/scifor/column_selection.py` | `ColumnSelection` base (container, `to_key()`, `__hash__`, `__name__`) |
| `scidb/src/scidb/column_selection.py` | scidb subclass: comparison operators, `.load()`, `.to_csv()` |
| `scidb/src/scidb/variable.py` | `BaseVariable.__class_getitem__`, `.for_columns()` |
| `scidb/src/scidb/foreach.py` | `_is_loadable`, `_load_input`, `_resolve_per_combo_loader` |
| `scifor/src/scifor/foreach.py` | Per-combo filter/extract logic (shared, package-agnostic) |
| `scimatlab/src/scimatlab/matlab/+scidb/BaseVariable.m` | `selected_columns` / `iterate` properties |
| `scimatlab/src/scimatlab/matlab/+scidb/for_each.m` | `describe_input_for_python` — bridges `selected_columns` to Python |
| `scimatlab/src/scimatlab/bridge.py` | `_reconstruct_input_for_keys` — rebuilds the Python `ColumnSelection` |

## See Also

- `docs/claude/scifor-scidb-modifier-unification.md` — why `ColumnSelection`
  is the one unified class that still needs a scidb-side subclass, and how
  that interacts with `_is_loadable`/isinstance checks throughout scidb.
