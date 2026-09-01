# Plan: auto-materialize MATLAB classdefs for TOML-declared variables

**Status: implemented 2026-09-01, uncommitted. Tests written but NOT run
(no Python in this environment — the user runs them).**

Commands to run:

```
pytest scimatlab/tests/test_stubs.py scimatlab/tests/test_matlab_entities_api_surface.py -q
pytest scistack-gui/tests/test_matlab.py scistack-gui/tests/test_config.py scistack-gui/tests/test_entity_update_endpoints.py scistack-gui/tests/test_variable_service.py -q
```

**Symptom (2026-09-01, user's `test_afl` project):**

```
12:55:28 [matlab] [entities] MATLAB load: 0 variable(s), 0 parameter(s), 0 path input(s), 0 rejected, from .
12:55:29 [matlab] ERROR: MATLAB: for_each FAILED: Unrecognized function or variable 'RawEMG'.
Error in scistack_run (line 103)
        {RawEMG()});
```

Two independent defects, both visible in that four-line log.

## Defect A — the generated script asks MATLAB to find the project from its cwd

`api/matlab_command._entities_script_lines` emits a bare `scidb.entities();`
(matlab_command.py:45). `+scidb/entities.m` then calls
`py.scimatlab.bridge.load_entities()` with **no** project root, so
`scidb.entities.entities_path(None)` walks up from *MATLAB's pwd*
(entities.py:444). Outside the project that finds nothing, and
`load_for_project` returns `EntitiesFile(path=Path())` — which is what
`from .` in the log means, with `0 variable(s), 0 parameter(s), 0 path
input(s)`.

Every declared Parameter/PathInput is therefore silently out of scope in a
generated script whenever MATLAB's cwd is not inside the project.
`entities.m` already accepts `PROJECT_ROOT`, and
`matlab_command_service.generate_matlab_command` already resolves
`project_root` (it logs it, and uses it for PathInput roots) — it just never
passes it through.

## Defect B — a TOML-declared variable never gets its classdef

`scidb.entities()` deliberately does not create variables: a variable is a
*type*, and MATLAB requires one classdef file per type. The stub is written
by `scistack_gui.matlab_registry.materialize_variable_stubs`
(matlab_registry.py:214), which `load_from_config` only calls when **both**
`entities_file` and `[matlab] variable_dir` are configured
(matlab_registry.py:185-191). With no `variable_dir` the branch is skipped
in silence, no classdef is ever written, and the first thing that tells the
user is `Unrecognized function or variable 'RawEMG'` in the middle of a run.

The desired flow (user, this session):

> create the variable in the GUI -> entity added to the entities TOML file ->
> on MATLAB run, check if the variable has a classdef .m file -> if not,
> create it from the TOML file so the run succeeds.

Note the run that failed is a *first-run* function: `fn_variants` is empty,
so `generate_matlab_command` takes the template branch and the outputs cell
comes from edge inference — which is why the failure lands on the `for_each`
outputs (`{RawEMG()}`) rather than in a `register_variable` block.

## Layer decision (CLAUDE.md NOTE 3)

Materialization moves **out of the GUI** and into **scimatlab**: "make a
declared variable referenceable from MATLAB" is a MATLAB-wrapper concern,
not a GUI concern, and a hand-written MATLAB script that calls
`scidb.entities()` deserves the same guarantee as a GUI-generated one.

The *existence check* belongs in MATLAB, not Python. MATLAB's own path is
the only authority on whether `RawEMG` resolves; checking "is there a file
in the stub dir" would happily write a second `RawEMG.m` shadowing a
hand-written classdef that lives somewhere else on the path. So:
`+scidb/entities.m` asks MATLAB (`exist(name, 'class')`), and only the names
that fail get written through the bridge.

## Stages

### ensure_classdefs — new `scimatlab/src/scimatlab/stubs.py`

- `variable_stub_dir(project_start=None) -> Path | None`
  Resolution order: `[tool.scistack.matlab] variable_dir` (relative to the
  config's directory) -> `<entities_file.parent>/scistack_variables`.
  `None` when the project has no entities file at all. Uses
  `scifor.discovery.find_project_config` / `read_scistack_section` and
  `scidb.entities.entities_path` — no new config parsing, and no dependency
  on `scistack_gui.config`.
- `write_variable_classdefs(names, project_start=None) -> dict`
  Writes `classdef <Name> < scidb.BaseVariable` for each name that has no
  file in the stub dir yet; creates the dir only when there is something to
  write. Returns `{"dir": str, "created": [...], "skipped": [...],
  "errors": [...]}`. Never overwrites, never deletes (project ethos:
  generated-but-referenced files are not removed).
- `bridge.ensure_variable_classdefs(names, project_start)` — thin bridge
  entry so MATLAB can call it; logs each file written at INFO through
  `scidb.log.Log` with `layer="matlab"`.

### entities_m — `+scidb/entities.m` self-heals before the run

After rebuilding Parameters/PathInputs, for each name in
`payload{'variables'}`: skip if `exist(name, 'class') == 8`. Collect the
rest, call the bridge once, `addpath` the returned dir, `rehash`, and log
what was created. Runs for both `nargout` shapes. When a name still does not
resolve afterwards, `warning('scidb:entities:noClassdef', ...)` naming the
file that was expected — the diagnostic that was missing entirely.

`entities.m` is already emitted at the top of every generated script (after
the addpath block, before `configure_database`), so this covers GUI runs,
sidecar runs, and hand-written scripts through one seam.

### project_root — generated scripts stop guessing

`_entities_script_lines(entities_script, entities_file, project_root)` emits
`scidb.entities('<project_root>');` when the root is known. Threaded through
both `generate_matlab_command` and `generate_matlab_pipeline_command`
(`project_root` is already a parameter of both).

### gui_alignment — the GUI uses the same dir and the same writer

- `matlab_registry.materialize_variable_stubs` delegates its writing to
  `scimatlab.stubs.write_variable_classdefs`, and skips any name already in
  `_matlab_variables` (a hand-written classdef the registry parsed), so the
  GUI cannot create a shadowing duplicate either.
- `load_from_config` drops the `matlab_variable_dir is not None` gate and
  uses the resolved stub dir.
- `config.load_config` adds the resolved stub dir to `matlab_addpath` when
  the project has MATLAB config, so the generated script's addpath block
  contains it. `matlab_variable_dir` itself stays configured-only —
  defaulting the *field* would make `has_matlab` true for every Python
  project with an entities file.
- `services/variable_service._create_matlab_variable` stops rejecting with
  "No matlab.variable_dir configured" when the entities file can supply a
  default dir.

### preflight — refuse to generate a script that cannot run

In `matlab_command_service.generate_matlab_command`, every var type about to
be emitted as `Type()` is checked against `matlab_registry`'s known
variables + the entities file's declared variables. Unknown names produce a
WARNING (`fn=..., unknown_var_types=[...]`) and a `% WARNING:` comment in
the script itself. Declared-but-unmaterialized names do not warn — stage
`entities_m` fixes those at run time.

### diagnostics — make defect A impossible to miss again

`bridge.load_entities` logs at WARNING, not INFO, when no entities file was
resolved: the cwd it searched from, the `project_start` it was given, and
the fact that no project config was found. The current INFO line reads
`from .`, which is only legible if you know it is `str(Path())`.

## Tests

- `scimatlab/tests/test_stubs.py` — stub dir resolution (configured
  `variable_dir` wins; default under the entities file; `None` with no
  project), write/skip/no-overwrite, dir created only on demand.
- `scimatlab/tests/test_matlab_entities_api_surface.py` — static check that
  `+scidb/entities.m` calls the bridge entry and `addpath`s the result
  (same pattern as `test_matlab_log_api_surface.py`).
- `scistack-gui/tests/test_matlab_command.py` — generated script contains
  `scidb.entities('<root>')`; addpath block contains the stub dir when
  `variable_dir` is unset; unknown var type produces the warning comment.
- `scistack-gui/tests/test_matlab.py` — `materialize_variable_stubs` skips a
  name the registry already knows from a hand-written classdef.

## What changed (as built)

| File | Change |
|---|---|
| `scimatlab/src/scimatlab/stubs.py` | **New.** `variable_stub_dir`, `classdef_text`, `write_variable_classdefs`. |
| `scimatlab/src/scimatlab/bridge.py` | `ensure_variable_classdefs` entry; `load_entities` now WARNs (with the cwd it searched) when no entities file resolved, instead of an INFO line reading `from .`. |
| `+scidb/entities.m` | Self-healing block: `exist(name,'class')` -> bridge -> `addpath` + `rehash`, `scidb:entities:noClassdef` / `classdefWriteFailed` warnings. |
| `api/matlab_command.py` | `_entities_script_lines` takes `project_root` and emits `scidb.entities('<root>')`; `_unresolvable_var_type_lines` preflight in both generators. |
| `matlab_registry.py` | `materialize_variable_stubs` delegates writing to `scimatlab.stubs`, skips names with a known classdef, registers skipped-but-present ones; moved after `load_from_sources`; no longer gated on `variable_dir`. |
| `config.py` | Resolved stub dir joins `matlab_addpath` for MATLAB projects; `matlab_variable_dir` docstring records why it stays configured-only. |
| `services/variable_service.py` | Falls back to the resolved stub dir instead of refusing with "No matlab.variable_dir configured". |
| `docs/claude/entity-editability-model.md`, `scimatlab/README.md` | Ownership, the default location, and the two diagnostics. |

## Known gap left open

`scistack_gui.config` reads `entities_file` only from the explicit config
key, while `scidb.entities.entities_path` also accepts a conventional
`src/scistack_entities.toml` that exists. A project relying on the
convention alone still *runs* (MATLAB self-heals at run time) but shows no
entities in the GUI. Pre-existing; not changed here because it is a change
to config semantics, not to this failure.

## Not in scope

- Terminal-run tracking (`plan-matlab-terminal-run-tracking.md`) — unrelated.
- Deleting stubs whose TOML declaration disappears. Still never delete.
