# Defer function-content staleness; add hash-tracking diagnostics

## Background

`scidb.log` showed 15 successfully-saved combos immediately reported as stale:

```
node load_csv: red (up_to_date=0, stale=15, missing=1)
stale: subject=XX, trial=YY — function hash changed (lineage)
```

The stale branch in `scihist-lib/src/scihist/state.py:_check_via_lineage`
fires when `stored_hash != fn.hash`:

- `stored_hash` — `function_hash` column in `_lineage`, written at save time
  from `MatlabLineageFcnInvocation.fcn.hash`.
- `fn.hash` — freshly computed `MatlabLineageFcn.hash` built by the GUI at
  state-check time from `matlab_parser.parse_matlab_function`'s `source_hash`.

The user confirmed (interactively) that both hash recipes agree on the
same file: GUI raw-bytes SHA-256 == MATLAB `fileread`+utf-8 SHA-256 ==
`387621759246…`, and both the GUI proxy and a live MATLAB proxy compute
`ce634fb42246…` from it. So the two sides no longer disagree at recipe
level, yet the stale check still fires on just-saved rows.

Until we actually see what is in `_lineage.function_hash` for those 15
rows, we cannot explain the false stale. Separately, the user has stated
that content-based function staleness is **out of scope for now** — they
only want per-Run traceability of which function contents produced each
record, and will add a proper "content changed" feature later.

## Plan

### Step 1 — diagnostic logging (land now)

1. `scihist-lib/src/scihist/state.py:_check_via_lineage` — include both
   hash values in the "function hash changed (lineage)" debug line:
   `stale: %s — function hash changed (lineage): stored=%s fn=%s`.
2. `scihist-lib/src/scihist/foreach.py:_save_lineage_fcn_result` — log
   `function_hash` right before persisting, at INFO or DEBUG, so we can
   verify what landed in the DB per-save without running SQL afterwards.
3. `sci-matlab/src/sci_matlab/matlab/+scidb/LineageFcn.m` — after
   constructing `obj.py_fcn`, log the source_hash, proxy hash, and the
   resolved .m path via `scidb.Log.debug`. Lets us compare MATLAB-side
   hashing against the GUI's `[pipeline] matlab proxy` log line without
   a MATLAB REPL round-trip.

No behavioural change from Step 1. It just turns every future run into a
self-contained trace.

### Step 2 — drop content-staleness from state check (land now)

In `scihist-lib/src/scihist/state.py:_check_via_lineage`:

- Remove the `if stored_hash != fn.hash: return "stale"` branch.
- Keep calling `_has_superseded_ancestor` so upstream-data changes still
  cascade to stale.
- Keep `_save_lineage` writing `function_hash` as-is — the column
  continues to answer the "which function contents produced this record"
  question. No schema or save-path change.

Because this removes the only path that consults `fn.hash` from
`_check_via_lineage`, `fn.hash` becomes purely informational on the check
side (still logged by Step 1). `_check_via_fn_hash` — used for
`scidb.for_each` outputs that carry `__fn_hash` in `version_keys` — is
not touched; that path is already documented as a fallback and has
different tests.

### Tests to update

Any test that asserted "function edit → stale via lineage path" must be
rewritten to reflect the new behaviour. Candidates to audit:

- `scihist-lib/tests/test_state.py`
- `scihist-lib/tests/test_state_matlab_pathinput.py`
- `scihist-lib/tests/test_foreach.py`
- `scistack-gui/tests/test_matlab.py`

For each, keep the `__fn_hash` (Priority 2) path's staleness-on-change
tests — that path is untouched. Replace any lineage-path
staleness-on-change test with an assertion that function-hash change
alone does **not** mark a combo stale, with a `# TODO` pointing to the
future content-staleness feature.

### Out of scope (future)

- Re-introducing content-staleness as a first-class feature, probably
  via: (a) tokenized-source hashing resilient to comment/whitespace
  edits; (b) an opt-in surface that warns rather than forces stale; or
  (c) a per-Run snapshot captured at the GUI layer and diffed against
  the current file on request.
- Unifying MATLAB/GUI hash recipes. Confirmed unnecessary today.
