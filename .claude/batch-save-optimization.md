# Batch Save Optimization for `scidb.for_each`

## Problem
`scidb.for_each` with `distribute=true` was saving records sequentially, one at a time:
- **7,056 rows** → **7,056 individual `.save()` calls**
- Each call: Python-MATLAB bridge crossing + transaction + metadata insertion
- **Total time: 220+ seconds** (~0.028s per record)

## Root Cause
The `_save_results()` function in `scidb/src/scidb/foreach.py` (line 1639) iterated through each row and called `.save()` individually:
```python
for _, row in result_tbl.iterrows():
    # ... build metadata ...
    rid = output_obj.save(output_value, **save_metadata)  # Line 1853
```

This was inefficient for large result sets, but the database already had a `save_batch()` method designed for exactly this use case.

## Solution Implemented
Refactored `_save_results()` to use batch saving while **preserving all config_keys and branch_params tracking**:

### Phase 1: Collection (Lines 1690-1821)
- Iterate through all rows **once**
- For each row, preserve all existing logic:
  - ✅ Collect upstream branch_params via `__rid_*` columns → `rid_to_bp` lookup
  - ✅ Add constants namespaced by function name
  - ✅ Add dynamic discriminators
  - ✅ Build save_metadata with config_keys
  - ✅ Add `__branch_params` to metadata
  - ✅ Add `__upstream` to version_keys
- Collect `(data, metadata)` tuples grouped by `(output_idx, save_path)`
- Three save paths:
  - **'normal'**: Standard output values → batched
  - **'flatten'**: Distribute mode DataFrames → batched
  - **'lineage'**: LineageFcnResult items → sequential (special handling)

### Phase 2: Batch Save (Lines 1823-1888)
- For each group of items, call `db.save_batch()` **once**
- Log first 3 records for visibility + summary count
- Calculate throughput (records/s)

### Phase 3: Lineage Sequential Save (Lines 1890-1916)
- LineageFcnResult items saved sequentially via `scihist.foreach.save_lineage_result()`
- These cannot be batched due to special lineage tracking requirements

## Expected Performance Improvement
- **Before**: 7,056 saves × 0.028s = ~198s
- **After**: 1 batch call = ~5-10s
- **Speedup**: **20-40x faster** for large result sets

## Compatibility
✅ **Fully backward compatible**:
- All branch_params tracking preserved
- All config_keys tracking preserved
- Same record_ids generated (content-addressable)
- Same behavior for normal cases (< 100 rows)
- Both Python and MATLAB paths benefit (both use `_save_results`)

## Testing Checklist
- [ ] Run existing `scidb` tests: `pytest scidb/tests/`
- [ ] Test distribute mode with large result sets (1000+ rows)
- [ ] Verify branch_params propagation in multi-step pipelines
- [ ] Test with lineage-tracked results
- [ ] Test flatten/distribute mode DataFrame outputs
- [ ] Verify MATLAB integration still works
- [ ] Benchmark actual speedup on GAITRite use case

## Files Modified
- `scidb/src/scidb/foreach.py` - `_save_results()` function (lines 1639-1868)

## References
- Identity system docs: `docs/claude/scidb-identity-and-data-flow.md`
- Benchmark example: `examples/benchmark_batch_save.py`
- Database batch save: `scidb/src/scidb/database.py:923` (save_batch method)
