# Entity declaration surfaces + reload cost

Fixes the `Unrecognized function or variable 'Raw_EMG'` failure and the
`"A variable named RawEMG already exists"` phantom, and pays for both by
*removing* full-registry reloads rather than adding them.

Status: drafted 2026-09-01, awaiting approval.

## Evidence (scidb.log, 2026-09-01 15:15–15:35)

| line | fact |
| --- | --- |
| 367 | `entities_file=None (writable), variable_file=None (read-only), matlab entities_file=None (read-only)` — no writable surface at all |
| 378 | `Loaded module file: ...\src\scistack_entities.py (0 functions)` — legacy `.py` picked up as an ordinary module |
| 384 | `Registry summary: 7 functions, 1 variables` — that one variable is `Raw_EMG` |
| 1010–1017 | canvas drop = `put_layout → write_manual_node → pipeline_store`, no declaration write |
| 1493 | `generate_matlab_command: ... output_types=['Raw_EMG']` |
| 1516 | `WARN no MATLAB classdef and no entity declaration for Raw_EMG` |
| 1527 | `ERROR MATLAB: for_each FAILED: Unrecognized function or variable 'Raw_EMG'` |

Two minutes elapse between the warning at 15:33:03.823 and the failure at
15:35:02.827. Everything needed to refuse the run was known at the warning.

### Measured cost of one `_refresh_registries()`

| stage | window | cost |
| --- | --- | --- |
| `config.load_config` | 15:15:43.601 → 15:15:46.059 | 2.5 s |
| `registry.load_from_config` | 15:15:46.059 → 15:15:47.679 | 1.6 s |
| `matlab_registry.load_from_config` (303 sources) | 15:15:47.679 → 15:16:02.566 | **14.9 s** |
| total | | **~16.5 s** |

The second startup reload (15:16:03.812 → 15:16:22.431) measured 18.6 s.
Creating one variable currently pays this in full.

## Root causes

1. **No writable surface.** `add_path` created `scistack.toml` at 15:15:43
   without an `entities_file` key. `scidb.entities.entities_path` only falls
   back to `src/scistack_entities.toml` *if it already exists*. So nothing
   could declare `Raw_EMG` for MATLAB, and `scimatlab.stubs.variable_stub_dir`
   returned `None` (no entities file ⇒ no stub dir), so no classdef was ever
   materialized.
2. **`BaseVariable._all_subclasses` is never pruned.**
   `registry.load_from_config` clears `_functions`, `_function_sources`,
   `_parameters`, `_parameter_sources`, `_path_inputs`, `_path_input_sources`,
   `_module_paths`, `_load_errors` — every registry except variables.
   `__init_subclass__` (`scidb/variable.py:109`) only ever inserts; no code
   anywhere deletes. A name is registered for the life of the process, so
   `create_variable`'s gate (`variable_service.py:42`) refuses against ghosts
   and the sidebar (`pipeline_service.py:222`) lists them as draggable.
3. **Drop ≠ declare.** `PipelineDAG.tsx:477` mints `var__{label}__{rand}` and
   persists layout only.

## Decisions

- **D1** Init runs in `bootstrap.open_or_create_project` — the one function
  both entry points already share. Every step is create-only-if-absent.
- **D2** Language stubs per language actually in use: `.py` if the config
  resolves any Python module/package, `.m` if it resolves any MATLAB source.
  Never overwritten. (user, 2026-09-01)
- **D3** A legacy `src/scistack_entities.py`/`.m` keeps being discovered and
  registered, read-only; nothing is migrated or moved. (user, 2026-09-01;
  consistent with `feedback_never_delete_mark_hidden`)
- **D4** Packaged projects (`pyproject.toml`) are still never auto-written —
  `config._reject_packaged_project` stands. Init logs and records a startup
  warning naming the exact key to add by hand.
- **D5** No new reload sites. Every step below either reuses an existing
  reload or replaces one with a narrower one. The 🔄 Refresh Code button keeps
  its full reload — that is the user-initiated escape hatch.
- **D6** Variable source attribution lives in `scistack_gui.registry` beside
  the existing `_function_sources`/`_parameter_sources`/`_path_input_sources`;
  only the `unregister` primitive goes into `scidb`, which owns the dict
  (CLAUDE.md NOTE 3). MATLAB already tracks sources via
  `matlab_registry._matlab_variables: dict[str, Path]`.

## Stage 1 — project init (D1–D4)

New `scistack_gui/services/project_init_service.py`, called from
`bootstrap.open_or_create_project` before the first `registry.load_from_config`:

1. `config.resolve_project_root(project, db_path)` — the existing single answer.
2. No `pyproject.toml`/`scistack.toml` at root → write `scistack.toml`.
   `pyproject.toml` present → skip per D4, warn.
3. Ensure `[tool.scistack] entities_file = "src/scistack_entities.toml"` and
   that the file exists with `scidb.entities.initial_text()`. Reuse
   `config.set_entities_file`, which already does exactly this.

Steps 2–3 run *before* the first `load_config`, so they cost no extra reload.

4. After `load_from_config` returns, write the per-language stubs (D2) from
   the already-loaded config. A fresh stub declares nothing, so **no reload
   follows it** — this is why step 4 is ordered after rather than before.

Stub header, both languages: read-only from the GUI; put here only what the
TOML cannot express (custom `to_db`/`from_db`, non-default `schema_version`,
PathInput `aliases`/`key_regex`/`regex`, computed Parameter values).

Knock-on: `target_file_service.get_or_create_target_file`'s auto-create
fallback (`reload_registries_from_disk`, a full 16.5 s reload) stops firing,
because the entities file now always exists. Kept as a safety net.

## Stage 2 — prune variables (root cause 2)

- `scidb/variable.py`: `BaseVariable.unregister(name)` classmethod.
- `registry.py`: `_variable_sources: dict[str, str]`, plus
  `_scan_module_variables(module, *, source)` mirroring
  `_scan_module_functions`' `__module__` filter so classes merely *imported*
  into a module aren't attributed to it.
- `load_from_config` / `refresh_module`: unregister every name in
  `_variable_sources`, clear it, repopulate during the scan. Names registered
  by anything else (scidb internals, test fixtures) are left alone.
- `_load_entities_file` and `matlab_registry._register_matlab_variable` record
  their sources the same way.
- `_diff_summary`'s removed-variables set becomes reachable for the first
  time; log it at INFO.

## Stage 3 — narrow reloads (D5, the cost ask)

New `registry.reload_entities_file()`: prune every `_parameters` /
`_path_inputs` / `_load_errors` / `_variable_sources` entry whose recorded
source is the entities file, re-run `_load_entities_file(path)`,
`record_source_hash(path)`. Cost: one TOML parse.

New `matlab_registry.reload_source(path)`: re-parse one `.m`, replacing only
entries sourced from it.

| call site | now | after |
| --- | --- | --- |
| `target_file_service.write_variable` | `_refresh_registries()` ~16.5 s | `reload_entities_file()` |
| `target_file_service.write_entity` | `_refresh_registries()` | `reload_entities_file()` |
| `update_declaration`, `.toml` source | `_refresh_registries()` ×1–2 | `reload_entities_file()` |
| `update_declaration`, `.m` source | `_refresh_registries()` | `matlab_registry.reload_source(path)` |
| `variable_service._create_matlab_variable` | `matlab_registry.refresh_all()` | `_register_matlab_variable(name, target_file)` — path already in hand |
| `variable_service.create_variable`, legacy `--module` | `registry.refresh_all()` | `refresh_module()` — already one file |
| `api/project._run_scan(force_refresh=True)` | full | unchanged (Refresh button, D5) |

`update_declaration`'s rollback path re-runs whichever narrow reload it used.

## Stage 4 — close the drop→run gap (root cause 3)

**Revised during implementation. Both halves were originally specified as
refusals; the test suite showed both to be wrong, for different reasons.**

- `layout_service.put_layout`: originally "reject an undeclared
  `variableNode`". **Reverted to a log line.** An undeclared manual variable
  node is a *designed* state — it graduates to a canonical `var__` id once a
  run gives it DB history (`graph_builder.merge_manual_nodes`), and
  paste/duplicate/extract copy such nodes wholesale.
  `test_pipeline_scopes.TestPasteNodes` uses synthetic labels on purpose and
  documents this. Refusing broke duplicate, paste, extract-to-submodule and
  edge-driven binding (9 tests).
- `matlab_command`: originally "escalate the warning to refusing the run".
  **Reverted to advisory**, and instead surfaced in the run console via the
  existing `warnings` channel, so the user sees it before waiting on MATLAB
  rather than only in a script comment and the log.

  The reason is not test breakage but correctness: `_unresolvable_var_types`
  sees classdefs the GUI registry parsed plus entities-file declarations,
  while a user's own `startup.m` can `addpath` a perfectly good `RawEMG.m`
  that nothing in the GUI will ever know about. Refusing would break that
  working setup. `scimatlab/stubs.py` already states the rule — *"MATLAB's
  path is the only authority on whether a class resolves"*, which is why
  `+scidb/entities.m` asks MATLAB itself via `exist(name, 'class')` — and
  the original refusal contradicted it.

  Follow-up worth considering separately: `+scidb/entities.m` already warns
  `scidb:entities:noClassdef` for names that still do not resolve *after*
  stub materialization. That check runs inside MATLAB, before the `for_each`,
  and is authoritative. Escalating **that** warning to an `error` is the
  correct way to fail fast — not done here because it is MATLAB control flow
  that cannot be exercised in this environment.

## Stage 5 — stub directory rename (user, 2026-09-01)

`scimatlab/stubs.py:34` `DEFAULT_STUB_DIRNAME`: `scistack_variables` →
`scistack_matlab_variables`. Clean break, no alias or fallback lookup
(`feedback_beta_no_deprecation`).

Touch points: `stubs.py:34` and its docstring at `:47`;
`scistack_gui/config.py:191` docstring; `scimatlab/tests/test_stubs.py:104`
(the one place that hardcodes the string rather than importing the constant).
`test_config.py:526,542` and `test_matlab.py:2467,2481` already import
`DEFAULT_STUB_DIRNAME` and need no edit.

An existing project keeps its old `src/scistack_variables/` folder — we don't
delete it (`feedback_never_delete_mark_hidden`). It simply stops being on the
MATLAB addpath, so the stubs in it go inert and are re-materialized under the
new name on the next run. No shadowing risk, because only the new directory is
ever added to the path. Init logs the old folder's presence once if found, so
the inert copy isn't a mystery later.

## Stage 6 — `{varName}scistack.m` stub filenames (user-reported)

**Not reproducible from the code as written, so this stage is diagnosis
first, not a speculative fix.** Every path that names a stub file builds it as
`{name}.m` with no infix:

| site | construction |
| --- | --- |
| `scimatlab/stubs.py:124` | `resolved / f"{name}.m"` |
| `matlab_registry.py:301,316` | `stub_dir / f"{name}.m"` |
| `variable_service.py:171` | `target_dir / f"{name}.m"` |
| `+scidb/entities.m:160` | `fullfile(stub_dir, [missing{i} '.m'])` |
| `+scidb/BaseVariable.m:883` | `fullfile(var_folder, [s '.m'])` |

A repo-wide search for a `"scistack"` literal concatenated into a filename
returns nothing. So the suffix is near-certainly riding in **on the name
itself** — `write_variable_classdefs` is being handed `RawEMGscistack` and
faithfully writing `RawEMGscistack.m`. The names reaching it come from three
places, and the bad one has to be among them:

1. the TOML `variables` array (`scidb.entities`),
2. MATLAB's unresolved-name list in `+scidb/entities.m` (`exist(n,'class')~=8`),
3. the GUI create request (`variable_service._create_matlab_variable`).

Plan:

- **Log the name at every hand-off**, before any file is touched:
  `write_variable_classdefs` logs the exact `wanted` list it received and the
  full target path per file; `ensure_variable_classdefs` logs what arrived
  over the bridge (before and after `str()` marshalling, since a MATLAB
  `string` vs `char` mismatch is a plausible mangler); `+scidb/entities.m`
  logs the `missing` cell it is about to send. That pins which of the three
  sources is producing it, from one reproduction.
- **Guard in `scimatlab.stubs`, regardless of source.** A MATLAB classdef
  filename must equal the class name, so validate each name before writing:
  reject anything that is not a valid MATLAB identifier, and refuse names not
  present in the declaration set that was asked for. Record it as an error in
  the returned `errors` list (already surfaced as a MATLAB warning and a GUI
  load error) rather than writing a file whose name can never resolve.
  This makes a bad name loud at the point of writing instead of producing a
  file that silently never matches its class.
- **Test**: `write_variable_classdefs` given `"RawEMGscistack"`-shaped or
  otherwise mangled input writes nothing and reports the rejection; given a
  clean name, writes exactly `{name}.m`.

If your reproduction has a `src/scistack_variables/` (soon
`scistack_matlab_variables/`) with such a file in it, the file's *contents*
settle it immediately: the `classdef` line inside says whether the name was
mangled before the write (`classdef RawEMGscistack`) or only the filename was
(`classdef RawEMG`). Worth checking before I start — it would collapse this
stage to a one-line fix.

## Stage 7 — logging + tests (CLAUDE.md NOTE 2)

Logging:
- One INFO line at config load naming every resolved declaration surface and
  why: entities file (writable), stub dir, each legacy read-only `.py`/`.m`.
  Today's line reports three `None`s and never mentions that
  `src/scistack_entities.py` is silently acting as a fourth.
- INFO on each init step, distinguishing created from already-present.
- DEBUG on every narrow reload naming the file and the entries pruned/added,
  so "did my write take effect" is answerable from the log.
- Removed-variable names in `_diff_summary`.

Tests:
- `test_project_init.py` — idempotency, packaged-project refusal, per-language
  stubs, existing files never overwritten.
- `test_variable_pruning.py` — declare, reload without the declaration, assert
  gone from `_all_subclasses` *and* creatable again (the reported bug).
- `test_narrow_reload.py` — an entities write updates the registry without
  re-importing modules or re-parsing MATLAB sources (assert via call counts on
  `_load_file_modules` / `matlab_registry.load_from_sources`). This is the
  regression guard for the cost ask.
- `test_drop_undeclared_variable.py` — `put_layout` rejects an unregistered
  variable label; `generate_matlab_command` refuses rather than warns.

## Explicit non-goals

- Migrating anything out of the legacy `.py`/`.m` (D3).
- Deleting the old `src/scistack_variables/` folder after the Stage 5 rename.
- Making `matlab_registry.load_from_config` itself faster. 14.9 s for 303
  sources is worth attacking, but this plan's job is to stop *calling* it,
  not to speed it up.
