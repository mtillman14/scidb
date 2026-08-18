# Real MATLAB Pipeline Execution (Browser + VS Code Extension)

## Context

Today, clicking "Run" on a MATLAB function node only generates a copy-paste command string (`matlab_command_service.py`/`api/matlab_command.py`) — there is no in-GUI execution, and no way to run a whole multi-step MATLAB pipeline at all. Since the user's real pipelines are mostly MATLAB, this is the actual blocker to using the GUI for real work, and was explicitly deferred from the discovery-focused plan (Stages 1-3, all shipped) to be designed properly on its own. Requirements already agreed with the user: real breakpoint debugging must work in the VS Code extension (the deployment target); the browser/standalone mode must also work, with minimal setup friction, but debugging there is out of scope.

**The scope turned out to be much smaller than originally estimated**, because most of the hard part already exists and works — it just isn't wired to the GUI's "Run" actions:

- **`scidb.Pipeline` (Python, `scidb/src/scidb/pipeline.py`) already refuses to self-execute a pipeline containing MATLAB steps** and instead expects an external driver to call `execution_order()` — a topologically-sorted, plain-data list of steps (`is_matlab` per step), explicitly designed for this. Ordering (Kahn's algorithm, deterministic tie-break) is already implemented and tested there.
- **MATLAB already has the matching driver: `+scidb/Pipeline.m`.** Its `run_all()`/`run_until()`/`run_endpoints()` call `drive()`, which asks Python for the execution order via the bridge (`pipeline_execution_order`) and then, per step, either runs it directly through MATLAB's own `scidb.for_each` (already a full, tested orchestrator — `+scidb/for_each.m` + `+scifor/for_each.m`, ~4200 lines combined, handles skip-computed, per-combo error recovery, lineage) or calls back into Python for Python-registered steps (`pipeline_run_python_step`) — mixed-language pipelines are already handled, not something this plan needs to build.
- **Building a `Pipeline` in MATLAB is just deferred registration**, mirroring how the GUI already builds Python pipelines (`execution_service.build_backend_pipeline` passes `pipeline=pipe` so `for_each(...)` registers instead of executing). In MATLAB: construct `scidb.Pipeline(name)` (this activates it), then ordinary `scidb.for_each(@fn, inputs, outputs, ...)` calls register as deferred steps instead of running, then `pipe.run_all()`. This is exactly the shape of command MATLAB already generates for a single function — extending it to a whole pipeline is mostly wrapping the existing per-function command text in a `Pipeline` envelope and emitting one such block per node, not building new registration logic.
- **VS Code's MathWorks-terminal integration already exists and works**: `extension/src/matlabTerminal.ts` (`isMatlabExtensionAvailable`, `runInMatlabTerminal`, clipboard fallback), wired into `dagPanel.ts`'s `handleMatlabRun()`. The DB file-watcher that refreshes the DAG after external MATLAB writes already exists too (`extension/src/extension.ts`'s `setupDbWatcher`, watches `.duckdb`/`.duckdb.wal`, debounced). Python's `debugpy` auto-attach (the reference debugging implementation) was verified intact, not stale.
- **What's genuinely new**: (1) whole-pipeline MATLAB command generation (today only emits one function's commands), (2) a standalone/browser execution path — confirmed there is *zero* existing MATLAB-side listener/socket/command-queue code anywhere in the repo, so Python cannot currently call into a running MATLAB process at all outside the terminal-injection trick.
- **The frontend needs no new UI.** `PipelineRunController.tsx` already calls a single, language-agnostic `start_pipeline_run` RPC (`pipeline_id`, `mode`, `target`, `finalized`, `skip_computed`, `run_id`) and listens for `run_output`/`run_done` tagged by `run_id` — the exact same plan-preview dialog, run console, and cancel button already used for Python pipelines. If the backend detects a MATLAB-containing pipeline and routes it correctly while still emitting `run_output`/`run_done` on the same `run_id`, the existing UI just works.

No MATLAB installation exists in this dev environment (confirmed: `matlab` not on PATH), so all new code will be tested with string/mocked-subprocess tests, matching the existing precedent in `test_matlab.py` — real verification needs the user's own MATLAB install, called out explicitly per stage below.

## Architectural decision

One new capability — whole-pipeline MATLAB command generation — consumed by two transports, chosen by what's available:

1. **VS Code + MathWorks extension present**: send the generated script through the *already-built* `matlabTerminal.ts` (`runInMatlabTerminal`). Real breakpoint debugging works for free — it's the MathWorks extension's own MATLAB session and its own DAP integration, not anything this plan builds. Completion detection stays exactly as fragile as it already is for single-node terminal runs today (DB file-watcher only, no real process tracking) — this plan doesn't invent a new completion signal for that path, it just extends the existing one to whole pipelines.
2. **Standalone/browser (or VS Code without the MathWorks extension)**: a new, lazily-started MATLAB sidecar process the Python backend manages directly (`subprocess.Popen(["matlab", "-nodesktop", "-nosplash", ...])`, stdin/stdout), kept warm after first use. Driven with a **sentinel-marker text protocol** — write the generated MATLAB command text to stdin, followed by `disp('__SCISTACK_DONE__')`; read stdout lines until that sentinel appears. This needs no new `.m` file at all (MATLAB's own REPL is the "server") and mirrors the proven shape of `extension/src/pythonProcess.ts`'s child-process management, adapted since MATLAB isn't a JSON-RPC server. Because this path is fully Python-controlled, real `run_output`/`run_done` streaming and (best-effort) cancellation are both possible here, unlike the terminal path.
3. **MATLAB unavailable entirely**: today's copy-paste command fallback, unchanged.

Backend routing lives in one place: `start_pipeline_run`'s handler inspects whether the target pipeline contains any MATLAB-registered steps and, if so, dispatches to (1) or (2) instead of the existing `Pipeline._run` Python-only path — same `run_id`, same `run_output`/`run_done` message shape, so the frontend requires no changes.

## Stage 1 — Whole-pipeline MATLAB command generation

**Verify exact `+scidb/Pipeline.m` API first** (constructor `Pipeline(name, varargin)`, `bind`, `use`, `run_all`/`run_until`/`run_endpoints` already located at `scimatlab/src/scimatlab/matlab/+scidb/Pipeline.m:39-179`) — confirm the deferred-registration behavior (does constructing `Pipeline(name)` auto-activate, matching `pipeline_active_name()`'s registration-seam check?) and the exact `varargin` options `run_all`/`run_until` accept, before writing the generator.

**`scistack_gui/services/matlab_command_service.py` / `scistack_gui/api/matlab_command.py`**
- Refactor the existing per-function command body (addpath, pyenv preamble, `PathInput` formatting, variant/constant formatting — all already built and tested in `test_matlab.py`) into a form callable once per node, not just for the single top-level function.
- Add `generate_matlab_pipeline_command(pipeline_id, nodes, edges, schema_keys, db_path, ...)`: emits the pyenv preamble once, then `pipe = scidb.Pipeline('{pipeline_id}');`, then one `scidb.for_each(@{fn}, ...)` block per MATLAB function node (registration order doesn't matter — `Pipeline`'s own `execution_order()` topo-sorts), then `pipe.run_all()` (or `run_until`/`run_endpoints` depending on the requested `mode`/`target`, mirroring what `execution_service.py`'s Python path already supports).
- Mixed Python+MATLAB pipelines need no special-casing here beyond registering the MATLAB steps — `Pipeline.m`'s `drive()`/`pipeline_run_python_step` bridge call already handles calling back into Python for Python-registered steps.

**Tests**: extend `tests/test_matlab.py` with the same string-assertion style already used for `generate_matlab_command` (e.g. `assert "scidb.Pipeline(" in cmd`, `assert cmd.count("scidb.for_each") == n_matlab_steps`, ordering-independence, mixed-pipeline step registration).

## Stage 2 — VS Code Tier 2: whole-pipeline terminal runs

**`server.py` / `api/run.py` / `services/execution_service.py`**
- In the `start_pipeline_run` handler, detect MATLAB-containing pipelines (check registered steps for the `__matlab__` option flag already set by `pipeline_register_step`/`execution_service.build_backend_pipeline`) and short-circuit before calling `Pipeline._run` — instead return a signal (or directly drive the JSON-RPC/host-side dispatch) telling the caller "this needs host-side terminal execution," analogous to how single-node MATLAB runs already intercept before reaching Python (`dagPanel.ts:86-89`).

**`extension/src/dagPanel.ts`**
- Extend the existing MATLAB interception (currently only for single-node `start_run`) to also catch `start_pipeline_run` when the target pipeline contains MATLAB steps. Call the new `generate_matlab_pipeline_command` RPC, then send the result through the *already-built* `runInMatlabTerminal()` (`matlabTerminal.ts`) — no new terminal-integration code.
- Emit `run_output`/`run_done` (via the existing notify/webview-message path) with the same fragile-but-already-accepted semantics as single-node terminal runs: an informational "sent to MATLAB" line, and completion inferred from the DB file-watcher's `dag_updated` rather than real process tracking.

## Stage 3 — Standalone/browser MATLAB sidecar

**New `scistack_gui/matlab_sidecar.py`**
- `MatlabSidecar` class: lazy `subprocess.Popen(["matlab", "-nodesktop", "-nosplash", "-nodisplay"], stdin=PIPE, stdout=PIPE, text=True)`, started on first MATLAB pipeline-run request and kept warm (module-level singleton, mirroring `scistack_gui/db.py`'s `_db` singleton pattern).
- Boot sequence: run the pyenv preamble once at process start (reuse the same text `matlab_command.py` already generates for the pyenv bootstrap).
- `run_command(text: str, on_line: Callable[[str], None]) -> bool`: writes `text + "\ndisp('__SCISTACK_DONE__')\n"` to stdin, reads stdout lines via a background thread, forwards each to `on_line` (feeds `run_output`), stops at the sentinel, returns success/failure (need a paired sentinel or exit-code convention to distinguish a MATLAB error from normal completion — e.g. wrap the command in `try/catch` in the generated script itself and `disp` a distinct `__SCISTACK_ERROR__: {msg}` on failure, matching the error-surfacing style already used elsewhere in this codebase).
- Graceful absence: if `shutil.which("matlab")` is `None`, `MatlabSidecar` reports unavailable and the caller falls back to the existing copy-paste command (Option D, unchanged).

**`api/run.py` / `services/execution_service.py`**
- New code path (parallel to `_run_pipeline_in_thread`) for MATLAB-containing pipelines in standalone/browser mode: generate the whole-pipeline command (Stage 1), drive it through `MatlabSidecar.run_command`, relay `on_line` callbacks as real `run_output` messages via the existing `push_message`/`ws.broadcast` machinery, and emit a real `run_done` on the sentinel (no file-watcher guessing needed here, unlike Tier 2 — this path knows exactly when the command finished).
- Best-effort cancellation: killing/restarting the sidecar process on `force_cancel_run` for a MATLAB run (real cancellation, not the cooperative-only story Python pipelines have).

**Tests**: `MatlabSidecar` tested with a mocked `subprocess.Popen` (stub stdin/stdout), matching the mocking style already used for the MATLAB-existence subprocess check in `test_builtin_functions.py`'s `TestMatlabBuiltin`.

## Stage 4 — Routing + fallback ladder

- One shared "what MATLAB execution capability do we have right now" check, used by both `start_run` (single-node) and `start_pipeline_run` (whole-pipeline): MathWorks extension available (VS Code only) → Tier 2 terminal; else `matlab` on PATH → sidecar; else → existing copy-paste fallback. No new frontend code — `PipelineRunController.tsx` and `FunctionNode.tsx` already call the same RPCs and listen for the same message shapes regardless of which path served them.
- Apply the same routing to single-node MATLAB runs too (today's `dagPanel.ts` MATLAB interception always goes to the terminal, even in standalone/browser mode where no terminal exists at all beyond clipboard-copy — the sidecar should be the standalone-mode default there as well, not just for whole-pipeline runs).

## Verification

- Stage 1: unit tests only (no MATLAB needed) — hand the user the `pytest` command.
- Stage 2: needs the user's own VS Code + MathWorks extension + MATLAB install. Verification steps: build a small multi-step MATLAB pipeline (2-3 functions with a dependency), click "Run Pipeline," confirm the whole script lands in the MATLAB terminal and executes in dependency order, confirm a breakpoint set in one of the `.m` files is hit.
- Stage 3: needs the user's own standalone MATLAB install, no VS Code. Same pipeline, run from a browser tab; confirm real-time output appears in the Runs console (not just a "sent" message) and the DAG updates immediately on completion (not after a file-watcher delay).
- Stage 4: confirm the fallback ladder — temporarily rename/hide the MathWorks extension or run standalone without MATLAB on PATH, confirm it degrades to the next tier without crashing.
- Hand over exact `pytest`/`npm test` commands per CLAUDE.md; the VS Code/MATLAB manual verification steps can't be run by me at all (no MATLAB in this environment) — these are steps for the user to perform themselves.
