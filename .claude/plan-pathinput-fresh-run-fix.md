# Fix: PathInput-backed functions can't run for the first time

Prerequisite for to-do #10 (agreed 2026-08-13: fix this before designing
EachOf multiplicity — building EachOf on a path that can't execute at all
is building on sand).

## Confirmed root cause

PathInput nodes are **name-matched, not edge-resolved**. A PathInput's
link to a function param is "the PathInput's `name` equals the function's
parameter name" — `pipeline_store`/`layout.py`'s `path_inputs[]` list
(`layout.py:402-424` `read_all_path_input_names`, `layout.py:427-439`
`write_path_input`) stores `{name, template, root_folder}` with **no
target-function field at all**. Any edge a user drags from a PathInputNode
to a function on the canvas is cosmetic: `edge_resolver.py`'s
`node_id_to_var_label` (lines 27-55) only recognizes `var__`-prefixed or
`variableNode`-typed sources, so a `pathInputNode` source falls through
every branch in `resolve_function_edges` (confirmed by direct read,
`edge_resolver.py:130-139`) and contributes nothing to `input_types`.

Consequence, verified directly against both call sites that build a
`for_each` `inputs` dict:

- `execution_service.py::derive_fn_targets`'s never-run fallback (lines
  112-165) builds `input_types` purely from `resolve_function_edges`
  (variable-node edges) and `constants` from constant-node pending values.
  **No branch anywhere reads `path_inputs[]` or constructs
  `scifor.PathInput(...)`.** A function whose only unresolved input is a
  PathInput-backed param (e.g. `def load_data(filepath)`, the typical
  first step of nearly every real pipeline) gets that param silently
  dropped from `input_types`.
- The two places that actually turn a target into the live `inputs=`
  dict passed to `scidb.for_each` — `api/run.py:420-465` (per-node Run
  button) and `execution_service.py::_build_inputs` (lines 549-566, the
  pipeline compiler) — are **near-identical duplicated blocks**, and
  *neither* constructs `scifor.PathInput(...)` anywhere. `grep`-confirmed:
  `PathInput(` is only ever constructed in `api/matlab_command.py`
  (MATLAB code-export text) and parsed back out of stored strings in
  `graph_builder.py::parse_path_input` — never instantiated for live
  Python execution.

Net effect: clicking Run on any function whose input comes from a
PathInput node — first run or re-run, GUI-driven or not — never actually
supplies that parameter to `for_each`. This is very likely the actual
wall blocking "start using the pipeline for real," since a PathInput-fed
loading step is the near-universal first step of a real pipeline.

## What `scifor.PathInput` needs (confirmed from `scifor/src/scifor/pathinput.py`)

```python
PathInput(path_template: str, root_folder: str | Path | None = None, ...)
```
— matches exactly what's stored per-name in `layout.json`'s
`path_inputs[]` (`{name, template, root_folder}`). No other required
args for the common case.

## Proposed fix

**1. Detect PathInput-backed params in `derive_fn_targets`'s never-run
fallback** (`execution_service.py:112-165`). After computing
`resolved.input_types` (variable-wired) and `resolved.constant_names`,
check remaining `sig_params` against `layout_store.read_all_path_input_names()`
(name → `{template, root_folder}`). Store matches as a new, JSON-safe
field on the target dict: `target["path_input_params"] = [param, ...]`
(names only — deliberately NOT constructing the live `scifor.PathInput`
object here, since target dicts get serialized into `run_start` push
messages elsewhere in `api/run.py`, and a `PathInput` instance isn't
JSON-safe).

**2. Deduplicate the two input-building blocks into one shared helper**
in `execution_service.py` (promote `_build_inputs` to a public function
both `api/run.py` and the pipeline compiler call, instead of `api/run.py`
carrying its own ~45-line copy of the same variable/constant logic). This
is the natural place to add PathInput construction once, instead of
patching two copies and risking the same drift that caused this gap to go
unnoticed. The shared helper gains: for each name in
`target.get("path_input_params", [])`, look up `{template, root_folder}`
and set `inputs[param] = scifor.PathInput(template, root_folder=root_folder)`.

**3. Add logging** (per project convention — this file already logs
heavily): an info line when a target resolves a PathInput-backed param
(mirroring the existing `"[execution] '%s': overriding DB output types
with manual wiring"` style), and a warning when a `sig_params` entry is
STILL unresolved after all three passes (variable/constant/path-input) —
today that case just silently vanishes from `input_types`; a named
function should always account for every one of its params in the
never-run path.

## Open risk — needs a live test, not just code review

I haven't traced whether `api/run.py`'s existing `schema_filter`/
`schema_iterables` plumbing (the "which schema keys to iterate" kwargs
alongside `inputs=`) is already correct for a PathInput-driven fresh run,
or whether PathInput's own `apply_discovery()` (which fills empty
iterables from the filesystem — `pathinput.py:563-682`) needs to be
invoked explicitly somewhere in this path. The README's basic pattern
(`scifor.PathInput(...)` + empty-list schema kwargs) may already fall out
correctly once the object exists in `inputs`, since `scifor.for_each`
itself calls `apply_discovery` internally per its own docs — but I want
to verify this against a real run rather than assume, since it's the one
part of this fix I can't confirm by reading alone.

## Tests

New coverage for `derive_fn_targets`'s never-run PathInput case
(`tests/test_pipeline_scopes.py` already covers `derive_fn_targets`
generally — natural home for a new case — or a new
`tests/test_execution_service.py` if that file is getting crowded) plus
a test on the consolidated input-builder confirming it produces a real
`scifor.PathInput` instance with the right template/root_folder. You run
pytest yourself per your standing instruction — I'll hand over the
command once the fix is written.

## Status: BUILT (2026-08-13), pending your live-test verification

Sign-off received: consolidate the duplicate input-builders (yes), verify
schema-key iteration via a live test after building (yes).

**Design changed from the original sketch above** after a fair
question mid-build: the first draft threaded a new `path_input_params`
field through every branch of `derive_fn_targets` AND
`derive_target_for_node` (4+ call sites), justified as "the never-run
fallback needs it." That framing was wrong — PathInput isn't tied to
which branch derivation takes; it's never a citizen of `input_types` or
DB history AT ALL (no versioned variable class — it resolves files, not
a DB record), so both branches equally lack it. Recognizing that, the
built version resolves PathInput in exactly ONE place —
`build_run_inputs(target, function_name)` — as the last step after
variable/constant resolution: whatever signature params are still
unfilled get checked by name against the stored PathInput registry.
`derive_fn_targets`/`derive_target_for_node` are UNCHANGED (only a
docstring note added to the former explaining the decision).

**What shipped:**
- `execution_service.py`: `_build_inputs` (private, `api/run.py`-only-
  duplicated) renamed to `build_run_inputs` (public, takes `function_name`
  now) and extended with the PathInput-by-elimination step described
  above. Its one internal caller (`build_backend_pipeline`) updated.
- `api/run.py`: the ~45-line duplicate input-building block replaced with
  a single call to `execution_service.build_run_inputs(v, function_name)`.
  No more independently-drifting copy.
- Logging: an info line each time a param resolves via PathInput
  (`"input '%s' resolved via PathInput(%r, root_folder=%r)"`), in the one
  place this now happens.
- Tests: `tests/test_pipeline_scopes.py::TestPathInputExecutionResolution`
  (4 cases) — never-run target correctly omits the path-input param from
  `input_types` (derivation unchanged); `build_run_inputs` resolves it to
  a real `PathInput` instance with the right template; the SAME
  resolution shows up on a compiled pipeline step's `.inputs` (the actual
  Run Pipeline / Run Until Here path, not just the helper in isolation);
  and a signature param with no stored PathInput match is left absent
  from `inputs` rather than crashing (matches the existing fail-safe
  contract other unresolvable params already have).

**Still needed from you:** run pytest, then do the live end-to-end check
we agreed on — build a real never-before-run PathInput-driven function in
the GUI and click Run, to confirm the existing `schema_keys=`/
`schema_iterables` plumbing (unchanged by this fix) actually drives
per-combo filesystem discovery correctly once the `PathInput` object is
present, not just that the object gets constructed.

```
cd /workspace
uv run pytest scistack-gui/tests/test_pipeline_scopes.py -k PathInput -v
```
(or your normal full-suite command — these tests live alongside the
existing `TestExecutionCompiler`/`TestDeriveTargetForNode` coverage in
the same file).
