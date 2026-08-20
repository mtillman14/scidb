# Code Discovery: Functions, Submodules, Variables, Constants, PathInputs, Sweeps

## Overview

The GUI's pipeline graph is built from **six** kinds of "things": functions,
variables, constants, PathInputs, sweeps, and submodules. As of the
PathInput/Sweep/Submodule source-of-truth work (see
`.claude/plan-pathinput-sweep-submodule-source-of-truth.md`), **all six** are
either scanned from source directly, or have a working source-code
translation. This doc is the map of which mechanism applies to which, in
both Python and MATLAB.

| Category | How it's found | Python source | MATLAB source |
|---|---|---|---|
| **Functions** | Scan source files/packages | `registry.py` / `scidb/discover.py` | `matlab_registry.py` + `matlab_parser.py` (regex) |
| **Variables** | Scan source files/packages | `BaseVariable` subclass (metaclass auto-register) | `classdef ... < ...BaseVariable` (regex) |
| **Constants** | Scan source files/packages | `scidb.Constant` instance (`scidb.constant(...)`) | **not supported** — no MATLAB equivalent |
| **PathInputs** | Scan source files/packages | top-level `scidb.PathInput(...)` binding | zero-arg "value getter" function (regex) |
| **Sweeps** | Scan source files/packages | top-level `scidb.Sweep(...)` binding (sugar for `EachOf`) | zero-arg "value getter" function (regex) |
| **Submodules** | GUI composition (`pipelineNode`) OR source (`scidb.Pipeline`) | `scidb.Pipeline`/`.use()`/`.bind()`, bidirectional (import + export) | export only (flattened into the script) |

---

## 1. Functions — scanned from source

### Python

Two separate scanners exist, used in different contexts:

- **`scistack_gui/registry.py`** — powers the live GUI/VS Code server. For
  each configured source (see "Where Python looks," below), it imports the
  module and calls `inspect.getmembers(module, callable)`, keeping anything
  that:
  - does **not** start with `_`
  - has `obj.__module__ == module.__name__` (i.e. actually *defined* there,
    not merely imported/re-exported — so `from scidb import for_each` inside
    a pipeline file doesn't leak `for_each` in as a discovered function)

  No `@scistack` decorator is required in this path — any bare top-level
  callable qualifies.

- **`scidb/src/scidb/discover.py`** (`scan_project`) — used for packaged
  projects (walks `src/{project}/` + everything in `uv.lock`). Here a
  function must be explicitly tagged `@scistack` (`is_scistack_function`,
  `scidb/src/scidb/pipeline.py`) to be picked up.

### MATLAB

`matlab_parser.py` never imports/runs the `.m` file — it's a pure regex
parse over the file's text (comments/line-continuations stripped first):

```
_FUNCTION_RE = r"^\s*function\s+(?:\[out1,out2\]\s*=\s*|out\s*=\s*)?name\s*\(params\)"
```

Rules:
- A file containing **any** `classdef` is never scanned for a function — a
  `function` match inside it is always a class method, not a pipeline step
  (prevents test-suite setup helpers from being mis-registered).
- A zero-arg function whose body constructs a `PathInput`/`Sweep` is a
  *value getter*, not a plain function — see §4/§5 below; `classify_matlab_file`
  checks for these BEFORE the plain-function check, since a getter also
  matches `_FUNCTION_RE`.
- The function name comes from the regex's name group; params/output names
  come from the bracket/parenthesis groups.
- Files can be explicitly declared (`[tool.scistack.matlab] functions =
  [...]`) or auto-classified during folder-scan (see below).

---

## 2. Variables — scanned from source

### Python

`BaseVariable` uses a metaclass (`BaseVariableMeta`) — **any** subclass
defined anywhere that gets imported registers itself into
`BaseVariable._all_subclasses` automatically, with no explicit call needed.
Discovery just needs to *import* the file; the metaclass does the rest.

### MATLAB

`parse_matlab_variable` regex-matches:

```
_CLASSDEF_RE = r"^\s*classdef\s+(\w+)\s*<\s*([\w.]+)"
```

and accepts it as a variable class if the parent name **ends with**
`BaseVariable` (covers both `BaseVariable` and `scidb.BaseVariable`). On
match, `matlab_registry._register_matlab_variable` creates a Python
*surrogate* class via `scimatlab.bridge.register_matlab_variable` so the DAG
builder can treat it like a real Python `BaseVariable` subclass.

---

## 3. Constants — scanned from source (Python only)

A constant is created explicitly with `scidb.constant(value, description=...)`,
which wraps `value` in a `Constant` object (`scidb/src/scidb/constant.py`)
that proxies attribute/operator access so it behaves like the wrapped value
everywhere except `isinstance(x, Constant)`.

Discovery (`_scan_module_constants` in `registry.py`, mirrored in
`discover.py`) walks `vars(module).items()` and keeps any non-`_`-prefixed
name bound to a `Constant` instance. Unlike functions/variables, this is
**not** filtered by `__module__` — `Constant` doesn't reliably expose one
(unknown attribute lookups proxy to the wrapped value), so a constant
imported into two scanned modules can legitimately show up attributed to
both.

**MATLAB has no equivalent.** There is no `scidb.constant()`-style wrapper
in `scimatlab`, so `matlab_registry.py` only tracks functions and variables
— constant values in a MATLAB pipeline are just plain values passed through
`for_each`'s `constants` struct, with no discoverable/named identity.
`pipeline_discovery.py`'s source→GUI import (§6) still surfaces these as
GUI constant nodes with a staged pending value, same as the GUI's own
"add a constant + pending value" action — it just has no *source-declared*
identity the way a Python `Constant` does.

---

## 4. PathInputs — scanned from source (clean break, 2026-08-20)

`PathInput` (`scifor/src/scifor/pathinput.py`) is a path-template object.
As of this migration, a PathInput is only GUI-visible when bound to a
top-level module name:

```python
RAW_EMG = scidb.PathInput("{subject}/{trial}.mat", root_folder=DATA_DIR)
```

### Python

`registry._scan_module_path_inputs` (mirrors `_scan_module_constants`
exactly) walks `vars(module).items()` for a `PathInput` instance, OR an
`EachOf` whose every alternative is a `PathInput` (this is how "alternate
templates" express themselves now — `EachOf(PathInput(t1), PathInput(t2))`
bound to one name — no separate GUI concept). No `__module__` filtering,
same reasoning as Constants.

There is **no DB-history fallback anymore** — the old
`overlay_saved_path_inputs`/layout.json-authored path was deleted. A
function's *historically recorded* PathInput usage (from a run before this
migration, or a still-inline/unnamed `PathInput(...)` at a call site) is
resolved back to a source-declared name by **content-matching**
(`graph_builder.resolve_path_input_name`: template+root_folder equality
against the registry) since the DB only ever recorded the value, never a
name. No match → a `__unresolved__:{template}` synthetic key, logged at
WARN — the node still renders (best-effort) but isn't wired to any current
source declaration.

### MATLAB

MATLAB has no module-level globals, so the Python binding doesn't translate
directly. Convention: a **PathInput getter** — a zero-argument function
whose body constructs `scifor.PathInput(...)` (or `scidb.PathInput(...)`,
or bare `PathInput(...)`), named after the object it exposes:

```matlab
function p = raw_emg_path()
    p = scifor.PathInput('{subject}/{trial}.mat');
end
```

`matlab_parser._parse_value_getter` (shared with Sweep, see §5) regex-parses
this: locate a zero-arg `_FUNCTION_RE` match, reject if the file has a
`classdef` (same one-file-one-entity rule as `parse_matlab_function`),
search the function's own body (up to the next `function`/EOF) for
`= (scifor\.|scidb\.)?PathInput\(`. Static-only — never runs MATLAB.
`matlab_registry` tracks these **by name only** (`_matlab_path_inputs:
dict[str, Path]`) — **known gap**: not yet merged into the GUI canvas's
`pathInput__` nodes or `execution_service`'s content-matching resolution
(both Python-only today); a MATLAB pipeline's PathInput resolves through
the MATLAB bridge calling the getter function natively at run time,
independent of this registry. Extracting real template/root_folder values
statically would need a much deeper MATLAB literal-expression parser than
this file's regex approach.

### Portability (cross-user export/import)

`portability_service.py` still bundles a referenced PathInput's resolved
value into the export document (`export_pipeline`, reading
`registry.get_path_inputs_registry()`) — but the semantics shifted from
"the only copy" to an **import-time fallback on a local name miss**:
`import_pipeline_document` reuses the LOCAL definition untouched if the
name already exists there; only on a miss does it call
`path_input_service.create_path_input` to *materialize* the bundled value
into the importer's own configured source file (never a phantom GUI-only
value). A materialization failure (no `variable_file` configured) surfaces
in the import result's `materialization_errors`, not a silent drop.

### GUI-side creation

`create_path_input`/`layout_service.py` append `NAME = PathInput(...)` to
`config.variable_file` and refresh the registry (`path_input_service.py`,
mirrors `variable_service.create_variable`'s append-only pattern exactly).
**No update/alternates endpoints anymore** — editing an existing
PathInput's template means editing the source file directly and hitting
Refresh Code. "Delete" (`delete_path_input`) hides the `pathInput__{name}`
node only (`pipeline_store.hide_node`) — the source declaration is never
touched (never delete, mark hidden).

---

## 5. Sweeps — scanned from source (2026-08-20), now real `EachOf` sugar

`scifor.Sweep` (`scifor/src/scifor/each_of.py`) is a trivial
`class Sweep(EachOf)` — `isinstance(x, EachOf)` is `True` for a `Sweep`, so
every existing `EachOf` expansion path (Python and MATLAB) picks it up with
zero changes. A Sweep only becomes GUI-visible bound to a top-level name,
exactly like PathInput:

```python
WINDOW_SECONDS = scidb.Sweep(10, 20, 30)
```

### Python

`registry._scan_module_sweeps` scans for `isinstance(obj, Sweep)` — note
this is checked BEFORE the PathInput/EachOf checks in the same scan loop,
since a `Sweep` IS an `EachOf`. A bare, unnamed `EachOf(...)` used inline at
a call site is intentionally NOT discovered — only a *named* top-level
binding is GUI-visible, same rule as an unwrapped literal constant.

At execution time (`execution_service.build_run_inputs`), the registry
already holds a live `Sweep`/`EachOf` object, so it's used directly as the
resolved input — no reconstruction needed (this used to rebuild
`EachOf(*values)` from a layout.json values list; now the object already
*is* that).

### MATLAB

`+scifor/Sweep.m` — `classdef Sweep < scifor.EachOf`, mirroring the Python
shape (MATLAB's `isa(x, 'scifor.EachOf')` respects inheritance the same way
Python's `isinstance` does, so every `isa(..., 'scifor.EachOf')` check in
`+scidb/for_each.m`/`+scifor/for_each.m` picks up a `Sweep` for free). Same
"value getter" convention and known name-only gap as PathInput (§4) — see
`matlab_parser.parse_matlab_sweep` / `matlab_registry._matlab_sweeps`.

### Portability & GUI creation

Same treatment as PathInput (§4): `export_pipeline`/`import_pipeline_document`
reuse-local-else-materialize via `path_input_service.create_sweep`;
`layout_service.create_sweep`/`delete_sweep` append-only creation / hide-only
delete, no update endpoint.

---

## 6. Submodules — GUI composition, with a working source-code translation

What appears in the graph as `pipelineNode` is a **nested pipeline**
(another whole pipeline placed as a node inside a parent one) — the
"Hypothesis tabs & submodules" feature, backed by `_pipeline_uses` DB rows
(`parent_pipeline_id` / `child_pipeline_id` / `use_id` / `binding_json =
{key_map, params, iterate}`). `scidb.Pipeline`/`.use()`/`.bind()`
(`scidb/src/scidb/pipeline.py`) already implements the identical shape in
source code — `binding_json`'s three keys are a direct, field-for-field
match with `PipelineBinding.key_map`/`.params`/`.iterate`.

### Source → GUI import (`scistack_gui/pipeline_discovery.py`)

A user's file can define a pipeline in source:

```python
pipe = Pipeline("gait_analysis")   # deliberately no db= -- see module docstring
pipe.activate()
for_each(bandpass_filter, {"signal": RawSignal, "low_hz": 20}, [Filtered], ...)
```

`Pipeline` registration is side-effect-free until `run_*` is called — the
same property that lets functions/variables/constants be discovered by
*importing* a file. `discover_and_seed_pipelines(db)` reads
`scidb.pipeline._all_pipelines` (filtered to `db=None` — the convention that
tells a genuine user-authored pipeline apart from
`execution_service.build_backend_pipeline`'s own per-request COMPILED
Pipelines, which always set `db=`), recursively seeds each into GUI state
(one manual `functionNode` + manual `variableNode`/`constantNode`/edges per
`StepSpec`, one `_pipeline_uses` row per `PipelineBinding` in `.uses`), then
discards them from scidb's own bookkeeping (avoids scidb's "pipeline
registered but never run" atexit warning; also how the function knows
what's new next time — nothing is left behind to re-process).

**"Create once"**: a discovered pipeline whose name already exists locally
is skipped entirely, never overwritten — same precedent as
`create_variable`/`create_path_input`. Re-editing the source file and
hitting Refresh Code does not resync hand-edited GUI state.

Manual `variableNode`/`constantNode` creation (not just edges) is required
because `build_variable_nodes`/`build_constant_nodes` only render from DB
run history — a genuinely never-run type/constant needs a manual node to
show up at all (`merge_manual_nodes` is what makes a manual node appear
regardless of history). PathInput/Sweep nodes are the one exception —
always registry-derived (§4/§5), never manual.

Wired into `bootstrap.open_or_create_project` (initial load, all project
modes) and `api/project.py._refresh_registries` (loose-script/single-file
"Refresh Code" path). **Known gap**: not wired into the packaged-project
(`pyproject.toml` present) `scan_project` refresh branch — see the comment
at that call site in `api/project.py`.

### GUI → source export (`scistack_gui/services/code_export_service.py`)

Already existed before this migration (contradicts
`docs/claude/gui-export-to-plain-python.md`'s "Status: not yet built" —
that doc is stale). Reuses `build_backend_pipeline`'s compiled
`scidb.Pipeline` directly (`Pipeline._composed_steps()`/`_topo_order()`) for
Python; a parallel manual closure walk + type-level topological sort for
MATLAB (registry.get_function only resolves Python callables, so it can't
reuse the same `Pipeline` object).

**Submodule composition is FLATTENED**: `_composed_steps()` already resolves
the full `.uses` closure with bindings pre-applied (key_map/params/iterate
rewritten into each `StepSpec`) and returns one flat, topologically-ordered
step list — the exported script has no explicit `child.use(parent.bind(...))`
calls, just one linear sequence of `for_each(...)` calls. PathInput/Sweep
values are inlined as reconstructed literals via `repr()`/duck-typing
(`getattr(value, "alternatives", None)`), not name references — needed zero
changes for the new `Sweep` class.

---

## Where Python looks for source files (config.py)

Governs where the **function/variable/constant/PathInput/Sweep** scanners
above look for `.py`/`.m` files in the first place — three tiers, in
priority order:

1. **`pyproject.toml` / `scistack.toml`**, `[tool.scistack]`:
   - `modules = [...]` — explicit files, directories (recursively walked),
     or glob patterns
   - `packages = [...]` — installed pip packages, walked recursively via
     `pkgutil.walk_packages`
   - `auto_discover = true` — scans installed packages' `scistack.plugins`
     entry points
   - `[tool.scistack.matlab]` — `functions = [...]`, `variables = [...]`,
     `path_inputs = [...]`, `sweeps = [...]`, `sources = [...]`
     (unclassified, auto-classified per-file), `src_dir`
2. **Folder-scan fallback** (no config file found at all): recursively walks
   the project root for `.py`/`.m` files, pruning noise dirs (`.git`,
   `__pycache__`, `.venv`, `node_modules`, `build`, `dist`) and, for MATLAB,
   `private/`, `@ClassName/`, `+package/` directories (never swept in — see
   `_is_matlab_skip_dir`).
3. **GUI "Paths" popup** (`add_path`/`remove_path` in `config.py`) — writes
   directories into `scistack.toml`'s `modules` + `[matlab] sources` lists;
   only available for loose-script projects (no `pyproject.toml`). Fully
   round-trips every `[tool.scistack]`/`[matlab]` field it knows about
   (including `path_inputs`/`sweeps` as of this migration) via
   `_render_scistack_toml` — earlier versions of this function silently
   dropped any field it wasn't explicitly passed on every popup save; fixed
   alongside adding the new MATLAB fields.

Later sources win on name collisions (functions/constants: last-loaded
wins, with a warning logged; see `_register_function`/`_register_constant`).

## See also

- `docs/claude/multi-source-discovery.md` — the `[tool.scistack]` config
  format in more detail (Python side).
- `docs/claude/input-markers-colname-pathinput-pathoutput.md` — full
  PathInput/PathOutput/ColName resolution semantics (PathInput's own
  template-resolution mechanics are unchanged by this migration — only
  *discovery* changed).
- `docs/claude/each-of-variant-expansion.md` — `EachOf`'s own design; `Sweep`
  is documented there as sugar, not a separate mechanism.
- `docs/claude/matlab-gui-implementation.md`,
  `docs/claude/matlab-gui-support-analysis.md` — broader MATLAB-GUI design.
- `docs/claude/pipeline-import-identity.md` — pipeline/submodule identity
  (`pipeline_id`) across export/import (unaffected by this migration —
  works identically whether a submodule originated from hand-drawn GUI
  wiring or a source-code import).
- `docs/claude/gui-export-to-plain-python.md` — **stale**, says "not yet
  built"; see §6 above for what's actually there.
- `.claude/plan-pathinput-sweep-submodule-source-of-truth.md` — the plan
  this whole migration executed.
