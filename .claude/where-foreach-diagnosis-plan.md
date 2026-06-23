# Plan: Fix empty/duplicate combos in `for_each()` with column-selected inputs

## Symptom (actual repro — NO `where=` involved)
```matlab
scidb.for_each(@LRtoUA, ...
   struct('lr', GAITRiteLoadedCycle("StartFoot"), 'uaConfig', uaConfig), ...
   {UAStartFoot}, ...
   subject=[], session=[], speed=[], trial=[], cycle=[], as_table=true);
```
Iteration 1 → 2×6 table (SS02/BL/FV/1/1, StartFoot="R", two rows).
Iteration 2 → 0×6 empty table. Alternates thereafter.

> NOTE: the initial `where=` theory was WRONG — the repro has no `where=`. The
> `where=` schema_id-vs-row-granularity notes are unrelated to this bug (kept only
> as a possible future logging improvement).

## Root cause (confirmed)
`GAITRiteLoadedCycle("StartFoot")` is a `_scifor.ColumnSelection`. Both
`_scifor.Fixed` and `_scifor.ColumnSelection` store their frame under `.data`.

`_for_each_prepare` Step 11 (`scidb/src/scidb/foreach.py:1143-1182`) detects the
wrapper with a bare `hasattr(data, 'data')` and sets `is_fixed = True` for BOTH.
Only the non-fixed branch runs `rid_keys.append(rid_col)`. So a ColumnSelection
input:
- is mislabeled Fixed,
- `fixed_rid_values` not set (its `len(df)` is the whole spread, not 1),
- `rid_keys` stays empty → `rid_per_combo` empty.

In full-iteration mode (all schema keys iterated) the non-existent-combo skip at
`foreach.py:1357-1366` only fires when `rid_per_combo` is non-empty. With it
empty, EVERY base combo hits the unconditional `else` (line 1377). And
`base_combos` is the full Cartesian product of distinct schema values
(`foreach.py:1206-1209`, because `subject=[]…` → explicit iterables →
`all_combos is None`), which includes combos with no data. Hence:
- existing location → real rows (the "2 rows");
- non-existent combo → empty slice → "0×6".

The two identical rows are simply that location's loaded rows (2 records or a
2-row table value); without rid registration they are also not variant-separated.

## Fix
In `_for_each_prepare` Step 11, distinguish wrapper types by `isinstance`, not by
`hasattr('.data')`:
- `isinstance(data, _scifor.Fixed)` → fixed path (unchanged).
- `isinstance(data, _scifor.ColumnSelection)` → treat like a plain DataFrame:
  rename `__record_id`→`__rid_{param}` inside `.data` AND
  `rid_keys.append(rid_col)`.
- plain `pd.DataFrame` → unchanged.

Verify downstream handles ColumnSelection-wrapped rid columns:
- `rid_per_combo` build (`foreach.py:1233-1265`) already unwraps `.data` — OK.
- aggregation-mode `__rid_*` strip (`foreach.py:1292-1307`) only handles raw
  DataFrames → extend to strip from `ColumnSelection.data` too.
- scifor schema extension (`foreach.py:1409-1412`) adds rid keys globally;
  scifor `ColumnSelection.apply` filters by combo then selects `self.columns`,
  so `__rid_*` is naturally excluded from what the fn sees — OK.

## Logging improvements (make this class of bug obvious)
1. Step 11: per input, log detected wrapper type and whether rid tracking was
   enabled (`rid key added` vs `skipped — no __record_id` vs `fixed`).
   A ColumnSelection silently getting NO rid key is the exact signal that was
   missing.
2. Step 12/13: log base_combo count, full_combo count, and **combos pruned for
   missing rids**. WARN when `len(full_combos) == len(Cartesian product)` AND no
   rid pruning happened in full-iteration mode (i.e. existence filtering didn't
   run) — that is the smoking gun for this bug.
3. Per-combo run (scifor): when a combo's prepared input is empty, log
   `[empty-combo] <metadata>: input '<name>' had 0 rows` at INFO so empty
   function calls are never silent.

## Regression tests
- `for_each` with a `ColumnSelection` input over fully-iterated schema where the
  data is sparse (some Cartesian combos absent): assert NO empty-input combos
  reach fn, and combo count == number of populated locations (parity with the
  same call using a plain variable input, no column selection).
- Variant case: a location with 2 records + ColumnSelection → rid expansion
  splits into 2 single-record calls (same as without column selection).
- MATLAB bridge parity test mirroring the repro.

## Docs
Offer to add a `docs/claude/` note: "rid tracking does double duty (variant
separation + non-existent-combo pruning); any input wrapper must register its
rid key or the Cartesian product leaks empty combos."
