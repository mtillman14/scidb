# Plan: PathInput adjacent-placeholder disambiguation via `key_patterns`

## Problem

`PathInput` templates like `"{subject}_EMG_{speed}{trial}.mat"` (matching
`SS01_EMG_SSV1.mat`) fail to discover correct values for `speed`/`trial`
when the two placeholders are adjacent with no delimiter between them.
`discover()`'s segment-to-regex compiler (`_segment_to_regex`,
`scifor/src/scifor/pathinput.py`) gives every placeholder the same greedy
catch-all group `(?P<key>[^/\\]+)`. With no literal separating two
placeholders, the regex engine has no anchor for where one field ends and
the next begins, so the earlier group swallows the whole token
(`speed="SSV1"`, `speed="FV-001"`).

## Fix

Add an optional, fully general `key_patterns: dict[str, str]` constructor
argument to `PathInput` (same shape/validation pattern as the existing
`aliases` argument): a map from placeholder key to a raw regex fragment
(no capture group) substituted for the default `[^/\\]+` when that key
appears in a template segment.

```python
PathInput(
    "{subject}_EMG_{speed}{trial}.mat",
    key_patterns={"speed": r"[A-Za-z]+", "trial": r"\d+"},
)
```

This is not a letters/digits-specific heuristic baked into the engine —
it's a generic per-key override, so any future adjacency ambiguity
(fixed-width codes, mixed alnum, etc.) is handled the same way.

## Changes

1. `scifor/src/scifor/pathinput.py`
   - `PathInput.__init__`: accept `key_patterns`, store it, validate each
     key is an actual template placeholder (`ValueError` otherwise, same
     message style as the existing `aliases` validation added in
     `_build_alias_reverse`).
   - `_segment_to_regex` (staticmethod today — becomes an instance method
     or gains access to `self.key_patterns`): for a placeholder found in
     `key_patterns`, emit `f"(?P<{group_name}>{pattern})"` instead of the
     hardcoded `[^/\\]+`.
   - `to_key()`: include `key_patterns` in the serialized JSON payload
     when non-empty, mirroring how `aliases`/`regex` are conditionally
     included (keeps old version keys byte-identical).
2. `scimatlab/+scifor/PathInput.m`
   - New `options.key_patterns struct = struct()` constructor option,
     marshaled to a `py.dict` the same way `aliases_to_py` works, passed
     into the Python constructor.
   - Update class help/docstring with an example.
3. Tests
   - New `scifor/tests/test_pathinput_key_patterns.py`: adjacent
     letter/digit discovery against a temp tree (mirrors the fixture
     style in `test_pathinput_discover.py`), validation error for a
     `key_patterns` key that isn't a placeholder, and a sanity check that
     templates with delimiters are unaffected by an unrelated
     `key_patterns` entry.
   - New MATLAB case in `scimatlab/tests/matlab/scifor/TestPathInput.m`
     exercising the same discovery through the MATLAB wrapper.
4. Docs
   - New `docs/claude/pathinput-key-patterns.md` describing the root
     cause and the mechanism, cross-linked from
     `docs/claude/pathinput-zero-padded-matching.md` and
     `docs/claude/input-markers-colname-pathinput-pathoutput.md`.

## Out of scope

- `_fallback_segment_regex` (the zero-pad/alias fallback scan) is not
  touched — it always receives a fully-known combo, so it never faces
  this specific discovery ambiguity.
- No automatic letters-vs-digits inference; the user declares the
  pattern explicitly per key.
