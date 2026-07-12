# Input Markers: ColName, PathInput, PathOutput

## Purpose

Three `for_each` input wrappers look similar (each resolves to a string/path at
run time) but play very different roles. This note distinguishes them and
records exactly when and where each is resolved across the scifor and scidb
layers, so they don't get conflated again.

| Marker | Resolves to | When | Reads/writes files? |
|--------|-------------|------|---------------------|
| `ColName` | a **column name** string | static (up front) or per-column | no |
| `PathInput` | an **existing input** file path | per-combo, with filesystem **discovery** | the function *reads* it |
| `PathOutput` | an **output** file path | per-combo + per-column | the function *writes* it |

The one-line mental model: **`ColName` = "which column," `PathInput` = "find the
input file," `PathOutput` = "name the output file."**

## ColName — a column name

Defined in `scifor/src/scifor/colname.py` (and a thin scidb mirror in
`scidb/src/scidb/colname.py` that converts to the scifor marker). Two forms:

- `ColName(df)` / `ColName(MyVar)` — **static**. Resolved once, up front, to the
  single non-schema data column name of the DataFrame/variable. Raises if there
  are 0 or 2+ data columns.
- `ColName()` (or the bare class `ColName`) — **deferred**. Resolves per-column
  inside a `for_columns` iteration to the column currently being fed to the
  function. Requires at least one iterate input.

```python
"data_column": scifor.ColName,   # deferred → "intervention", "prepost", ...
```

It is a *resolution marker*, not a real constant — see "Version keys" below.

## PathInput — locate an existing input file

Defined in `scifor/src/scifor/pathinput.py`. Substitutes `{key}` from combo
metadata into a template and resolves it to a real path the function then
**reads**. In scidb it is heavyweight:

- it drives **Step 3 filesystem discovery** (`scidb/foreach.py:602`,
  `_find_pathinput`, `discover()`) — walking the filesystem to enumerate which
  combos exist as files, even to decide how many combos to run;
- it is **loadable** (`_is_loadable`) — wrapped in a `PerComboLoader` whose
  `.load(**combo)` resolves the path per combo;
- `regex=True` matches the last segment against existing files and raises
  `FileNotFoundError` on zero matches;
- zero-padded numeric filenames (`6MWT-001.mat` from `trial=1`) are handled
  natively by a numeric-equivalence fallback in `load()` — see
  `docs/claude/pathinput-zero-padded-matching.md`.

All of that is about *finding inputs to read*. Pointing a `PathInput` at an
output path is wrong: discovery finds nothing and regex mode errors.

## PathOutput — name an output file

Defined in `scifor/src/scifor/pathoutput.py`, re-exported as `scidb.PathOutput`.
A **pure output-path template**: no discovery, no regex, no `.load`. It
substitutes two sources via literal `str.replace` (so other braces pass through):

- **combo metadata** — every `{key}` matching a metadata name for the current
  combo (e.g. `{subject}`, `{session}`). Missing keys are left untouched.
- **current column** — the token `{ColName}` becomes the current `for_columns`
  column. Using `{ColName}` requires an iterate input (hard error otherwise).

The result keeps the template's type: `Path` in → `Path` out, `str` in → `str`
out. The function receives a finished path as a plain argument and decides what
to write.

```python
"filename": scifor.PathOutput(root / "{subject}_{ColName}_anova2way.pdf"),
# → root/"1_intervention_anova2way.pdf", root/"1_prepost_anova2way.pdf", ...
```

This is the right home for per-column output filenames. Earlier iterations
overloaded `ColName(template)` for this — reverted, because a column-name marker
shouldn't emit a filesystem path — and `PathInput` is the wrong host because of
its input-discovery baggage above.

## How PathOutput resolves (scifor only)

scidb **delegates the core loop to `scifor.for_each`** (`scidb/foreach.py:437`),
so all `PathOutput` resolution lives in scifor; scidb is transparent to it.

In `scifor/src/scifor/foreach.py`:

1. `PathOutput` is **not** a data input (`_is_data_input` is False) → it lands in
   `constant_inputs`.
2. Guard (Step 6.5 area): a `PathOutput` whose template contains `{ColName}` with
   **no** iterate input raises — mirroring the deferred-`ColName` guard.
   Metadata-only templates are fine without an iterate input.
3. **Non-iterate** combo: `_resolve_path_outputs(filtered_inputs, metadata, None)`
   resolves the template with combo metadata just before `_call_fn`.
4. **for_columns** combo: `_run_column_iteration` (now receiving `metadata`)
   resolves each `PathOutput` per column with `metadata` + the current column.

scidb only re-exports `PathOutput` and (see below) excludes it from version keys.
Because it has no `.load`, is not in `_is_loadable`'s tuple, and is not a
`PathInput`, scidb's discovery/loading never touch it — `_convert_inputs` passes
it through as a constant into `scifor.for_each`, and `state.full_combos` carries
the schema-key metadata it substitutes.

## Version keys: ColName and PathOutput are excluded

`scidb/src/scidb/foreach_config.py` `_get_direct_constants` excludes **both**
`ColName` and `PathOutput`. Reasons:

- They are per-combo/column **resolution markers**, not fixed scalar constants.
- The for_each save path serializes `config_keys` via `json.dumps` **without**
  `default=str` (`scidb/foreach.py:501`); a raw marker object (neither is
  JSON-serializable) would crash it.
- Semantically, an output path is *write bookkeeping*, not computation identity.
  So changing only the output filename does **not** fork the version-key group
  (a re-run reuses/overwrites rather than creating a new variant). If output
  paths ever need to fork variants, this is the line to revisit.

## Key Files

| File | Role |
|------|------|
| `scifor/src/scifor/colname.py` | `ColName` (two forms) |
| `scifor/src/scifor/pathinput.py` | `PathInput` (input discovery/loading) |
| `scifor/src/scifor/pathoutput.py` | `PathOutput` (output template + `resolve`) |
| `scifor/src/scifor/foreach.py` | `_resolve_path_outputs`, per-column resolution in `_run_column_iteration`, the `{ColName}`-needs-iterate guard |
| `scidb/src/scidb/colname.py` | scidb `ColName` → scifor marker |
| `scidb/src/scidb/foreach_config.py` | `_get_direct_constants` excludes `ColName` + `PathOutput` from version keys |
| `scifor/tests/test_foreach_standalone.py` | `PathOutput` + deferred-`ColName` tests |
| `scidb/tests/test_for_columns.py` | `TestForColumnsPathOutput`, deferred-`ColName` tests |

## MATLAB note

The MATLAB bridge serializes a deferred scifor `ColName` as `{"kind":
"colname"}` (`sci-matlab/src/sci_matlab/bridge.py:771`) and rebuilds a bare
`scifor.ColName()` on the other side. `PathOutput` is **not** threaded through
MATLAB yet — a templated output path would not round-trip. Add it there only if
MATLAB pipelines need per-column output filenames.

## See Also

- `docs/claude/for-columns-iteration.md` — the column-wise fan-out/reassembly
  that `{ColName}` resolution rides on.
- `docs/claude/scifor-for-each-internals.md` — the standalone loop.
- `docs/claude/scidb-for-each-internals.md` — input conversion + the delegation
  to `scifor.for_each`.
