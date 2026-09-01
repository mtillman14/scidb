# Plan: the entities file becomes TOML (`src/scistack_entities.toml`)

**Status: ALL STAGES (1–7) IMPLEMENTED, uncommitted, 2026-09-01.**
Two things still need the user, not the test suite: a real **MATLAB run**
of `+scidb/entities.m` (never executed — no MATLAB here), and a **browser
pass** over the Paths popup and the entity panels. One decision is open:
whether `[matlab] entities_file` should stop being writable (see Stage 5).
Reference doc: `docs/claude/entities-toml-format.md`.
Source: `todos_26-08-22.md` item 3 — the default "Variable File" should be
(a) named "Entities File", (b) relative to the project root rather than the
datasets folder, (c) a TOML file with sections for the entity kinds.

Supersedes the write-half of `docs/claude/entity-editability-model.md`
(which stays correct about *policy* — confinement, staleness, rollback —
and becomes wrong about *format*).

## Decisions (confirmed with the user, 2026-08-31)

- **D1 — TOML is the only WRITABLE surface; the other two stay readable.**
  *(Revised 2026-08-31, mid-Stage-2, at the user's question "is it possible
  to make the TOML path live alongside the .m and .py entities files?")*
  One language-neutral `entities_file` is the only file the GUI writes.
  `variable_file` (`.py`) and `[matlab] entities_file` (`.m` script) are
  **demoted to read-only discovery inputs**, not deleted: their
  declarations still appear in the GUI, marked read-only with their source
  location — which is already the contract for any declaration outside the
  entities file, so this adds no new concept.

  Why this shape rather than full replacement or two writable files:
  Python coexistence is *already free* (`registry._scan_module_parameters`
  runs over every scanned module, so a `.py` file's declarations are
  discovered whether or not it is the write target). MATLAB coexistence
  costs only *keeping* `matlab_parser.parse_matlab_entities_script`, not
  writing anything new. A second **writable** target is what would cost:
  it reopens "which file does a new Parameter land in?", and doubles the
  write path the whole editability model rests on.
- **D2 — hand-written code reaches entities through a `scidb.entities`
  namespace.** `from scidb import entities; entities.WINDOW_SECONDS` in
  Python; `e = scidb.entities(); e.WINDOW_SECONDS` in MATLAB. No generated
  `.py` shim, no import magic.
- **D3 — three sections: `[variables]`, `[parameters]`, `[path_inputs]`.**
  The note's "Sweeps"/"Constants" are one `scidb.Parameter` since
  2026-08-24 (entity-editability-model.md D6); reintroducing both spellings
  would restore the split that removed.
- **D4 — no `type` key, no `options` tables; the section IS the type.**
  An entry is `NAME = <the value itself>`. Each section accepts exactly
  the fields its kind needs and nothing more: Variables are a value-less
  list of names, PathInputs take `template` + optional `root_folder`,
  Parameters take their value(s) directly. Everything a declaration
  cannot say in that shape is a Python declaration, read-only.
- **D5 — the project root is inferred, not asked for.** Upward search for
  an existing `pyproject.toml`/`scistack.toml` → explicit
  `--project-root` (the VS Code workspace folder) → server cwd →
  `db_path.parent` as the last resort. Whichever rule fires is logged at
  INFO.

## The format

```toml
# src/scistack_entities.toml
# Variables are a value-less list, so they come first: a bare top-level
# key placed after a [section] header would be parsed as belonging to it.
variables = ["StepLength", "EmgEnvelope"]

[parameters]
SAMPLING_RATE_HZ = 1000                    # one value
WINDOW_SECONDS   = [10, 20, 30]            # three values (fan-out)
SUBJECT_IDS      = ["01", "02"]            # stays string, never 1/2
CONFIG           = { fld1 = 1, fld2 = 2 }  # the dict IS the value

[path_inputs]
EMG_FILE = "{subject}/{session}_emg.csv"
RAW_FILE = { template = "{subject}/raw.csv", root_folder = "/data/raw" }
```

Rules that fall out of the format:

- **A TOML array is the alternative list.** `WINDOW_SECONDS =
  [10, 20, 30]` is three Parameter values. To declare a Parameter whose
  single value is genuinely a list, nest it: `X = [[1, 2, 3]]` — the
  outer array is always alternatives. No extra key, no ambiguity.
- **An inline table means the value under `[parameters]`, and the field
  set under `[path_inputs]`.** `CONFIG = { fld1 = 1 }` is a dict-valued
  Parameter — a case the `type`-keyed draft could not express without
  escaping. A PathInput has no dict-shaped value, so a table there is
  unambiguously `{template, root_folder}`; any other key is a rejected
  entry.
- **Zero-padded keys survive by construction.** `["01", "02"]` is a TOML
  string array; there is no eval and no literal re-parse that could turn
  `"01"` into `1` (`feedback_zero_padded_schema_keys`). Strictly safer
  than both the `.py` and `.m` paths it replaces, which round-tripped
  values through a literal parser.
- **A one-value Parameter is a bare scalar; adding a value makes it an
  array.** A change of *form* in the file, but not of kind, id, node or
  history — `Parameter(30)` and `Parameter(30, 45)` are the same
  construct (D6), and the editor rewrites the whole RHS either way.
- **Descriptions are not expressible.** `Parameter.description` and a
  Variable docstring have no home in this format, so they become
  Python-only: still read and shown for `.py`-declared entities, not
  settable from the GUI. See "Consequences" below.
- **What TOML cannot express stays in Python, read-only.** A
  `BaseVariable` with custom `to_db`/`from_db`, a non-default
  `schema_version`, a PathInput using `aliases`/`key_regex`/`regex`, or a
  Parameter whose values are computed (`Parameter(*range(10, 60, 10))`) —
  each remains a `.py` declaration discovered through `modules` and
  refused by the editor with its exact source location. That is the
  existing read-only contract, unchanged.

### Consequences of the value-only shape

Three follow directly, and each needs a call in Stage 4/6 rather than
silent behaviour:

1. **The GUI's description field for Parameters becomes dead.**
   `create_parameter`/`update_parameter` take `description`, and the
   panel has an input for it. Plan: drop it from both the TOML write path
   and the UI, keeping `scidb.Parameter(description=...)` for
   hand-written Python. A field that silently discards what you type is
   worse than no field.
2. **Same for the Variable docstring** in the create-variable form.
3. **`variables` must be written before the first section header.** The
   GUI always writes it first; the loader additionally rejects a
   `variables` key found *inside* `[parameters]`/`[path_inputs]` with an
   explicit "move this above the first section header" error, because
   TOML would otherwise silently attach it to the preceding table.

**One deliberate extension, flagged:** `[path_inputs] X = [{template =
...}, {template = ...}]` (an array of the same two-field form) loads as
`EachOf(PathInput, PathInput)`. Nothing in the GUI creates one, but
`portability_service.import_pipeline_document` materializes bundled
multi-template PathInputs and would otherwise have nowhere to write them.
It adds no new fields — only the same array-means-alternatives rule the
`[parameters]` section already has.

## Stages

### Stage 1 — `scidb.entities` (new, scidb-owned) — **IMPLEMENTED 2026-08-31, uncommitted, pytest not yet run**

Landed: `scidb/src/scidb/entities.py`, `scidb/tests/test_entities_toml.py`,
`scifor.discovery.{find_project_config,read_scistack_section,extract_scistack_section}`,
and `entities` exported from `scidb/__init__.py`.

New `scidb/src/scidb/entities.py`. scidb owns the declaration grammar
(CLAUDE.md NOTE 3), exactly as `scidb.source_edit` does for the Python
form.

Read half:
- `load(path) -> EntitiesFile` — parse, validate, construct:
  `variables = [...]` → `type(N, (BaseVariable,), {})` per name
  (auto-registers via `__init_subclass__`); `[parameters] N = <value |
  [values]>` → `Parameter(*values)`; `[path_inputs] N = <template |
  {template, root_folder} | [...]>` → `PathInput(...)` /
  `EachOf(PathInput...)`.
- Validation is per entry, and a rejected entry is recorded (name + line)
  and skipped rather than raised — one bad entry must not take the whole
  file down, which is exactly what an exec'd `.py` entities file did.
  Rejections: a non-string in `variables`, a name that isn't a valid
  identifier, an unknown key in a `[path_inputs]` table, a PathInput
  table with no `template`, a `variables` key nested inside a section,
  and a duplicate name across sections.
- Each entry carries `source_file` + `source_line` (the `[section.NAME]`
  header line), feeding the GUI's "declared at file:line".
- `namespace()` → attribute access object backing D2, resolving the
  project's entities file lazily.

Write half (mirrors `source_edit`'s render/splice role):
- `find_entry_span(text, section, name)` (the RHS of `NAME = ...` inside
  `[section]`, or the element inside the `variables` array),
  `render_value(...)`, `upsert_entry(text, ...)` — **line-level splice,
  not whole-file regeneration**, so hand-written comments and unrelated
  entries survive an edit. Reuses `Span`/`splice` from `source_edit`.
- With options tables gone, every write is exactly one span: one entry,
  one line, one splice.

Locating the file from scidb (for D2) needs "find the project config, read
one key". That helper goes into `scifor.discovery` next to `read_project_name`
and is then used by BOTH `scidb.entities` and `scistack_gui.config` —
not copied (`feedback_avoid_scifor_scidb_duplication`,
`project_discovery_consolidation`).

### Stage 2 — config: `entities_file` joins `variable_file` — **IMPLEMENTED 2026-08-31, uncommitted, pytest not yet run**

- `SciStackConfig` gains `entities_file` (writable). `variable_file` and
  `matlab_entities_file` are **kept and demoted** per the revised D1, with
  docstrings saying so.
- `load_config` folds `variable_file` into `modules` when nothing else
  covers it. Previously `set_variable_file` guaranteed that entry; nothing
  writes the key any more, so nothing maintains it either — without this,
  a hand-written config's declarations would silently stop being
  discovered.
- `set_variable_file`/`clear_variable_file` → `set_entities_file`/
  `clear_entities_file`; default `src/scistack_entities.toml`, created via
  `scidb.entities.initial_text()`. Both round-trip the demoted keys so a
  Paths-popup write never deletes a `variable_file` a user still has.
- The entities file is **not** appended to `modules` — it is not `.py` and
  must never reach `_exec_file_modules`.
- `infer_project_root` + `set_project_root_hint` implement D5 and fix (b);
  every branch logs which rule fired. `--project-root` added to both
  `__main__.py` and `server.py`; the VS Code extension passes its
  workspace folder. `add_path`'s first write moves to the inferred root
  too, seeding **both** the database's directory and the project root so
  folder-scan discovery doesn't silently narrow.
- Route/handler/UI rename came with it (pulled forward from Stage 6, since
  leaving the frontend calling a deleted route was not an option):
  `/api/project/entities-file`, `set_entities_file`/`clear_entities_file`
  JSON-RPC, `EntitiesFileEditor.tsx`, "Entities file" labels, wizard
  default `src/scistack_entities.toml`. The Paths popup also now shows the
  two read-only legacy files, so a user can see where an entity the editor
  refuses to touch comes from.

**Known seam until Stage 4:** the entities file is now TOML, but
`parameter_service`/`path_input_service`/`variable_service` still append
Python source. `test_bootstrap.py::test_pathinput_created_after_bootstrap_lands_in_eager_entities_file`
is `xfail` for exactly this and asserts the TOML form Stage 4 will write.
`TestUpdateDeclaration` in `test_target_file_service.py` still configures a
`.py` entities file so the format-independent policy (confinement,
staleness, rollback) stays covered meanwhile.

### Stage 3 — registry: scan the TOML — **IMPLEMENTED 2026-09-01, uncommitted**

`registry._load_entities_file` calls `scidb.entities.load` and registers
the results, **last** in `load_from_config` so a TOML declaration wins over
a same-named one found in a module: the entities file is what the GUI
writes, so if the two disagree, what the user just edited is what they
should see. Per-entry errors go into the same `_load_errors` list a failed
module load uses, so a bad declaration surfaces in the Discovered Code
panel instead of vanishing. Variables need no registration call —
constructing the class registers it through `__init_subclass__`.

Stages 3 and 4 are **mutually dependent** and were done together:
`update_declaration` verifies a write by re-scanning, so writing TOML
before the registry could read it would have rolled back every edit.

The MATLAB-side deletions listed below are **not** done — under the revised
D1 the `.m` entities script stays readable, so `matlab_parser`'s parse half
stays. Its render half is unused by the TOML path but still serves the
still-writable `matlab_entities_file` (see Stage 4's note).

Original scope, for reference:

- `registry.load_from_config` calls `scidb.entities.load(config.entities_file)`
  and registers parameters/path_inputs/variables with
  `source=str(entities_file)`; `record_source_hash` as today.
- `matlab_registry`: entities-script loading deleted. MATLAB and Python now
  read the *same* declarations, so MATLAB-side Parameter/PathInput
  registration disappears rather than being ported.
- `matlab_parser`: `parse_matlab_entities_script`,
  `collect_matlab_literal_scope`, `binding_path_input_literal`,
  `render_matlab_parameter`, `render_matlab_path_input` and their helpers
  are deleted. Function/classdef parsing stays.
- **MATLAB Variables still need a classdef file** — MATLAB cannot create a
  class at runtime, and `class(obj)` is the table name. So a
  `[variables.N]` entry is *materialized* as a stub `.m` classdef in
  `matlab_variable_dir` when one is configured. The TOML stays the
  declaration of record; the stub is generated output, not a second
  declaration surface.

### Stage 4 — services: writes go to the TOML — **IMPLEMENTED 2026-09-01, uncommitted**

Landed: `target_file_service.write_entity`/`write_variable` (creation) and
a TOML branch in `update_declaration` (editing), with all write *policy*
kept verbatim — confinement, stale-hash guard, atomic write, re-scan
verification, rollback, PathInput history. `_location_of` gained a TOML
branch so a read-only TOML declaration still reports `file:line`.
`update_declaration` now takes `toml_expr` alongside the other two.

**Deviation from the plan as written, deliberate:** `ensure_scidb_import`
and the Python append path are **kept**, behind a suffix dispatch
(`is_toml_target`). Legacy single-file mode (`--module pipeline.py`) has no
config file to record an entities file in, and auto-creating a
scistack.toml there would flip the project into config-driven discovery as
a side effect of creating a Parameter. So: `.toml` target → TOML grammar,
anything else → the existing Python grammar. `_invalidate_bytecode` is now
a no-op for non-`.py`.

Consequences 1–2 are implemented as **logged drops**, not silent ones: a
`description` passed to `create_parameter`, or a `docstring` passed to
`create_variable`, is written nowhere and logged at WARNING naming the
value. Removing the UI fields is Stage 6.

Not yet done: `matlab_entities_file` is still a writable target (see
`_editable_targets`' docstring) until Stage 5 gives MATLAB a TOML path.

Original scope, for reference:

- `target_file_service`: `get_or_create_target_file` →
  `get_or_create_entities_file`; `update_declaration` delegates the
  grammar to `scidb.entities.upsert_entry`. **Policy is kept verbatim**:
  entities-file confinement, stale-hash guard, atomic write, re-scan
  verification, rollback, PathInput history recording (D7).
  `ensure_scidb_import` and `_invalidate_bytecode` are deleted — TOML has
  neither imports nor bytecode, which removes that entire class of bug.
- `parameter_service` / `path_input_service` / `variable_service` write
  TOML entries instead of appending source lines. Their result shapes
  (`{ok, name}` / `{ok, error}`) do not change, so `portability_service`
  and `layout_service` are untouched; their `description` / `docstring`
  arguments are dropped (Consequences 1–2), which is a signature change
  their callers in `api/` and `server.py` follow.

### Stage 5 — MATLAB access — **IMPLEMENTED 2026-09-01, uncommitted; needs a real MATLAB run**

- `scimatlab.bridge.load_entities(project_start)` — flattens the loaded
  entities file to plain dicts/lists/scalars. Only plain data crosses:
  handing MATLAB the constructed Python objects would give it Python
  proxies, not the MATLAB classes `for_each` expects. `root_folder` is
  `None` (MATLAB `[]`) when unset, never `""`, so "no root" stays
  distinguishable from "rooted at the empty string".
- `+scidb/entities.m` — `e = scidb.entities()` returns a struct of
  `scidb.Parameter`/`scidb.PathInput` objects; `scidb.entities()` with no
  output assigns them into the **base workspace**, reproducing what
  `scistack_entities;` did for a script. Rejected entries are re-raised as
  MATLAB warnings — someone at the MATLAB prompt never sees the GUI's
  load-errors panel. Uses the existing `+scidb/+internal` converters
  (`pylist_to_cell`, `pydict_to_struct`, `from_python`).
- `api/matlab_command._entities_script_lines` emits **both** sources when
  both are configured (they declare different names), TOML first.
- `matlab_registry.materialize_variable_stubs` writes a `classdef` stub per
  TOML-declared variable into `matlab_variable_dir`. Create-only: a stub
  whose declaration later disappears is left alone
  (`feedback_never_delete_mark_hidden`). `variable_service._create_matlab_variable`
  now declares in the TOML first, then materializes the stub, so a MATLAB
  variable is declared once and visible to both languages.

**Correct-by-inspection only:** there is no MATLAB in this environment, so
`entities.m` has never been executed. The Python half (bridge payload
shape, stub materialization, emitted command lines) is covered in
`test_matlab.py` and `test_entity_update_endpoints.py`.

**Open decision for Stage 6/7:** `matlab_entities_file` is still a
*writable* target (`_editable_targets`). Now that MATLAB can read the TOML,
revised D1 says it should be demoted to read-only like `variable_file` —
but that removes a working edit path from MATLAB-only projects, so it is
the user's call, not a silent change.

Original scope, for reference:

- `+scidb/entities.m`: `e = scidb.entities()` calls the Python loader over
  the existing bridge (`py.` — MATLAB has no TOML reader, and every other
  `+scidb` entry point already routes through Python) and marshals into a
  struct of `scidb.Parameter` / `scidb.PathInput` objects.
- `api/matlab_command.py`'s `_entities_script_lines` emits the
  `scidb.entities()` load instead of running a script. One place, all
  execution tiers, still idempotent.

### Stage 6 — GUI and extension (part a: the rename) — **DONE 2026-09-01; most of it landed with Stage 2**

The rename shipped in Stage 2 (leaving the frontend calling a deleted route
was not an option). What remained for this stage was Consequences 1–2:
removing the Parameter description and Variable docstring inputs.

**They never existed.** `EditTab.tsx` calls `create_parameter` and
`create_variable` with `{ name }` only, and no panel renders a description
field — the arguments existed solely in the API/service signatures. So
nothing was removed, and nothing is silently dropped in the UI. The
arguments are **kept** on the services because they still work for the
non-TOML targets (a `.py` module's class docstring, a MATLAB classdef
comment); passing one with a TOML target logs a WARNING naming the value.

Also verified format-agnostic and needing no change: the read-only hint in
`ParameterSettingsPanel`/`PathInputSettingsPanel` ("Declared in X — edit it
there and hit Refresh Code").

`VariableFileEditor.tsx` → `EntitiesFileEditor.tsx`, label **"Entities
File"**; `PathsPopup` row label; `paths.variable_file` →
`paths.entities_file`; `api.ts` `set_entities_file`/`clear_entities_file`;
routes `/api/project/entities-file`; `server.py` JSON-RPC handler names;
`api/bootstrap.py`'s `variable_file` field → `entities_file` defaulting to
`src/scistack_entities.toml`; `ProjectBootstrapWizard` label + default;
`extension/src/projectInit.ts`'s scistack.toml template comment.

Also in this stage: remove the Parameter **description** input and the
Variable **docstring** input from the create/edit forms (Consequences
1–2). Descriptions still render for `.py`-declared entities that have
one — they just cannot be authored from the GUI any more.

### Stage 7 — logging, tests, docs — **DONE 2026-09-01**

Logging and tests landed with each stage rather than at the end. Docs:

- **New**: `docs/claude/entities-toml-format.md` — the format, the four
  rules, what it deliberately cannot express, the coexistence table, where
  the code lives, per-entry errors, the two traps the format removed
  (stale bytecode; `variables` below a section header), MATLAB specifics.
- **Rewritten format halves**: `config-file-formats.md` (the three
  declaration keys, plus a new "Where a NEW config file gets written"
  section for `infer_project_root`) and `entity-editability-model.md` (a
  superseded-in-part banner, the TOML scalar/array table beside the Python
  one, and MATLAB's classdef-stub constraint).
- **Corrected in passing**, because they would actively mislead:
  `code-discovery-categories.md`, `scistack-gui-project-setup-guide.md`,
  `multi-source-discovery.md`, `matlab-gui-implementation.md`,
  `matlab-path-resolution.md`.

Original scope, for reference:

Logging (NOTE 2): INFO for the resolved entities path, the project-root
rule that fired, and per-section counts after each load; WARN per rejected
entry with its name and line; DEBUG per constructed entity; INFO on every
write with old → new, as `update_declaration` already does.

Tests: new `scidb/tests/test_entities_toml.py` (parse, per-entry error
isolation, `"01"` preservation, multi-template round-trip, comment
preservation across an edit). Updated: `test_config.py`,
`test_target_file_service.py`, `test_entity_round_trip.py`,
`test_bootstrap.py`, `test_api.py`, `test_portability.py`,
`test_pipeline_scopes.py`, `test_entity_update_endpoints.py`, `conftest.py`.

Docs: `docs/claude/entities-toml-format.md` (new); rewrite the format
halves of `config-file-formats.md` and `entity-editability-model.md`.

## Risks

1. **249 `variable_file` references** across 22 Python files, 5 TS files,
   and the docs. Mechanical, but wide.
2. **The MATLAB `.m` entities script and its parser/renderer are deleted**,
   not migrated. Any project using one must move those declarations into
   the TOML. There is no MATLAB in this environment, so Stage 5 is
   correct-by-inspection until you run it — same standing caveat as
   entity-editability-model.md.
3. **Variables materialized as MATLAB classdef stubs** is new generated
   output; a stub whose TOML entry later changes needs regenerating on
   refresh.

## Verification

Per `feedback_user_runs_tests`, the pytest commands are handed over, never
run here. Frontend `tsc`/`build` are run directly
(`project_node_npm_available`).
