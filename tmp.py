# Performance Bottleneck Analysis for scidb.for_each with distribute=true
# =========================================================================

# PROBLEM IDENTIFIED
# ------------------
# Location: scidb/src/scidb/foreach.py, line 1677-1806
#
# The _save_results function saves records ONE AT A TIME in a loop:
#
#   for _, row in result_tbl.iterrows():  # Line 1677
#       # ... build metadata for this row ...
#       rid = output_obj.save(output_value, **save_meta)  # Line 1806
#
# With 7,056 records, this means:
#   - 7,056 individual .save() calls
#   - 7,056 Python-MATLAB bridge crossings
#   - 7,056 transaction commits
#   - 7,056 metadata insertions
#
# At ~0.028s per save: 7,056 × 0.028s ≈ 198 seconds ✓ matches your 220s

# SOLUTION EXISTS
# ---------------
# The codebase already has a save_batch() method:
#   - scidb/src/scidb/database.py, line 923
#   - Takes: list[tuple[data_value, metadata_dict]]
#   - "Amortizes setup work and batches SQL operations using DataFrame-based inserts"
#
# But _save_results() is NOT using it - it calls .save() individually instead.

# DIAGNOSTIC CODE TO ADD TIMING
# ------------------------------
# To confirm this hypothesis, add timing instrumentation:

import time
from scidb.log import Log

# Add this at the start of _save_results (line 1639):
def _save_results_instrumented(result_tbl, outputs, output_names, config_keys, db, **kwargs):
    """Instrumented version with timing diagnostics"""

    t_start = time.perf_counter()

    # Existing metadata prep code...
    t_prep = time.perf_counter()
    Log.info(f"[TIMING] Metadata prep: {t_prep - t_start:.3f}s")

    # The iteration loop
    t_loop_start = time.perf_counter()
    save_times = []

    for idx, (_, row) in enumerate(result_tbl.iterrows()):
        t_row_start = time.perf_counter()

        # Existing per-row save code...
        # rid = output_obj.save(...)

        t_row_end = time.perf_counter()
        save_times.append(t_row_end - t_row_start)

        if idx < 10 or idx % 1000 == 0:
            Log.info(f"[TIMING] Row {idx}: {t_row_end - t_row_start:.4f}s")

    t_loop_end = time.perf_counter()
    Log.info(f"[TIMING] Total loop: {t_loop_end - t_loop_start:.3f}s")
    Log.info(f"[TIMING] Avg per row: {sum(save_times)/len(save_times):.4f}s")
    Log.info(f"[TIMING] Min/Max: {min(save_times):.4f}s / {max(save_times):.4f}s")

# EXPECTED RESULTS
# ----------------
# This will confirm:
# 1. Metadata prep is fast (< 1s)
# 2. The loop dominates the time (~220s)
# 3. Each save averages ~0.028s
# 4. The bottleneck is sequential individual saves

# RECOMMENDED FIX
# ---------------
# Refactor _save_results to:
# 1. Collect all (data_value, metadata_dict) tuples in a list
# 2. Call db.save_batch(output_class, data_items) ONCE per output
# 3. Expected speedup: 220s → ~5-10s (22-44x faster)

print("Analysis complete. See comments above for full diagnostic approach.")
