# Fix: MATLAB runs hang the GUI (todos #13, folds in #5)

## Symptom (todo #13)

Clicking **Run** on a MATLAB function node logs

```
start_run: function=loadDelsysEMGOneFile language=matlab variants=0
handleMatlabRun: requesting generate_matlab_command for loadDelsysEMGOneFile
```

…and then nothing. No `handleMatlabRun: got command (N chars)` (which
`dagPanel.ts:307` logs immediately after the RPC returns), so the
`generate_matlab_command` JSON-RPC **never came back**. The run hangs, and
the output variable ends up disconnected from the function node.

## Root causes

### A — A failed `acquire_db_connection()` silently kills the request thread

`scistack-gui/scistack_gui/server.py:998`:

```python
acquire_db_connection()      # <-- OUTSIDE the try
try:
    result = handler(params)
    ...
except Exception as e:
    ...
    _respond_error(req_id, -32000, str(e))
finally:
    release_db_connection()
```

`_handle_request` is the target of a per-request `threading.Thread`
(`server.py:1306`). If `acquire_db_connection()` raises, the exception
escapes before the `try`, the thread dies, and **no JSON-RPC response is
ever written to stdout**. `pythonProcess.request()`
(`extension/src/pythonProcess.ts:222-234`) has no timeout, so the pending
promise never settles — the webview waits forever. That is exactly the
observed hang: last log line is whatever preceded the RPC.

**When does `acquire_db_connection()` raise?** `db.py:52-64` calls
`_db.reopen()` → `duckdb.connect(...)`, which raises
`duckdb.IOException: Could not set lock on file ... Conflicting lock is
held in <pid>` when **another process has the database open**. And the GUI
is *designed* to let that happen — `db.py:22-31`:

> The DuckDB file lock is held only while a request is being serviced…
> Between requests the lock is released so MATLAB can open the same file.

MATLAB's `scihist.configure_database` opens the `.duckdb` and holds it for
the rest of the MATLAB session. So the moment a MATLAB process is attached
and has touched the database, the GUI's very next RPC hits a locked file
and hangs instead of erroring. **This is the blocker.**

### B — The DB file-watcher stampedes RPCs into the locked database

`extension/src/extension.ts:388-419` watches `<db>.duckdb*` and fires
`dag_updated` 2 s after any change. WAL writes happen *throughout* a MATLAB
run, not just at the end, so every burst makes the webview refetch the
graph — more RPCs into a DB that MATLAB currently owns, each one killing
another thread and leaking another never-settled promise. This is how the
whole GUI wedges, and the most likely path to "**it also disconnected the
output variable from the function node**": layout writes (`put_edge`,
node-config saves) issued in that window die with no response, so the edge
is never persisted, and the next successful `get_dag` legitimately renders
the node without it.

### C — Single-node MATLAB run routing lives only in the extension host (todo #5)

`dagPanel.ts:76-89` intercepts `start_run` and re-routes it to
`handleMatlabRun` **only** when the webview happens to send
`params.language === 'matlab'`. Neither backend entry point looks at
`language` at all:

- `server.py:_h_start_run` (line 587) reads `language` *purely to log it*
  and then calls `_run_in_thread` regardless.
- `api/run.py:start_run` (`POST /api/run`, line 797) — the browser path —
  has no `language` field on `RunRequest` at all.

Both fall through to the Python registry, producing todo #5's
`"Function 'loadDelsysEMGOneFile' not found in registry, and is not an
importable library function…"`. Whole-*pipeline* runs already solved this
properly in the backend (`api/run.py:1286-1315`:
`pipeline_has_matlab_steps` → `host_execution_required` for the privileged
VS Code host, MATLAB sidecar for plain HTTP callers). Single-node runs
never got the same treatment — this is open question #2 left unanswered in
`.claude/matlab-run-and-reveal-fixes.md`.

### D — No client-side timeout

`pythonProcess.ts:222` never times out a pending request, so any lost
response is an unrecoverable hang rather than a visible error.

## Which other todos are contributing factors

- **#5 — yes, same root cause C.** Folded into Stage 2; browser-mode MATLAB
  runs start working as a direct consequence.
- **#12** (creating a variable re-reads all code files) — *not* causal.
  Nothing in the `generate_matlab_command` path reloads the registry
  (`get_path_inputs_registry`/`get_parameters_registry` are plain dict
  copies). It makes unrelated RPCs slow on a network drive; tracked
  separately.
- **#1, #2, #4, #7, #9, #10, #11** — UI/wizard/paths issues with no path to
  the run hang. Not folded in.

## Fix

### Stage 1 — A request can never vanish without a response

*`scistack_gui/server.py`*
- Move `acquire_db_connection()` **inside** `_handle_request`'s `try`, and
  make `release_db_connection()` conditional on a successful acquire (the
  refcount contract in `db.py:34-43` already says a failed acquire must not
  be released).
- Wrap the whole of `_handle_request` in an outer safety net that responds
  with a JSON-RPC error for *any* escaping exception, and logs
  `RPC !! {method} NO RESPONSE` if it somehow still can't.
- Map the locked-database case to a distinct code (`-32010`) with an
  actionable message naming the conflicting PID, instead of a raw
  `IOException` string.

*`scistack_gui/db.py`*
- New `DatabaseLockedError(RuntimeError)` carrying `db_path` and the
  conflicting PID parsed out of DuckDB's message.
- `acquire_db_connection(timeout=…)`: bounded retry with backoff (default
  ~5 s, since MATLAB's own writes are short) before giving up. Every
  attempt logged with the refcount and the DuckDB message — per CLAUDE.md
  NOTE 2, this window has been invisible until now.

*Tests* — `tests/test_db_lifecycle.py`: a failing acquire still produces a
response; retry succeeds when the lock clears mid-backoff; a persistent
lock raises `DatabaseLockedError` and the dispatcher turns it into a
`-32010` error frame (not a dead thread).

### Stage 2 — Backend-owned MATLAB run routing (fixes #5)

*`scistack_gui/api/run.py`*
- Add `language: str | None` and `output_types: list[str] | None` to
  `RunRequest`.
- Route in **one** place, mirroring `start_pipeline_run`'s existing ladder,
  with `matlab_registry.is_matlab_function(function_name)` as the
  authority (the frontend's `data.language` becomes a hint, not the only
  signal):
  - `host_can_dispatch_matlab=True` (set only by `_h_start_run`, the
    privileged VS Code host) → return
    `{"run_id", "host_execution_required": True, "language": "matlab"}`
    without spawning a Python thread.
  - otherwise (browser / plain HTTP) → generate the command via
    `matlab_command_service.generate_matlab_command` and drive it through
    the existing `_run_matlab_command_in_thread` → real
    `run_output`/`run_done`. If `matlab` isn't on PATH, emit the honest
    "MATLAB not available" message instead of today's misleading
    "not found in registry".

*`extension/src/dagPanel.ts`*
- Reshape the `start_run` interception to match the `start_pipeline_run`
  one already at lines 102-122: forward to Python, inspect the result for
  `host_execution_required`, then call `handleMatlabRun`. Removes the
  duplicated language knowledge and makes browser and extension take the
  same decision from the same source.

*Tests* — `tests/test_matlab.py` (new class): MATLAB function + host
dispatch returns `host_execution_required`; MATLAB function without a host
spawns the sidecar thread (mocked); Python function is unaffected; MATLAB
function with no `matlab` on PATH reports the right error.

### Stage 2b — Hand the database to MATLAB explicitly (found during implementation)

Stage 2's browser path could not have worked without this. Only the
JSON-RPC server drops its DuckDB lock between requests; in
browser/standalone mode (FastAPI) the connection stays open for the life of
the process, so a sidecar run started there would find the database locked
by *us* and die on MATLAB's first `scihist.configure_database` call.

- `db.py`: new `external_db_access(holder)` context manager — closes our
  connection, marks the database externally owned so a concurrent request
  can't quietly reopen it and steal the lock back mid-run (such a request
  gets a non-retryable `DatabaseLockedError` naming the holder), and
  restores the connection on exit.
- `api/run.py`: both sidecar paths (single-node and whole-pipeline) drive
  MATLAB inside that block, via one shared `_drive_sidecar` helper.

### Stage 3 — Don't refresh into a database MATLAB owns

- Backend: expose `matlab_run_active` (the `_active_runs` entries already
  carry a `matlab_sidecar` flag; add the terminal-dispatch case).
- `dagPanel.ts`: track an in-flight MATLAB dispatch, cleared on
  `run_done`.
- `extension.ts:setupDbWatcher`: while a MATLAB run is in flight, skip the
  `dag_updated` broadcast and fire exactly one refresh after it clears.

### Stage 4 — Client-side safety net

- `pythonProcess.ts:request()`: per-request inactivity timeout
  (`scistack.rpcTimeoutMs`, default 300000 — generous, since RPCs are
  meant to return promptly and long work is reported via notifications).
  On expiry, reject with the method name and elapsed time so the failure is
  visible instead of silent.
- Log request/response pairs with elapsed ms to the SciStack output
  channel, so a lost response is diagnosable from the log alone.

*Tests* — `extension/src/*.test.ts` (node `--test`, existing
`tsconfig.test.json` harness): the watcher-suppression decision and the
run-routing decision extracted as pure helpers and tested directly.

## Verification

- `pytest` for the Python stages — commands handed over, not run here
  (no Python in this environment).
- `npm test` / `npm run build:all` in `scistack-gui/extension`.
- Manual, needs the user's MATLAB: open a project with MATLAB attached and
  the DB already open in MATLAB, click Run on a MATLAB node — expect either
  a real terminal dispatch or a clear "database is open in MATLAB (pid N)"
  message, never a hang. Then the browser-mode equivalent for #5.
