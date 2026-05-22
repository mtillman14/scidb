# Table/DataFrame Concatenation Optimization

## Problem

When saving data with cell array columns containing homogeneous tables (e.g., GAITRite data where each row contains a 1x54 table), the original implementation converted each table individually:

```
[16:16:37.563] processing table column 1/54 "DateTimeSaved_GaitRite"
[16:16:37.563] processing table column 2/54 "L_Idx_GR"
...
[16:16:37.563] processing table column 54/54 "frames"

[16:16:37.770] processing table column 1/54 "DateTimeSaved_GaitRite"  ← Second row
[16:16:37.770] processing table column 2/54 "L_Idx_GR"
...
```

For N rows with 54-column tables, this resulted in:
- **N × 54 log messages** (very verbose)
- **N separate MATLAB→Python bridge crossings** (slower)
- **N separate pandas DataFrame conversions** (inefficient)

## Solution (Bidirectional)

### to_python optimization (saving data)

Added a new optimization strategy in `to_python.m` that detects when all cells in a column contain tables with identical schemas, then:

1. **Concatenates** all 1-row tables into one N-row table
2. **Converts once** to pandas DataFrame
3. **Splits** back into list of single-row DataFrames for pandas object column

### from_python optimization (loading data)

Added a new optimization strategy in `from_python.m` that detects when a Python list contains DataFrames with identical schemas, then:

1. **Concatenates** all DataFrames using `pandas.concat`
2. **Converts once** from pandas DataFrame to MATLAB table
3. **Splits** back into individual table rows (one per original DataFrame)

## Benefits

For N rows with homogeneous tables:
- **Logging**: 54 log messages instead of N×54
- **Performance**: 1 bridge crossing instead of N
- **Robustness**: Falls back gracefully if schemas differ or concatenation fails

## Implementation Details

### Locations
- **to_python**: `sci-matlab/src/sci_matlab/matlab/+scidb/+internal/to_python.m`
- **from_python**: `sci-matlab/src/sci_matlab/matlab/+scidb/+internal/from_python.m`

### New Functions

**to_python.m**:
- `try_concat_homogeneous_tables(col)`: Checks if all cells contain tables with matching schemas and concatenates them

**from_python.m**:
- `try_concat_homogeneous_dataframes(c)`: Checks if all list elements are DataFrames with matching schemas and concatenates them using `pandas.concat`

### Optimization Strategy Order

**to_python** - when processing cell array columns in tables:
1. **Table concatenation** (new) - for homogeneous tables
2. **Numeric/logical flattening** (existing) - for homogeneous numeric vectors
3. **Element-by-element** (existing fallback) - for everything else

**from_python** - when processing Python lists:
1. **Numpy array conversion** (existing) - for homogeneous numeric values
2. **DataFrame concatenation** (new) - for homogeneous DataFrames
3. **Element-by-element** (existing fallback) - for everything else

### Safety
- Checks all cells are non-empty tables
- Verifies all tables have identical `VariableNames`
- Gracefully falls back to element-by-element if:
  - Schemas don't match
  - Concatenation fails (type incompatibility)
  - Any non-table elements exist
  - Any empty cells exist

## Testing

Run `test_table_concat_optimization.m` to verify:
1. Homogeneous tables trigger the optimization
2. Mixed types fall back to element-by-element
3. Schema mismatches fall back to element-by-element
4. Output correctness is preserved

## Example Log Output

### Saving (to_python) - Before (N=3, 54 columns)
```
[DEBUG] processing table column 1/54 "col_1"
[DEBUG] processing table column 2/54 "col_2"
...
[DEBUG] processing table column 54/54 "col_54"
[DEBUG] processing table column 1/54 "col_1"    ← Row 2
...
[DEBUG] processing table column 54/54 "col_54"
[DEBUG] processing table column 1/54 "col_1"    ← Row 3
...
[DEBUG] processing table column 54/54 "col_54"
```
Total: **162 log messages** (3 × 54)

### Saving (to_python) - After (N=3, 54 columns)
```
[DEBUG] trying table concat for cell column "GAITRiteLoaded" (3 rows, 54 cols each)
[DEBUG] processing table column 1/54 "col_1"
[DEBUG] processing table column 2/54 "col_2"
...
[DEBUG] processing table column 54/54 "col_54"
[DEBUG] table concat succeeded for column "GAITRiteLoaded"
```
Total: **~56 log messages** (setup + 54 columns + success)

**~66% reduction** for saving.

### Loading (from_python) - Before (N=3, 54 columns)
```
[DEBUG] convert_dataframe: column 1/54 "col_1"
...
[DEBUG] convert_dataframe: column 54/54 "col_54"
[DEBUG] convert_dataframe: column 1/54 "col_1"    ← Row 2
...
[DEBUG] convert_dataframe: column 54/54 "col_54"
[DEBUG] convert_dataframe: column 1/54 "col_1"    ← Row 3
...
```
Total: **162+ log messages** (3 × 54+)

### Loading (from_python) - After (N=3, 54 columns)
```
[DEBUG] trying DataFrame concat for list (3 DataFrames)
[DEBUG] convert_dataframe: column 1/54 "col_1"
...
[DEBUG] convert_dataframe: column 54/54 "col_54"
[DEBUG] DataFrame concat succeeded
```
Total: **~56 log messages** (setup + 54 columns + success)

**~66% reduction** for loading.

### Combined Impact
For a round-trip (save + load) with N=195 rows, 54 columns:
- **Before**: ~21,060 log messages (195 × 54 × 2 directions)
- **After**: ~120 log messages (60 per direction)
- **~99.4% reduction in log verbosity!**

## Related Code

- Caller: `scidb.for_each` lines 286-316 (where to_python is called on result tables)
- Consumer: Python's `for_each_save` in `sci-matlab/src/sci_matlab/bridge.py`
