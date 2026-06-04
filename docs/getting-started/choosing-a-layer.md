# Choosing Your Layer

<!-- Ground truth (tests win over prose). Verified against:
     scifor/tests/test_foreach_standalone.py  (set_schema, for_each, inputs=, returns DataFrame)
     scidb/tests/test_integration.py + conftest.py  (configure_database, BaseVariable,
        save->record_id, load->record with .data/.record_id/.metadata)
     scihist/src/scihist/__init__.py + scihist/tests/test_foreach.py  (for_each + outputs=,
        auto-wraps in LineageFcn)
     scilineage/tests/test_lineage.py + README  (@lineage_fcn -> result.data, Python-only)
     Package __init__ exports; docs/claude/layer-friction-analysis.md (layer separation). -->

SciStack is a **stack**, not a single library. Each layer adds one capability on
top of the one below it, and **you can enter at any level**. Start with just the
piece you need today; adopt the layers above it only when you actually need what
they add.

```
  scihist     lineage + staleness on top of scidb   (reproducible pipelines)
    │
  scidb       typed, versioned storage + DB-backed for_each
    │
  scifor      batch iteration over conditions on plain tables   (no database)

  scilineage  provenance + caching for a function graph   (used by scidb/scihist,
              or directly when you don't need batch iteration or storage)
```

## Quick chooser

| You want to… | Use | Import | Languages |
|---|---|---|---|
| Replace nested `for` loops over subjects/sessions/trials; data is already in a table | **scifor** | `from scifor import for_each, set_schema` | Python & MATLAB |
| Add reproducibility / caching to a chain of functions (no batch, no storage) | **scilineage** | `from scilineage import lineage_fcn` | Python |
| Persist typed results in a versioned database, loaded/saved by metadata | **scidb** | `from scidb import configure_database, BaseVariable, for_each` | Python & MATLAB |
| Run a full pipeline that auto-tracks provenance and recomputes only what's stale | **scihist** | `from scihist import for_each` | Python (MATLAB via the scidb path) |

If you're unsure, start one layer lower than you think you need — moving up is
additive and doesn't require rewriting your analysis function.

---

## scifor — batch iteration, no database

**What it adds:** turns a function you already wrote into a batch job over every
combination of experimental conditions. You declare which columns are conditions
(`set_schema`) and which inputs to slice; scifor filters each table to the
matching rows, calls your function, and collects the results into one table.

**Choose this when:** your data already lives in a DataFrame (Python) or table
(MATLAB), you just want to stop writing slice-call-collect loops, and you don't
need anything persisted between runs.

=== "Python"
    ```python
    from scifor import set_schema, for_each

    set_schema(["subject", "session"])

    results = for_each(
        my_analysis,
        inputs={"emg": data_table, "cutoff_hz": 20},  # cutoff_hz is a constant
        subject=[1, 2, 3],
        session=["pre", "post"],
    )
    # -> DataFrame: one row per (subject, session) with an `output` column
    ```

=== "MATLAB"
    ```matlab
    scifor.set_schema(["subject", "session"]);

    results = scifor.for_each(@my_analysis, ...
        struct('emg', data_table, 'cutoff_hz', 20), ...
        subject=[1, 2, 3], session=["pre", "post"]);
    ```

Your function never sees the looping, filtering, or metadata — it just receives
data and returns a result. No database is created or touched.

---

## scilineage — provenance & caching for a function graph

**What it adds:** automatic provenance tracking. Decorate a function with
`@lineage_fcn` and every call captures its inputs and a hash of the function
itself, building a complete lineage graph. With a caching backend registered, a
repeated computation can be served from cache instead of re-run.

**Choose this when:** you want reproducibility or caching for a chain of
computations, but you are *not* iterating over experimental conditions and you
don't need data persisted to a database. This layer is **Python only**.

```python
from scilineage import lineage_fcn

@lineage_fcn
def process(data, factor):
    return data * factor

result = process([1, 2, 3], 2)
result.data            # [2, 4, 6]  — the computed value lives on .data
result.invoked.inputs  # captured inputs, for the lineage graph
```

A `@lineage_fcn` call returns a `LineageFcnResult` (carrying lineage), not the
raw value — read `.data` to get the value. scilineage is the provenance engine
that **scidb** and **scihist** build on; you only use it directly when you want
provenance without batch iteration or storage.

---

## scidb — typed, versioned storage + DB-backed `for_each`

**What it adds:** a versioned DuckDB database of *typed variables*. You define
each variable as a `BaseVariable` subclass, then `save`/`load` it by metadata.
Every save is versioned automatically. `scidb.for_each` is the same iteration
engine as scifor, but it **loads inputs from the database and saves outputs
back** — so you pass variable *types* and an `outputs=` list instead of raw
tables.

**Choose this when:** results need to persist across sessions and be retrieved by
metadata (subject/session/trial), with version history — but you don't yet need
automatic provenance.

```python
from scidb import configure_database, BaseVariable, for_each
import numpy as np

db = configure_database("experiment.duckdb", ["subject", "session"])

class RawSignal(BaseVariable):
    schema_version = 1

# Save returns the new record's id; load returns one record object
RawSignal.save(np.array([1, 2, 3]), subject=1, session="A")
rec = RawSignal.load(subject=1, session="A")
rec.data, rec.record_id, rec.metadata   # value + provenance metadata

# DB-backed batch: inputs/outputs are variable *types*, loaded and saved for you
for_each(
    process_signal,
    inputs={"raw": RawSignal},
    outputs=[ProcessedSignal],
    subject=[1, 2, 3],
    session=["A", "B"],
)
```

`load(..., version="all")` returns a generator over every stored version instead
of the latest one. scidb has **first-class MATLAB support** via `scidb.*` (see
[MATLAB Setup](../matlab-setup.md)). Lineage tracking here is *optional*: if
scilineage is installed and you pass a `@lineage_fcn`, provenance is recorded —
but scidb does not wrap your functions for you.

---

## scihist — full reproducible pipelines

**What it adds:** everything scidb does, plus it **automatically wraps your
functions in lineage tracking** and adds node-state / staleness logic — the
machinery that lets a pipeline recompute only the outputs that are actually out
of date. It exposes the *same* `for_each` interface as scidb.

**Choose this when:** you want the full story — persisted, versioned results
*and* automatic provenance *and* "only recompute what's stale" behavior.

```python
from scihist import for_each, Fixed, configure_database
from scilineage import lineage_fcn

configure_database("experiment.duckdb", ["subject", "session"])

@lineage_fcn
def process_data(raw, calibration):
    return raw * calibration

for_each(
    process_data,
    inputs={"raw": RawData, "calibration": Fixed(Calibration, session="baseline")},
    outputs=[ProcessedData],
    subject=[1, 2, 3],
    session=["A", "B", "C"],
)
```

Because scihist drives the database through scidb, its storage and batch features
work with the MATLAB bridge; the `@lineage_fcn` decorator itself is Python.
See [Node States](../concepts/node-states.md) for how staleness is decided.

---

## How the layers stack

Each layer depends only on the ones below it, so adopting a higher layer never
takes a capability away:

- **scihist** → scidb + scilineage
- **scidb** → scifor + sciduckdb + scicanonicalhash + scipathgen
- **scilineage** → scicanonicalhash

Practical path: prototype your analysis function against plain tables with
**scifor**; move to **scidb** when results need to persist; adopt **scihist**
when you want provenance and stale-aware recomputation. Reach for **scilineage**
directly only when you need provenance without batch iteration or a database.

**Next:** [Installation](installation.md) · [Quickstart](../quickstart.md) ·
[Architecture & Layers](../concepts/architecture.md)
