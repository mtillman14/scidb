# Filters API — `where=` Parameter

Filters allow you to load data conditionally based on the values of other variables. Use the `where=` parameter in `load()`, `load_all()`, and `for_each()` to filter which records are loaded.

---

## Quick Start

=== "Python"

    ```python
    # Simple equality filter
    StepLength.load_all(where=Side == "L")

    # Combine filters with & (AND) and | (OR)
    StepLength.load_all(where=(Side == "L") & (Speed > 1.2))
    StepLength.load_all(where=(Side == "L") | (Side == "R"))

    # Negate with ~
    StepLength.load_all(where=~(Side == "L"))

    # Column-specific filtering (tabular variables)
    StepLength.load_all(where=GaitData["side"] == "L")

    # Use in for_each
    for_each(fn, inputs, outputs, where=Side == "L", subject=[1, 2, 3])
    ```

=== "MATLAB"

    ```matlab
    % Simple equality filter
    StepLength().load_all(where=Side() == "L")

    % Combine filters with & (AND) and | (OR)
    StepLength().load_all(where=(Side() == "L") & (ScalarVar() > 1.2))
    StepLength().load_all(where=(Side() == "L") | (Side() == "R"))

    % Negate with ~
    StepLength().load_all(where=~(Side() == "L"))

    % Column-specific filtering (tabular variables)
    StepLength().load_all(where=GaitData("side") == "L")

    % Use in for_each
    scidb.for_each(@fn, inputs, {Out()}, where=Side() == "L", subject=[1 2 3])
    ```

---

## MATLAB: CRITICAL — Use `&` not `&&` for Filter Combination

!!! danger "Common Error"
    In MATLAB, you **MUST** use `&` (bitwise AND) to combine filters, **NOT** `&&` (logical AND).

    ```matlab
    % ❌ WRONG - This will error: "Conversion to logical from scidb.Filter is not possible"
    where=Side() == "L" && Speed() > 1.2

    % ✅ CORRECT - Use single & operator
    where=(Side() == "L") & (Speed() > 1.2)
    ```

**Why?** In MATLAB:

- `&&` is short-circuit logical AND that requires both sides to be convertible to `true`/`false`
- `&` is element-wise AND that can be overloaded for custom objects like `scidb.Filter`
- `scidb.Filter` objects cannot be converted to logical values, so `&&` fails

The same applies to OR:

```matlab
% ❌ WRONG
where=Side() == "L" || Side() == "R"

% ✅ CORRECT
where=(Side() == "L") | (Side() == "R")
```

**Tip:** Always use parentheses when combining filters to ensure correct operator precedence.

---

## Creating Filters

### Comparison Operators

All standard comparison operators are supported:

=== "Python"

    ```python
    Side == "L"           # equality
    Side != "L"           # inequality
    Speed > 1.2           # greater than
    Speed >= 1.2          # greater than or equal
    Speed < 0.8           # less than
    Speed <= 0.8          # less than or equal
    ```

=== "MATLAB"

    ```matlab
    Side() == "L"         % equality
    Side() ~= "L"         % inequality (note: ~= not !=)
    Speed() > 1.2         % greater than
    Speed() >= 1.2        % greater than or equal
    Speed() < 0.8         % less than
    Speed() <= 0.8        % less than or equal
    ```

**Note:** These operators create filter objects. They do NOT evaluate to true/false.

### Compound Filters (AND / OR)

=== "Python"

    ```python
    # AND - both conditions must be true
    (Side == "L") & (Speed > 1.2)

    # OR - either condition must be true
    (Side == "L") | (Side == "R")

    # Complex combinations
    ((Side == "L") & (Speed > 1.0)) | ((Side == "R") & (Speed < 0.8))
    ```

=== "MATLAB"

    ```matlab
    % AND - both conditions must be true (use & not &&)
    (Side() == "L") & (Speed() > 1.2)

    % OR - either condition must be true (use | not ||)
    (Side() == "L") | (Side() == "R")

    % Complex combinations
    ((Side() == "L") & (Speed() > 1.0)) | ((Side() == "R") & (Speed() < 0.8))
    ```

### NOT Filter

=== "Python"

    ```python
    # Negate a filter
    ~(Side == "L")           # everything except L
    ~((Side == "L") & (Speed > 1.0))  # negate a compound filter
    ```

=== "MATLAB"

    ```matlab
    % Negate a filter
    ~(Side() == "L")         % everything except L
    ~((Side() == "L") & (Speed() > 1.0))  % negate a compound filter
    ```

---

## Column Filtering

When your variable stores a multi-column table, you can filter on specific columns:

=== "Python"

    ```python
    # Filter on a specific column (not the default "value" column)
    StepLength.load_all(where=GaitData["side"] == "L")
    StepLength.load_all(where=GaitData["speed"] > 1.5)

    # Combine column filters
    StepLength.load_all(
        where=(GaitData["side"] == "L") & (GaitData["speed"] > 1.5)
    )

    # Mix column filters with whole-variable filters
    StepLength.load_all(
        where=(GaitData["side"] == "L") & (Side == "L")
    )
    ```

=== "MATLAB"

    ```matlab
    % Filter on a specific column (not the default "value" column)
    StepLength().load_all(where=GaitData("side") == "L")
    StepLength().load_all(where=GaitData("speed") > 1.5)

    % Combine column filters (remember: use & not &&)
    StepLength().load_all( ...
        where=(GaitData("side") == "L") & (GaitData("speed") > 1.5))

    % Mix column filters with whole-variable filters
    StepLength().load_all( ...
        where=(GaitData("side") == "L") & (Side() == "L"))
    ```

**Technical note:** Column filtering is for the WHERE clause, not for data extraction. To extract specific columns as inputs, use column selection in the input specification (see [for_each.md](for-each.md#column-selection)).

---

## Raw SQL Filters

For advanced use cases, you can provide raw SQL that operates on the target variable's data table:

=== "Python"

    ```python
    from scidb import raw_sql

    # Raw SQL applied to target variable's "value" column
    StepLength.load_all(where=raw_sql('"value" > 0.70'))

    # Can reference any column in the target variable's table
    GaitData.load_all(where=raw_sql('"side" = \'L\' AND "speed" > 1.2'))
    ```

=== "MATLAB"

    ```matlab
    % Raw SQL applied to target variable's "value" column
    StepLength().load_all(where=scidb.raw_sql('"value" > 0.70'))

    % Can reference any column in the target variable's table
    GaitData().load_all(where=scidb.raw_sql('"side" = ''L'' AND "speed" > 1.2'))
    ```

**Caution:** `raw_sql()` is an escape hatch for cases not covered by the standard operators. You must:

- Use proper SQL syntax (DuckDB dialect)
- Quote column names with double quotes if they might be reserved keywords
- Handle SQL injection risks if building SQL from user input

**Error handling:** DuckDB syntax errors are caught and re-raised with a descriptive message.

---

## Using Filters with `where=`

### In `load_all()`

=== "Python"

    ```python
    # Load only records where filter condition is true
    results = StepLength.load_all(
        where=Side == "L",
        subject=[1, 2, 3]
    )
    ```

=== "MATLAB"

    ```matlab
    % Load only records where filter condition is true
    results = StepLength().load_all( ...
        where=Side() == "L", ...
        subject=[1 2 3]);
    ```

### In `load()`

=== "Python"

    ```python
    # Load single record with filter
    result = StepLength.load(
        subject=1,
        session="A",
        where=Side == "L"
    )
    ```

=== "MATLAB"

    ```matlab
    % Load single record with filter
    result = StepLength().load( ...
        subject=1, ...
        session="A", ...
        where=Side() == "L");
    ```

### In `for_each()`

The `where=` parameter filters which iterations run:

=== "Python"

    ```python
    for_each(
        compute_metrics,
        {"signal": RawEMG, "baseline": Fixed(Baseline, session="BL")},
        [Metrics],
        where=Side == "L",
        subject=[1, 2, 3],
        session=["A", "B", "C"]
    )
    # Only runs for iterations where Side == "L"
    ```

=== "MATLAB"

    ```matlab
    scidb.for_each(@compute_metrics, ...
        struct('signal', RawEMG(), 'baseline', scidb.Fixed(Baseline(), session="BL")), ...
        {Metrics()}, ...
        where=Side() == "L", ...
        subject=[1 2 3], session=["A" "B" "C"]);
    % Only runs for iterations where Side == "L"
    ```

**Multi-step filters in for_each:**

=== "Python"

    ```python
    # Combine multiple filter conditions
    for_each(
        fn,
        inputs,
        outputs,
        where=(Side == "L") & (Speed > 1.2) & (Quality["valid"] == True),
        subject=[1, 2, 3]
    )
    ```

=== "MATLAB"

    ```matlab
    % Combine multiple filter conditions (use & not &&)
    scidb.for_each(@fn, inputs, {Out()}, ...
        where=(Side() == "L") & (Speed() > 1.2) & (Quality("valid") == true), ...
        subject=[1 2 3]);
    ```

---

## How Filters Work

### Schema-Level Filtering

Filters are resolved **before** data is loaded:

1. The filter variable (e.g., `Side`) is queried to get its values at all matching schema locations
2. Only `schema_id`s where the filter condition is true are kept
3. The target variable (e.g., `StepLength`) is loaded only for those `schema_id`s

This is efficient — no unnecessary data is loaded from the database.

### Latest Version Semantics

Filters always use the **latest version** of the filter variable at each schema location. There is no mechanism to filter on a specific version of the filter variable.

### Schema Level Validation

**Filters must be at the same or coarser schema level than the target:**

✅ **OK:** Filter at `subject` level, target at `trial` level (coarser → finer)
✅ **OK:** Filter at `trial` level, target at `trial` level (same level)
❌ **Error:** Filter at `trial` level, target at `subject` level (finer → coarser)

**Example error message:**
```
Filter variable 'Side' is stored at schema level 'trial' which is finer than
target 'StepLength' at level 'subject'. Filters must be at the same or coarser
level than the target.
```

### Coverage Validation

Every schema location in the target must have a corresponding filter value:

❌ **Error if incomplete:**
```
Filter variable 'Side' is missing data at 2 schema locations that 'StepLength'
has data for. Ensure the filter variable covers all target locations.
```

**Fix:** Save the filter variable at all schema locations where the target has data.

---

## Limitations

### Version-Specific Filtering

Filters always use the latest version of the filter variable. You cannot specify a particular version to filter on.

### Cross-Database Filters

The filter variable must be in the same database as the target variable.

### Filters with Merge

`where=` filters are **NOT applied** to `Merge` constituents in `for_each()`. `Merge` inputs use their own schema-key inner-join logic and bypass the filter path.

**Example:**

=== "Python"

    ```python
    # where= has NO EFFECT - only input is a Merge
    for_each(
        fn,
        {"data": Merge(A, B)},
        [Out],
        where=Side == "L",
        subject=[1, 2]
    )
    # Runs for every subject that has both A and B data, regardless of Side value

    # where= IS APPLIED - non-Merge input present
    for_each(
        fn,
        {"signal": RawEMG, "data": Merge(A, B)},
        [Out],
        where=Side == "L",
        subject=[1, 2]
    )
    # Runs only where RawEMG passes the Side filter; Merge loads unfiltered
    ```

=== "MATLAB"

    ```matlab
    % where= has NO EFFECT - only input is a Merge
    scidb.for_each(@fn, ...
        struct('data', scidb.Merge(A(), B())), ...
        {Out()}, ...
        where=Side() == "L", subject=[1 2]);
    % Runs for every subject that has both A and B data, regardless of Side value

    % where= IS APPLIED - non-Merge input present
    scidb.for_each(@fn, ...
        struct('signal', RawEMG(), 'data', scidb.Merge(A(), B())), ...
        {Out()}, ...
        where=Side() == "L", subject=[1 2]);
    % Runs only where RawEMG passes the Side filter; Merge loads unfiltered
    ```

---

## See Also

- [Variables API](variables.md) - `load()` and `load_all()` documentation
- [Batch Processing API](for-each.md) - `for_each()` documentation
- [Internal Documentation](../claude/where-filter-system.md) - Detailed implementation notes
