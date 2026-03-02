# scifor

Standalone `for_each` batch execution utilities for data pipelines.

Works with plain DataFrames, file I/O, or any custom `.load()`/`.save()` implementation.
No database required.

Available in both **Python** and **MATLAB**.

## What `for_each()` replaces

A typical pipeline iterates over every combination of subjects and sessions,
loads data, processes it, and saves results. Written by hand:

**Python**
```python
subjects = [1, 2, 3]
sessions = ["pre", "post"]

for subject in subjects:
    for session in sessions:
        df = pd.read_csv(f"data/{subject}/{session}.csv")
        result = bandpass_filter(df["emg"].values)
        out = pd.DataFrame({"emg": result})
        out.to_csv(f"results/{subject}/{session}.csv", index=False)
```

**MATLAB**
```matlab
subjects = [1, 2, 3];
sessions = ["pre", "post"];

for i = 1:numel(subjects)
    for j = 1:numel(sessions)
        tbl = readtable(sprintf("data/%d/%s.csv", subjects(i), sessions(j)));
        result = bandpass_filter(tbl.emg);
        writetable(table(result, 'VariableNames', {'emg'}), ...
            sprintf("results/%d/%s.csv", subjects(i), sessions(j)));
    end
end
```

With `for_each()`, the same pipeline becomes:

**Python**
```python
from scifor import set_schema, for_each, CsvFile

set_schema(["subject", "session"])

raw      = CsvFile("data/{subject}/{session}.csv")
filtered = CsvFile("results/{subject}/{session}.csv")

results = for_each(
    bandpass_filter,
    inputs={"emg": raw},
    outputs=[filtered],
    subject=[1, 2, 3],
    session=["pre", "post"],
)
```

**MATLAB**
```matlab
scifor.set_schema(["subject", "session"]);

raw      = scifor.CsvFile("data/{subject}/{session}.csv");
filtered = scifor.CsvFile("results/{subject}/{session}.csv");

results = scifor.for_each(@bandpass_filter, ...
    struct('emg', raw), {filtered}, ...
    'subject', [1, 2, 3], ...
    'session', ["pre", "post"]);
```

The function body stays clean. `for_each()` handles the loop, the I/O, and
returns a table of results indexed by subject and session.

## Python Usage

```python
import pandas as pd
from scifor import set_schema, for_each, Col

set_schema(["subject", "session"])

raw_df = pd.DataFrame({
    "subject": [1, 1, 2, 2],
    "session": ["pre", "post", "pre", "post"],
    "emg": [...],
})

filtered = CsvFile("results/{subject}/{session}.csv")

results = for_each(
    my_fn,
    inputs={"signal": raw_df},
    outputs=[filtered],
    subject=[1, 2],
    session=["pre", "post"],
)
```

## MATLAB Usage

The `+scifor` namespace is part of the `scidb-matlab` package. Both `for_each`
and its supporting utilities (schema management, filters, file I/O) live in
the `scifor` namespace. `scidb.for_each()` is a thin passthrough for
backward compatibility.

```matlab
% Set the schema key list once (called automatically by scidb.configure_database)
scifor.set_schema(["subject", "session"]);

% Run a function over all subject/session combinations
% Inputs can be plain tables, scifor.CsvFile, scifor.MatFile, or constants
filtered = scifor.CsvFile("results/{subject}/{session}.csv");

results = scifor.for_each(@my_fn, ...
    struct('signal', raw_tbl), ...
    {filtered}, ...
    'subject', [1, 2], ...
    'session', ["pre", "post"]);

% Column-based filtering
f = (scifor.Col("side") == "R") & (scifor.Col("speed") > 1.5);
results = scifor.for_each(@my_fn, struct('data', raw_tbl), {filtered}, ...
    'subject', [1, 2], 'where', f);

% File-backed I/O without a database
csv = scifor.CsvFile('/data/{subject}/{session}.csv');
mat = scifor.MatFile('/data/{subject}/{session}.mat');

results = scifor.for_each(@my_fn, struct('signal', csv), {mat}, ...
    'subject', [1, 2], 'session', ["pre", "post"]);
```
