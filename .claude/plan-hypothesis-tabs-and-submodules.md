# Plan: Hypothesis Tabs, Composable Submodule Extraction, and Pipeline Duplication

## Context

SciStack's versioning/lineage API is mature, but the GUI has two higher-level
abstractions the user actually needs day to day that are missing or half-built:

1. **Composable submodules** — grouping a reusable chunk of a pipeline (e.g.
   "load + filter + arrange EMG/IMU/spatiotemporal data") into its own
   encapsulated, droppable-elsewhere unit. The *backend* (`scidb.Pipeline`,
   `use()`, `bind()`) and the *GUI's nested-pipeline navigation* (double-click
   to descend into a pipeline-node, breadcrumb to ascend — shipped
   2026-07-16, `docs/claude/scistack-gui-frontend-architecture.md`) already
   exist. What's missing is the actual **authoring gesture**: select existing
   nodes on a canvas and turn them into a submodule in place. Today a
   submodule can only be built by creating an empty pipeline and populating
   it from scratch.
2. **Hypothesis-specific pipelines** — one tab per research question, each
   with its own downstream DAG, typically forking from a shared submodule
   at the point where analyses diverge (e.g. "gait symmetry" vs "gait speed"
   forking off a shared load/filter/arrange submodule). This is entirely
   unimplemented — there is currently one implicit root scope (`main`);
   other pipelines are only reachable by navigating *down* into them, not as
   independent sibling top-level pipelines with their own tab.

This plan adds both, plus documentation fields (research question, hypothesis
statement, evidence for/against) attached to each hypothesis tab, entirely in
the `scistack-gui` layer (per project convention: GUI-only concerns live in
the GUI layer; no changes needed in `scidb`/`scifor`/`scilineage`).

Research already done (this session): read `scidb`/`scistack` READMEs,
`docs/claude/scistack-gui-frontend-architecture.md`,
`.claude/plan-gui-nested-pipelines.md`, the `endpoint-first-pipelines`
project memory, and had two Explore agents fully read
`pipeline_store.py`, `scope_service.py`, `execution_service.py`,
`api/scopes.py`, `api/pipeline.py`, `graph_builder.py`, `layout.py`, and the
frontend's `PipelineDAG.tsx`, `PipelineNode.tsx`, `PipelineSettingsPanel.tsx`,
`Sidebar.tsx`/`EditTab.tsx`, `ScopeContext.tsx`, `App.tsx`, `api.ts`.

### Decisions confirmed with the user

- Hypotheses are a **new concept**: one tab = one pipeline = one research
  question, extending (not replacing) the existing nested-pipeline/scope
  system. A hypothesis's pipeline can still contain arbitrarily nested
  submodules.
- Submodules created via extraction are **immediately shared/reusable**
  across hypothesis tabs — no separate "publish" step.
- Duplicating a pipeline **forks its own nodes** (fresh copies you can edit
  freely) but **keeps submodule placements (`_pipeline_uses`) pointing at the
  same child pipeline** — editing the shared submodule later affects every
  hypothesis using it, which is the point of factoring it out.
- `main` is not a special scratch scope — it's simply the default name of
  the first/default hypothesis, a sibling to every other hypothesis. The
  sidebar's flat pipeline list, once tabs exist, should show hypotheses (not
  a mix of hypotheses and submodules) — submodules get their own list.
- **PathInputs need a scoping fix.** They are currently a single
  project-wide list keyed only by parameter name (`layout.py` `path_inputs[]`,
  `write_path_input(name, template, root_folder)`) — not tied to a pipeline,
  a node, or even a specific call site. Two independent placements that
  happen to feed a parameter of the same name silently share one template
  today, in and out of hypothesis tabs alike. This is bundled into this
  effort rather than deferred.

### Design call: how PathInputs behave on copy (revised per user decision)

Resolved: PathInputs should behave **exactly like function code and
variable-type references** — shared by default. Copying a PathInput node
(via node copy/paste, "extract to submodule," or "duplicate pipeline")
keeps pointing at the **same named definition**; editing the template in
one place changes it everywhere it's used, which is the expected behavior
for a reusable named path template (mirrors `write_path_input`'s existing
palette-item semantics — nothing needs to change here structurally).

On top of that default, add one new **explicit, opt-in** action: **"Deep
copy this PathInput"** on a placed PathInput node. This is the escape
hatch for "I need this one research-question pipeline to point at a
different path template than everywhere else this name is used." It mints
a new, independently-named definition (template/root_folder cloned as the
starting values) and repoints *only that one node's* config to the new
name — every other placement of the original name is untouched.

This means Stage 4 (duplicate pipeline) needs **no special-casing for
PathInput nodes at all** — copying a node's config verbatim (as already
planned for every other node type) already produces the correct "shared by
default" behavior, since the config just holds a name reference, not the
template data itself. The opt-in deep-copy action is the only new surface.

## Staging

Four stages, each independently shippable and testable, and now fully
independent of each other (the PathInput opt-in action has no ordering
dependency on duplication, since duplication needs no special-casing for
it). Suggested order: tabs first (immediate value), then extraction, then
the PathInput deep-copy action, then duplication.

---

### Stage 1 — Hypothesis tabs + documentation

**Data model** (`scistack-gui/scistack_gui/pipeline_store.py`, follow the
existing `_ensure_tables`/migration pattern at lines 63–137):

```sql
CREATE TABLE IF NOT EXISTS _hypotheses (
    pipeline_id         VARCHAR PRIMARY KEY,  -- FK to _pipelines.pipeline_id
    research_question   VARCHAR DEFAULT '',
    hypothesis_statement VARCHAR DEFAULT '',
    evidence_for        VARCHAR DEFAULT '[]', -- JSON list of {text, added_at}
    evidence_against    VARCHAR DEFAULT '[]'
)
```

One-time sentinel-guarded migration (mirror the existing manual-nodes/JSON
migration pattern, `pipeline_store.py:36-42`): insert a `_hypotheses` row
for the existing `main` pipeline so it appears as the default first tab,
exactly like any other hypothesis (no renaming, no special-casing).

**Store functions** (`pipeline_store.py`, new, alongside
`create_pipeline`/`rename_pipeline`/`delete_pipeline` at lines 410–499):
`create_hypothesis(db, name) -> pipeline_id` (calls `create_pipeline` then
inserts an empty `_hypotheses` row), `list_hypotheses(db)` (join
`_pipelines`/`_hypotheses`), `update_hypothesis(db, pipeline_id, fields)`,
`delete_hypothesis` (reuse `delete_pipeline`'s existing cascade/guard, plus
delete the `_hypotheses` row).

**API** (`scistack-gui/scistack_gui/api/scopes.py`, same `_guard` pattern as
lines 48–62): `GET /api/hypotheses`, `POST /api/hypotheses`,
`PUT /api/hypotheses/{pipeline_id}`, `DELETE /api/hypotheses/{pipeline_id}`.
Register matching JSON-RPC handlers in `server.py` (same snake_case name on
both sides, e.g. `list_hypotheses`, `create_hypothesis`) and matching
entries in the frontend `routes` table in `api.ts` (lines 129–139 show the
exact shape to copy).

**Frontend:**
- New `HypothesisTabs.tsx`, mounted in `App.tsx` between `<header>` and the
  `<ReactFlowProvider>` div (confirmed empty slot, `App.tsx:265-266`) —
  outside react-flow's context since it doesn't touch the canvas. Fetches
  `list_hypotheses`, renders one tab per hypothesis + a "+ new hypothesis"
  tab. Clicking a tab calls `jumpTo(pipeline_id, name)` — `ScopeContext`'s
  existing `jumpTo` (lines 71–75) already does 100% of "switch tabs" (resets
  breadcrumb, changes `currentScope`, which `PipelineDAG` already refetches
  on). No new navigation plumbing needed.
- "+ new hypothesis" opens a small inline dialog (name only, to start) →
  `create_hypothesis` → `jumpTo` into it.
- New sidebar panel (new tab in `Sidebar.tsx`'s `BASE_TABS`, or folded into
  the existing `Project` tab) showing the *current* tab's hypothesis
  metadata: research question, hypothesis statement (text areas), and two
  evidence lists (for/against) with simple add/remove rows. Follow
  `PipelineSettingsPanel.tsx`'s exact pattern: re-seed on
  `[currentScope]` change (mirrors its `useEffect` at lines 53–59), save via
  `callBackend('update_hypothesis', ...)`, `status.ok`/`status.error`
  display (lines 314–324).
- `EditTab.tsx`'s existing flat "Pipelines" list (lines 44–65, 229–317)
  gets filtered to exclude anything with a `_hypotheses` row — per the
  user's decision, that list becomes "submodules only" (feeds naturally
  into Stage 3's extraction UI, since that's exactly the list of things you
  can drop onto a canvas as a submodule).

---

### Stage 2 — PathInput "deep copy" action (opt-in fork)

No schema change: PathInput definitions (`layout.py`'s `path_inputs[]`,
`{name, template, root_folder}`) stay a global named registry, and node
copies keep referencing the same name by default (see design call above —
this is the desired behavior, not a gap to fix).

**New store function** (`layout.py`, alongside `write_path_input`/
`delete_path_input` at lines 320–337): `deep_copy_path_input(name) ->
new_name` — reads the existing definition, mints a disambiguated name
(`f"{name}_copy"`, incrementing if taken), writes it via the existing
`write_path_input(new_name, template, root_folder)`, returns `new_name`.

**Service + API**: `layout_service.deep_copy_path_input(node_id)` — looks
up the PathInput node's current name from its config, calls the store
function above, updates *that node's own* config to reference `new_name`
via the existing `update_node_config` (`pipeline_store.py:271-277`), and
bumps the graph. New endpoint `POST /api/path-inputs/{node_id}/deep-copy`
following the same router/`_guard` pattern as `api/scopes.py`, plus a
matching `deep_copy_path_input` entry in `server.py` and `api.ts`.

**Frontend**: a "Deep copy" button in `PathInputSettingsPanel.tsx` (same
button-and-status pattern as `PipelineSettingsPanel.tsx`'s save button,
lines 302–324) — calls the new endpoint, then `bumpGraph()`. No changes
needed to `PipelineDAG.tsx`'s copy/paste handling or to Stage 4's
duplication logic — both already do the right thing (share by default) by
simply copying each node's config verbatim, since the config only holds a
name reference.

---

### Stage 3 — Extract selection into a new submodule

**Frontend** (`PipelineDAG.tsx`):
- Enable multi-select: add `onSelectionChange` to `<ReactFlow>` (around
  lines 340–353) tracking `selectedNodes` in local state (react-flow
  already supports box-select via shift+drag by default — the app just
  never reads `node.selected` today).
- When `selectedNodes.length > 1`, show a small floating toolbar/button
  ("Extract to submodule"), styled like the existing single-node context
  menu (lines 378–384). Clicking prompts for a name, then calls
  `callBackend('extract_to_submodule', { pipeline_id: currentScope,
  node_ids: selectedNodes.map(n => n.id), name })`, then `bumpGraph()` —
  matching the existing `onNodesDelete` precedent (lines 289–303) of never
  hand-splicing local state after a backend mutation.

**Backend** (`scistack_gui/services/scope_service.py`, new function
`extract_to_submodule(db, pipeline_id, node_ids, name)`):
1. `new_pid = pipeline_store.create_pipeline(db, name)`.
2. For each `node_id`: update `_pipeline_nodes.pipeline_id` to `new_pid`
   (an UPDATE — this is a **move**, not a copy, matching "removing all of
   those nodes from the screen and replacing it with just a submodule
   icon"). If it's a PathInput node, do **not** fork it here — moving is not
   copying, so it should keep referencing its existing named definition.
   Also move its saved position row to the new scope (DB-derived node scope
   is position-keyed per `domain/scope_filter.py` — confirmed in Explore
   research; reuse `layout_store.write_node_position(..., pipeline_id=)`
   under the new scope and remove the old-scope entry).
3. Compute the new pipeline's interface via the existing
   `pipeline_interface`/`Pipeline.interface()` machinery
   (`scope_service.py:94-110`) — inputs = types consumed inside but not
   produced inside, outputs = produced inside.
4. Rewrite boundary edges: any edge crossing from a moved node to a node
   still on the parent canvas (or vice versa) is deleted on the parent
   canvas and replaced by wiring the parent-side node to/from the new
   pipeline-node's corresponding port — the same port-edge convention
   already used for placed pipeline nodes today. Edges fully internal to
   the moved set need no rewriting (edges aren't scope-columned; they
   already resolve to the new scope via node membership, per
   `pipeline_store.py:32-34`).
5. `pipeline_store.add_pipeline_use(db, pipeline_id, new_pid, binding=None,
   x, y)` at roughly the centroid of the removed nodes — this reuses the
   existing cycle guard (`_uses_reachable`) for free.
6. Wrap all of the above in the store's existing `ValueError`→400 `_guard`
   convention (`api/scopes.py:48-52`) for a new
   `POST /api/pipelines/{id}/extract` route + matching `api.ts` entry.

---

### Stage 4 — Duplicate pipeline

**Backend** (`scope_service.py`, new `duplicate_pipeline(db, pipeline_id,
new_name)`):
1. `new_pid = pipeline_store.create_pipeline(db, new_name)`.
2. For every node in the source scope (`get_manual_nodes` +
   DB-derived nodes): mint a fresh `node_id`, copy `node_type`, `label`,
   and `config` JSON **verbatim** into `new_pid` via `_upsert_node` — this
   is what forks `schemaFilter`/`schemaLevel`/`runOptions` (and
   `whereFilters`, once wired up) for free, since they're already per-node
   config. Build an `old_id → new_id` map. PathInput nodes need no special
   handling here — copying `config` verbatim naturally keeps them pointing
   at the same shared named definition (Stage 2's default), and the user
   can hit "Deep copy" afterward on the duplicate if they want that one
   pipeline to diverge.
3. Copy positions for every new node into the new scope (small offset, e.g.
   +40/+40, purely cosmetic).
4. Copy internal edges: for every edge whose `source` and `target` are both
   in the `old_id` map, insert a new edge with remapped endpoints (mirrors
   `graduate_manual_node`'s existing old→new id rewrite pattern,
   `pipeline_store.py:286-301`).
5. Copy `_pipeline_uses` rows where `parent_pipeline_id == pipeline_id`:
   new `use_id`, **same `child_pipeline_id`** (the shared submodule
   reference — confirmed decision, this is the "ground truth" link that
   must NOT fork), `binding_json` copied verbatim (the duplicate's binding
   becomes independently editable from this point on, which already
   requires no special handling — it's just a normal column value on a new
   row).
6. Sanity-check the result by calling `execution_service.build_backend_pipeline`
   /`plan_pipeline` on `new_pid` — if it doesn't compile, something in the
   copy was inconsistent; surface that as a 400 rather than leaving a
   broken pipeline in the document.

**Frontend:** a "Duplicate pipeline" button on `PipelineNode.tsx` (next to
the existing "Run"/"Open pipeline" buttons — same `styles.button` pattern)
when viewing a pipeline node from its parent, and/or a "Duplicate" action on
the hypothesis tab strip itself (Stage 1) for the top-level case (gait
symmetry → gait speed). Calls `callBackend('duplicate_pipeline', ...)`,
then `bumpGraph()` (for a submodule duplicate) or `jumpTo` the new tab (for
a hypothesis duplicate).

**Known, explicitly-surfaced v1 limitation:** the `_pipeline_pending_constants`
staging table (candidate constant values not yet run) stays global/shared
across all pipelines — it's a project-wide "values I'm exploring" pool, not
GUI-owned per-pipeline state, and the user's own duplicate-pipeline
description didn't ask for this to fork. *Actual* bound constant values are
derived from real `scidb` call-site/variant records, not GUI document state,
so editing a constant on a duplicated pipeline's canvas already creates an
independent variant automatically — no special-casing needed or possible at
the GUI layer.

**Post-implementation correction (found by the user's first pytest run):**
step 2 above originally also duplicated already-executed ("graduated")
DB-derived nodes via `get_pipeline_graph`, on the (wrong) theory that
global function/variable identity made a fresh same-label node harmless.
It isn't: `var__{Type}` and `fn__{fn}__{call_id}` are single GLOBAL,
scope-singular canonical ids in this codebase — a second manual node with
the same label collides on the next graph build (`merge_manual_nodes`
graduates by label match, not scope) and STEALS the canonical node's
position away from the source pipeline. A failing test caught this:
duplicating `main` left it with 0 nodes. Fixed by restricting step 2 to
`get_manual_nodes` only — graduated content is deliberately left alone
(still correctly shared/global) rather than corrupted. **Net effect: v1
duplicate is a no-op for a fully-executed pipeline's own already-graduated
content** — only still-manual/staged wiring gets copied. A real fix would
need per-scope canonical identity for graduated nodes (a bigger redesign,
not attempted here).

---

## Verification (you run these — no Python in my environment)

Backend (from repo root):
```
cd scistack-gui
uv run pytest tests/ -k "pipeline or scope or hypothesis" -v
```

Frontend build + manual check (VS Code extension mode covers both build
targets):
```
cd scistack-gui/frontend
npm run build
```
Then, per this repo's existing practice (no automated frontend tests): open
the GUI, and manually verify per stage —
- Stage 1: tabs render, `main` shows as the first tab, creating/renaming/
  editing hypothesis metadata persists across a reload.
- Stage 2: copy-paste a PathInput node and confirm it still shares the
  same template as the original (editing either changes both); then hit
  "Deep copy" on one and confirm it now has an independent template that
  no longer affects the other.
- Stage 3: select 3+ connected nodes, extract, confirm the canvas now shows
  one submodule node with correct ports, and double-clicking descends into
  exactly those nodes.
- Stage 4: duplicate a hypothesis containing a submodule use; edit a
  constant/schemaFilter on the duplicate only; confirm the original is
  unaffected but both still show the same submodule when descended into,
  and editing the *shared submodule's own* internals shows up in both.

After this plan is approved, I'll also write a copy to
`.claude/plan-hypothesis-tabs-and-submodules.md` per this repo's convention
(every plan doc lives there), and will ask afterward whether to write a
`docs/claude/hypothesis-pipelines.md` conceptual doc once Stage 1 ships, per
this repo's practice of writing that up after implementing something
non-obvious.
