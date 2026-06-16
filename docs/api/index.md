# API Reference

<!-- Ground truth (exports/signatures win over prose). Verified against:
     scidb/src/scidb/__init__.py exports (BaseVariable, configure_database, get_database,
       for_each, Fixed, Variant, Merge, ColumnSelection, ColName, EachOf, Constant, constant,
       Col, set_schema, PathInput, PathOutput, raw_sql, schema_key, exclude_schema,
       include_schema, list_exclusions, manual);
     scihist/__init__ (for_each, save, configure_database, lineage_fcn, LineageFcn,
       LineageFcnResult, LineageFcnInvocation, find_by_lineage, check_node_state...);
     scilineage/__init__ (lineage_fcn, extract_lineage, get_upstream_lineage, manual);
     scimatlab/src/scimatlab/matlab/+scidb (configure_database 2 args; classdef vars).
     NOTE: NO @thunk/Thunk/ThunkOutput/load_all — the decorator is @lineage_fcn, results are
     LineageFcnResult, and load() returns BaseVariable | list | DataFrame. -->

SciStack's public API is the three user-facing layers — `scifor`, `scidb`, and
`scihist`. Because each layer re-exports the one below it, the top layer
(`scihist`) surfaces the whole API — storage, batch processing, and the lineage
decorator — from a single import. The same concepts are available from MATLAB
through the `scidb.*` / `scifor.*` surfaces.

## Packages

| Package | Purpose | Import |
|---|---|---|
| `scifor` | Standalone batch iteration on tables | `from scifor import ...` / `scifor.*` |
| `scidb` | Variables, database, DB-backed `for_each` | `from scidb import ...` / `scidb.*` |
| `scihist` | `for_each` + lineage + `save` (full pipeline); re-exports the layers below, incl. `lineage_fcn` | `from scihist import ...` |

The lineage engine, hashing, DuckDB layer, and MATLAB bridge are **internal
packages** reached through the three layers above — see
[Internals](../internals/index.md).

## Sections

### [Variables (BaseVariable)](variables.md)
The central abstraction — every stored value is a `BaseVariable` subclass.
Key members: `save()`, `load()`, `save_from_dataframe()`, `to_csv()`, `to_db()` / `from_db()`.

### [Database](database.md)
Configuration and database operations.
Key members: `configure_database()`, `get_database()`, `list_versions()`,
`get_provenance()`, variable groups, exclusions.

### [Lineage](lineage.md)
Provenance tracking and caching.
Key members: `@lineage_fcn`, `LineageFcnResult`, `extract_lineage()`,
`get_upstream_lineage()`, `manual()`, `scihist.save()`.

### [Batch Processing (for_each)](for-each.md)
Run a function over every combination of conditions.
Key members: `for_each()`, `Fixed`, `Merge`, `ColumnSelection`, `EachOf`,
`PathInput`, `PathOutput`.

### [Filters](filters.md)
Conditional loading by other variables' values.
Key members: the `where=` parameter, `&` / `|` / `~` composition, column filters,
`raw_sql()`, `schema_key()`.

## Python ↔ MATLAB

Every page shows Python and MATLAB side by side in tabs. The main differences:

| Concept | Python | MATLAB |
|---|---|---|
| Define a type | `class MyVar(BaseVariable): ...` | `classdef MyVar < scidb.BaseVariable; end` |
| Save | `MyVar.save(data, subject=1)` | `MyVar().save(data, subject=1)` |
| Loaded value | a `BaseVariable` instance (`.data`, `.metadata`) | a variable instance (`.data`, `.metadata`) |
| Lineage decorator | `@lineage_fcn` / `lineage_fcn(fn)` | (define functions; tracked on the Python side) |
| Column selection | `MyVar["col"]` | `MyVar("col")` (constructor argument) |
| `for_each` inputs | `dict` | `struct` (field order = argument order) |
| `for_each` outputs | `list` of classes | cell array of instances |
| Filter combination | `&` / `|` | `&` / `|` (never `&&` / `||`) |
