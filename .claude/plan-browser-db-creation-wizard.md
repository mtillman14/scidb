# Browser-Frontend Database Creation Wizard

## Context

The SciStack GUI can already be driven "exclusively via GUI" from VS Code:
the extension's `SciStack: Open Pipeline` command (`extension/src/extension.ts`)
walks the user through creating a new `.duckdb` (folder, filename, schema
keys) and picking a pipeline-code source (project / module / none), then
spawns the JSON-RPC backend with `--schema-keys ...` so `server.py` calls
`create_db()`.

The browser-only path (`scistack-gui <db_path>` from a terminal, no VS Code)
has no equivalent — `__main__.py` requires `db_path` to already exist and
exits immediately otherwise. This plan adds the same wizard to the React
frontend so a user can launch `scistack-gui` with nothing set up yet and
create a project/database entirely from the browser.

Per the user's steer, the path/folder picker will be a **plain text input**
(not a server-side folder browser) — VS Code's native file dialog has no
browser equivalent that exposes real filesystem paths, and a full
directory-browsing endpoint + navigator UI was judged unnecessary scope for
now. This keeps the change backend-endpoint-light.

Per CLAUDE.md: `create_db()`/`init_db()`/`configure_database()` already live
in the right layers (`scistack_gui/db.py`, `scidb`) — this plan reuses them
as-is and only adds GUI-layer plumbing (CLI + API + frontend) to reach them
without requiring a pre-existing file on disk.

## Backend Changes (`scistack-gui/scistack_gui/`)

### 1. New `bootstrap.py` — extract the "load a project" sequence

`__main__.py` currently inlines (lines ~66–181): import user code
(project/module/auto-discover + MATLAB registry), `init_db()`/`create_db()`,
`replay_persisted_builtins()`, `Log.bridge_python_logging()`, and
`startup.check_lockfile_staleness()`. Extract this into one function so both
the CLI (immediate) and the new wizard endpoint (deferred, triggered by an
HTTP request after the process is already running) can call it:

```python
# scistack_gui/bootstrap.py
@dataclass
class BootstrapResult:
    db_name: str
    schema_keys: list[str]
    functions_loaded: int
    variables_loaded: int
    matlab_functions_loaded: int
    matlab_variables_loaded: int
    warnings: list[str]

def open_or_create_project(
    db_path: Path, *,
    schema_keys: list[str] | None = None,   # if given + db_path doesn't exist -> create_db()
    module: Path | None = None,
    project: Path | None = None,
) -> BootstrapResult: ...
```

Raises the same exceptions the current code already handles
(`FileNotFoundError`, `ValueError`, `FileExistsError`) so both callers can
map them to their own error surface (CLI: print + exit; API: HTTP 400/404/409).

### 2. `__main__.py` — make `db_path` optional

- Change `db_path` from a required positional to `nargs="?"`.
- Add `--schema-keys` (mirroring `server.py`'s existing flag) for CLI-driven
  creation parity.
- If `db_path` is given: call `bootstrap.open_or_create_project(...)` exactly
  as today (same error handling), then `uvicorn.run(...)` as usual.
- If `db_path` is omitted: skip straight to `uvicorn.run(...)` with no
  project loaded. The browser opens onto the wizard (see frontend section).

### 3. `db.py` — tiny state check helper

Add `is_loaded() -> bool` (`return _db is not None`) next to `get_db()`/
`get_db_path()`. Used by `get_info()` and the new endpoints to avoid probing
via try/except.

### 4. `services/pipeline_service.py` — `get_info()` tolerates no DB

Today `get_info()` calls `get_db_path()`, which raises `RuntimeError` if
nothing is open — this currently can't happen because `__main__.py` always
loads a DB before `uvicorn.run()`. Once that's no longer guaranteed, make it
explicit:

```python
def get_info() -> dict:
    from scistack_gui.db import is_loaded, get_db_path
    if not is_loaded():
        return {"db_loaded": False}
    return {
        "db_loaded": True,
        "db_name": get_db_path().name,
        "startup_errors": [...],  # unchanged
    }
```

This is the single existing endpoint `App.tsx` already polls on mount
(`App.tsx:277`) — reusing it avoids adding a parallel status endpoint.

### 5. New router `api/bootstrap.py`

Two POST endpoints, mounted at `/api/bootstrap` in `app.py`:

- `POST /api/bootstrap/create` — body `{folder: str, filename: str,
  schema_keys: list[str], module?: str, project?: str}`. Joins
  `folder`/`filename` (append `.duckdb` if missing, mirroring
  `extension.ts:79-82`), calls `bootstrap.open_or_create_project(path,
  schema_keys=..., module=..., project=...)`. Maps `FileExistsError` → 409,
  `ValueError` (empty schema keys) → 400.
- `POST /api/bootstrap/open` — body `{db_path: str, module?: str,
  project?: str}`. Calls `bootstrap.open_or_create_project(path, module=...,
  project=...)` (no `schema_keys`, so it takes the existing-DB branch).
  Maps `FileNotFoundError` → 404.

Both return the same shape as `get_info()` (`db_loaded: true, db_name, ...`)
so the frontend can reuse one "project ready" handler for either path.

Logging: follow the existing verbose style in `db.py`/`server.py`
(`logger.info` at each step — folder validated, schema keys parsed, db
created/opened, source loaded) per the project's diagnostic-logging
convention.

## Frontend Changes (`scistack-gui/frontend/src/`)

### 1. `App.tsx` — branch on `db_loaded`

In the existing `/api/info` effect (`App.tsx:277`), when the response has
`db_loaded: false`, render `<ProjectBootstrapWizard>` instead of the DAG
shell. On successful create/open, the wizard calls the same effect's
refetch so the app transitions straight into the normal view — no reload,
no process restart (confirmed: `_db` in `db.py` is a plain swappable module
global, so setting it mid-process via a request handler works identically
to setting it before `uvicorn.run()`).

This screen only needs to handle standalone/browser mode: in VS Code,
`server.py` never sends its "ready" notification (and the webview never
mounts) until a DB is already open or created via the extension's own
QuickPick flow, so `db_loaded` is always `true` by the time the VS Code
webview's React bundle runs. The wizard therefore talks to the backend with
plain `fetch()` calls, not the dual-transport `callBackend()` used
elsewhere in `api.ts` (that abstraction exists for endpoints VS Code's
JSON-RPC also implements; these two are FastAPI/browser-only).

### 2. New `components/Bootstrap/ProjectBootstrapWizard.tsx`

Step sequence mirrors the extension exactly, swapping native dialogs for
text inputs:

1. Choice: "Open existing database" / "Create new database".
2. **Open**: single text input for the full `.duckdb` path.
   **Create**: text input for destination folder + text input for filename
   (`.duckdb` appended if omitted) + text input for comma-separated schema
   keys, validated non-empty client-side (same rule as
   `extension.ts:84-90` and server-side `create_db()`).
3. Pipeline-source choice: "Project (pyproject.toml)" / "Single module
   (.py)" / "No module" — each revealing one more text-path input, or none
   for "No module".
4. Submit → `POST /api/bootstrap/create` or `/open` → on success, call the
   passed-in `onReady()` callback (triggers `App.tsx`'s info refetch); on
   error, show the message inline in the wizard (reuse the
   `StartupErrorDialog` overlay/dialog style constants already defined in
   `App.tsx` for visual consistency rather than inventing new modal chrome).

### 3. `api.ts`

No changes needed to the `callBackend` abstraction — the wizard's two calls
are plain `fetch('/api/bootstrap/create', ...)` / `fetch('/api/bootstrap/open', ...)`,
consistent with how other FastAPI-only endpoints are already called
elsewhere in the codebase (e.g. `schema.py`'s `/api/info`, `/api/schema`).

## Files Touched

- `scistack-gui/scistack_gui/bootstrap.py` (new)
- `scistack-gui/scistack_gui/__main__.py` (refactor to use `bootstrap.py`; optional `db_path`; new `--schema-keys` flag)
- `scistack-gui/scistack_gui/db.py` (add `is_loaded()`)
- `scistack-gui/scistack_gui/services/pipeline_service.py` (`get_info()` tolerant of no DB)
- `scistack-gui/scistack_gui/api/bootstrap.py` (new router)
- `scistack-gui/scistack_gui/app.py` (mount new router)
- `scistack-gui/frontend/src/App.tsx` (branch on `db_loaded`)
- `scistack-gui/frontend/src/components/Bootstrap/ProjectBootstrapWizard.tsx` (new)
- `scistack-gui/tests/` — new test file for `bootstrap.py` + `api/bootstrap.py` (create → `db_loaded` flips true; create on existing path → 409; create with empty schema keys → 400; open nonexistent path → 404), following existing test conventions in that directory
- `docs/claude/scistack-gui-project-setup-guide.md` — once built, add a short section documenting this as a second wizard entry point (browser, text-path based) alongside the existing §4 (VS Code, dialog-based)

## Out of Scope (explicitly, per the user's answer)

- Server-side directory browsing / breadcrumb navigator — plain text paths
  only, matching the user's chosen option.
- Touching `server.py` (the VS Code JSON-RPC entry point) — it already
  supports `--schema-keys` and its own creation flow; no change needed there.
- Full project scaffolding (`pyproject.toml`/`uv.lock`/`src/` layout) from
  the wizard — same limitation as the VS Code wizard already documented in
  the setup guide; still CLI-only (`scistack project new`).

## Verification

I don't have Python in this environment (per CLAUDE.md), so I can't run the
FastAPI backend myself. Plan:

- I can run `npm run build` / `tsc --noEmit` in `scistack-gui/frontend` myself
  to confirm the new component compiles cleanly against the existing types.
- Backend: hand you copy-paste terminal commands to launch `scistack-gui`
  with no `db_path` (fresh landing page) and click through both the "create"
  and "open" branches against a scratch `.duckdb`.
- New pytest file for `bootstrap.py`/`api/bootstrap.py` — you run it
  yourself per your existing preference; I'll hand over the `pytest -k
  bootstrap` command.
- Per CLAUDE.md NOTE 2, the new endpoints/functions get `logger.info` calls
  at each step (folder validated, schema keys parsed, db created/opened,
  source loaded) so a failed wizard run is diagnosable from `scidb.log`
  without re-running anything.
