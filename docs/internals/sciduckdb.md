# sciduckdb — the DuckDB persistence layer

!!! info "Internal package"
    You normally use storage through **`scidb`** (`BaseVariable`,
    `configure_database`, `save`/`load`). This page describes the layer beneath it.

`sciduckdb` is a thin DuckDB layer for versioned scientific data. It stores
**each variable in its own table**, associated with a hierarchical dataset schema
(e.g. `subject → session → trial`), and supports multiple versions of each
variable natively.

## What it owns

- **One table per variable**, saved at any level of the dataset hierarchy.
- **Native versioning** — every save is a new version; history is preserved.
- **Queryable types** — all data, including arrays, is stored in inspectable
  DuckDB types (`LIST`, nested `LIST`, `JSON`), so the database opens in DBeaver
  or any DuckDB-compatible viewer.
- **Lossless type round-trips** — values come back out as they went in.

It knows nothing about iteration or provenance — that separation is what lets
`scidb` layer typed variables and `for_each` on top of plain persistence. For the
user-facing model, see [Variables & Storage](../concepts/variables.md) and the
[Database guide](../guide/database.md).
