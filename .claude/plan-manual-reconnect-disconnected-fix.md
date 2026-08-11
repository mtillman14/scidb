# Plan: manually reconnecting a disconnected wiring should clear the disconnected state

> **Note:** This file was accidentally overwritten later (2026-08-11) by an
> unrelated planning session and could not be recovered from git (untracked)
> or editor history. This is a best-effort reconstruction from the intact
> retrospective at `docs/claude/scistack-gui-disconnected-wiring-reconnect.md`
> and the actual diff on this branch, written back in "plan" form. Treat the
> docs/claude file as the authoritative account of what was actually built;
> this file exists mainly so the filename the docs file references resolves
> to something.

## The bug

Deleting a function node's required inbound edge (e.g. `RawVO2 -> signal`)
is a GUI-only "hide," never a real delete (project ethos: never delete, mark
hidden — see `pipeline_store.hide_edge`/`get_hidden_edge_ids`). It correctly
marks the node's wiring "disconnected" (🔌 badge, forced red, Run blocked).
But manually wiring a *different* variable onto that same `in__signal`
handle (drag `RawHeartRate -> signal`) did nothing: the badge/red state
never cleared and Run kept failing with `"input 'signal' is disconnected"`,
even though the canvas visibly showed a new edge feeding that input.

## Root cause

Every "is this input disconnected" check —
`graph_builder.hidden_wirings()` (badge + forced-red run state) and
`variant_resolver.filter_disconnected_targets()` (actual execution
eligibility, via `execution_service.derive_fn_targets`/
`derive_target_for_node`) — decided purely from the function's DB-recorded
wiring (`db.list_pipeline_variants()`) crossed against the hidden-edge-id
set. Neither looked at whether a manual edge now supplied that same
`target_handle` with a different variable. Hiding one inbound edge therefore
poisoned that input forever, unless the user reconnected the *exact same*
source (already handled by `layout_service.put_edge`'s `candidate_edge_id`
auto-unhide special case).

## Planned fix

Introduce the concept of **hidden-handle coverage**: a hidden inbound edge
id doesn't by itself say which input param it feeds — reconstruct that
association explicitly, then check whether a live manual edge currently
covers it.

- Add `graph_builder.inbound_edge_candidates_by_handle(fn, wid, input_params,
  const_names, path_names) -> {candidate_edge_id: target_handle}`.
- Add `graph_builder.manual_edge_handle_index(manual_edges) ->
  {(fn_name, wiring_id, target_handle): edge}`, keyed via
  `parse_fn_node_id(edge["target"])` so bare/grouped/scope-placed target ids
  all resolve the same way.
- "Is this wiring disconnected" becomes: for each hidden handle, is there a
  manual edge covering `(fn, wid, handle)`? If every hidden handle is
  covered, the wiring is reconnected; a partial reconnection (e.g. only the
  variable input, not a hidden constant) stays disconnected.
- Wire this into two places:
  1. **Display/run-state** — `hidden_wirings()` takes an optional
     `manual_edges` param; `api/pipeline.py` fetches
     `manual_edges_for_fn_lookup` earlier and threads it through, clearing
     `node["data"]["disconnected"]` and the forced-red state.
  2. **Execution** — `variant_resolver.filter_disconnected_targets()` takes
     `manual_edges`/`manual_nodes`. When covered, don't just re-admit the
     stale DB target (that historical call never ran with the new
     variable) — synthesize a fresh target with the covered handle's
     `input_types` substituted for the manually-wired variable's type (via
     `edge_resolver.node_id_to_var_label`), and drop any stale `call_id` so
     `compute_call_id` recomputes fresh. `derive_fn_targets`/
     `derive_target_for_node` thread `all_edges`/`manual_nodes` through.
     `disconnected_reason()`/`disconnected_report_entries()` get the same
     coverage check for consistent messaging.

## Known limitation accepted going in

`get_hidden_edge_ids(db)` in `execution_service.py` is called with no
`pipeline_id` (global union across scopes). A manual edge in one scope can
in principle "cover" a hidden handle for a same-wiring placement in a
different scope. Not fixed here — see
`docs/claude/scistack-gui-scoped-hidden-state.md`.

## Files touched (per actual diff on this branch)

- `scistack_gui/domain/graph_builder.py`
- `scistack_gui/domain/variant_resolver.py`
- `scistack_gui/services/execution_service.py`
- `scistack_gui/api/pipeline.py`

## Tests

`tests/test_graph_builder.py::TestHiddenWirings` (manual-reconnect cases),
`tests/test_variant_resolver.py::TestFilterDisconnectedTargets`
(substitution cases), `tests/test_api.py::TestDisconnectedEdges`
(end-to-end reconnect/Run cases), `tests/test_pipeline_scopes.py::
TestDeriveTargetForNode` (graduated-node reconnect case).
