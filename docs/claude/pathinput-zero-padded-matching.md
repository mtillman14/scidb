# PathInput: zero-padded numeric filename matching

## Purpose

Filenames commonly zero-pad numbers (`6MWT-001.mat`, `sub-002/`). Users pass
the numbers as numbers (`trial=1:12` from MATLAB, ints from Python), and the
template `{trial}` renders `str(1)` → `6MWT-1.mat` → file not found. As of
2026-07-12, `PathInput.load()` handles this natively with **numeric-equivalence
fallback** — no template syntax, no format specs, nothing to remember.

## Resolution order (non-regex mode, `scifor/src/scifor/pathinput.py::load`)

1. **Literal resolution** — today's historical behavior, unchanged. Substitute
   `str(value)` per placeholder, anchor (root_folder → project root → as-is).
   If the path **exists**, return it. Zero cost added: one `stat`.
2. **Pad-width cache shortcut** — if a previous fallback learned pad widths
   (e.g. `trial → 3`), re-render with `zfill` and try one more `stat`.
3. **Numeric fallback scan** — only when the literal path is missing and at
   least one metadata value is *numeric-like*: `int`, integral `float`
   (MATLAB doubles arrive as `1.0`), or a digit string (`num2str` marshaling
   sends `"1"`). Bools are excluded. The template is walked segment by
   segment (`_numeric_fallback_scan`): numeric-bound `{key}` matches `(\d+)`
   with an `int(capture) == int(value)` check, other keys substitute
   literally. Padded *directory* segments work, not just the filename.
4. **Outcome** — exactly one match: return it and learn each key's pad width
   from the capture. Multiple numerically-equal matches (`6MWT-1.mat` and
   `6MWT-001.mat` both on disk): `RuntimeError` (MATLAB translates it to
   `scifor:PathInput:MultipleMatches` via the "matched N files" wording).
   Zero matches: return the literal path unchanged — `load()` has never
   raised on missing files in non-regex mode, and callers rely on that.

`regex=True` mode is completely untouched.

## Performance

- Files that exist literally: no change (the `exists()` check).
- Padded datasets: the **first** missing combo does directory scans and
  learns pad widths per key; every subsequent combo hits the width cache with
  a single extra `stat`. Directory listings are additionally memoized per
  instance, invalidated by directory mtime (`_dir_cache`). So a
  1000-combo run over 1000-file folders costs ~one listing + one regex sweep,
  then 2 stats per combo.
- Mixed pad widths in one directory degrade gracefully to per-combo scans
  (the width cache misses, the scan still finds the right file).

## MATLAB

`+scifor/PathInput.m` delegates `load` to the Python object, so the feature
needs no MATLAB changes. Its marshaling (`num2str(1)` → `"1"`) is exactly the
digit-string case the fallback covers. Error translation for the ambiguity
case already worked via message sniffing.

## What this deliberately does NOT do

- **No value conversion.** Discovered combos still carry `"001"` as strings
  (feedback rule: never auto-int zero-padded schema keys). Only the filename
  *lookup* is numeric-tolerant.
- **Known caveat:** schema-key strings still differ by source for the same
  file — discovery-driven runs store `trial="001"`, explicit `trial=1:12`
  runs store `"1"`. Both now *resolve*; they are not unified. Adjacent to the
  recorded latest-record-selection future issue; revisit canonicalization if
  it bites.
- Rejected alternatives: `{trial:03d}` format specs (Python-specific syntax
  burden) and inferring a format from an example file (extra failure modes:
  mixed widths, which example to trust, stale learned widths — direct
  equality matching subsumes it).

## Key files

| File | Role |
|------|------|
| `scifor/src/scifor/pathinput.py` | `load()` fallback, `_numeric_fallback_scan`, `_pad_width`/`_dir_cache` |
| `scifor/tests/test_pathinput_padded.py` | Python coverage (literal-first, fallback, ambiguity, boundaries) |
| `scimatlab/tests/matlab/scifor/TestPathInput.m` | `test_padded_fallback_*` MATLAB cases |

## See also

- `docs/claude/input-markers-colname-pathinput-pathoutput.md` — PathInput's
  role among the input markers.
