# Plan: prevent cycles in the pipeline DAG canvas

## Diagnosis

Manual edges (the only kind of edge a user can freely add) travel this path with **no cycle
check anywhere**:

```
PipelineDAG.tsx onConnect (line 333)
  -> callBackend('put_edge', {edge_id, source, target, source_handle, target_handle})
  -> server.py _h_put_edge (line 324)
  -> layout_service.put_edge (layout_service.py:95)
  -> pipeline_store.write_manual_edge (pipeline_store.py:401) -> raw upsert into _pipeline_edges
```

- No `isValidConnection` prop on the `<ReactFlow>` canvas, so the drag is never blocked
  client-side.
- `onConnect` also never `.catch()`s the backend call (unlike `onNodesDelete`, which rolls
  back optimistic state on failure — PipelineDAG.tsx:322-326), so even a backend rejection
  today would leave a dangling edge drawn on screen.
- This is the *only* place a cycle can be introduced. The other edge type in this codebase,
  `_pipeline_uses` (pipeline-as-node nesting), already rejects cycles at creation
  (`pipeline_store.add_pipeline_use`, reachability BFS via `_uses_reachable`,
  pipeline_store.py:581-619, raises `ValueError`, tested in
  `test_pipeline_scopes.py:239 test_cycle_rejected_direct_and_transitive`). DB-derived
  (data-lineage) edges are structurally acyclic — they reflect already-executed function
  calls. So `_pipeline_edges` (manual wiring) is the one gap.
- Nothing catches this today until actual execution: `scidb`'s `Pipeline._topo_order`
  (Kahn's algorithm, `scidb/src/scidb/pipeline.py:778`) raises `PipelineCycleError` if no
  step is ever "ready" — correct, but a confusing failure far downstream of where the user
  made the mistake.
- No core-layer (scifor/scidb) DAG/graph concept exists to hook into — the canvas
  node/edge/DAG abstraction is a `scistack-gui`-only invention (confirmed against
  scistack/README.md and scifor/README.md, and consistent with
  `plan-placement-qualified-node-ids.md`'s note that node ids here have "no backend/scidb
  counterpart"). So per project convention, this fix belongs entirely in `scistack-gui`.

## Fix — two layers, both in scistack-gui

### A. Backend — authoritative guard

1. New pure helper in `domain/graph_builder.py`:
   `find_cycle(edges: list[dict], new_source: str, new_target: str) -> list[str] | None`
   — BFS from `new_target` over existing `source`/`target` edges; if `new_source` is
   reachable (or `new_source == new_target`), return the cycle path for a useful error
   message, else `None`.
2. Wire into `services/layout_service.put_edge`: before calling
   `pipeline_store.write_manual_edge`, fetch existing **manual** edges only
   (`layout_store.read_manual_edges()`, excluding this same `edge_id` in case it's an
   upsert) and run `find_cycle`. On a hit, `raise ValueError(...)` — mirrors
   `add_pipeline_use`'s existing raise/message style, propagates through the existing RPC
   error path unchanged (`_respond_error` / `HTTPException(400)`, both already preserve the
   raw message verbatim to the frontend).
3. Add `logger.warning(...)` at the rejection point (source, target, cycle path).

**Revised scope (post-implementation correction):** the original plan called for checking
against the *full* combined graph (DB-derived + manual, via
`services.pipeline_service.get_pipeline_graph`), reasoning that a manual edge could close a
loop through pre-existing DB-derived lineage that a manual-edges-only check would miss.
**That path was reverted** — `get_pipeline_graph` (→ `api/pipeline.py`'s `_build_graph`) is
not a pure read: it *persists* manual-node graduation as a side effect
(`layout_store.graduate_manual_node`, `api/pipeline.py:738`). Calling it mid-request, before
a freshly-wired manual node's edges are all in place, graduated nodes prematurely on
incomplete wiring and broke 6 unrelated tests (duplicate-pipeline, extract-to-submodule,
document-interface, derive-target-for-node — all sequences that build up a manual node's
wiring edge-by-edge). The check now covers manual edges only, same as
`add_pipeline_use`'s existing precedent (which also only checks its own edge type). A cycle
closed purely through immutable, already-executed DB-derived edges plus one new manual edge
is an accepted, documented gap — it still surfaces at run time as scidb's
`PipelineCycleError`, just not as immediately as the common case. Revisiting this later
would require extracting a genuinely pure edge-computation path out of `_build_graph`
(everything up to, but not including, `merge_manual_nodes`/graduation).

### B. Frontend — instant UX guard

1. Add `isValidConnection` to `<ReactFlow>` in `PipelineDAG.tsx` doing the same
   self-loop + reachability check, purely client-side, over the already-rendered `edges`
   state (the same DB-derived+manual, scope-resolved list currently on screen). Rejects the
   drag before `onConnect` fires — no round trip, no flicker. This is the standard
   ReactFlow pattern for this exact case.
2. Fix `onConnect`'s currently fire-and-forget `callBackend('put_edge', ...)` — add
   `.catch(err => { window.alert(...); setEdges(prev => prev.filter(e => e.id !== edgeId)) })`,
   mirroring the rollback pattern already used in `onNodesDelete` (PipelineDAG.tsx:322-326).
   This is defense-in-depth for anything the client-side check can't see (e.g. a concurrent
   edit from another tab).

### C. Tests

1. `graph_builder.find_cycle` unit tests (new or alongside `test_graph_builder.py`):
   self-loop, direct 2-node cycle, transitive N-node cycle, and a mixed case (existing
   DB-derived edge + new manual edge closing the loop).
2. `layout_service.put_edge` / API-level test confirming a rejected cycle surfaces as
   `ValueError` / HTTP 400 with `"cycle"` in the message — mirrors
   `test_pipeline_scopes.py:414 test_cycle_and_binding_validation_are_400`.
3. No frontend test framework exists in this repo (checked: no vitest/jest config anywhere
   under `scistack-gui/frontend`). The `isValidConnection` client-side check is therefore
   UX-only and not covered by an automated test — flagged as an accepted gap, not proposing
   to stand up a frontend test harness as part of this fix unless requested.

## Known gap

A cycle closed purely through existing DB-derived data-lineage edges plus one new manual
edge (no other manual edge involved) is not caught at connect-time — only at run time, as
scidb's `PipelineCycleError`. See "Revised scope" under A above.
