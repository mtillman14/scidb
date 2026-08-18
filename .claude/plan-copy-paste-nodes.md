# Copy/paste nodes, within- and cross-hypothesis (to-do #5)

## Existing precedent this reuses

`scope_service.duplicate_pipeline` already solves almost this exact
problem at whole-scope granularity: fresh `node_id`s, config copied
verbatim, positions offset, submodule `uses` re-pointed at the SAME child
(never duplicated), and a "solidify" step so a bare/implicitly-placed
source node doesn't appear to vanish once its copy independently
graduates to its own placement. Copy/paste is the same operation at
**selection granularity** instead of "the whole scope," so the plan is:
extract that per-node/per-use/per-edge copy loop out of `duplicate_pipeline`
into a shared helper, and add a new `paste_nodes` entry point that calls
it with an explicit `node_ids` subset and an arbitrary target scope
(which may equal or differ from the source scope — "within- and between
hypothesis pipelines" falls out for free, no special-casing needed).

## What differs from `duplicate_pipeline` at subset granularity

- **Boundary edges are dropped, not preserved.** `duplicate_pipeline`
  never has this problem (it copies 100% of a scope's nodes, so every
  edge is internal by construction). A partial selection can have edges
  to nodes NOT in the copied set — those are silently dropped (logged
  with a count). This is the only coherent behavior once cross-scope
  paste is possible (an edge into a node that doesn't exist in the
  target scope is meaningless), and it matches the project's established
  "reversible, not restrictive" stance — a dangling paste just needs
  manual re-wiring after, same as any other partially-wired state the
  GUI already tolerates.
- **No compile-validation gate.** `duplicate_pipeline` validates the
  result compiles because it produces a whole new, supposedly-standalone
  pipeline. A paste is adding a subgraph into an already-valid scope —
  it's expected to often be a dangling fragment (missing boundary inputs)
  immediately after paste, exactly like manually dragging in a few nodes
  one at a time. No validation, no rollback-on-failure needed.
- **Paste target position**: translate the copied selection so its
  bounding-box top-left lands at the paste point (last mouse position
  over the canvas, tracked the same way drag-and-drop already does today)
  instead of `duplicate_pipeline`'s fixed +40/+40 offset — keyboard paste
  (Cmd/Ctrl+V) should land where the user is looking, not accumulate in
  a corner on repeated pastes.

## Design

**Backend** (`services/scope_service.py`):
- Refactor the copy loop inside `duplicate_pipeline` into
  `_clone_nodes(db, source_pid, node_ids, target_pid, anchor) ->
  (old_to_new, n_nodes, n_edges)` — `node_ids=None` means "every node in
  `source_pid`" (today's full-scope behavior, unchanged). `anchor` is
  the target top-left point the selection's bounding box gets translated
  to. `duplicate_pipeline` keeps its own compile-validation wrapped
  around the call; the new `paste_nodes` skips it.
- `paste_nodes(source_pipeline_id, node_ids, target_pipeline_id, x, y) ->
  {"ok": True, "node_id_map": {...}}` — thin wrapper: resolve the
  selection's current bounding box, call `_clone_nodes` with anchor
  `(x, y)`, return the old→new id map so the frontend can auto-select
  the pasted copies.
- API: `POST /api/pipelines/{pipeline_id}/paste-nodes`, body
  `{source_pipeline_id, node_ids, x, y}`, in `api/scopes.py` — wired
  through `server.py`'s `_HANDLERS` and `api.ts` (three-places rule).

**Frontend**:
- New `context/ClipboardContext.tsx` (same shape as the existing small
  contexts): holds `{sourcePipelineId, nodeIds} | null` — a lightweight
  *reference*, not a snapshot of node data, so paste always works off
  live current config/wiring (a copy made, then the source edited, then
  pasted, picks up the edit — matches how every other "fork from current
  state" operation in this codebase already behaves, e.g.
  `duplicate_pipeline`).
- `PipelineDAG.tsx`: reuses the existing `selectedIds` (box-select,
  already wired for "Extract to submodule"). Adds:
  - Cmd/Ctrl+C → clipboard = `{sourcePipelineId: currentScope, nodeIds:
    selectedIds}` (only when `selectedIds.length > 0` and focus isn't in
    a text input, so it doesn't steal browser/OS copy elsewhere in the
    app).
  - Cmd/Ctrl+V → `paste_nodes` at the last tracked mouse position over
    the canvas (a ref updated on canvas `mousemove`, same idea as the
    existing drag-and-drop drop-point handling), then `bumpGraph()` and
    select the returned pasted ids.
  - The existing multi-select toolbar Panel (today gated on
    `selectedIds.length > 1`, "Extract to submodule") gains a "Copy"
    button alongside it, now shown from `length >= 1`; a always-present
    "Paste" button (enabled when the clipboard is non-empty, showing a
    count) covers users who don't know/use the keyboard shortcut, and is
    the natural way to paste **between** hypotheses (copy on canvas A,
    switch tabs, click Paste on canvas B).

## Effort shape

Backend: a refactor (no behavior change to `duplicate_pipeline`) + one
new thin service function + one endpoint through the usual 3 layers.
Small. Frontend: one new context (boilerplate-sized), two keyboard
handlers, two toolbar buttons. Small-medium.

## Status: BUILT (2026-08-13)

Implemented exactly as designed above:

- **Backend** — `duplicate_pipeline`'s copy loop extracted into
  `_clone_nodes(db, source_pid, node_ids, target_pid, anchor=None)`
  (`node_ids=None` = whole scope, unchanged `duplicate_pipeline`
  behavior; explicit `node_ids` + `anchor=(x, y)` = the new selection
  path). New `paste_nodes(source_pipeline_id, node_ids,
  target_pipeline_id, x, y)` — no compile-validation gate, boundary
  edges dropped, submodule placements re-point at the same child. New
  `POST /api/pipelines/{pipeline_id}/paste-nodes` in `api/scopes.py`,
  wired through `server.py`'s `_HANDLERS` and `api.ts`.
- **Frontend** — new `context/ClipboardContext.tsx` (reference-only:
  `{sourcePipelineId, nodeIds}`), wired into `App.tsx`. `PipelineDAG.tsx`
  gained Cmd/Ctrl+C (copies `selectedIds`, the existing box-select
  tracking) and Cmd/Ctrl+V (pastes at the last tracked mouse position
  over the canvas, ignored while a text field has focus), plus Copy/Paste
  buttons in the existing selection toolbar (now shown from 1 selected
  node, not just >1) for discoverability and for pasting **between**
  hypotheses (copy on one tab, switch tabs, click Paste).
- **Tests** — `tests/test_pipeline_scopes.py::TestPasteNodes`: same-scope
  paste (config + internal edges copied, fresh ids, originals untouched),
  anchor-based position translation (bounding-box top-left lands exactly
  at the anchor, relative layout between copied nodes preserved),
  boundary-edge dropping, cross-scope paste, submodule `uses` staying
  pointed at the same child, and the empty-selection no-op. Not yet run
  by the user.
