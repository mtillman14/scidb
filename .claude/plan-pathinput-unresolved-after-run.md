# Plan: `__unresolved__` PathInput node appears after a MATLAB run

Date: 2026-09-01

## Symptom

A MATLAB function node ran successfully from the GUI for the first time. Immediately
afterwards a second PathInput node appeared on the canvas labelled
`__unresolved__:data/aw_pilot002/data/10MWT/10MWT_{pass}.mat`, alongside the real
`delsysEMG` node it duplicates.

## Diagnosis (from `test_logs.md`)

Timeline:

| time | log | meaning |
|---|---|---|
| 13:21:47 | `[entities] Declared path input delsysEMG with 1 template(s)` | one declared PathInput, `root_folder` unset |
| 13:21:48 | `build_path_input_nodes: building 1 path input node(s)` | canvas correct before the run |
| 13:22:37 | `generate_matlab_command: ... path_input_params=1, project_root=/Users/.../aging-well-abilitylab` | GUI renders the run script |
| 13:23:09 | `WARN: [graph_builder] PathInput usage with no matching source declaration: template='data/aw_pilot002/data/10MWT/10MWT_{pass}.mat' root_folder='/Users/.../aging-well-abilitylab' — renamed or removed?` | the just-recorded run cannot be attributed |
| 13:23:09 | `build_path_input_nodes: building 2 path input node(s)` | the ghost node |

Root cause — `scistack-gui/scistack_gui/api/matlab_command.py::_format_path_input`:

```python
if not root_folder and project_root:
    if not _Path(bare).is_absolute():
        root_folder = project_root          # <-- rewrites the entity's identity
```

The declaration is `delsysEMG = { template = "data/..." }` with **no** root folder. The
generated script emits `scifor.PathInput("data/...", root_folder="/Users/.../aging-well-abilitylab")`.
`PathInput.to_key()` serializes `(template, root_folder)`, so the run is recorded under a
key the declaration does not have.

`graph_builder.resolve_path_input_name` content-matches DB history against the registry on
exactly that `(template, root_folder)` pair — there is no name in DB history — so the match
fails and it synthesizes `__unresolved__:{template}`.

The injection exists for a real reason: a rootless `PathInput` resolves against
`scifor.pathinput._find_project_root()`, which walks up from **cwd**, and MATLAB's cwd is
the temp script directory. So the GUI was fixing a resolution problem by mutating identity.

This is not GUI-only: a run launched from the user's own MATLAB script (using the declared,
rootless PathInput) records a *different* key than the same run launched from the GUI.

## Fix

Per CLAUDE.md NOTE 3, the resolution problem belongs to scifor, not the GUI.

1. **scifor** (`scifor/src/scifor/pathinput.py`) — add an explicit project-root override:
   `set_project_root()` / `get_project_root()` / `clear_project_root()`, consulted by
   `_find_project_root()` when no explicit `start` is given. It changes only *resolution*,
   never `to_key()`, so identity stays `(template, None)`.

2. **scimatlab** (`bridge.py`) — expose `set_pathinput_project_root(root)`, and have
   `load_entities(project_start)` set the override to the project it just loaded. Any
   script calling `scidb.entities(root)` — generated or hand-written — now resolves
   rootless PathInputs against that project, not MATLAB's cwd.

3. **GUI** (`api/matlab_command.py`) — stop injecting `root_folder`. Emit an explicit
   `py.scimatlab.bridge.set_pathinput_project_root('<root>')` preamble line instead, so the
   guarantee holds even when no entities file is configured.

4. **GUI** (`domain/graph_builder.py`) — make `resolve_path_input_name` tolerant of the
   already-recorded bad keys: after the exact and history matches fail, retry with a
   `root_folder` equal to the project root normalized to `None`. Without this, every run
   the user has *already* recorded keeps its ghost node forever. Logged at INFO. The root
   is passed in explicitly (`resolve_path_input_name` / `convert_scidb_path_inputs` /
   `aggregate_variants` gained a `project_root` argument, sourced from the new
   `registry.get_project_root()`) so `graph_builder` stays pure.

5. **GUI** (`services/matlab_command_service.py`) — `_drop_project_root_folder` normalizes
   a DB-read `root_folder` that is just the project root back to `None` before generating.
   `path_input_params` reads the old rows straight back, so without this the next run
   re-records the divergent key and the ghost node never heals.

## Supporting change

`scidb.entities.project_root(start)` — the config file's parent, shared so the bridge
doesn't re-derive it (`entities_path` now uses it too).

## Tests

- `scifor/tests/test_pathinput_project_root.py` — override wins over cwd; `to_key()`
  unaffected; explicit `root_folder` and explicit `start` still win; `clear_project_root()`
  restores the walk-up behavior.
- `scistack-gui/tests/test_matlab.py` — `TestFormatPathInput`: the generated script no
  longer injects `root_folder` for a rootless declaration, keeps an explicitly declared
  one, and emits the project-root pin before the first `scifor.PathInput`.
  `TestDropProjectRootFolder`: the DB-read normalization.
- `scistack-gui/tests/test_graph_builder.py` — `TestResolvePathInputNameProjectRoot`:
  project-root-rooted history attributes to the rootless declaration instead of
  `__unresolved__`; a different root still doesn't; an exactly-declared root still wins.
- `scimatlab/tests/test_bridge_project_root.py` — `set_pathinput_project_root` and
  `load_entities` pin scifor's root; the payload's `root_folder` stays `None`.

## Verification commands

```
.venv/bin/python -m pytest scifor/tests/test_pathinput_project_root.py scifor/tests/test_to_key.py scifor/tests/test_foreach_pathinput.py -q
.venv/bin/python -m pytest scimatlab/tests/test_bridge_project_root.py scimatlab/tests/test_stubs.py -q
.venv/bin/python -m pytest scistack-gui/tests/test_graph_builder.py scistack-gui/tests/test_matlab.py -q
.venv/bin/python -m pytest scidb/tests -q -k entities
```
