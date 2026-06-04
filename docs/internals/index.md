# Internals

SciStack's three user-facing layers — [`scifor`](../getting-started/choosing-a-layer.md),
`scidb`, and `scihist` — are built on a set of **internal packages**. You
normally never import these directly; you reach their capabilities through the
user-facing layers (for example, the lineage decorator is re-exported by
`scihist`, and the database lives behind `scidb`).

This section exists for contributors and the curious: it explains *what each
internal package is for* and *which user-facing layer surfaces it*, without
requiring any of it to use SciStack.

| Internal package | Provides | Reached through |
|---|---|---|
| [scilineage](scilineage.md) | Provenance graph + `lineage_fcn` decorator | `scihist` |
| [sciduckdb](sciduckdb.md) | DuckDB persistence (one table per variable, versioning) | `scidb` |
| [scicanonicalhash](scicanonicalhash.md) | Deterministic content/function hashing | `scidb`, `scihist` |
| [scipathgen](scipathgen.md) | Metadata → file-path generation | `scidb` |
| [scimatlab](scimatlab.md) | MATLAB bridge for `scifor.*` / `scidb.*` | MATLAB usage |
| [scidb-net](scidb-net.md) | Optional networking / serialization | optional |

For how the user-facing layers compose, see
[Architecture & Layers](../concepts/architecture.md).
