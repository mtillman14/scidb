# SciStack

<!-- Ground truth (source/tests win over prose). Verified against this session's reconciled
     pages and: scidb/__init__ (BaseVariable, configure_database, get_database, for_each);
     scihist/__init__ (for_each, save, configure_database, AND re-exports lineage_fcn,
     LineageFcn, set_schema, Fixed, ... from the layers below); scimatlab configure_database
     (2 args); all data + lineage in one DuckDB file. NOTE: three USER-FACING layers
     (scifor/scidb/scihist); lineage is a scihist feature (lineage_fcn is re-exported by
     scihist, so import it from scihist — the scilineage package is internal); decorator is
     @lineage_fcn (not @thunk); configure_database takes 2 args (no SQLite "pipeline.db");
     persist lineage results via scihist.save, not VarClass.save. -->

**A layered framework for reproducible scientific data processing.**

SciStack turns ordinary analysis functions into versioned, provenance-tracked,
cache-aware pipelines. Every result remembers how it was produced; nothing is
recomputed unless an input or the code actually changed; and all data plus lineage
lives in a single, inspectable DuckDB file. It works from both **Python** and
**MATLAB**.

## Enter at any level

SciStack is a *stack* of small packages — use only the layer you need, and adopt
the ones above it when you want more. (See
[Choosing Your Layer](getting-started/choosing-a-layer.md).)

| Layer | Package | What it adds |
|---|---|---|
| Batch iteration | `scifor` | Run a function over every condition combination on plain tables — no database |
| Storage | `scidb` | Typed, versioned variables in a database; DB-backed `for_each` |
| Full pipeline | `scihist` | `for_each` with automatic lineage + "recompute only what's stale" |

Each layer re-exports the one below it, so the top layer (`scihist`) gives you the
whole API from a single import.

## Quick example

```python
import numpy as np
from scidb import BaseVariable
from scihist import for_each, configure_database, lineage_fcn

# One DuckDB file holds data and lineage; declare the experiment's condition keys
configure_database("experiment.duckdb", ["subject", "session"])

class RawSignal(BaseVariable): schema_version = 1
class SignalPower(BaseVariable): schema_version = 1

# A tracked function: each call records its inputs + a hash of the function
@lineage_fcn
def compute_power(signal):
    return float(np.mean(signal ** 2))

# Process every subject/session, loading inputs and saving outputs with lineage
for_each(compute_power, inputs={"signal": RawSignal}, outputs=[SignalPower],
         subject=[1, 2, 3], session=["A", "B"])

# Re-run: nothing recomputes — every result is already current
for_each(compute_power, inputs={"signal": RawSignal}, outputs=[SignalPower],
         subject=[1, 2, 3], session=["A", "B"])
```

## Why SciStack

| Question | How SciStack answers it |
|---|---|
| "Which version of this data did I use?" | Content-addressed `record_id`s and automatic versioning |
| "What produced this result?" | Lineage captured automatically via `@lineage_fcn` |
| "I already computed this — why recompute?" | Cache hits and `skip_computed` reuse current results |
| "How do I organize experimental data?" | Address records by flexible metadata (subject/session/…) |
| "Can I share or inspect the database?" | One DuckDB file, queryable in DBeaver |

## Get started

- [Installation](getting-started/installation.md) — install the layers you need
- [Quickstart](quickstart.md) — a working pipeline in a few minutes
- [Choosing Your Layer](getting-started/choosing-a-layer.md) — pick your entry point
- [Concepts](concepts/index.md) — variables, lineage, caching, hashing
- [User Guide](guide/index.md) — task-oriented how-tos
- [API Reference](api/index.md) — the full surface
- [MATLAB Setup](matlab-setup.md) — the same workflow from MATLAB
