# scilineage — provenance engine

!!! info "Internal package"
    You normally use lineage through **`scihist`**, which re-exports the
    `lineage_fcn` decorator and wraps your functions automatically. Import it as
    `from scihist import lineage_fcn`. This page describes the underlying engine.

`scilineage` is the provenance engine behind SciStack's lineage features. It
captures the full computational lineage of each result — which function ran, what
its inputs were, and a version stamp of the function itself — building a graph
that doubles as a cache key. It is **Python-only** and depends only on
[`scicanonicalhash`](scicanonicalhash.md).

## What it owns

- **Automatic lineage tracking** — decorate a function with `@lineage_fcn` and
  each call captures its inputs and a hash of the function, returning a
  `LineageFcnResult` (the value lives on `.data`).
- **Input classification** — distinguishes genuine data dependencies from literal
  constants so the recorded lineage is accurate.
- **Pluggable caching** — register a backend via `configure_backend()` to serve
  repeated computations from cache by their lineage hash.
- **Manual interventions** — `manual()` records an out-of-band correction as a
  first-class lineage step instead of a silent hand-edit.

## Where it sits

`scidb` imports `scilineage` only behind a `HAS_LINEAGE` flag, so the database
works without it. The full provenance graph and automatic function wrapping come
from `scihist`. For the user-facing model and examples, see
[Lineage & Provenance](../concepts/lineage.md) and the
[Lineage guide](../guide/lineage.md).
