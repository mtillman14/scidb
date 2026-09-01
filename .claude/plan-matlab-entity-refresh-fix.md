# Fix: "'delsysEMG' no longer resolves after the edit"

**Status: implemented 2026-09-01, uncommitted. Tests not yet run (no Python
in this environment).**

## The symptom

Editing a PathInput from the sidebar — pasting a root folder — returned:

> 'delsysEMG' no longer resolves after the edit — the new value may be invalid.

The write was correct; the *verification* was wrong, and the edit was rolled
back.

## Root cause

`target_file_service.update_declaration` writes, re-scans, and then verifies
that the entity still resolves (`_resolves_as_any_kind`), rolling the file
back if it does not. That re-scan (`_refresh_registries`) only ever refreshed
the **Python** registry:

```python
registry.refresh_all()      # or refresh_module()
```

But `registry.load_from_config` **clears** the shared `_path_inputs` /
`_path_input_sources` / `_parameters` / `_parameter_sources` dicts
(registry.py:239-246) and repopulates them from Python modules, packages,
entry points and the TOML entities file — *and nothing else*.

MATLAB-declared PathInputs and Parameters live in those **same shared dicts**;
they are put there by `matlab_registry._register_matlab_path_input_object` /
`_register_matlab_parameter_object` (see `matlab_registry._matlab_path_inputs`'
docstring). Only `matlab_registry.load_from_config` can restore them, and
`_refresh_registries` never called it.

So on every GUI entity write:

1. every MATLAB-declared PathInput/Parameter silently vanished from the
   registry (canvas nodes, `build_run_inputs`, command generation all lose
   them until the next 🔄 Refresh Code), and
2. for an edit **to** a MATLAB-declared PathInput, the post-write verification
   looked in the registry it had just emptied, found nothing, and rolled the
   good write back with the message above.

Every other "re-scan everything" site already got this right:
`api/project._refresh_registries`, `registry_reload_service`,
`variable_service`, `pipeline_service`, and bootstrap all refresh Python
**then** MATLAB.

## Changes

1. **`services/target_file_service._refresh_registries`** — refreshes both
   registries, Python then MATLAB (the startup order).
   `matlab_registry.refresh_all()` is a logged no-op when no MATLAB config was
   ever loaded, so pure-Python projects pay nothing.
2. **`services/target_file_service.append_and_refresh`** — was a second,
   Python-only copy of that sequence; now calls `_refresh_registries`.
3. **`services/target_file_service._verify_failure_reason`** (new) — when
   verification does fail, the message now carries the reason the registries
   recorded (`scidb.entities`' own `EntityError.describe()`, e.g. *"RAW (line
   2): missing a 'template' string"*), and a WARNING logs the whole registry
   state: known path inputs, known parameters, all load errors. Previously the
   only evidence was destroyed by the rollback that followed.
4. **`services/path_input_service.update_path_input`** — refuses an empty
   template up front (*"'X' needs a path template — a root folder alone is not
   a PathInput"*) instead of writing `{ template = "", root_folder = "…" }`,
   failing verification, and rolling back. This is the shape an edit takes when
   only the Root Folder box is filled in.
5. **`config.SciStackConfig.has_matlab`** (new property) + its four call sites
   in `bootstrap.py` and `server.py`. All four inlined
   `matlab_functions or matlab_variables or matlab_sources`, so a project whose
   only MATLAB config is `[matlab] entities_file` (or `variable_dir`) never
   loaded the MATLAB registry at startup and its entities did not exist in the
   GUI at all. Same failure family; found while tracing the above.

## Tests

`scistack-gui/tests/test_target_file_service.py::TestRefreshCoversMatlab`

- `test_editing_a_matlab_path_input_is_not_rolled_back` — the exact reported
  bug: a `[matlab] entities_file` PathInput, edited to add a root folder,
  survives on disk and in the registry.
- `test_matlab_entities_survive_a_toml_write` — creating a TOML Parameter does
  not evict MATLAB entities from the shared registry.
- `test_verify_failure_reports_the_recorded_reason` — a genuinely invalid write
  is still refused and rolled back, but the message names the reason.
- `test_empty_template_is_refused_before_any_write` — no write/rollback cycle
  for a blank template.

`tests/conftest.py` now resets `matlab_registry`'s module state
(`_config` and its four dicts) between tests. Required by change 1: with
`_refresh_registries` re-scanning MATLAB, a leaked `_config` from an earlier
test would re-register a previous test's tmp_path project.

## Verify with

```
pytest scistack-gui/tests/test_target_file_service.py -v
pytest scistack-gui/tests/test_matlab.py scistack-gui/tests/test_registry.py \
       scistack-gui/tests/test_startup.py scistack-gui/tests/test_config.py -q
```

The conftest change touches every GUI test, so the full
`pytest scistack-gui/tests` run is the real gate.
