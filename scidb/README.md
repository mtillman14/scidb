# SciDB

Database operations layer for SciStack. Provides abstractions for defining typed variables, configuring the database, and saving/loading data by metadata.

## Named Filters (value-based, reusable)

`Filter` objects are first-class values — assign them to a variable and reuse
them in any `where=` clause, or compose them with `&` / `|` / `~`:

```python
# Define once (this IS a ColumnFilter — no special wrapper needed)
clean_gr = GAITRiteLoadedCycle["StepLengths_GR"] != 0

# Use anywhere
for_each(mean_change_from_reference,
         inputs={"baseline": Fixed(GAITRiteLoadedCycle["StepLengths_GR"], session="BL"),
                 "value":    GAITRiteLoadedCycle["StepLengths_GR"]},
         outputs=[DeltaStepLength],
         where=clean_gr & (UAStartFoot() == "A"))

# Compose named filters
clean_and_unilateral = clean_gr & (UAStartFoot() == "U")
for_each(..., where=clean_and_unilateral)
```

MATLAB equivalent:

```matlab
clean_gr = GAITRiteLoadedCycle("StepLengths_GR") ~= 0;
scidb.for_each(@meanChangeFromReference, ..., where=clean_gr & (UAStartFoot() == "A"));
```

## Permanent Schema-Level Exclusions

For data that should be excluded from **every** analysis (e.g., a failed
recording session), use the exclusion registry instead of per-call filters.

```python
# Mark a specific trial as excluded (persisted in the database)
scidb.exclude_schema(subject=1, trial=2,
                     reason="equipment malfunction during recording")

# Exclude an entire subject (trial omitted = wildcard)
scidb.exclude_schema(subject=3, reason="participant withdrew")

# Inspect currently-excluded combinations
exclusions_df = scidb.list_exclusions()

# Re-include (logged; the original exclusion row is preserved)
scidb.include_schema(subject=1, trial=2,
                     reason="re-reviewed video, recording was valid")
```

MATLAB equivalent:

```matlab
scidb.exclude_schema("equipment malfunction", 'subject', 1, 'trial', 2)
scidb.include_schema("re-reviewed, recording was valid", 'subject', 1, 'trial', 2)
tbl = scidb.list_exclusions()
```

Exclusions are applied automatically by `for_each` before the iteration loop.
The full exclusion table is hashed and stored in `version_keys`
(`__schema_overrides_hash`) so that adding or removing an exclusion
invalidates cached results.

```python
from scidb import configure_database, BaseVariable
import numpy as np

db = configure_database("experiment.duckdb", ["subject", "session"])

class RawSignal(BaseVariable):
    schema_version = 1

RawSignal.save(np.array([1, 2, 3]), subject=1, session="A")
(raw,) = RawSignal.load(subject=1, session="A")  # generator; unpack for single result
all_versions = list(RawSignal.load(subject=1, session="A", version="all"))
```