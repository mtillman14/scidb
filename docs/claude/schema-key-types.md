# Schema key types: numeric/string declaration + canonicalization

## Purpose

Zero-padded filenames (`6MWT-001.mat`) mean the same logical trial can be
spelled `"001"` (disk), `1` (explicit iterable), or `1.0` (MATLAB double).
PathInput's numeric fallback makes every spelling *resolve*
(`docs/claude/pathinput-zero-padded-matching.md`), but stored schema-key
identity needs one spelling. The hybrid contract (user-designed, 2026-07-12)
fixes identity with **minimal syntax burden**: declarations are only required
when the dataset proves the ambiguity real.

## The contract

| Situation | Behavior |
|---|---|
| All path matches exact | No declaration needed. Verbatim spellings, exactly as before. |
| PathInput bridges spellings (`trial=1` → `"001"`) on an **undeclared** schema key | `SchemaKeyTypeError` telling the user to declare the key once. Aborts the whole run (`scifor_fatal`), not a per-combo skip. |
| Key declared `"numeric"` | Canonicalization is **unconditional** — every spelling from every source (explicit iterables, discovery combos, DB fills, direct save/load) collapses to the unpadded form before storage. Path lookups still bridge padding via the fallback. |
| Key declared `"string"` | Verbatim everywhere; spelling IS identity. PathInput matches these keys **exactly only** — `"1"` never bridges to `"001"` (both could legitimately exist as distinct trials). |

Key insight from the design discussion: the *error* is resolution-triggered,
but the *canonicalization* must not be — a discovery-driven run
literal-matches `"001"` (no resolution event) while an explicit run resolves,
so resolution-triggered-only canonicalization would reintroduce the mixed
spellings it exists to fix.

## API

```python
configure_database(path, ["subject", "trial"],
                   schema_key_types={"trial": "numeric"})
```

Validation at construction: declared keys must be schema keys; values must be
`"numeric"` or `"string"`. Not persisted in the DB (dataset in testing mode;
declarations live in user code like the schema keys themselves).

## Where each piece lives (layering per CLAUDE.md NOTE 3)

| Piece | Location |
|---|---|
| `load_with_captures(metadata, db=None, numeric_match=None)` — resolve + report bridged spellings; `numeric_match` restricts fallback-eligible keys | `scifor/src/scifor/pathinput.py` (policy-free reporting) |
| `scifor_fatal` escape hatch — exceptions with this attr abort the loop instead of per-combo skip | `scifor/src/scifor/foreach.py` main loop |
| `SchemaKeyTypeError` (`scifor_fatal = True`) | `scidb/src/scidb/exceptions.py` |
| `_canonical_numeric_value(key, value)` — "001"→1, 1.0→1, "1.50"→1.5, else raise | `scidb/src/scidb/database.py` |
| `schema_key_types=` param + validation + `canonicalize_metadata()` | `scidb/src/scidb/database.py` (`configure_database`, `DatabaseManager`) |
| Entry-point canonicalization — `save_variable`, `save_batch`, `load`, `load_all_as_df` all call `canonicalize_metadata` (one seam covers Python direct calls AND the MATLAB bridge's `save_batch_bridge`/`load_and_extract`, which bypass `BaseVariable`) | `scidb/src/scidb/database.py` |
| Step 5 iterable canonicalization + discovered-combo canonicalization/dedupe | `scidb/src/scidb/foreach.py` (`_prepare_foreach_state`) |
| Per-combo enforcement (`_load_pathinput_checked`) — string keys excluded from `numeric_match`, undeclared resolved keys raise | `scidb/src/scidb/foreach.py` (Step 16 wrapper → `_resolve_per_combo_loader`) |

Standalone Python scifor (no database) keeps the silent fallback: there is no
stored identity to protect, and scifor never sees schema policy.

## Notes / edges

- Canonicalization can collapse discovered combos that differed only in
  spelling (both `6MWT-1.mat` and `6MWT-001.mat` on disk) — deduped in Step 5.
  If such a tie needs *resolving* per combo, the fallback's ambiguity
  RuntimeError still fires at load time.
- Non-schema combo keys (version params) keep the silent fallback; their
  spelling doesn't define dataset identity. Revisit if version-key spelling
  splits ever bite.
- `canonicalize_metadata` handles list values (load()'s OR semantics)
  element-wise; bools on numeric keys are rejected.
- Floats: integral → int ("1.0" ≡ 1); non-integral normalize via float
  ("1.50" ≡ 1.5).
- **MATLAB parity implemented (2026-07-12, same session).** Architecture
  differs from Python because the MATLAB loop resolves PathInput itself:
  - Canonicalization comes free: `for_each_prepare` runs Python Steps 2-15
    (combos return canonical), and the entry-point canonicalization in
    `DatabaseManager` covers the bridge save/load functions.
  - Declaration: `scidb.configure_database(..., schema_key_types=
    struct('trial','numeric'))` (`+scidb/configure_database.m` → py.dict).
  - Enforcement: `+scidb/for_each.m` injects a `_pathinput_loader` callback
    into `+scifor/for_each.m` (new opt; scifor stays policy-free). The
    callback is `+scidb/+internal/load_pathinput_checked.m`, which calls
    the new `+scifor/PathInput.m::load_with_captures` and raises error ID
    `scidb:SchemaKeyTypeError`.
  - Fatal abort comes free in MATLAB: the constant-resolution block in the
    scifor loop has no per-combo try/catch, so the error propagates and
    aborts the run (no `scifor_fatal` mirror needed).
  - Standalone MATLAB scifor (no loader injected) keeps the silent
    fallback, same as standalone Python scifor.

## MATLAB categorical schema-key columns (2026-07-13)

MATLAB `categorical` stores category labels as text, so it erases whether a
column's source values were numeric or string — `categorical([1;2])` and
`categorical(["1";"2"])` are indistinguishable. A table whose schema-key
columns were made categorical (`categorical=true` on a prior `for_each`/
`load`) therefore used to come back with **string** keys in lexical order
("10" < "2") when fed back into `scifor.for_each` with `key=[]`, silently
changing schema-key identity.

Fix (`+scifor/for_each.m::decategorize_schema_column`, called from
`distinct_values_from_inputs`): when resolving `key=[]` from a categorical
column, recover numerics **only when every label round-trips losslessly**
through `str2double` (`"1"` → 1 → `"1"`, `"1.5"` → 1.5 → `"1.5"`). Any
non-canonical spelling — zero-padded `"01"`, mixed `"1"`/`"01"`, text labels,
missing values — keeps ALL labels as strings verbatim (no partial
conversion). This is the same lossless rule as `_canonical_numeric_value`,
applied as inference only where categorical has already destroyed the type;
plain string columns are never touched. The type decision is logged at DEBUG.
Python scifor is unaffected: pandas categoricals keep their values' dtypes.

## Tests

- `scidb/tests/test_schema_key_types.py` — validation, canonical-value unit
  tests, direct save/load identity, for_each numeric/string/undeclared paths,
  discovery+explicit identity sharing.
- `scifor/tests/test_pathinput_padded.py::TestLoadWithCaptures` — reporting
  API and `numeric_match` exclusion.
- `scimatlab/tests/matlab/scidb/TestSchemaKeyTypes.m` — MATLAB mirror:
  declaration round-trip, numeric/string/undeclared for_each paths,
  discovery+explicit identity sharing (helper: `read_file_value.m`).
- `scimatlab/tests/matlab/scifor/TestSciforForEachCategorical.m` section F —
  categorical schema-key INPUT columns: numeric recovery + ordering,
  zero-padded/mixed/text labels stay strings, categorical=true round-trip,
  two-key nested-struct regression mirror.

## See also

- `docs/claude/pathinput-zero-padded-matching.md` — the resolution mechanism.
- `.claude/plan-schema-key-type-canonicalization.md` — design history and
  the rejected alternatives.
