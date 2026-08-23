# Plan: three GUI bugs found building the vo2max example project (2026-08-22)

User report while building a pipeline in the GUI against `examples/vo2max`:

1. `scistack.toml::variable_file` gets written as an absolute path.
2. Editing Variables/Constants/Sweeps/PathInputs in the GUI doesn't update
   source — values stay at their defaults.
3. A PathInput's path template disappeared after dragging a new node onto
   the canvas.

## Findings

**#1** — `set_variable_file` (`scistack_gui/config.py`) always wrote the
normalized *absolute* path into `scistack.toml`, even though the packaged
(`pyproject.toml`) docs already document `variable_file` as relative, and
`load_config` already resolves a relative `raw_vf` against `project_root`
fine. `modules`/`sources` legitimately stay absolute (they can point
outside the project), but `variable_file` always lives inside it.

**#3** — Any node's `put_layout` broadcasts a `dag_updated` websocket
message to every client, which triggers `PipelineDAG.fetchPipeline()` — a
full node-array replace from the backend's last-*saved* state — on every
client, including one mid-edit. Sidebar panels that preview edits live
(update canvas on every keystroke, persist only on blur/Enter) had no
protection: an unrelated refetch (e.g. from dragging a brand new node
elsewhere) silently reverted the in-progress draft to the last-saved value.

**#2** — Turned out to be two things:
- `PathInputSettingsPanel`/`SweepSettingsPanel` still called
  `update_path_input` / `update_sweep` / `add_path_input_alternate` /
  `remove_path_input_alternate`. Neither the JSON-RPC `METHODS` table in
  `server.py` (VS Code transport) nor the FastAPI routers in
  `scistack_gui/api/layout.py` (browser transport) implement these —
  confirmed by grepping both dispatch paths. They were removed (or never
  built) when PathInputs/Sweeps/Constants were migrated to be
  **source-scanned** (commits `066cc53`, `6738212`, same day) — the
  frontend just never got the memo, so every edit silently no-opped
  (PathInput) or visibly errored (Sweep).
- The user's actual expectation (edits should write back to source, with
  history in the DB) is the *opposite* of that source-scanned design,
  decided the same day. Asked the user via AskUserQuestion which way to
  go: **fix the bug only**, keep the source-scanned design (chosen), vs.
  reopen the design and build write-back + DB history (bigger scope,
  declined).

## Fixes applied

1. `scistack_gui/config.py::set_variable_file` — write `variable_file`
   relative to `project_root` when it's inside it, absolute fallback
   otherwise. Updated `test_config.py` (3 existing tests + 1 new one for
   the outside-project-root fallback). Fixed the checked-in
   `examples/vo2max/scistack.toml` by hand.
2. `ScopeContext.tsx` — added `markNodeDirty`/`clearNodeDirty`/
   `getDirtyPatch`, a ref-backed per-node pending-patch registry.
   `PipelineDAG.fetchPipeline`'s merge re-applies any pending patch on top
   of the freshly fetched node, the same way it already preserves on-screen
   *positions* across a refetch. Wired into `FunctionSettingsPanel`'s
   where-filter fields (the one other live-preview-before-save case found —
   `PathInputSettingsPanel`'s template field no longer needs it after #2's
   fix removed its editable inputs).
3. `PathInputSettingsPanel.tsx` / `SweepSettingsPanel.tsx` — rewritten
   read-only (matches `ConstantSettingsPanel`'s "source-scanned, edit via
   source + Refresh Code" precedent). Removed the dead
   `update_path_input`/`update_sweep`/`add_path_input_alternate`/
   `remove_path_input_alternate` entries from `api.ts`'s REST route table.
   Rebuilt the frontend (`npm run build`) so the checked-in
   `scistack_gui/static/` bundle matches.

## Verification

- `tsc --noEmit` and `npm run build` both pass.
- No frontend test runner exists in this repo — user needs to click
  through manually (drag a new node while typing a where-filter value;
  confirm PathInput/Sweep panels show read-only values with a
  Refresh-Code hint).
- Backend: user runs `test_config.py` themselves (no Python access here).
