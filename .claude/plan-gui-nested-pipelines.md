# Plan: GUI Nested Pipelines + Endpoint-First Surface (GUI stage)

Status: APPROVED 2026-07-16 (G1–G4 all confirmed by user). Execution
order confirmed: stage 4 (MATLAB parity) first, then Part A (nesting),
then Part B item 1 (endpoint presentation). NOT yet implemented.
Grounding: `docs/claude/scistack-gui-backend-internals.md` (dual-protocol
server, service layer, `_pipeline_*` DuckDB tables + JSON layout);
backend stages 1–3 all verified (registry, composition, bindings,
endpoint verbs). Existing GUI features (drag-drop pipeline, code
discovery, variant definition, node creation) are assumed working and
untouched.

## Part A — Nested pipelines (pipeline-as-node)

User requirement: a node that itself represents a pipeline; double-click
opens the encapsulated pipeline (hiding all other pipelines' nodes);
navigation between pipeline screens.

### A1. Data model (GUI persistence — scistack-gui layer)

The GUI's flat document model gains pipeline scoping:

- New `_pipelines` table: `(pipeline_id, name)`. A reserved root pipeline
  (`main`) exists implicitly; migration assigns all existing nodes to it
  (one-time, sentinel-guarded — same pattern as the manual-nodes JSON
  migration).
- `_pipeline_nodes` gains a `pipeline_id` column (scope of every node).
- New `_pipeline_uses` table: `(use_id, parent_pipeline_id,
  child_pipeline_id, binding_json)` — one row per pipeline-node placed on
  a parent canvas. `binding_json` holds `{key_map, params, iterate}`
  (empty = identity). The pipeline NODE on the canvas is
  `node_type='pipeline'`, `node_id=use_id` — so the same child pipeline
  placed twice (with different bindings = two variants, matching the
  backend's binding-signature dedup) is two nodes.
- Layout JSON becomes per-scope: positions keyed
  `{pipeline_id: {node_id: {x, y}}}` (migration: existing positions →
  root scope).
- Cycle guard on `_pipeline_uses` insert (mirror backend
  `PipelineCycleError` — reject at edge creation with a clear message).

**Deliberate consistency with the no-spec-persistence decision:** these
tables are the GUI's DOCUMENT (what the user drew), not backend spec
persistence. At run time the GUI constructs in-session backend `Pipeline`
objects from its document (below); the backend still never stores
pipelines.

### A2. Pipeline node rendering (ports)

A pipeline node shows its INTERFACE: input ports = variable types consumed
inside but not produced inside; output ports = types produced inside.
Backend helper (new, tiny, in scidb — it is pure graph logic that MATLAB/
CLI can also use): `Pipeline.interface() -> {"inputs": [...classes],
"outputs": [...classes]}` computed from the composed steps'
`input_classes`/`output_classes`. The GUI service mirrors the same
computation over its document for unsaved/edited pipelines.
Edges on the parent canvas connect variable nodes to pipeline-node ports
using the existing edge machinery.
Binding badge: non-identity bindings render like variant badges today
(`low_hz=30`, `session→subject`).

### A3. Navigation

- **Descend:** double-click a pipeline node → canvas swaps to the child
  pipeline's scope (ONLY its nodes; nothing from other pipelines).
- **Breadcrumb path:** `main ▸ loading ▸ filters` — composition is a DAG
  (one pipeline used by many parents), so the breadcrumb is the
  navigation PATH taken, not a unique address; clicking a crumb ascends
  to that scope. Entering via a BOUND use shows the binding in the crumb
  (`loading (low_hz=30)`) — context for why constants display overridden.
- **Sidebar:** flat list of all pipelines (from `_pipelines`) for direct
  jumps; current scope highlighted.
- Frontend state: `current_scope` (pipeline_id) + `breadcrumb` (list of
  use_ids); all node/edge queries and layout reads become scope-filtered.

### A4. Execution integration (where stages 1–3 pay off)

The GUI currently executes per-node `for_each` in worker threads. New
model — the GUI service builds in-session backend pipelines from the
document:

1. For each GUI pipeline: `db.pipeline(name)` (or `Pipeline(name, db)`
   without activation), register each function node's call via
   `for_each(..., pipeline=pipe)` marshalled exactly as the run service
   already marshals eager calls.
2. Pipeline-use rows → `parent.use(child.bind(**binding_json))`.
3. Run controls map to backend verbs: node context-menu **"Run until
   here"** → `run_until(step)`; pipeline-node **"Run"** → child
   `run_all()` semantics via `run_until` on its own steps; canvas **"Run
   endpoints"** → `run_endpoints()`.
4. **Plan-preview dialog** (R2, was never built): before any run, call
   `plan(target)` and show the step list with green/red state + combo
   counts + owner pipeline; Run/Cancel. Non-blocking backend (N3) means
   the GUI owns this gate, as designed.
5. Roll-up state: a pipeline node is red if any step in its subtree is
   red — derivable from `plan()` entries (each carries owner pipeline).

### A5. Out of scope for this stage

MATLAB-registered steps in the GUI (stage 4 descriptors could surface
later); editing a child pipeline "in place" on the parent canvas
(expand-in-situ) — navigation-only v1; auto-layout of imported pipelines.

## Part B — Gap analysis: other missing GUI features

Ranked; 1–2 are the "crucial" ones given recent backend work.

1. **Endpoint-first presentation (the original vision, now unlockable).**
   - Endpoint nodes styled distinctly (plot/stat kinds via
     `_endpoint_kind`); optionally an "endpoints rail" listing
     `pipe.endpoints()` as cards — the inverted view where processing is
     the collapsible ancestry.
   - **Artifact preview panel:** clicking a plot node shows its rendered
     figure(s) (paths from records, or from `show()` drafts), with
     stamp-derived provenance caption (function, inputs, branch_params —
     `read_artifact_stamp` exists). Stat nodes: formatted JSON table.
   - **Draft/finalized toggle** on run controls (D3 flag is plumbed
     through everything already).
   - **`show()` button** on endpoint nodes: draft-run + preview, zero DB
     writes — the everyday "let me look at it" loop.
   - **Report button:** `db.inspect.write_report(dir)` + open
     `index.html` (report CLI shipped 2026-07-07; no GUI trigger yet).
2. **Pull-execution controls** — "Run until here" + plan-preview dialog
   (folded into A4 above; listed here because they matter even before
   nested pipelines ship).
3. **Binding editor** — placing a pipeline node opens a small form:
   key_map (dropdowns: child's keys → project schema keys), params
   (discovered constants of the child subtree, validated via `bind()`'s
   bind-time errors surfaced inline), iterate overrides.
4. **Discovery convergence (small, decide-once):** GUI `registry.py`
   collects ANY top-level callable; `scidb.discover` collects
   `@scistack`-tagged only. Two palettes will drift. Proposal: GUI
   palette prefers tagged functions when any exist in a module, falls
   back to all-callables otherwise (zero-friction for untagged projects,
   signal-respecting for tagged ones).
5. **Not needed now:** GUI spec persistence (document tables suffice);
   MATLAB pipeline surfacing (post-stage-4); multi-DB pipelines (backend
   C3 forbids).

## Decisions needed / proposed

- **G1.** Pipeline-node identity = use_id (same child twice = two nodes,
  bindings live on the use edge) — matches backend variant semantics.
  → **Confirm.**
- **G2.** Execution rearchitecture per A4 (GUI builds in-session backend
  Pipelines and runs through run_until/plan instead of per-node eager
  for_each). The alternative — keep per-node execution and bolt nested
  display on top — preserves none of the pull-execution/plan benefits.
  → **Confirm.**
- **G3.** Breadcrumb = navigation path (DAG-aware), sidebar for direct
  jumps. → **Confirm.**
- **G4.** Part B priority order (endpoint presentation first after
  nesting) and the discovery-convergence proposal (B4). → **Confirm.**

## Suggested sequencing vs. stage 4 (MATLAB parity)

Stage 4 (M1–M4 also still awaiting confirmation) and this GUI stage are
independent — different layers, no shared files except tiny scidb
helpers (`Pipeline.interface()`). Recommendation: implement stage 4
first (small, already designed), then GUI Part A, then Part B item 1;
but either order works.
