# Quickstart

<!-- Ground truth (tests/source win over prose). Verified against:
     scidb/src/scidb/{variable,database}.py (BaseVariable.schema_version; save->record_id;
       load->.data/.record_id/.metadata; configure_database; get_provenance ->
       {function_name, function_hash, inputs, constants});
     scihist/src/scihist/{__init__,foreach,database}.py (configure_database wires the
       lineage cache backend via configure_backend; for_each(inputs=, outputs=);
       save(variable_class, data, **metadata) persists a LineageFcnResult WITH lineage);
     scihist/tests/test_cache_hit.py (save(VarClass, result, ...); reload->cache hit);
     scihist/tests/test_skip_computed.py (second for_each run skips current combos);
     scilineage/tests/test_core.py (@lineage_fcn -> LineageFcnResult, value on .data).
     NOTE: `Thunk` is NOT a real export; persist lineage results with scihist.save. -->

Go from raw data to a cached, provenance-tracked pipeline in a few minutes. This
uses the top layer, `scihist`, which gives you typed storage, automatic lineage,
and caching together. (You can also enter lower — see
[Choosing Your Layer](getting-started/choosing-a-layer.md).)

## Install

SciStack is a set of packages installed in dependency order. See
[Installation](getting-started/installation.md) for the full setup; once done,
the imports below resolve.

## 1. Define variable types

A *variable* is a typed kind of result, defined as a `BaseVariable` subclass. For
scalars, numpy arrays, lists, dicts, and DataFrames you don't write any
serialization code:

```python
import numpy as np
from scidb import BaseVariable

class RawSignal(BaseVariable):
    schema_version = 1

class SignalPower(BaseVariable):
    schema_version = 1
```

`schema_version` stamps the variable's structure — bump it whenever its layout
changes. (See [Variables & Storage](concepts/variables.md).)

## 2. Configure the database

Declare where data lives and which metadata keys are your experiment's
*conditions*. Importing `configure_database` from `scihist` also wires up lineage
caching:

```python
from scihist import configure_database

db = configure_database("experiment.duckdb", ["subject", "session"])
```

## 3. Save and load by metadata

`save` returns a content-addressed `record_id`; `load` returns the value plus its
provenance metadata:

```python
RawSignal.save(np.sin(np.linspace(0, 2 * np.pi, 100)), subject=1, session="A")

raw = RawSignal.load(subject=1, session="A")
raw.data        # the numpy array
raw.record_id   # content-addressed id (same data + coords -> same id)
raw.metadata    # {"subject": 1, "session": "A"}
```

## 4. Process with lineage

Decorate a processing function with `@lineage_fcn`. Calling it returns a result
that carries provenance; the value is on `.data`. Persist it with `scihist.save`
so the lineage is recorded too:

```python
from scihist import save, lineage_fcn

@lineage_fcn
def compute_power(signal):
    return float(np.mean(signal ** 2))

power = compute_power(raw)          # a LineageFcnResult; value on power.data
save(SignalPower, power, subject=1, session="A")   # persists WITH lineage
```

Now you can ask what produced a stored result:

```python
prov = db.get_provenance(SignalPower, subject=1, session="A")
prov["function_name"]   # "compute_power"
prov["inputs"]          # the variable inputs it consumed
prov["constants"]       # any literal parameters
```

## 5. Scale it to a batch

The same function runs across every combination of conditions with `for_each`,
which loads each input and saves each output for you. First seed some inputs,
then process them all:

```python
from scihist import for_each

for s in (1, 2, 3):
    RawSignal.save(np.random.randn(100), subject=s, session="A")

for_each(
    compute_power,
    inputs={"signal": RawSignal},
    outputs=[SignalPower],
    subject=[1, 2, 3],
    session=["A"],
)
```

Each `SignalPower` is saved with full lineage — no loops, no manual bookkeeping.

## 6. Re-runs are cached

Run the exact same `for_each` again and nothing recomputes — every combination is
already current, so `compute_power` is never called:

```python
for_each(compute_power, inputs={"signal": RawSignal}, outputs=[SignalPower],
         subject=[1, 2, 3], session=["A"])   # all combos skipped
```

Change an input's data (giving it a new `record_id`) or edit the function, and
only the affected results recompute. (See [Computation Caching](concepts/caching.md).)

## Next steps

- [Choosing Your Layer](getting-started/choosing-a-layer.md) — enter at the level
  you need (`scifor` / `scidb` / `scihist`)
- [VO2 Max Walkthrough](guide/walkthrough.md) — a full example pipeline
- [Concepts](concepts/index.md) — how variables, lineage, caching, and hashing fit
  together
- [MATLAB Setup](matlab-setup.md) — the same workflow from MATLAB
