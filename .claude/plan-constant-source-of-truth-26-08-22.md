# Plan: Constants as source-of-truth in the GUI

Date: 2026-08-22

## Progress

- **Phase 1 (backend item 1, `build_constant_nodes` source-value merge):
  DONE**, uncommitted. `graph_builder.build_constant_nodes` takes
  `source_values`; `api/pipeline.py:624` wires
  `registry.get_constants_registry()` in. Tests in
  `test_graph_builder.py::TestBuildConstantNodes`.
- **Phase 2 (backend item 2, persisted include/exclude storage): DONE**,
  uncommitted. New `_pipeline_hidden_constant_values (pipeline_id,
  const_name, value)` table in `pipeline_store.py`, pipeline-id scoped from
  the start (unlike `_pipeline_hidden_combos`, which stayed globally scoped
  as a deferred follow-up). `pipeline_store.hide_constant_value` /
  `unhide_constant_value` / `list_hidden_constant_values`; parallel
  `layout_service` wrappers; FastAPI endpoints `POST`/`DELETE
  /constants/{name}/hidden_values/{value}` + `GET
  /constants/hidden_values`; JSON-RPC handlers in `server.py` for the VS
  Code extension. Tests in
  `test_pipeline_store.py::TestHiddenConstantValues`. **Not yet wired
  anywhere** — nothing calls these yet; that's item 3 (execution filtering)
  and items 4-5 (frontend). Investigated `execution_service.
  resolve_combo_call_ids`/`variant_resolver.constants_match`: hiding by
  content-match on already-derived targets (no call_id hashing needed) is
  how the existing `hide_combo` mechanism actually resolves "combos that
  have never run" (via `derive_fn_targets`'s pending-merge fallback) — item
  3 should likely reuse that same content-match pattern rather than a new
  hashing scheme.
- **Phase 3 (execution_service.derive_fn_targets/derive_target_for_node
  filtering): DONE**, uncommitted. Used the content-match approach found
  while investigating Phase 2 (no call_id hashing): new
  `variant_resolver.filter_hidden_constant_value_targets(targets,
  hidden_values)` drops any target whose `constants` dict contains a
  hidden `(name, value)` pair. Wired into `execution_service.
  derive_fn_targets` and `derive_target_for_node` at every return point (a
  new `_hidden_constant_values(db)` helper fetches
  `pipeline_store.list_hidden_constant_values(db, None)` — union-all-scopes,
  matching `get_hidden_node_ids`'s fail-open convention — once per
  derivation call), so it covers the per-node Run path (`api/run.py`),
  pipeline Run/compile path (`build_backend_pipeline`, via
  `derive_target_for_node`), and code/MATLAB export (same function).
  Covers both previously-run (real DB history) and never-run
  (pending/inferred) combos, since both are already materialized as target
  dicts with a concrete `constants` dict by the time this filter runs — no
  separate "not yet materialized" case needed. Tests:
  `test_variant_resolver.py::TestFilterHiddenConstantValueTargets` (pure)
  and new `test_execution_service.py` (integration, via `populated_db` for
  the previously-run case and a manual-edge-wired never-run wiring for the
  inferred-value case).
  - **Known open edge case, not handled**: `apply_pending_overrides` (called
    by `build_backend_pipeline`/export services AFTER `derive_target_for_node`
    already filtered) can change a target's constants post-filter — a
    constant that's both hidden AND has a pending override could
    theoretically slip through or get wrongly excluded. Left alone as an
    unlikely, self-contradictory user state; worth revisiting if it
    surfaces in practice.
- **Phases 4-6 (frontend): DONE**, uncommitted.
  - Closed a naming mismatch found while wiring the frontend: Phase 2's
    JSON-RPC handlers (`server.py`) used `params["const_name"]` while the
    REST path param (and every other constant endpoint) uses `name` —
    changed the JSON-RPC handlers to `params["name"]` so `callBackend`'s
    single params object works identically over both transports.
  - `api.ts`: added `hide_constant_value`/`unhide_constant_value`/
    `list_hidden_constant_values` REST routes (JSON-RPC side already
    existed from Phase 2).
  - `graph_builder.build_constant_nodes`: new `hidden_values` param — every
    value row now always carries a `checked` bool (`value not in
    hidden_values.get(const_name, set())`), not just when hiding is in
    play, so the frontend never has to special-case a missing field.
    `api/pipeline.py`'s `_build_graph` fetches
    `pipeline_store.list_hidden_constant_values(db, pipeline_id)` (scoped
    to the request's actual pipeline_id — display, unlike execution, IS
    scope-aware) and passes it through.
  - `PipelineDAG.tsx`: removed the `checked: true` hardcode (the
    "Current gaps to close" item from the top of this plan) — now passes
    the backend's `checked` through, defaulting only if a value somehow
    omits it.
  - `ConstantNode.tsx`: `toggleValue` now optimistically flips local state
    AND fires `hide_constant_value`/`unhide_constant_value` in the
    background (errors logged, not surfaced — a `dag_updated` broadcast
    from the backend call reconciles either way). Added an `is_current_source_value`
    badge ("src" pill) next to the matching row.
  - `Sidebar.tsx`'s `cartesian()`: confirmed no change needed — it already
    reads whatever `values` the backend sends and doesn't filter by
    `checked` (the Variants preview table intentionally still shows hidden
    rows; only execution excludes them, per Phase 3).
  - Verified with `tsc --noEmit` and `npm run build` (both clean) — no
    Python test additions needed here (no new pure/testable backend
    logic beyond the `hidden_values` param, covered by new
    `test_graph_builder.py` cases).
  - **Not verified**: haven't run the dev server / clicked through the
    actual browser UI. Recommend the user does a manual pass: uncheck a
    value, confirm the checkbox survives a refresh, confirm a Run then
    skips it.

## Problem

Per the "source code is truth, DB is run history" decision (already applied to
PathInput and Sweep), editing a `scidb.constant(...)` value in source and
refreshing does not surface the new value in the GUI. PathInput and Sweep
already behave correctly.

## Root cause

All three kinds are discovered identically by `registry._scan_module_constants`
/ `_scan_module_path_inputs` / `_scan_module_sweeps`
(`scistack-gui/scistack_gui/registry.py:498-527, 555-582, 610-630`), which
populate live in-memory registries on every code refresh. The divergence is
downstream, in `api/pipeline.py`'s `_build_graph`:

- **Sweep**: node values are read straight from
  `registry.get_sweeps_registry()` on every request
  (`api/pipeline.py:613-618`) — no DB involved.
- **PathInput**: `registry.get_path_inputs_registry()` is merged against DB
  history by content match (`api/pipeline.py:427-431`,
  `graph_builder.convert_scidb_path_inputs` /
  `seed_undiscovered_path_inputs`) — the *displayed* value always comes from
  the live registry object.
- **Constant**: `build_constant_nodes` (`graph_builder.py:868-896`) only
  takes `const_counts` (DB run history) and `pending_constants` (a
  user-typed staging table, `_pipeline_pending_constants` in
  `pipeline_store.py`). `registry.get_constants_registry()` is never
  consulted anywhere in this path (`api/pipeline.py:624`). So a source edit
  updates the in-memory registry but nothing ever reads it for constant node
  display.

## Decisions (confirmed with user)

1. Editing a Constant's value in source and it being new (not already an
   existing DB-recorded or pending value) creates a new variant row, shown
   automatically in the GUI node — no manual "add value" step required, the
   way PathInput/Sweep already auto-update.
2. A value that disappears from source but has DB run history **stays
   visible** in the node — the DB is the record of what was actually run,
   and source-code edits must never cause a historical row to vanish.
3. Per-value checkboxes (already rendered in `ConstantNode.tsx`) are the
   include/exclude UI: unchecking a value excludes every combo (Cartesian
   product row / `call_id`) containing it from future runs, without
   deleting anything, per [[feedback_never_delete_mark_hidden]].

## Current gaps to close

- `ConstantNode.tsx`'s checkbox state is **not persisted** —
  `PipelineDAG.tsx:133-141` force every value's `checked` to `true` on every
  load, so today's checkbox is session-only UI theater, not a real
  include/exclude control.
- `execution_service.derive_fn_targets` pulls `db.list_pipeline_variants()`
  directly and does not consult any hidden/excluded state
  (see [[project_pending_constant_combo_hiding]]) — even if we persist
  "unchecked", nothing stops that combo from actually running.
- No existing concept of "this value is the current source-declared value"
  vs. "this value is old DB history" vs. "this value is user-staged
  pending" — the merge needs to tag rows so the frontend can distinguish
  them (e.g. a small "source" badge).

## Design

### Backend

1. **`graph_builder.build_constant_nodes`**: add a `source_values:
   dict[str, str]` parameter (constant name → current registry value,
   stringified) built from `registry.get_constants_registry()` at the
   `api/pipeline.py:624` call site, mirroring the PathInput/Sweep merge
   pattern. For each constant, if the current source value isn't already in
   `const_counts` or `pending_constants`, append it as a new row tagged
   `"is_current_source_value": true`. Existing DB-history rows are left
   untouched (satisfies decision #2 automatically — nothing removes them).
   Log at INFO when a new source value is merged in (name + value), per the
   project's logging-on-issues convention.
2. **Persisted include/exclude state**: extend the existing hide-without-delete
   mechanism (`_pipeline_hidden_nodes` / `call_id`-keyed hiding, see
   [[project_pending_constant_combo_hiding]]) to a new granularity: hiding a
   *constant value* means hiding every `call_id` whose version-key hash
   includes that `(const_name, value)` pair — computable up front via the same
   deterministic `call_id_from_version_keys` hashing used for pending combos,
   so it works even for combos that have never run. Store as
   `(pipeline_id, const_name, value)` rows in a new or extended table; expose
   `hide_constant_value` / `unhide_constant_value` / `list_hidden_constant_values`
   endpoints, parallel to `hide_combo`/`unhide_combo`.
3. **`execution_service.derive_fn_targets`**: filter out any call_id implied
   by a hidden constant value (closes the gap flagged in
   [[project_pending_constant_combo_hiding]]) so excluded values are actually
   skipped on Run, not just hidden from display. This applies to both the
   per-node Run and pipeline Run paths.

### Frontend

4. **`ConstantNode.tsx`**: `checked` must be initialized from the persisted
   hidden-constant-value state returned by the backend, not hard-coded to
   `true` in `PipelineDAG.tsx:133-141`. Toggling a checkbox calls the new
   hide/unhide-constant-value endpoint (optimistic update, same pattern as
   `FunctionSettingsPanel.tsx`'s existing hide-row toggle).
5. Add a small visual marker (badge/dot) on rows where
   `is_current_source_value` is true, so users can tell "this is what source
   currently says" apart from historical DB rows and user-staged pending
   rows.
6. `Sidebar.tsx`'s `cartesian()` needs no change — it's already generic over
   whatever `values` the backend sends.

## Tests / logging (per project convention)

- `test_graph_builder.py`: new test that a constant with a fresh registry
  value (not in `const_counts`/`pending_constants`) produces an extra row
  tagged `is_current_source_value`; a test that removing the value from the
  registry (simulating a further source edit) leaves prior DB-history rows
  intact.
- `test_pipeline_store.py` (or new): hide/unhide constant value persists and
  is idempotent.
- `test_execution_service.py`: `derive_fn_targets` excludes call_ids implied
  by a hidden constant value, for both never-run and previously-run combos.
- Frontend: checkbox initial state reflects backend-provided hidden state,
  not a hardcoded `true`.

## Open sub-decisions to resolve during implementation

- Exact schema/table name for persisted hidden-constant-values (new table
  vs. extending `_pipeline_hidden_nodes`'s existing shape).
- Whether "current source value" badge should also appear on PathInput/Sweep
  nodes for consistency, or is Constant-only (out of scope unless asked).

## Files likely touched

`scistack-gui/scistack_gui/domain/graph_builder.py`,
`scistack-gui/scistack_gui/api/pipeline.py`,
`scistack-gui/scistack_gui/pipeline_store.py`,
`scistack-gui/scistack_gui/services/execution_service.py`,
`scistack-gui/scistack_gui/services/variant_resolver.py` (if pending-merge
logic needs the same call_id-hiding awareness),
`scistack-gui/frontend/src/components/DAG/ConstantNode.tsx`,
`scistack-gui/frontend/src/components/DAG/PipelineDAG.tsx`,
`scistack-gui/frontend/src/components/Sidebar/FunctionSettingsPanel.tsx`
(pattern reference / possibly shared hide-toggle logic),
`scistack-gui/tests/*`.
