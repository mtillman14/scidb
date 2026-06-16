# Architecture & Layers

<!-- Ground truth (tests/declared deps win over prose). Verified against:
     pyproject [dependencies] of each package (the authoritative dependency graph);
     package __init__.py exports (scihist re-exports scidb + scifor + lineage_fcn/LineageFcn);
     scidb/src/scidb/foreach.py (delegation + HAS_LINEAGE conditional import; lazy
     scihist.save_lineage_result callback); scidb/tests/test_optional_lineage_dependency.py
     (scidb runs without scilineage); scifor/tests/test_foreach_standalone.py;
     scidb/tests/test_integration.py; scihist/tests/test_foreach.py;
     docs/claude/layer-friction-analysis.md.
     NOTE: three USER-FACING layers (scifor/scidb/scihist); everything else
     (scilineage, sciduckdb, scipathgen, scicanonicalhash, scimatlab, scidb-net) is an
     internal package — see docs/internals/. -->

SciStack is a **layered stack of three user-facing packages**. Each one owns a
single responsibility and re-exports the layer below it, so you can
[enter at any level](../getting-started/choosing-a-layer.md) — the low-level
iteration engine on plain tables, or the full provenance-tracked pipeline, with
the same core ideas throughout.

## The three layers

```
  scihist   reproducible pipelines: for_each + automatic lineage + recompute-only-what's-stale
    │  re-exports scidb + scifor + the lineage decorator
  scidb     typed, versioned variable storage + DB-backed for_each
    │  re-exports scifor
  scifor    pure batch iteration over condition combinations on plain tables
```

| Layer | Role | Depends on (user-facing) |
|---|---|---|
| `scifor` | Pure batch-iteration engine over plain tables/DataFrames | — |
| `scidb` | Typed versioned storage + DB-backed `for_each` | `scifor` |
| `scihist` | Lineage-wrapped `for_each` + node-state / staleness | `scidb` |

Because each layer re-exports the one below it, `from scihist import ...` gives
you the whole public surface — `for_each`, `BaseVariable`-style storage,
`configure_database`, `set_schema`, and the `lineage_fcn` decorator — from a
single import.

## What each layer owns

- **scifor** — the iteration engine. Given a schema (which columns are
  conditions) and inputs, it filters each table to the matching rows, calls your
  function, and collects the results. **Zero** awareness of databases,
  versioning, or lineage — by design, so it runs standalone on a DataFrame.
- **scidb** — adds *identity and persistence*: typed variables, a versioned
  database, content hashing, filters and exclusions, and a `for_each` that loads
  inputs from and saves outputs to the database (delegating the actual looping to
  scifor).
- **scihist** — adds *reproducibility*: it auto-wraps your functions in lineage
  tracking, records lineage on save, and computes node states so a pipeline
  recomputes only what is stale.

## The core flow: how a `for_each` call descends and returns

The architecture is clearest in how a single `scihist.for_each` call moves
through the layers:

```
scihist.for_each(fn, inputs={Var}, outputs=[Out], subject=[...], ...)
  │  wraps fn for provenance; applies skip_computed (staleness)
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
- **Single responsibility.** scifor never touches a database; scidb never tracks
  provenance on its own. Bugs and changes stay contained to one layer.
- **Optional provenance.** Lineage is additive: scidb works without it, and the
  heavyweight staleness machinery lives only in scihist.

## Under the hood: internal packages

The three layers above are built on a set of **internal packages** you normally
never import directly — you reach them through `scifor`/`scidb`/`scihist`. They
are documented separately in [Internals](../internals/index.md); in brief:

| Internal package | What it provides | Reached through |
|---|---|---|
| `scilineage` | The provenance graph + `lineage_fcn` decorator (re-exported by scihist) | `scihist` |
| `sciduckdb` | The DuckDB persistence layer (one table per variable, versioning) | `scidb` |
| `scicanonicalhash` | Deterministic content/function hashing behind versioning + lineage | `scidb`, `scihist` |
| `scipathgen` | Generates file paths from metadata for on-disk data | `scidb` |
| `scimatlab` | The MATLAB bridge that exposes `scifor.*` / `scidb.*` to MATLAB | MATLAB usage |
| `scidb-net` | Optional networking / serialization for moving data between machines | optional |

Two facts worth knowing about the boundary: `scidb` imports `scilineage` only
behind a `HAS_LINEAGE` flag (it runs fine without it, verified by
`test_optional_lineage_dependency.py`), and the full provenance graph plus
automatic function wrapping come from `scihist`. See
[Internals](../internals/index.md) for details.

**Next:** [Variables & Storage](variables.md) ·
[Lineage & Provenance](lineage.md) · [Computation Caching](caching.md) ·
[Node States](node-states.md)
