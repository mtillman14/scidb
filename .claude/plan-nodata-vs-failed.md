# Plan: distinguish "no data" from "failed" in scifor's for_each reporting

## Problem
`for_each`'s end-of-run summary (and per-iteration failure log) labels every
skipped combo as "failed", including combos skipped because no data exists
for them — a normal, expected outcome when the schema key cross-product
(subject × session × speed × trial, etc.) is sparser than the full grid.
This makes benign missing-data situations look like errors (e.g. "failed:
283 × scifor:NoData ...").

## Root cause
- MATLAB's `prepare_input`/`prepare_iterate_table`
  (`scimatlab/.../for_each.m:1048,1102`) already raise a distinguishable
  `scifor:NoData` error when a combo's filtered data is empty, but the
  end-of-run summary (`for_each.m:951`) reports every failure reason —
  NoData included — as `failed: N × "..."`.
- Python's `_prepare_input`/`_prepare_iterate_df`
  (`scifor/src/scifor/foreach.py`) don't raise at all on empty data; they
  silently hand the empty DataFrame to `fn`, which typically then raises its
  own unlabeled exception — also folded into "failed". This is an asymmetry
  with MATLAB (documented as intentional-ish in
  `docs/claude/scidb-for-each-internals.md:263`, but never given a distinct
  identity).

## Design
1. **Python**: add `NoDataError` (new exception in `foreach.py`, exported
   from `scifor`). Raise it from `_prepare_input` when a per-combo DataFrame
   filters to 0 rows outside `as_table` mode (mirrors MATLAB's `as_table`
   exemption), and from `_prepare_iterate_df` unconditionally on 0 rows
   (mirrors MATLAB's `prepare_iterate_table`, which has no `as_table`
   opt-out for `for_columns`).
2. **Both layers**: in the per-iteration failure recorder
   (`_record_iteration_failure` / `record_iteration_failure`), detect NoData
   failures and skip the WARN-level "iteration failed" line + traceback for
   them (DEBUG `[skip]` only) — they're expected, not alarming.
3. **End-of-run summary**: split into `no data: N combo(s) — ...` vs
   `failed: N × "..." — ...`, each still capped/truncated the same way. The
   top summary line becomes
   `completed=X, failed=Y, no_data=W, total=Z` (Y = genuine `fn` failures
   only).
4. **Progress event**: add a `no_data` count alongside `completed`/`failed`
   in the "summary" progress event; keep the existing `failed`/`skipped`
   keys so current consumers (scistack-gui) don't break, but `failed` now
   correctly excludes no-data skips.
5. **Tests**: update `scifor/tests/test_logging.py` for the new summary
   wording; update `scifor/tests/test_each_of.py::test_each_of_where_axis`
   (currently asserts the *old* pass-through-empty-data behavior — will now
   correctly skip those combos as no-data); add MATLAB-side equivalent
   coverage in `scimatlab/tests/matlab/scifor/TestForEach.m` (if it exists)
   or the relevant for_each test file.
6. **Docs**: update `docs/claude/scidb-for-each-internals.md:263` (and the
   scifor-internals doc) to describe the new no-data/failed distinction
   instead of the old "the function call typically fails and is skipped"
   description.

## Addendum: GUI propagation (done)
User asked for this as a follow-up once the scifor/MATLAB tests passed.
Found the same "no data folded into failed" conflation one layer further
in, in **scidb** (not just the GUI):
- `scidb/src/scidb/foreach.py`: `_run_summary`/`_tracking_progress_fn` and
  the `for_each(...) run summary` log line labeled every skip "failed".
- `scidb/src/scidb/pipeline.py`: `_execute_step`'s `_collecting_progress_fn`
  built `last_run_report` entries the same way; `pipeline_run_finished`
  summed `failed_total` over the (conflated) `failed` field.

Fixed both to carry a `no_data` count alongside `completed`/`failed` (regression test in `scidb/tests/test_pipeline_registry.py`). Then updated
`scistack-gui/scistack_gui/api/run.py`'s two run flows (`_run_in_thread`'s
`combo_totals`, `_run_pipeline_in_thread`'s `report`-based aggregation) to
track and surface `no_data_combos` in logs and the `run_done`/`run_progress`
push messages, alongside the existing `failed_combos` (which now correctly
excludes no-data skips end-to-end). `success` was already derived from
`failed` only, so no behavior change there — this is purely making the
already-correct verdict visible with the right label. Frontend TSX changes
(actually rendering `no_data_combos` in the Runs-tab UI) were not made —
`records_skipped`/`failed_combos` aren't currently rendered there either, so
this is additive backend/API surface for a future UI treatment, not a
behavior fix on the frontend.
