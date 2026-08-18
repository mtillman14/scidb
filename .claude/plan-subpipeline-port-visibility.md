# Feasibility: manual show/hide of subpipeline ports (to-do #9)

Correction to my earlier framing: this is not a one-time "settle the shape"
decision — it's a live toggle the user flips at any time by right-clicking
a node inside the subpipeline's own canvas and choosing "show/hide outside
pipeline." This doc plans that feature against the actual current code
(the `scistack-gui-backend-internals.md` doc in `docs/claude` is stale —
it predates nested pipelines and describes a different port model; ignore
it for this feature).

## How subpipeline ports work TODAY (verified in source)

`domain/scope_filter.py::document_interface(scope_id, ...)` is a **pure,
fully-automatic** function, recomputed on every graph fetch — nothing about
today's ports is stored:

- Walks every edge in the whole document.
- `consumed` = variable TYPES with an edge into a function node inside
  `scope_id`.
- `produced` = variable TYPES with an edge out of a function node inside
  `scope_id`.
- Recurses into nested `uses` (a used pipeline's inputs join `consumed`,
  its outputs join `produced`) so a sub-sub-pipeline's ports bubble up.
- Returns `{"inputs": sorted(consumed - produced), "outputs": sorted(produced)}`.

`scope_service.build_pipeline_nodes` calls this per `use` row and hands
`inputs`/`outputs` straight to the frontend as `PipelineNodeData.inputs`/
`.outputs`. `PipelineNode.tsx` renders **one handle per array entry** —
`in__{typeName}` / `out__{typeName}` — directly off those arrays. So the
dots the user sees on a pipeline node ARE this array, with no filtering
step anywhere today.

**Key implication: ports are keyed by variable TYPE, one dot per type**,
not one dot per function-parameter or per internal node. If two different
functions inside the subpipeline both consume `EMGData`, there is still
only ONE `in__EMGData` dot on the outside — the model has no finer
resolution than that today.

Two consequences worth knowing before deciding scope:
- **Outputs over-expose today.** `outputs = produced` unconditionally —
  a variable that's produced AND immediately consumed inside (a pure
  intermediate) still gets an external output dot. This is very likely
  the actual clutter driving the original to-do ("clean up sub-pipelines
  a bit").
- **Bindings aren't port-validated.** `update_use_binding`'s only
  validation is a whitelist of the binding dict's top-level keys
  (`key_map`/`params`/`iterate`), not the port names themselves. So
  hiding a port cannot corrupt an existing binding — nothing needs
  migrating there.

## The one real design fork: granularity

**Option A (recommended): keep type-level granularity, toggle from the
variable node.** Since a variable node is already exactly 1:1 with a
type, right-clicking it and choosing "show/hide outside pipeline" maps
perfectly onto the existing one-dot-per-type model — no data model
change beyond adding a filter step. Right-clicking a function node's
specific input dot would, under this option, resolve to "the type wired
to that dot" and toggle the SAME type-level flag (so if two functions
share a type, hiding via either one hides the single shared dot for
both — there's only one dot to hide either way).

**Option B: per-edge granularity — one dot per internal wiring, not per
type.** Lets two functions consuming the same type independently expose
or hide "their" copy of it. This does NOT fit today's model at all — it
would mean a pipeline node can show *multiple* `in__EMGData` dots
simultaneously, which changes `PipelineNodeData` (array of `{type,
edge_id}` instead of `string[]`), changes how a parent wires INTO those
dots (today one dot = one type = one thing to connect; multiple same-type
dots need distinguishing labels), and changes `build_backend_pipeline`'s
execution-time resolution of which internal edge a given external wire
feeds. Substantially bigger — new wiring semantics, not just a visibility
filter.

I'm recommending **Option A** — it's additive (a filter on an existing
pure function, described below) rather than a new wiring primitive, it
matches "one of the dots... show/hide" literally when read as "the dot for
this type," and it directly fixes the over-exposed-outputs clutter that's
almost certainly the real pain point. Flagging this explicitly because
it's a real fork, not a detail — **confirming this before I build is the
open question below.**

## Design (assuming Option A)

**Storage** — new table in `pipeline_store.py`, mirroring
`_pipeline_hidden_edges` exactly (same composite-key/migration pattern):

```sql
CREATE TABLE _pipeline_hidden_ports (
    pipeline_id VARCHAR NOT NULL DEFAULT 'main',
    direction   VARCHAR NOT NULL,   -- 'input' | 'output'
    var_type    VARCHAR NOT NULL,
    PRIMARY KEY (pipeline_id, direction, var_type)
)
```

Three functions alongside `hide_edge`/`unhide_edge`/`get_hidden_edge_ids`:
`hide_port(db, pipeline_id, direction, var_type)`,
`unhide_port(db, pipeline_id, direction, var_type)`,
`get_hidden_ports(db, pipeline_id) -> {"input": set[str], "output": set[str]}`.

**Domain logic** — `document_interface` gains a `hidden_ports` param
(dict of the same shape, keyed by scope — same call shape as the existing
`uses_by_parent`/`positions_by_scope` maps it already threads through).
At the end of each scope's own computation (before recursing further),
filter that scope's `inputs`/`outputs` against `hidden_ports.get(scope_id,
{})`. Because every recursive call filters its OWN scope before returning,
a sub-sub-pipeline's hides are already baked into what bubbles up to its
parent — no special-casing needed for the recursive `uses` case.

**Service/API** — `scope_service.pipeline_interface` and
`build_pipeline_nodes` fetch `ps.get_all_hidden_ports(db)` once (mirroring
how `uses_by_parent` is prefetched) and thread it through. New endpoints
`hide_port`/`unhide_port` in `api/scopes.py`, wired through
`server.py`'s `_HANDLERS` and `api.ts`'s route table (the three-places
rule from `scistack-gui-frontend-architecture.md`).

**Frontend** — `PipelineDAG.tsx`'s `onNodeContextMenu` (today gated to
`node.type === 'functionNode'` for "Run until here") extends to also fire
for `variableNode`, carrying the node's type label. The context menu
gains a "Hide outside pipeline" / "Show outside pipeline" item (label
flips based on current state — needs the scope's hidden-ports set fetched
alongside `hiddenEdges`, same pattern already in this file) that calls
`hide_port`/`unhide_port` then `bumpGraph()`.

**No separate restore panel needed** — unlike hidden edges/nodes (which
stop rendering the thing itself, so a restore list is the only way back),
here the internal variable node stays fully visible on its own canvas at
all times; only its OUTWARD dot disappears. Un-hiding is just: right-click
the same always-visible node again. This is simpler than the existing
hidden-edges UX, not an extra surface to build.

**Restricting where the menu item appears**: only meaningful outside the
root scope (root is never itself a pipeline node anywhere, so hiding its
ports is a no-op) — I'd hide the menu item at root for clarity, though
it'd be harmless either way.

## Known consequence, deliberately not guarded against

Hiding a type that's genuinely required (consumed inside, produced
nowhere inside) strands that need — nothing downstream can feed it from
outside anymore, and the run will fail with a missing-input error same as
today's "disconnected wiring" case. I'm not proposing a block on this
(matches the project's general "reversible, not restrictive" pattern —
same reasoning as hidden edges/nodes), but it's worth you knowing before
sign-off: a hidden required input fails loud at run time, not silently.

## Effort shape

- Backend: one new table + 3 store functions (near-copy of the
  hide_edge/unhide_edge/get_hidden_edge_ids trio) + a filter step in one
  pure function + 2 new endpoints through the usual 3 layers. Small,
  closely tracks an existing pattern.
- Frontend: extend one context-menu handler, one new menu item, one new
  fetched set (mirrors `hiddenEdges` state already in `PipelineDAG.tsx`).
  Small-medium.
- No changes needed to bindings, execution/`build_backend_pipeline`, or
  the export-to-Python design doc (`gui-export-to-plain-python.md`) — all
  three already treat `document_interface`'s output as the source of
  truth for "what's connectable," so they inherit the filtering for free.

## Decision (2026-08-13)

**Option A confirmed** — type-level granularity, one shared dot per
variable type, toggleable from any node wired to that type. Design above
is final; ready to implement as scoped.

## Status: BUILT (2026-08-13)

Implemented exactly as designed above, all four layers plus frontend:

- **Storage** — `_pipeline_hidden_ports` table + `hide_port`/`unhide_port`/
  `get_hidden_ports`/`get_hidden_ports_by_scope` in `pipeline_store.py`,
  same shape as planned.
- **Domain** — `document_interface` gained the `hidden_ports` param,
  threaded through the recursive `uses` call, filtered at the very end
  against `hidden_ports.get(scope_id, {})`.
- **Service/API** — `scope_service.pipeline_interface`/`build_pipeline_nodes`
  fetch `get_hidden_ports_by_scope` once and pass it through; new
  `scope_service.hide_port`/`unhide_port`/`get_hidden_ports`; new REST
  endpoints `GET/POST .../hidden-ports`, `.../hide-port`, `.../unhide-port`
  in `api/scopes.py`, wired through `server.py`'s `_HANDLERS` and
  `api.ts`'s route table.
- **Frontend** — `PipelineDAG.tsx`'s `onNodeContextMenu` now also fires for
  `variableNode` (restricted to non-root scopes), with a new context-menu
  block offering "Hide/Show as input port" and "Hide/Show as output port"
  (label flips on current `hiddenPorts` state), calling `hide_port`/
  `unhide_port` then `bumpGraph()`. No restore panel needed, per the
  design above — un-hiding is the same right-click toggle.
- **Tests** — `tests/test_pipeline_scopes.py`: `TestHiddenPorts` (store-level
  hide/unhide/get roundtrip, idempotency, per-scope keying) and
  `TestHiddenPortsFiltering` (API-level: hidden-ports endpoint state,
  input/output suppression from `/interface` and the placed pipeline
  node's ports, confirms the internal node stays visible on its own
  canvas, confirms a hide on one scope doesn't leak into another scope's
  own report). Not yet run — handed to the user per project convention.

No changes were needed to bindings, `build_backend_pipeline`, or the
Python/MATLAB export design — all three already treat `document_interface`
as the source of truth and inherit the filtering for free, as anticipated.
