# EachOf — Generalized Variant Expansion

## Problem

Before `EachOf`, variants in `for_each()` were only created by different constant values (e.g., `low_hz=20` vs `low_hz=30`). Two other natural sources of variation had no concise expression:

1. **Multiple variable types** feeding the same input parameter (e.g., running the same statistical test on `StepLength` and `StepTime`)
2. **Multiple `where=` filters** selecting different schema-id subsets (e.g., left steps vs right steps vs all steps)

Without `EachOf`, both required separate `for_each()` calls with duplicated arguments.

## Solution

`EachOf` is a wrapper that means "iterate over these alternatives as separate variants." It can wrap any of three things:

- **Variable types** in `inputs`: `EachOf(StepLength, StepTime)`
- **Constants** in `inputs`: `EachOf(0.05, 0.01)`
- **`where=` filters**: `EachOf(Side == "L", Side == "R", None)`

Multiple `EachOf` axes combine as a cartesian product. A single `for_each()` call with all three axes:

```python
for_each(
    run_anova,
    inputs={
        "metric": EachOf(CadenceVar, StrideVelocity),
        "alpha": EachOf(0.05, 0.01),
    },
    outputs=[AnovaResult],
    where=EachOf(Where(side="L"), Where(side="R"), None),
    subject=[], session=[],
)
```

produces `2 types x 2 alphas x 3 filters = 12` variant branches, each iterating over all `(subject, session)` combinations.

## Key design properties

1. **Single-value collapse**: `EachOf(X)` behaves identically to passing `X` directly. No special case needed — there is simply one iteration of one alternative.

2. **No downstream changes**: `EachOf` is resolved at the very top of `for_each()` by expanding into multiple recursive calls, each with concrete values. All existing machinery (version_keys, branch_params, rid expansion, save/load) sees only concrete values and works unchanged.

3. **Natural discrimination**: Each axis already produces distinct records:
   - Different variable types produce different `__inputs` version keys
   - Different constants produce different `__constants` version keys and `branch_params`
   - Different `where=` filters produce different `__where` version keys

4. **Incremental**: Adding a second alternative later (e.g., going from `alpha=0.05` to `EachOf(0.05, 0.01)`) creates new records that coexist with existing ones. Nothing is overwritten.

## Implementation

- **`scidb/src/scidb/each_of.py`** — `EachOf` class (holds `alternatives` list)
- **`scidb/src/scidb/foreach.py`** — expansion logic at top of `for_each()`: scans inputs and `where` for `EachOf` instances, computes cartesian product, recursively calls `for_each()` with concrete values, concatenates results
- **`scidb/src/scidb/__init__.py`** — `EachOf` exported as public API

## Relationship to existing variant machinery

`EachOf` sits above the existing variant system, not alongside it. The hierarchy:

```
EachOf expansion (top of for_each — recursive decomposition)
  |
  v
ForEachConfig / version_keys (constants, inputs, where serialization)
  |
  v
rid expansion / branch_params (upstream variant tracking across pipeline steps)
  |
  v
save / load / list_versions (DB-level record discrimination)
```

Each layer is unaware of `EachOf`. By the time any downstream code runs, it sees a normal `for_each()` call with concrete values.
