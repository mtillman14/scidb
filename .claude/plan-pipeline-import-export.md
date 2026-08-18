# Import/export pipelines between users (to-do #7)

Goal: let a user hand a colleague one pipeline (a hypothesis, or a bare
reusable submodule) as a single portable file — the DOCUMENT only (wiring,
layout, config), never the underlying data/records, since the colleague has
their own database. Also serves as a local backup/escape hatch per the
roadmap doc's Phase D rationale.

**User-confirmed design decision**: when an imported pipeline references a
Constant/PathInput/Sweep NAME that already exists locally, import **reuses
the local definition** rather than renaming or prompting per-conflict —
matches the "shared by name" convention `duplicate_pipeline` already
established for PathInput (same reasoning: same name = same real-world
thing; no piling up of near-duplicate definitions on repeated imports).

## What gets exported

One pipeline_id, **recursively including every pipeline it uses** (nested
submodules) so the result is self-contained — the same reasoning
`duplicate_pipeline` uses when it walks the FULL resolved graph (not just
`get_manual_nodes`), so already-executed ("graduated") nodes export too.

Collected across the closure of exported pipeline_ids:
- **Pipelines**: id (own, for internal remapping only — NOT reused on
  import), name, hidden flag (skip — an export is implicitly "visible"),
  hypothesis tag + fields (`_hypotheses`) **only for the root exported
  pipeline** — a used submodule was never itself a tab, so it doesn't
  become one on import either.
- **Nodes**: id/type/label/config for every node in each exported scope's
  RESOLVED graph (`services.pipeline_service.get_pipeline_graph`, same
  source `_clone_nodes` already uses) — not just manual DB rows, so
  graduated nodes carry over as manual imports (identical to how
  `duplicate_pipeline`/`paste_nodes` already turn a graduated node into a
  fresh manual one; it re-graduates locally if the label matches real
  local DB history).
- **Positions**: from `layout_store.read_positions_by_scope()`, per
  exported scope.
- **Edges/uses**: only those with BOTH endpoints inside the exported node/
  pipeline set (same boundary-drop rule `_clone_nodes` already uses for a
  partial selection — here the "selection" is just every node across the
  whole closure, so in practice nothing crosses the boundary since the
  closure is transitively complete by construction). Taken from
  `get_pipeline_graph`'s already hidden-filtered edge list, same source as
  nodes — so a currently-hidden DB-derived edge is simply absent, same as
  today's canvas view.
- **Hidden ports**: scoped to the exported pipeline_ids — this is a pure
  wiring-shape override (`document_interface`'s manual suppression),
  present the moment nodes/edges are placed, independent of any execution
  history, so it transfers meaningfully.
- **NOT exported: hidden nodes/edges/combos**
  (`_pipeline_hidden_nodes/_edges/_combos`). These ALL apply exclusively to
  DB-DERIVED ("graduated") wiring — content only present because the
  exporting user already ran it (`hide_edge`'s own docstring: "Manual
  edges are hard-deleted instead of hidden; this table is for DB-derived
  edges only"). A freshly-imported pipeline has no execution history in
  the target database, so nothing auto-derives there yet regardless — the
  exporting user's past "I explicitly cut this auto-derived edge" choice
  isn't portable data, it's local to a run history that doesn't exist on
  the other end. If the importing user later runs the same wiring
  locally, whether to hide anything is their own local decision, exactly
  like it would be for any other DB-derived content they produce. (Their
  hidden edges DO stay exportable in a later re-export of the imported
  copy, once local history exists — this just isn't transferable on the
  FIRST hop.)
- **Referenced globals** (constants/path_inputs/sweeps are name-global,
  not scope-scoped — collected by which NAMES the exported `constantNode`/
  `pathInputNode`/`sweepNode` nodes reference): full definitions
  (PathInput's `alternate_templates`, Sweep's `values`,
  `_pipeline_pending_constants` rows for each exported constant name).

**Not exported**: any actual data/records, run history, artifacts on disk,
`_variables` registry rows (the colleague's own registered Python/MATLAB
classes are what a node's `label` resolves against locally — same as
today's manual-node model already assumes for any node, imported or not).

## File format

A single JSON file, written server-side to `{project_dir}/exports/` (same
"write into the project directory, return the path" pattern as
`endpoint_service.write_report`) AND returned directly in the API response
body (so the frontend doesn't need a second round trip to read it back for
display/download).

```json
{
  "format_version": 1,
  "root_pipeline_id": "<the exported pipeline's OWN id — for internal remap only>",
  "exported_at": "...",
  "pipelines": [{"pipeline_id": "...", "name": "...", "is_root": true}],
  "hypothesis": {"research_question": "...", "hypothesis_statement": "...", "evidence_for": [...], "evidence_against": [...]} | null,
  "nodes": [{"node_id": "...", "pipeline_id": "...", "node_type": "...", "label": "...", "config": {...}, "x": .., "y": ..}],
  "edges": [{"edge_id": "...", "source": "...", "target": "...", "source_handle": ..., "target_handle": ...}],
  "uses": [{"use_id": "...", "parent_pipeline_id": "...", "child_pipeline_id": "...", "binding": {...}, "x": .., "y": ..}],
  "hidden_ports": [{"pipeline_id": "...", "direction": "...", "var_type": "..."}],
  "constants": {"<name>": ["<value>", ...]},
  "path_inputs": [{"name": "...", "template": "...", "root_folder": ..., "alternate_templates": [...]}],
  "sweeps": [{"name": "...", "values": [...]}]
}
```

## Import algorithm

Same "fresh id + remap" pattern `_clone_nodes` already uses, generalized
across a DATABASE boundary instead of a scope boundary within one DB:

1. For every `pipelines` entry, `pipeline_store.create_pipeline` with a
   collision-safe name (append " (imported)" / a counter if the name is
   already taken locally — names must stay unique per
   `create_pipeline`'s existing guard) → build `old_pipeline_id ->
   new_pipeline_id` map. The root's new id becomes the import's return
   value (what the frontend jumps to).
2. If `hypothesis` is present, tag the ROOT's new pipeline_id via the same
   path `create_hypothesis`/`update_hypothesis` already use.
3. For every `node`, mint a fresh id (same `{prefix}__{label}__{uuid[:8]}`
   scheme as `_clone_nodes`), `write_manual_node` + `update_node_config`
   into the remapped pipeline_id, `write_node_position` under the remapped
   scope → `old_node_id -> new_node_id` map.
4. For every `use`, remap parent/child pipeline_ids and re-place via
   `add_pipeline_use` (binding copied verbatim) → `old_use_id ->
   new_use_id` map (use_id IS the canvas node id, so this feeds the same
   node-id map above for edge remapping).
5. For every `edge`, remap endpoints through the node-id map (drop + log
   if either side didn't remap — defensive; shouldn't happen given the
   export's own boundary-drop guarantee).
6. For every `hidden_port`, remap `pipeline_id` only (type-level, no node
   endpoints to remap).
7. For each referenced **constant name**: if it already exists locally
   (`layout_store.read_all_constant_names()`), reuse it as-is (per the
   confirmed decision) — the imported values are simply not applied. If
   it doesn't exist locally yet, create it (`write_constant` + each
   pending value via `add_pending_constant`).
9. Same reuse-by-name rule for **path_inputs** (`write_path_input` +
   `add_path_input_alternate` per alternate, only when the name is new
   locally) and **sweeps** (`write_sweep`, only when new locally).
10. Return `{"ok": True, "pipeline_id": new_root_pipeline_id, "reused": {"constants": [...], "path_inputs": [...], "sweeps": [...]}, "unresolved_labels": [...]}` —
    `reused` lets the frontend show "these already existed locally and
    were kept as-is" instead of silently doing so; `unresolved_labels` is
    every function/variable label the import created a node for that
    isn't in the LOCAL registry yet (informational only — same as any
    node referencing an unregistered label already behaves in this GUI
    today; nothing blocks the import).

No compile-validation gate (mirrors `paste_nodes`, not
`duplicate_pipeline`): an imported pipeline commonly references functions/
variables the importing user hasn't written locally yet — that's expected,
not an error, and the GUI already tolerates unresolved labels everywhere
else.

## API / UI

- `GET /api/pipelines/{pipeline_id}/export` → writes the file, returns
  `{"path": "...", "document": {...the JSON above...}}`.
- `POST /api/pipelines/import` → body is the JSON document itself, returns
  the shape from step 10 above.
- **Export button**: next to existing "⎘ Duplicate" actions — the
  hypothesis tab strip (`HypothesisTabs.tsx`) and a submodule's placed
  node (`PipelineNode.tsx`), so both a whole hypothesis and a bare reusable
  submodule are exportable. Shows the written path in an alert (same
  pattern as the existing "📄 Report" button in `App.tsx`) and also
  triggers a browser download of the returned JSON via a client-side
  `Blob` + `<a download>` (works in standalone mode; VS Code webview mode
  shows the path only, same limitation `handleReport` already has for
  opening new tabs).
- **Import button**: next to "+ new hypothesis" in `HypothesisTabs.tsx` —
  a hidden `<input type="file" accept=".json">`, read client-side via
  `FileReader` (works identically in standalone and VS Code webview modes,
  since the File API is pure browser/JS with no filesystem-path
  dependency), parsed, POSTed as the request body. On success, jump to the
  new root pipeline and show a short summary (reused names,
  unresolved labels) if either list is non-empty.

## Effort shape

Backend: the bulk of the work — a recursive-closure collector (export) and
a multi-table id-remapping importer (import), both structurally close to
`_clone_nodes` but spanning every table (hidden state, globals) that
function doesn't touch. Medium-large. Frontend: two buttons + a file input
+ Blob-download glue, reusing existing panel/button styles. Small.

## Status: BUILT (2026-08-13)

Implemented per the design above, with the hidden-state scope revision
noted inline earlier (hidden ports export/import; hidden nodes/edges/
combos deliberately don't, since they're DB-derived-execution-history-only
and not portable):

- **Backend** — new `services/portability_service.py`: `export_pipeline`
  (recursive closure walk, boundary-drop edges/uses, referenced-globals
  collection) and `import_pipeline_document` (fresh-id remap across every
  table, reuse-by-name for constants/PathInputs/Sweeps, informational
  `unresolved_labels`). `export_pipeline_to_file` writes into
  `{project_dir}/exports/` (mirrors `endpoint_service.write_report`'s
  pattern) and returns the document too. Thin delegates in
  `scope_service.py`; `GET /api/pipelines/{id}/export` and
  `POST /api/pipelines/import` in `api/scopes.py`; wired through
  `server.py`'s `_HANDLERS` and `api.ts`.
- **Frontend** — Export button (⇩) added next to Duplicate in both
  `HypothesisTabs.tsx` (whole hypothesis) and `PipelineNode.tsx` (a bare
  placed submodule) — triggers a browser download of the returned JSON in
  standalone mode (Blob + `<a download>`), shows the written server path
  in both modes. Import button (⇧ import) in `HypothesisTabs.tsx` uses a
  hidden `<input type="file">` + `FileReader` (works identically in
  standalone and VS Code webview modes — pure browser File API, no
  filesystem-path dependency), then jumps to the new root pipeline and
  surfaces reused-definition/unresolved-label counts if either is
  non-empty.
- **Tests** — `tests/test_portability.py`: same-database roundtrip
  (fresh-id remap, config/wiring preserved, reuse-by-name naturally
  exercised since names already exist locally) and cross-database
  roundtrip via a genuinely separate second `DatabaseManager` (recursive
  submodule bundling, hypothesis tag carrying over, a bare submodule NOT
  getting hypothesis-tagged, and globals created fresh when absent
  locally). Verified `npx tsc --noEmit` and `npm run build` both pass
  (ran directly — Node/npm work in this environment). Python tests not
  yet run by the user.

Note for whoever runs the tests: `TestExportImportCrossDatabase` had to
work around a real two-globals distinction in this codebase —
`configure_database()` only sets scidb's own internal global, not
`scistack_gui.db`'s separate `_db`/`_db_path` pointer that `layout_store`
(positions/constants/PathInputs/Sweeps) always reads through regardless of
whatever `db` object a caller passes explicitly. `conftest.py`'s own
`populated_db` fixture already sets both for exactly this reason; the
test helper `_second_db` does the same. This isn't a bug in
`portability_service.py` itself — every real call path in the app already
has exactly one active database, so the explicit `db` parameter and the
`scistack_gui.db` global always coincide in production; it only needed
explicit handling here because the test deliberately keeps two databases
open at once.
