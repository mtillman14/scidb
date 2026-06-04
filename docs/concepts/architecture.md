# Architecture & Layers

<!-- Ground truth (tests/declared deps win over prose). Verified against:
     pyproject [dependencies] of each package (the authoritative dependency graph);
     package __init__.py exports; scidb/src/scidb/foreach.py (delegation + HAS_LINEAGE
     conditional import; lazy scihist.save_lineage_result callback at line ~2636);
     scidb/tests/test_optional_lineage_dependency.py (scidb runs without scilineage);
     scifor/tests/test_foreach_standalone.py; scidb/tests/test_integration.py;
     scihist/tests/test_foreach.py; docs/claude/layer-friction-analysis.md. -->

SciStack is a **layered stack**: each package owns one responsibility and depends
only on the packages below it. That separation is what lets you
[enter at any level](../getting-started/choosing-a-layer.md) — use the low-level
iteration engine on plain tables, or the full provenance-tracked pipeline, with
the same core ideas throughout.

## The dependency graph

Arrows point from a package to what it depends on. This is the **declared**
graph (from each package's `pyproject.toml`), not just intent:

```
                    scihist
                   /        \
              scidb          scilineage
            /  |   \   \           \
      scifor  |    \    scipathgen  \
              |     \                \
         sciduckdb   \________ scicanonicalhash
                              (also used by scidb directly)
```

| Package | Depends on (scistack) | Role |
|---|---|---|
| `scicanonicalhash` | — | Deterministic content hashing (the basis of versioning + lineage) |
| `sciduckdb` | — | Thin DuckDB layer: one table per variable, versioning, type round-trip |
| `scipathgen` | — | Generates file paths from metadata |
| `scifor` | — | Pure batch-iteration engine over plain tables/DataFrames |
| `scilineage` | `scicanonicalhash` | Provenance graph + pluggable caching (`@lineage_fcn`) |
| `scidb` | `scifor`, `sciduckdb`, `scicanonicalhash`, `scipathgen` | Typed versioned storage + DB-backed `for_each` |
| `scihist` | `scidb`, `scilineage` | Lineage-wrapped `for_each` + node-state / staleness |

The four leaf packages have **no scistack dependencies**, which is why `scifor`
runs standalone with nothing but a DataFrame, and `scilineage` runs with nothing
but `scicanonicalhash`.

### scilineage is optional *below* scihist

`scidb` does **not** declare `scilineage` as a dependency. It imports it
conditionally behind a `HAS_LINEAGE` flag: if scilineage is installed, `scidb`
records provenance for `@lineage_fcn` inputs; if it isn't, `scidb.for_each` still
works on plain functions (verified by `test_optional_lineage_dependency.py`).
There is also a single **lazy callback** from `scidb` into `scihist`
(`save_lineage_result`), used only on the lineage save path — it is not a
declared dependency and does not invert the layering.

## What each layer owns

- **scicanonicalhash** — turns a value or a function into a stable hash. Every
  higher layer leans on this for "has this changed?" decisions.
- **sciduckdb** — persists each variable in its own queryable DuckDB table, with
  automatic version numbering and lossless type round-trips. It knows nothing
  about iteration or provenance.
- **scipathgen** — resolves metadata (e.g. `subject=1, trial=3`) into concrete
  file paths, for data that lives on disk rather than in the database.
- **scifor** — the iteration engine. Given a schema (which columns are
  conditions) and inputs, it filters each table to the matching rows, calls your
  function, and collects the results. **Zero** awareness of databases,
  versioning, or lineage — by design.
- **scilineage** — wraps a function so every call records its inputs and a hash
  of the function, building a provenance graph that also serves as a cache key.
- **scidb** — adds *identity and persistence*: typed `BaseVariable`s, a versioned
  database (via sciduckdb), content hashing (via scicanonicalhash), filters and
  exclusions, and a `for_each` that loads inputs from and saves outputs to the
  database (delegating the actual looping to scifor).
- **scihist** — adds *reproducibility*: it auto-wraps your functions in
  `scilineage`, records lineage on save, and computes node states so a pipeline
  recomputes only what is stale.

## The core flow: how a `for_each` call descends and returns

The architecture is clearest in how a single `scihist.for_each` call moves
through the layers:

```
scihist.for_each(fn, inputs={Var}, outputs=[Out], subject=[...], ...)
  │  wraps fn in a LineageFcn (provenance); applies skip_computed (staleness)
  ▼
scidb.for_each(...)
  │  loads each input Var from the database into a DataFrame (by metadata)
  │  sets scifor's schema to the dataset's condition columns
  ▼
scifor.for_each(...)
  │  for every combination: filter DataFrames → call fn → collect a result row
  ▲
scidb   saves each result as a new version of the Out variable(s)
  ▲
scihist records lineage for each output and updates node state
```

Each layer adds its concern on the way down and unwinds it on the way back up.
Run `scidb.for_each` directly and you get the same flow **without** the lineage
wrapping and staleness steps; run `scifor.for_each` directly and you get **just**
the middle box, operating on tables you supply yourself.

## Why it's layered this way

- **Enter at any level.** Because each layer is usable on its own, you adopt only
  the capability you need today (see
  [Choosing Your Layer](../getting-started/choosing-a-layer.md)).
- **Single responsibility.** scifor never touches a database; sciduckdb never
  iterates; scilineage never persists. Bugs and changes stay contained to one
  layer.
- **Optional provenance.** Lineage is additive: scidb degrades gracefully without
  scilineage, and the heavyweight staleness machinery lives only in scihist.

## Peripheral packages

- **scimatlab** — the MATLAB bridge. It exposes the `scifor.*` and `scidb.*`
  surfaces to MATLAB so the same pipelines run from MATLAB code (see
  [MATLAB Setup](../matlab-setup.md)).
- **scidb-net** — an optional networking / serialization layer for moving data
  between machines.

**Next:** [Variables & Storage](variables.md) ·
[Lineage & Provenance](lineage.md) · [Computation Caching](caching.md) ·
[Node States](node-states.md)
