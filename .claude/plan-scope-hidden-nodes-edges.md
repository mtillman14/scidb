# Plan: scope hidden-node/edge state per pipeline (fix cross-hypothesis delete/re-add bleed)

**Status: implemented (uncommitted).** See "Implementation notes" at the bottom.

## Bug reports
1. Duplicated a hypothesis' pipeline. Deleted a node from the COPY. The node also
   disappeared from the ORIGINAL pipeline.
2. Re-added the same node (unconnected) to the ORIGINAL pipeline. A second copy of
   the node, still wired to its old connections, reappeared automatically in the
   DUPLICATE pipeline too.

## Root cause
`graph_builder.wiring_id()` (scistack_gui/domain/graph_builder.py:173-190) hashes
only `fn_name + input/output shape` — it is entirely scope-independent by design
(so identical, unedited wiring keeps computing to the same real DB data across
hypotheses — this part is correct and intentional per `duplicate_pipeline`'s
docstring). Consequently two hypothesis pipelines with identical wiring compute
the exact same BARE canonical ids: `var__MaxVO2`,
`fn__compute_max_vo2__{wiring_id}`, `e__compute_max_vo2__{wiring_id}__MaxVO2`.

The bug is that "hidden" state for these canonical ids is recorded and read back
GLOBALLY instead of per pipeline scope:

- `_pipeline_hidden_nodes` / `_pipeline_hidden_edges`
  (scistack_gui/pipeline_store.py:100-120) have no `pipeline_id` column.
- `layout.delete_node` (layout.py:312-338) explicitly strips any placement
  suffix and calls `pipeline_store.hide_node(db, bare_id)` — docstring says
  "Hiding is deliberately GLOBAL (not per-placement)".
- `api/pipeline.py::_build_graph(db, pipeline_id)` (api/pipeline.py:351-373) is
  called once per scope, yet fetches `get_hidden_node_ids(db)` /
  `get_hidden_edge_ids(db)` with NO scope filter — so hiding a node in one
  hypothesis hides it in every hypothesis sharing that wiring (bug #1).
- `layout.write_manual_node` (layout.py:251-305) symmetrically calls
  `pipeline_store.unhide_node(db, canonical_id)` globally when a node is
  re-added, resurrecting it (already wired, since the edge-hide entry is also
  global) in every other scope that shares the wiring too (bug #2).

This is entirely a GUI-layer (scistack_gui) issue — scidb/scifor are untouched.

## Fix
1. **Schema**: add `pipeline_id VARCHAR DEFAULT 'main'` to `_pipeline_hidden_nodes`
   and `_pipeline_hidden_edges` (same ALTER-in-`_ensure_tables` pattern already
   used for `_pipelines.hidden`). Composite key becomes (pipeline_id, node_id) /
   (pipeline_id, edge_id) conceptually — `node_id`/`edge_id` alone can no longer
   be the sole PRIMARY KEY.
2. **pipeline_store.py**: `hide_node`, `unhide_node`, `unhide_nodes_by_prefix`,
   `get_hidden_node_ids` and `hide_edge`, `unhide_edge`, `get_hidden_edge_ids`
   all take an explicit `pipeline_id` and scope every read/write to it.
3. **layout.py**: `delete_node(node_id, pipeline_id)` and
   `write_manual_node(..., pipeline_id)` (already has pipeline_id!) thread scope
   into the hide/unhide calls instead of stripping it away.
4. **api/layout.py**: `DELETE /layout/{node_id}` and `DELETE /edges/{edge_id}`
   gain a `pipeline_id` field (mirrors the `pipeline_id` already on
   `PositionUpdate` for `PUT /layout/{node_id}`), defaulting to `"main"` for
   back-compat. `layout_service.delete_layout` / `delete_edge` /
   `put_edge`'s hidden-edge-reconnect check pass it through.
5. **api/pipeline.py::_build_graph**: pass its own `pipeline_id` into
   `get_hidden_node_ids` / `get_hidden_edge_ids` instead of fetching globally
   (api/pipeline.py:370-373).
6. Frontend: send the active tab's `pipeline_id` on the two DELETE calls (it
   already sends it on the PUT calls for the same resources).

## Tests (scistack-gui/tests/)
- `test_pipeline_scopes.py`: duplicate a pipeline with shared wiring, delete a
  node in the COPY, assert the ORIGINAL pipeline's graph is unaffected
  (regression for bug #1).
- Re-add a previously-deleted node in one scope; assert a DIFFERENT scope that
  independently placed the same wiring stays hidden/unaffected (regression for
  bug #2).
- `test_graph_builder.py`: unit-level test that `filter_hidden` /
  `build_edges` only suppress ids hidden in the scope being built.

## Logging
Existing logging already names the scope on every graph-build step. Add one
line each in `hide_node`/`hide_edge`/`get_hidden_node_ids`/`get_hidden_edge_ids`
logging the resolved `pipeline_id`, so a future scope-leak is visible in the
log immediately instead of requiring log archaeology like this investigation.

## Out of scope / follow-up
- `_pipeline_hidden_combos` (pending-constant combo hiding) keeps its
  existing GLOBAL behavior on purpose (unioned into every scope's
  `get_hidden_node_ids` regardless of `pipeline_id`) — same
  scope-independence risk, not implicated in this bug report, worth the
  same treatment in a follow-up.
- The execution/run-readiness path (`execution_service.py`'s
  `derive_fn_targets`, `disconnected_reason`, etc.) still fetches hidden
  ids globally (`get_hidden_node_ids(db)`/`get_hidden_edge_ids(db)` with no
  scope) — unchanged from before this fix. This means canvas rendering can
  now show a function as "connected" for scope X while the actual RUN path
  still treats it as disconnected because of a hide recorded in a
  different scope Y. Not touched here because none of those functions
  currently take a `pipeline_id` at all — scoping them is a materially
  bigger change than this fix and wasn't part of the reported bug.

## Implementation notes (what actually changed)
- `pipeline_store.py`: `_pipeline_hidden_nodes`/`_pipeline_hidden_edges`
  migrated to a composite `(pipeline_id, node_id|edge_id)` primary key
  (DuckDB can't ALTER an existing single-column PK, so `_ensure_tables`
  detects the old schema via a probe `ALTER ADD COLUMN` and recreates the
  table, backfilling existing rows to `'main'`). `hide_node`/`unhide_node`/
  `unhide_nodes_by_prefix`/`hide_edge`/`unhide_edge` take `pipeline_id`
  (default `'main'`); `get_hidden_node_ids`/`get_hidden_edge_ids`/
  `list_hidden_edges` take `pipeline_id: str | None` (`None` = every scope
  unioned, preserving the old global read for not-yet-scoped callers).
  `get_hidden_node_ids` always unions in `_pipeline_hidden_combos` too
  (still global by design, see above).
- Scope is derived from the (already scope-resolved) ids the frontend
  already sends — `domain.scope_filter.node_scope` for node deletes,
  and the edge's `source`/`target` endpoints for edge deletes/reconnects
  — so **no new required frontend fields** were needed for the two
  reported bugs (simpler than the plan's original idea of adding
  `pipeline_id` to the DELETE endpoints).
- `layout.delete_node` / `layout.write_manual_node` (unhide-on-recreate) /
  `layout_service.delete_edge` / `layout_service.put_edge` (reconnect
  unhide) all thread the resolved scope through.
- `api/pipeline.py::_build_graph` passes its own `pipeline_id` into
  `get_hidden_node_ids`/`get_hidden_edge_ids` instead of fetching globally.
- Restore-panel gap found and fixed along the way: `unhide_edge`/
  `get_hidden_edges` (the "restore hidden edges" UI) also needed scope —
  here the frontend DOES already have `currentScope` in hand, so
  `POST /edges/{edge_id}/unhide` and `GET /edges/hidden` gained an optional
  `pipeline_id` field/query param, threaded from `PipelineDAG.tsx`.
- `server.py` (VS Code extension JSON-RPC mode) handlers updated in
  parallel with the FastAPI routes so both frontends stay consistent.

## Follow-up bug found in manual testing (fixed same session)
After the above landed, manual testing found a second, distinct bug in the
same area: duplicate a pipeline to a hypothesis, delete a leaf OUTPUT
variable node in the copy — the function node that PRODUCES it also
disappeared from the copy's canvas (not deleted from the DB, just invisible;
reappeared on refresh only if the position happened to still resolve).

**Root cause**: `graph_builder.filter_hidden` (api/pipeline.py's PRE-grouping
call, before `group_call_sites_by_wiring`) subtracts hidden variable TYPES
out of `agg.fn_outputs`/`agg.fn_input_params` VALUES for every surviving call
site, not just the hidden node's own dict entry. Since `wiring_id()` hashes
`fn_name + input/output var types`, hiding one of a function's own outputs
changed the hash fed into grouping, which changed the function's canonical
node id (`fn__{fn}__{wiring_id}`). The node's saved scope placement/position
was recorded under the OLD id, so `scope_filter._resolve_in_scope` found no
placement for the NEW id in the (non-root) scope and dropped the node from
that scope's view entirely — while the "main" root scope masked the bug by
defaulting unplaced ids to root.

**Fix**: `graph_builder.filter_hidden` gained a `strip_var_type_values: bool
= True` parameter. The pre-grouping call in `api/pipeline.py` now passes
`strip_var_type_values=False` (fn-id-keyed removal, `all_var_types`,
const/path-input hiding still run — only the VALUE-level var-type scrubbing
on `fn_outputs`/`fn_input_params` is skipped), so `wiring_id` is computed
from the function's true recorded shape, unaffected by what the user has
hidden. The existing post-grouping `filter_hidden` call keeps the default
(`True`) — by then the group's identity is already fixed, so stripping
values there only affects displayed ports, safely.

Tests: `test_graph_builder.py::TestFilterHidden` (new
`strip_var_type_values` cases + a direct `wiring_id`-stability regression
test) and `test_pipeline_scopes.py::TestScopedNodeEdgeHiding::
test_delete_output_var_does_not_delete_its_producing_fn` (end-to-end via the
seeded bandpass_filter/FilteredSignal graph).
- Tests: `tests/test_pipeline_store.py::TestScopedHiding` (pure
  pipeline_store-level scoping unit tests) and
  `tests/test_pipeline_scopes.py::TestScopedNodeEdgeHiding` (end-to-end,
  duplicate real seeded wiring + delete/re-add through the HTTP API,
  reproducing both reported bugs).
