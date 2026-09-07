# Plan: speed up MATLAB function execution (generated run script preamble)

Date: 2026-09-02

## What the existing log already tells us

From `/workspace/scidb.log` (real runs, warm MATLAB terminal session, project on
`Y:\…` and database on `\\fs2.smpp.local\…` — both **network shares**):

| Run (14:17:16) | wall time |
| --- | --- |
| GUI emits command (last `[scidb]` line before dispatch) → MATLAB's first `[matlab]` line | **~4.4 s** |
| `[entities] MATLAB load` → `Loaded 3 entity declaration(s)` | 0.05 s |
| → `configure_database (MATLAB host)` | 0.16 s |
| → `for_each_prepare returned` | 0.07 s (`0.011s` inside Python) |
| → `for_each_save` → `db.close` | 0.14 s |

Same shape in the 14:16:16, 14:18:36, 14:25:32 and 16:27:00 runs: **4.0–4.8 s
before MATLAB's first scidb log line**, then a few hundred ms of scidb work.
For a short run that pre-log window is ~90 % of the wall time; for the 16:27 run
(34 s of real function work) it is ~12 %.

Everything that happens in that 4–5 s window is currently **unlogged**: VS Code
writing `scistack_run.m` + `matlab.openCommandWindow` + `sendText`, then MATLAB
parsing the script, the `pyenv` preamble, and the `addpath` block. We cannot
attribute it yet — hence Stage 0.

## Stage 0 — instrumentation — IMPLEMENTED 2026-09-02 (uncommitted)

Files changed:
- `scistack-gui/scistack_gui/api/matlab_command.py` — `_timing_init_lines` plus
  a `_PreambleTiming` collector (`section` / `summary_lines` / `total_lines`);
  wired into both `generate_matlab_command` (variants **and** template
  branches) and `generate_matlab_pipeline_command`. The summary names **only
  the sections that were emitted**: a first cut listed all six unconditionally,
  which put `pyenv=%.3fs` into scripts generated with
  `python_executable=None` and broke `test_pyenv_preamble_omitted_when_none` —
  that contract is "no pyenv code at all", and a phase for a section that never
  ran is also just wrong.
- `scistack-gui/extension/src/matlabTerminal.ts` — write / openCommandWindow /
  sendText deltas + a local-time `sent_at` stamp (`formatStamp`). Bundle
  rebuilt (`dist/extension.js`).
- `scidb/src/scidb/database.py` — `Log.timer` phases in `configure_database`
  (`database_manager`, `register_types`, `scifor_set_schema`) and in
  `DatabaseManager.__init__` (`duck_open`, `ensure_*`); `attach_log_file` moved
  **before** construction so those lines reach the file on a MATLAB host,
  which is usually the first scidb caller in its process.
- Tests: `scistack-gui/tests/test_matlab.py::TestPreambleTimingInstrumentation`,
  `scidb/tests/test_log_shim.py::test_setup_phase_timings_reach_the_file`.

Original intent, kept for reference:

1. **Generated script** (`scistack_gui/api/matlab_command.py`): stamp
   `fprintf('[SciStack][timing] script_start %s\n', datestr(now,'HH:MM:SS.FFF'))`
   as line 1 (pure MATLAB — Python may not be loaded yet), then a
   `toc`-based line after each section: `pyenv_preamble`, `addpath`,
   `project_root`, `entities`, `configure_database`, `register_variables`.
   Sections after Python is up route through `scidb.Log.info('[timing] …')` so
   they land in `scidb.log` next to the existing `for_each_prepare returned in
   …` lines; the pre-Python ones use `fprintf` and are captured in the run
   console.
2. **Extension** (`extension/src/matlabTerminal.ts`): log `Date.now()` deltas
   around `writeFileSync`, `matlab.openCommandWindow`, and `sendText`. This
   splits "VS Code dispatch latency" from "MATLAB script time" — the single
   biggest unknown in the 4–5 s.
3. **scidb layer** (`scidb/database.py`): wrap `DatabaseManager.__init__` in
   `Log.timer("configure_database")` with phases `duck_open`,
   `ensure_meta_tables`, `ensure_provenance_tables`, `register_subclasses`.
   The `[timing]` tag is already the established grep target.

Regression tests: assert the generated script contains the timing stamps
(`scistack-gui/tests/test_matlab.py`), and a `matlabTerminal` unit test for the
new logging is not needed — the assertions belong on the script generator.

## Stage 1 — cuts that are safe on *every* run

1. **Delete the `scidb.register_variable(X())` block** from both generated
   scripts (`generate_matlab_command`, `generate_matlab_pipeline_command`).
   It is redundant: `+scidb/for_each.m:192` calls
   `scidb.internal.ensure_registered` for every output class *before* the
   deferred-pipeline early return, and lines 1262/1278/1300 do the same for
   input values. `register_variable` is only needed for a **non-default
   `schema_version`**, which the generator never emits. Each removed line costs
   one MATLAB→Python crossing plus a `_registered_types` SELECT against a
   network DuckDB.
2. **Guard `addpath`.** The generator emits an unconditional `addpath(...)` per
   configured directory — including the scimatlab package dir, prepended on
   every run (`matlab_command_service.py:243`). Re-adding a directory that is
   already on the path invalidates MATLAB's function/class resolution cache, so
   the *next* call to every `+scidb`/`+scifor`/`+scihist` function is re-resolved
   from disk — over a network share. Add
   `scidb.internal.ensure_on_path(dirs)` (scimatlab layer, per CLAUDE.md
   NOTE 3): one call, compares against `path` once, adds only what is missing.
3. **Only `rehash` when a stub was actually written.** `+scidb/entities.m`
   currently does `addpath(stub_dir); rehash;` whenever any declared variable
   did not resolve, even if `stub_result{'created'}` is empty. `rehash` rescans
   the whole MATLAB path; on a network drive that is not cheap. Gate both on
   `~isempty(created)`, and route the `addpath` through `ensure_on_path`.
4. **Short-circuit the `pyenv` preamble when Python is already loaded.** Keep
   the executable-mismatch `error` (pure MATLAB, ~free). Skip
   `py.sys.version`, `py.importlib.import_module('scidb')` and the two
   `fprintf`s when `pyenv().Status == "Loaded"` and the executable matches —
   they exist to make the *first* load debuggable. Keep the full diagnostic
   dump on the failure path. (This is the "run 2+ guard" from the question,
   expressed as a status check rather than a try/catch, so a genuinely broken
   bridge still reports fully.)

## Stage 2 — session guard for the entity preamble (run 2+)

5. Cache `scidb.entities(project_root)` in a `persistent` keyed on
   `(project_root, entities-file mtime)`, so an unchanged TOML skips the bridge
   call, the Parameter/PathInput rebuild and the `assignin` loop (~50–95 ms
   measured). The mtime check is mandatory, not optional: re-emitting
   `scidb.entities()` on every run is exactly what makes a GUI entity edit
   visible to a warm session (see the docstring in `_entities_script_lines`).
   The guard must also verify the names are still present in the base
   workspace, so a user's `clear` does not leave the script referencing
   undefined names.
6. Fold `py.scimatlab.bridge.set_pathinput_project_root` into the same guard —
   it is idempotent and unchanged between runs.

## Stage 3 — scidb layer: stop re-running schema DDL per run (network-DB cost)

7. Every `configure_database` builds a fresh `DatabaseManager`, which runs ~10
   `CREATE TABLE IF NOT EXISTS` statements (meta, record_save, schema
   overrides, seven provenance tables) plus one `SELECT` per known
   `BaseVariable` subclass. Measured 172 ms end-to-end against the network DB.
   Add a one-query "schema already provisioned at version N" probe that
   short-circuits the `_ensure_*` calls, and replace the per-class register loop
   with a single `SELECT type_name FROM _registered_types` + one multi-row
   INSERT for the missing ones. Lives in scidb, so Python runs benefit too.
   The script must keep opening/closing the DB per run — that is the
   lock hand-back contract (docs/claude/matlab-run-database-ownership.md).

## Stage 4 — GUI dispatch (only if Stage 0 shows it matters)

8. `matlabTerminal.ts` `await`s `matlab.openCommandWindow` on every dispatch.
   Skip it when a terminal named `MATLAB` already exists; call it only to
   create one.

## Do NOT remove

- The `try/catch` + `scidb.close_database(db)` in both branches — that is what
  hands the DuckDB write lock back to the GUI.
- The schema kwargs on the template (never-run-function) branch — without them
  `for_each` collapses to a single combo (defect 2 in
  `.claude/plan-matlab-struct-and-iteration-26-09-02.md`).
- The `_unresolvable_var_type_lines` preflight — generation-time only, no
  runtime cost.
- `scidb.entities()` when the TOML mtime changed.

## Cross-cutting flag

Both the project (`Y:\…`) and the database (`\\fs2.smpp.local\…`) are on network
shares. Every path rehash, DDL round trip and DuckDB open above is amplified by
that. Worth one control measurement with a local-disk copy of the `.duckdb`
before investing in Stage 3.
