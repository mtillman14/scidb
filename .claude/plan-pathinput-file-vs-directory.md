# scifor PathInput: distinguish files from directories

Status: **BUILT (2026-08-13)**. Follow-on from the PathInput fresh-run
execution fix (`.claude/plan-pathinput-fresh-run-fix.md`) — the live test
of that fix surfaced this real, separate scifor-layer bug: a flat file
sitting next to real subject folders got silently discovered as a fake
subject and crashed downstream (`NotADirectoryError`).

## Design (per user's direction)

Infer file-vs-directory intent from whether the template's LAST path
segment has a literal `.ext`-style suffix (`Path(segment).suffix`) —
operates on the raw segment text including `{placeholder}` braces, so
`{subject}.csv` and `report_{year}.csv` both read as file-like via their
literal `.csv`; a bare `{subject}` (no literal suffix at all) reads as
directory-like. No new constructor parameter, no template syntax change
— every existing template already implies its own answer.

**Fallback, per the user's explicit ask** ("check both... in case someone
names a folder ending with something matching .ext"): the heuristic is a
first PREFERENCE, not a hard rule. If the strict, kind-filtered pass
finds NOTHING at all, an unfiltered second pass runs so a real match
(the heuristic guessed wrong on) is never silently lost.

Only the LAST segment of a template was ever ambiguous — every
intermediate segment is already directory-only by construction (the
walker only descends into `is_dir()` entries to keep going).

## Why this fixes both Python and MATLAB with one change

`scimatlab`'s `+scifor/PathInput.m` is a thin wrapper — its own docstring
says "All template parsing, filesystem walking, and regex matching is
owned by Python so MATLAB-driven and Python-driven pipelines stay
byte-identical." It constructs and delegates to the same
`py.scifor.pathinput.PathInput` instance. No MATLAB-side logic exists to
duplicate or port.

## What changed (`scifor/src/scifor/pathinput.py`)

- New module-level helpers: `_expects_file(segment) -> bool` (the
  heuristic) and `_matches_kind(path, expects_file) -> bool`.
- `discover()` / `_walk()`: both `is_last` branches (literal segment and
  placeholder-regex segment) now require `_matches_kind` when
  `enforce_kind=True` (the default). `discover()` runs a strict pass
  first, then an unfiltered fallback pass only if the strict pass found
  nothing.
- `_fallback_scan()` (the numeric-equivalence/alias matching
  `load()`/`load_with_captures()` uses when the literal path is missing):
  same `enforce_kind` threading, same strict→fallback two-pass wrapper.
  This path had a LATENT bug beyond the reported one: a directory and a
  file that both parse to the same numeric-equivalent value (e.g. a
  directory named `006.mat` and a file named `06.mat`, both meaning
  trial=6) used to trigger `RuntimeError("matched 2 files")` for a
  wrong-kind entry that was never a real candidate. Now excluded
  correctly, leaving one clean match.
- Direct `load()` literal-path check (concrete metadata, no enumeration
  among candidates) was deliberately left untouched — there's no
  ambiguity to resolve when the metadata is already fully concrete, only
  when scifor is choosing among multiple filesystem entries (`discover()`
  and the fallback scan).

## Tests added (`scifor/tests/test_pathinput_discover.py`)

New `TestDiscoverFileVsDirectory` class, 5 cases: bare placeholder
excludes same-level files; extension placeholder excludes a same-level
directory (even one deliberately named to match the regex, e.g.
`S03.csv` as a directory); the heuristic applies to the LAST segment
specifically in a multi-segment template; the fallback pass rescues an
extensionless file the heuristic guessed wrong on; and the
`_fallback_scan`/numeric-equivalence case (directory `006.mat` + file
`06.mat`) that used to raise `RuntimeError` and now resolves cleanly.

Verified by reasoning through every existing PathInput test
(`test_pathinput_discover.py`, `test_pathinput_padded.py`,
`test_pathinput_aliases.py`, `test_pathinput_key_regex.py`,
`test_pathinput_regex.py`) — every existing template's last segment
already had a literal extension matched only against real files, or is
regex mode (untouched, already file-only via a separate code path). None
rely on the ambiguous behavior this closes, so nothing should regress.

## To verify

```
cd /workspace
uv run pytest scifor/tests/test_pathinput_discover.py scifor/tests/test_pathinput_padded.py scifor/tests/test_pathinput_aliases.py scifor/tests/test_pathinput_key_regex.py scifor/tests/test_pathinput_regex.py -v
```

Then re-run the live GUI test from before (`load_vo2_from_csv` /
`load_heart_rate_from_csv` in `gui_test_data.py`) — should now work even
WITHOUT the `by_subject/` subfolder separation I made as a workaround
last time, since PathInput itself now correctly excludes the flat CSV
files from a bare `{subject}` match. That workaround wasn't reverted
(harmless either way) — flagging in case you'd rather simplify back to
one flat `data/` folder now that the real bug is fixed at its source.
