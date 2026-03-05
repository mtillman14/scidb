# SciEco

## Better Research Tools, Better Research Outcomes

SciEco is a set of tools for scientific data analysis. It handles the repetitive infrastructure that every scientist ends up building — looping over experimental conditions, organizing results, tracking which function produced what — so you can focus on the analysis itself.

It works in both **Python** and **MATLAB**.

## The Problem

Every scientist who writes analysis code eventually builds the same thing: a tangle of folders, naming conventions, and bookkeeping scripts to track which data came from where, which version of a function produced it, and whether it's already been computed.

That infrastructure code is never the point. But it eats weeks of your time, it's fragile, and it's different in every lab.

## Three Layers, Use What You Need

SciEco is organized as three layers. Each one builds on the one below it, and you only need to use the layers that make sense for your project.

### Layer 1: scifor — Loop Orchestration

The lightest layer. Works with plain tables (MATLAB tables or pandas DataFrames) — no database, no setup beyond a one-liner. If you have data in tables and you're tired of writing nested loops, this is all you need.

```python
from scifor import set_schema, for_each

set_schema(["subject", "session"])

results = for_each(
    bandpass_filter,
    inputs={"signal": raw_df, "low_hz": 20},
    subject=[1, 2, 3],
    session=["pre", "post"],
)
```

```matlab
scifor.set_schema(["subject", "session"]);

results = scifor.for_each(@bandpass_filter, ...
    struct('signal', raw_tbl, 'low_hz', 20), ...
    subject=[1, 2, 3], session=["pre", "post"]);
```

You tell scifor which columns identify your experimental conditions (the "schema"), and it loops over every combination, filters each table to matching rows, calls your function, and collects the results into a clean output table.

scifor is standalone and has no dependencies beyond standard data structures. It can be dropped into any project.

See the [scifor README](scifor/README.md) for more.

### Layer 2: scidb — Database Storage

Wraps scifor with a database layer. Instead of working with tables you've already loaded, scidb loads inputs from a DuckDB database and saves results back. You define named variable types for each kind of data in your pipeline, and scidb gives you structured, queryable storage with metadata-based addressing.

```python
from scidb import BaseVariable, configure_database, for_each

# One-time setup
db = configure_database("experiment.duckdb", ["subject", "session"])

# Define variable types (one-liners)
class RawEMG(BaseVariable):
    pass

class FilteredEMG(BaseVariable):
    pass

# Save data with metadata
import numpy as np
RawEMG.save(np.random.randn(1000), subject=1, session="pre")

# Load it back
raw = RawEMG.load(subject=1, session="pre")
print(raw.data)  # your numpy array

# Batch processing — loads from DB, runs function, saves results
for_each(
    bandpass_filter,
    inputs={"signal": RawEMG, "low_hz": 20},
    outputs=[FilteredEMG],
    subject=[1, 2, 3],
    session=["pre", "post"],
)
```

```matlab
scidb.configure_database("experiment.duckdb", ["subject", "session"]);

RawEMG().save(randn(1000, 1), subject=1, session="pre");
raw = RawEMG().load(subject=1, session="pre");

scidb.for_each(@bandpass_filter, ...
    struct('signal', RawEMG(), 'low_hz', 20), ...
    {FilteredEMG()}, ...
    subject=[1 2 3], session=["pre" "post"]);
```

Because your data lives in a real database, you can query it with SQL, view it in tools like [DBeaver](https://dbeaver.com), and load slices of it by any metadata combination — no folder traversal or filename parsing.

### Layer 3: scihist — Lineage and Caching

Wraps scidb with automatic provenance tracking. When you wrap a function with `@thunk`, scihist records which function produced each result, what inputs it received, and what parameter values were used. If you run the same computation again with the same inputs, it returns the cached result instead of recomputing.

```python
from thunk import thunk

@thunk
def bandpass_filter(signal, low_hz, high_hz):
    # your filtering logic
    return filtered_signal

# Run the pipeline — lineage is tracked automatically
raw = RawEMG.load(subject=1, session="pre")
filtered = bandpass_filter(raw, low_hz=20, high_hz=450)
FilteredEMG.save(filtered, subject=1, session="pre")

# Later: "What function produced this?"
provenance = db.get_provenance(FilteredEMG, subject=1, session="pre")
print(provenance["function_name"])  # "bandpass_filter"
print(provenance["constants"])      # {"low_hz": 20, "high_hz": 450}

# Run the same pipeline again — cache hit, no recomputation
filtered = bandpass_filter(raw, low_hz=20, high_hz=450)  # returns instantly
```

```matlab
db = scihist.configure_database("experiment.duckdb", ["subject", "session"]);

filter_fn = scidb.Thunk(@bandpass_filter);
raw = RawEMG().load(subject=1, session="pre");
filtered = filter_fn(raw, 20, 450);
FilteredEMG().save(filtered, subject=1, session="pre");
```

Your functions stay as plain functions — they receive normal arrays and return normal values. The `@thunk` decorator handles the bookkeeping at the boundary.

## What a Full Pipeline Looks Like

Here's a complete pipeline using all three layers:

```python
from scidb import BaseVariable, configure_database, for_each
from thunk import thunk

# --- Setup ---
db = configure_database("gait_study.duckdb", ["subject", "session", "trial"])

# --- Variable types ---
class RawKinematicData(BaseVariable):
    pass

class StepLength(BaseVariable):
    pass

class MeanStepLength(BaseVariable):
    pass

# --- Processing functions ---
@thunk
def extract_step_length(kinematic_data):
    # your biomechanics logic here
    return step_lengths

@thunk
def compute_mean(values):
    return float(np.mean(values))

# --- Run the pipeline ---
for_each(
    extract_step_length,
    inputs={"kinematic_data": RawKinematicData},
    outputs=[StepLength],
    subject=[1, 2, 3],
    session=["pre", "post"],
    trial=[1, 2, 3, 4, 5],
)

for_each(
    compute_mean,
    inputs={"values": StepLength},
    outputs=[MeanStepLength],
    subject=[1, 2, 3],
    session=["pre", "post"],
)

# --- Analyze results ---
df = MeanStepLength.load_all(as_df=True)
print(df.groupby("session")["data"].mean())
```

No file I/O code. No path management. No version tracking logic.

Change a function's logic or a parameter value, and the next run will recompute only the affected steps. Previous results are preserved — you can load any version by its metadata.

## Querying Your Data

Because data is stored in DuckDB, you can query it from Python, MATLAB, SQL, or any tool that speaks SQL:

```python
# Load one record
emg = FilteredEMG.load(subject=3, session="post")

# Load all sessions for a subject
all_sessions = FilteredEMG.load(subject=3)

# Load everything as a DataFrame
df = FilteredEMG.load_all(as_df=True)
```

```sql
SELECT subject, session, value
FROM FilteredEMG;
```

## Cross-Language Support

Data saved from Python can be loaded in MATLAB and vice versa. The MATLAB API mirrors the Python API closely:

```matlab
scidb.configure_database("experiment.duckdb", ["subject", "session"]);

RawEMG().save(randn(1000, 1), subject=1, session="pre");
raw = RawEMG().load(subject=1, session="pre");

scidb.for_each(@bandpass_filter, ...
    struct('signal', RawEMG(), 'low_hz', 20), ...
    {FilteredEMG()}, ...
    subject=[1 2 3], session=["pre" "post"]);
```

## Installation

```bash
pip install scidb
```

This pulls in all core dependencies (`sciduckdb`, `thunk`, `scipathgen`, `canonicalhash`, `scirun`).

For development (editable installs of all packages):

```bash
git clone https://github.com/mtillman14/general-sqlite-database
cd general-sqlite-database
./dev-install.sh
```

## Learn More

- [Quickstart Guide](docs/quickstart.md) — Get running in 5 minutes
- [VO2 Max Walkthrough](docs/guide/walkthrough.md) — Full example pipeline with design explanations
- [Variables Guide](docs/guide/variables.md) — Deep dive into variable types
- [Lineage Guide](docs/guide/lineage.md) — How provenance tracking works
- [Batch Processing Guide](docs/guide/for_each.md) — for_each in depth
- [API Reference](docs/api.md) — Complete API documentation
