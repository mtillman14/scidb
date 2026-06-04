# Caching Computations

<!-- Ground truth (tests/source win over prose). Verified against:
     scihist/tests/test_skip_computed.py (skip_computed default True; second run -> [skip];
       skip_computed=False bypasses; input change -> [recompute] only affected combo;
       constants are independent variants; output saved without lineage -> always recompute);
     scihist/tests/test_cache_hit.py (save(VarClass, result) then reload + re-run same
       @lineage_fcn -> cache hit, function not re-called);
     scihist/tests/test_generates_file.py (@lineage_fcn(generates_file=True); save(Figure, result)
       -> id starts "generated:"; re-run cache hit -> result.data is None, result.is_complete True;
       different inputs -> executes; idempotent save);
     scilineage/src/scilineage/core.py lineage_fcn(..., generates_file=False);
     scihist.configure_database wires the db as the scilineage cache backend.
     NOTE: `@thunk` / `Thunk.query` / "PipelineDB (SQLite)" are stale — the decorator is
     @lineage_fcn, lineage lives in the same DuckDB, and lineage results persist via scihist.save. -->

SciStack reuses results instead of recomputing them. This guide shows the two
practical ways that happens and how to control them. For the model behind it, see
[Computation Caching](../concepts/caching.md). Caching relies on `scihist` —
import `configure_database` from `scihist` so the database is registered as the
cache backend.

## Batch caching with `for_each`

The common case: `scihist.for_each` runs `skip_computed=True` by default, so a
re-run executes only the combinations whose outputs are missing or out of date.
Each run prints `[skip]` / `[recompute]` lines so you can see what it decided:

```python
from scihist import for_each

for_each(process, inputs={"x": RawSignal}, outputs=[Filtered],
         subject=[1, 2, 3], session=["A"])   # first run: all compute

for_each(process, inputs={"x": RawSignal}, outputs=[Filtered],
         subject=[1, 2, 3], session=["A"])   # second run: all [skip]
```

- **Change one input** (re-save it with different data) and only *that*
  combination recomputes; the rest still skip.
- **Edit the function or pass a new constant value** and the affected results
  recompute (a new constant is a new [variant](../concepts/caching.md), so old
  results are kept, not overwritten).
- **Force a full re-run** with `skip_computed=False`.

```python
for_each(process, inputs={"x": RawSignal}, outputs=[Filtered],
         skip_computed=False, subject=[1, 2, 3], session=["A"])
```

An output written with a plain `VariableClass.save()` (no lineage) can't be proven
current, so `for_each` always recomputes it — another reason to persist pipeline
outputs through `for_each` or `scihist.save`.

## Per-call caching with lineage

Outside of `for_each`, a `@lineage_fcn` call is itself cached. Persist a result
with `scihist.save`, and re-running the same function on the same input returns
the stored result **without executing again** — even after reloading the input or
in a separate script:

```python
from scihist import save
from scilineage import lineage_fcn

@lineage_fcn
def double(x):
    print("computing")     # prints only on the first run
    return x * 2

RawSignal.save(np.array([1, 2, 3]), subject=1)
result = double(RawSignal.load(subject=1))
save(SignalOut, result, subject=1)        # records the result + its lineage

# later, or in another script
again = double(RawSignal.load(subject=1))  # cache hit — "computing" does NOT print
```

This works because `scihist.configure_database` registers the database as
scilineage's cache backend, and saved results carry the lineage hash used as the
lookup key.

## What counts as the "same" computation

A cache hit requires all of:

- the **same function** (its bytecode hash — reformatting doesn't matter, changing
  what it computes does),
- the **same inputs** (saved variables by `record_id`, unsaved values by content),
- the **same constants** (a different constant value is a separate variant).

So cache *misses* happen on the first run, when an input's data changes, when the
function's code changes, or for a brand-new constant value. You never invalidate
manually — changing any ingredient simply produces a new identity.

!!! tip "Stable cache keys"
    Pass *loaded variables* to your functions rather than raw arrays. A loaded
    variable has a `record_id`, giving a stable key; an inline `np.array(...)` is
    keyed by its content each time.

## Side-effect steps that write files

Some steps produce a file — a plot, a report — instead of data to store. Mark them
with `generates_file=True` so they still get cache-hit skipping:

```python
@lineage_fcn(generates_file=True)
def plot_signal(data):
    plt.plot(data)
    plt.savefig("signal.png")
    return None

result = plot_signal(ProcessedData.load(subject=1))
save(Figure, result, subject=1)     # records lineage only; id starts "generated:"
```

On a later run with the same input, the function is **skipped**: the cached result
has `data is None` and `is_complete is True`, and nothing is re-plotted. Different
inputs run it again. This works inside `for_each` too — pass `as_table=True` when
the function needs the current schema-key values as arguments.

**Next:** [Node States](../concepts/node-states.md) ·
[Batch Processing (for_each)](for_each.md) · [Tracking Lineage](lineage.md) ·
[Concept: Computation Caching](../concepts/caching.md)
