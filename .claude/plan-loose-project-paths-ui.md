# Editable Paths in the Paths popup (loose-script projects)

## Context

The user is testing the browser-based "new project creation" wizard, which
creates a `.duckdb` + schema with no `pyproject.toml` ("loose-script mode" —
their words: "what scientists typically use, not packages"). They then open
the header's 📁 Paths popup expecting to add folders for the GUI to discover
code in, but that popup (`PathsPopup.tsx`) is currently 100% read-only —
paths can only be changed by hand-editing a TOML file, which doesn't exist
at all yet for a loose project (`docs/claude/scistack-gui-project-setup-guide.md`
and `.claude/plan-todos-order-26.08.12.md` both confirm the write-back UI
was explicitly scoped out when the popup was first built). They want:

1. `+`/`-` buttons above a scrollable (non-editable) list of configured paths.
2. `+` opens a textbox; submitting a folder path triggers recursive code
   discovery under it.
3. `-` removes the selected path (and, since discovery of a path is
   all-or-nothing recursive, everything under it stops being discovered).
4. The "Libraries" section / "Add Library" button removed entirely (backend
   included — confirmed with user, no other consumer exists).
5. Both Python and MATLAB paths managed together (confirmed with user).

**Primary use case (confirmed with user)**: the path being added is
typically an external, reusable computational-code repository shared across
multiple projects — not necessarily anything inside the project's own
folder. This is why absolute-path storage (see below) is the right call,
not paths relative to the project/db location: the shared repo can live
anywhere on disk and is pointed to from many different projects' configs
independently.

Confirmed with the user: this is scoped to **loose-script projects** (no
`pyproject.toml`). Packaged projects keep today's fully read-only popup,
hand-edited as before — out of scope. Confirmed: no TOML-writing library —
`scistack.toml` is a small, GUI-owned file we fully control, so plain
wholesale regeneration (matching the existing f-string template pattern in
`scistack/src/scistack/project.py`) is enough; no `tomlkit`/`tomli_w`
dependency needed.

## Backend: `scistack_gui/config.py` (owns reading *and* now writing this file)

- **Refactor**: factor the noise-dir-pruning `os.walk` body out of
  `_walk_source_files` (493-506) into a shared `_walk_pruned(root, suffix, *,
  matlab=False)`, and use it for the directory-entry branches in
  `load_config`'s `modules` loop (178-190), `_resolve_glob_paths`'s directory
  branch (343-355), and the new `matlab.sources` branch below. Today those
  branches use bare `p.rglob(...)`, which — unlike folder-scan mode — does
  **not** skip `.venv`/`node_modules`/etc. This must be fixed as part of this
  change: the very first "+" click seeds `modules` with the project root
  (see below), so without this fix every loose project would immediately
  start sweeping in noise directories it never used to.
- **New `[matlab] sources = [...]` config key**: resolved the same way as
  `modules`/`matlab.functions`, populated into `SciStackConfig.matlab_sources`
  (an existing field, currently only ever populated by `_folder_scan_config`).
  `matlab_registry.load_from_config` (registry.py:61-124) already handles
  `config.matlab_sources` by auto-classifying each file via
  `classify_matlab_file` — no registry changes needed. This is what lets a
  single GUI-added path work for MATLAB without asking the user to declare
  "functions vs. variables."
- **New `add_path(db_path: Path, new_path: Path) -> Path`**: locates the
  existing `scistack.toml` via `_locate_pyproject(None, db_path)`; if none
  exists, the target is `db_path.parent / "scistack.toml"` and current
  content is treated as empty. Loads the *raw* TOML dict (not the resolved
  `SciStackConfig`). On first write ever (file doesn't exist), seeds
  `modules`/`matlab.sources` with `str(_normalize(db_path.parent))` so the
  db's own directory — implicitly scanned today — doesn't silently vanish
  once a config file exists. Appends `new_path` (absolute, `_normalize()`-d)
  to **both** `modules` and `matlab.sources` if not already present
  (exact-string dedup after normalization — no parent/child containment
  special-casing; nested entries are harmless, `rglob` already covers them).
  Re-renders the whole file via a small template, round-tripping any other
  existing keys (`packages`, `auto_discover`, `variable_file`,
  `matlab.functions`, `matlab.variables`, `matlab.variable_dir`) unchanged.
  Rejects (raises) if `new_path` doesn't exist or isn't a directory, or isn't
  absolute (a relative string typed into the box would resolve against an
  unpredictable cwd).
- **New `remove_path(db_path: Path, path_to_remove: Path) -> Path`**: same
  load, filters the (normalized) path out of both lists, rewrites. No-op /
  raises `FileNotFoundError` if no `scistack.toml` exists yet — never
  creates a file on remove.
- **New `_render_scistack_toml(...)`**: shared template renderer used by both
  of the above.
- Why here and not a new `config_writer.py`: this module already owns
  `_normalize`/`_locate_pyproject`/the noise-dir constants and is the sole
  authority on this file's format; a sibling module would just re-import all
  of that for no isolation benefit, since read and write must agree on
  format exactly.

## Backend: `scistack_gui/api/project.py`

- **Critical correctness fix, not just an add**: `registry.refresh_all()` /
  `matlab_registry.refresh_all()` (used by `_refresh_registries()`, which
  `_run_scan(force_refresh=True)` calls) replay against the **stale**
  module-level `_config` captured at the last load — they do **not** re-read
  `scistack.toml` from disk. Naively calling `refresh_project_sync()` after
  `add_path()` would silently fail to discover the new path until the server
  restarts. The new handlers must instead: call `load_config(None, db_path)`
  fresh, then call `registry.load_from_config(new_config)` and
  `matlab_registry.load_from_config(new_config)` directly (both update their
  own stored `_config` as a side effect), then `_run_scan(force_refresh=False)`
  to rebuild `_last_result` from the now-current registries.
- `get_project_paths()` (125-169): add two response fields —
  `packaged: bool` (server-computed: does `pyproject.toml` exist at the
  resolved root?) and `managed_paths: list[str]` (the raw, pre-rglob-expansion
  `modules` list entries — what the new editable list actually displays,
  since the resolved `modules`/`matlab_functions` arrays are individual files,
  far too granular for this UI).
- New `add_project_path(body: dict) -> dict`: validates `body["path"]`
  exists/is a directory, calls `config.add_path`, does the fresh-reload
  sequence above, returns the same shape as `get_project_paths()` plus
  `{"ok": True}` (or `{"ok": False, "error": ...}` on validation failure —
  matches `add_library`'s existing error-shape convention).
- New `remove_project_path(body: dict) -> dict`: mirrors the above via
  `config.remove_path`.
- `POST /project/paths` and `DELETE /project/paths?path=...` (query param,
  matching `remove_library`'s `DELETE /project/libraries/{name}` precedent).

## Backend: `scistack_gui/services/project_service.py` + `server.py`

Add `add_project_path`/`remove_project_path` thin delegators (mirroring
`get_project_paths`'s existing shape) and two new JSON-RPC handlers
registered as `"add_project_path"`/`"remove_project_path"`, each calling
`notify("dag_updated", {})` on success (mirrors `_h_refresh_project`).

## Frontend

**`frontend/src/api.ts`**: add
`add_project_path: { path: '/api/project/paths', method: 'POST', body: true }`
and
`remove_project_path: { path: (p) => \`/api/project/paths?path=${encodeURIComponent(p.path as string)}\`, method: 'DELETE' }`.

**`PathsPopup.tsx`**: gate on the new `packaged` field. Packaged projects:
keep today's read-only grid, byte-for-byte unchanged. Loose projects
(`packaged: false`, regardless of whether `scistack.toml` exists yet):
render a new `ManagedPathsList` component instead of the read-only grid.

**New `frontend/src/components/ManagedPathsList.tsx`**:
- Toolbar row (`+` / `-` buttons) above a scrollable `<div>` of clickable
  rows sourced from `managed_paths` (not a literal `<textarea>` — the
  "scrollable text area" language in the request just means "scrollable
  list," and a real textarea would fight click-to-select).
- Single-select: clicking a row highlights it (`selectedPath` state),
  enabling `-`.
- `+` reveals an inline `<input type="text">` (placeholder
  `/path/to/folder`) + Add/Cancel. Submit calls
  `callBackend('add_project_path', { path: value })`; on success clears and
  refetches `get_project_paths`; on failure shows an inline error without
  closing the input.
- `-` (enabled only with a selection): `window.confirm` (matches this
  codebase's lack of a styled confirm dialog elsewhere in this popup), then
  `callBackend('remove_project_path', { path: selectedPath })`, clear
  selection, refetch.
- Empty state ("No paths configured yet.") covers the zero-`scistack.toml`
  case too — same component renders whether or not the file exists yet.

## Libraries: full removal

Delete outright (no other consumer confirmed via grep):
- `scistack_gui/api/indexes.py`, `scistack_gui/services/indexes_service.py`
- `frontend/src/components/Sidebar/AddLibraryDialog.tsx`
- `tests/test_indexes_api.py`
- In `scistack_gui/app.py`: the `indexes_router` import + `include_router` call
- In `scistack_gui/server.py`: `_h_get_project_libraries`,
  `_h_get_indexes`/`_h_search_index_packages`/`_h_add_library`/`_h_remove_library`
  and their 5 registration-table entries
- In `scistack_gui/api/project.py`: `get_project_libraries()` only — **do
  not** touch `_last_result.non_empty_libraries()`/`.libraries` usage inside
  `refresh_project_sync()`, that's unrelated to the Libraries *section* UI
- In `scistack_gui/services/project_service.py`: `get_project_libraries()`
- In `frontend/src/api.ts`: `get_project_libraries`, `get_indexes`,
  `search_index_packages`, `add_library`, `remove_library` (confirmed
  `get_indexes` has no consumer besides the dialog being deleted)
- In `ProjectConfigPanel.tsx`: the entire "Libraries" section (state,
  JSX, the `get_project_libraries` half of `fetchData`'s `Promise.all`, the
  `AddLibraryDialog` import) — keep "Project Code" + Refresh as-is
- In `tests/test_project_api.py`: delete `TestGetProjectLibraries` (104-112)

## Test plan (per NOTE 2 — logging + regression tests are required, not optional)

`tests/test_config.py` (tmp_path-based, no mocking, mirrors existing style):
- add_path creates scistack.toml when none exists, seeding the project root
- add_path appends to an existing scistack.toml, leaving unrelated keys
  (`packages`, `auto_discover`) untouched
- add_path is idempotent on an exact duplicate
- remove_path deletes an entry from both `modules` and `matlab.sources`
- remove_path is a no-op (raises, no file created) when no config exists
- **regression test for the noise-dir-pruning fix**: a `modules`-listed
  directory containing a `.venv`/`node_modules` subtree with `.py` files —
  assert those are excluded (extends the existing
  `test_modules_directory_recursively_discovers_py_files` pattern)
- `[matlab] sources = [...]` populates `config.matlab_sources` unsplit
  (functions/variables NOT populated from this key)

`tests/test_project_api.py` (extend the `loose_project_client` fixture):
- add creates config + rescans, and the new code is visible via
  `GET /project/code` immediately (no server restart) — this is the test
  that catches the stale-`_config` bug if the handler is implemented wrong
- add rejects a nonexistent path / a file (not a directory)
- remove stops discovery of that path's code
- delete `TestGetProjectLibraries`

`tests/test_indexes_api.py`: delete entirely.

No frontend test infra exists in this repo (confirmed) — `ManagedPathsList`/
`PathsPopup` changes are manually verified only: build the frontend, run the
GUI against a loose (no-`pyproject.toml`) project, and check the `+`/`-`
flow discovers/un-discovers Python and MATLAB code without a restart, and
that a packaged (`pyproject.toml`) project still shows the old read-only view.

## Verification (copy/paste, per CLAUDE.md — user runs Python; only `npm`/`tsc` here run directly)

```
cd /workspace/scistack-gui/frontend
npm run build
```
Then launch the GUI against a loose project (`scistack-gui <db>` with no
`--project`) and manually verify the `+`/`-` flow.

Python test commands (for the user to run):
```
cd /workspace/scistack-gui
python -m pytest tests/test_config.py -v
python -m pytest tests/test_project_api.py -v
```
