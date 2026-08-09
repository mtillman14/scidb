# Per-combo hide/unhide for the constant Cartesian product

## Context

The Sidebar's "Variants" table (`FunctionSettingsPanel.tsx`) shows the full Cartesian product of a function's constant values — e.g. `a=[1,2], b=[2]` → rows `[a=1,b=2], [a=2,b=2]`. Today the only removal mechanism is deleting a whole value from one constant node, which drops *every* row containing that value. The user wants to exclude one specific row (e.g. just `a=1,b=2`, keeping `a=2,b=2`).

Per explicit user correction: this project's ethos is **never delete data**. "Removing" a combo must mean marking it hidden and excluding it from future runs — real DB records are never touched. The user also confirmed (via AskUserQuestion) that a **minimal restore/unhide UI** should ship in this same pass, not be deferred.

Investigation found the pieces mostly already exist:
- `call_id` (`scidb.foreach_config.call_id_from_version_keys`) is a pure SHA-256 hash of a call site's `(fn, inputs, constants, distribute, as_table)` — computable even before a combo is ever run.
- scistack-gui already has a hide-without-delete primitive: `_pipeline_hidden_nodes` + `pipeline_store.hide_node/unhide_node/get_hidden_node_ids`, consumed by `graph_builder.filter_hidden`. It already operates at the exact `(fn_name, call_id)` granularity *before* `group_call_sites_by_wiring` groups combos into one canvas node — so hiding one exact `fn__{fn}__{call_id}` already removes just that one row from an otherwise-visible node's display, with zero DB-record changes. This already works today for already-run combos; it's simply never been wired to a UI for single-row hiding, and never consulted at execution time.

**The one real gap**: `execution_service.py` (`derive_fn_targets`, `derive_target_for_node`, `build_backend_pipeline`) and `api/run.py`'s run thread never consult the hidden-node set at all — hiding is purely a display-layer concept today. Closing that gap is the core of this plan.

## Design decisions

- **New sibling table `_pipeline_hidden_combos`**, not new columns on `_pipeline_hidden_nodes`. The existing table is a tiny, heavily-reused primitive (`hide_node`/`unhide_node`/`get_hidden_node_ids`/`unhide_nodes_by_prefix`, consumed only by `filter_hidden`) — mixing bare whole-node hides with structural combo data into it forces every future reader to learn a second concept. The new table stores the structural `{constant_name: value}` data needed to show a hidden combo back in a restore UI (a SHA-256 hash can't be reversed), and its `hide_combo`/`unhide_combo` wrappers call the *existing* `hide_node`/`unhide_node` primitives internally — no hidden-set logic is duplicated.
- **Call_id computation lives in `scistack_gui/domain/variant_resolver.py`** (pure, no I/O) — already the home for target-list operations (`filter_variants`, `deduplicate_variants`), and `execution_service.py` already imports scidb symbols directly inside functions, so importing `scidb.foreach_config.call_id_from_version_keys` there is consistent, not a new layering pattern. **Already-run combos reuse the real `call_id` DB variant rows already carry — never recomputed.** Only never-run/pending combos need the hash computed fresh.
- **Filtering happens after `apply_pending_overrides`**, not inside `derive_fn_targets`/`derive_target_for_node`. Overrides mutate a target's `constants` in place, which can change its true identity — a hidden-combo check must always reflect the *final* post-override constants, never a possibly-stale `call_id` field left over from before an override touched that target.
- **Scope cut: constants-only in v1**, not multi-type input axes. `derive_fn_targets`'s never-run cross-product only iterates over constants — a multi-type input stays a single unresolved `EachOf`/list on one target, with no per-choice target to compute a call_id for. The hide affordance is disabled (with a tooltip) on any Variants row whose uniqueness comes from an input-type column, not a constant column. Already-run rows aren't blocked by this (real DB history has a real call_id regardless), but the pending-combo path can't support it cleanly, so v1 doesn't either.
- **`distribute`/`as_table` fail safe, not silently wrong.** Two real chokepoints exist (`api/run.py`'s eager per-node Run, and `execution_service.build_backend_pipeline` used by both Run Pipeline and plan preview) and — confirmed by reading the file — **`build_backend_pipeline` never passes `distribute`/`as_table` to `for_each` at all today**, a pre-existing gap unrelated to this feature. Each chokepoint's filter call must use *that chokepoint's own* actual distribute/as_table value (`api/run.py`: the parsed `opt_distribute`/`opt_as_table`; `build_backend_pipeline`: hardcoded `False`/`None`, matching its existing behavior) — never a value borrowed from elsewhere. If a hidden pending combo's stored call_id (computed at hide-time from the node's current config) later drifts from what actually runs, the filter simply stops matching and the combo reappears/runs — it can never mis-hide a *different* combo, since constants/inputs are still part of the hash. This existing `build_backend_pipeline` gap is not being fixed here — out of scope.
- Hide-time lookup of a node's current `distribute`/`as_table` uses `pipeline_store.get_manual_nodes(db).get(node_id, {}).get("config", {})` (no new getter needed — `get_manual_nodes` already returns `config` when present). Note this returns `{}` for already-*graduated* nodes (graduation deletes the manual-node row; there's a separate pre-existing gap where `update_node_config` doesn't upsert for graduated nodes — not this plan's concern), which just means the distribute/as_table estimate defaults to `False`/`None` for those — an acceptable, safe default that matches `build_backend_pipeline`'s own existing default.

## Backend changes (build first, verify with tests, then move to frontend)

**1. `scistack_gui/pipeline_store.py`** — add, right after `get_hidden_node_ids` (~line 837):
- Table in `_ensure_tables`: `_pipeline_hidden_combos(node_id VARCHAR PRIMARY KEY, function_name VARCHAR NOT NULL, variant_key VARCHAR NOT NULL)` — `variant_key` is JSON of `{constant_name: value_str}`.
- `hide_combo(db, node_id, function_name, variant_key: dict)` — calls `hide_node(db, node_id)` then inserts the structural row.
- `unhide_combo(db, node_id)` — calls `unhide_node(db, node_id)` then deletes the structural row.
- `list_hidden_combos(db, function_name) -> list[dict]` — `[{"node_id", "variant_key"}, ...]`.

**2. `scistack_gui/domain/variant_resolver.py`** — add pure functions:
- `compute_call_id(function_name, target, distribute=False, as_table=None) -> str | None`. Builds the version-keys dict (`__fn`, `__inputs`, `__constants`, `__distribute`, `__as_table`) matching `ForEachConfig.to_version_keys()`'s shape exactly (including `__as_table`'s `sorted(...)`-for-lists normalization), calls `scidb.foreach_config.call_id_from_version_keys`. Returns `None` (fail-safe "unknown, don't filter") when an input param is a multi-value list — the v1 scope cut.
- `hidden_call_ids_for_fn(hidden_node_ids: set[str], function_name: str) -> set[str]` — parses `fn__{fn}__{call_id}` ids via `graph_builder.parse_fn_node_id`, keeps only this function's.
- `filter_hidden_targets(targets, function_name, hidden_call_ids, pending_constants, distribute=False, as_table=None) -> list[dict]` — for each target, reuse its real `call_id` only if none of `pending_constants` touched its constants (i.e. it wasn't overridden), else recompute via `compute_call_id`; drop it if the id is in `hidden_call_ids`.
- Rename `_constants_match` → public `constants_match` (one-line, update its one call site in `filter_variants`) — the new hide endpoint needs it too.

**3. `scistack_gui/services/execution_service.py`**:
- New `resolve_combo_call_ids(db, function_name, node_id, variant_key) -> list[str]`: derive targets (`derive_target_for_node` if `node_id` given, else `derive_fn_targets`), apply pending overrides, filter to targets matching `variant_key` via `constants_match`, compute each match's call_id (reusing real `call_id` when present and untouched, else `compute_call_id` using the node's current config for distribute/as_table). Used by the hide endpoint to turn a UI row into the (usually one, occasionally more if multiple outputs share the row) call_id(s) to hide.
- Wire enforcement into `build_backend_pipeline` (~line 447-449): after `targets = apply_pending_overrides(derive_fn_targets(db, fn_label), pending_consts)`, filter via `filter_hidden_targets(targets, fn_label, hidden_call_ids_for_fn(hidden_ids, fn_label), pending_consts, distribute=False, as_table=None)`, where `hidden_ids = pipeline_store.get_hidden_node_ids(db)` is hoisted once above the `for fn_label in ...` loop (not re-fetched per function).

**4. `scistack_gui/api/run.py`** — in `_run_in_thread`, after `opt_as_table` is parsed and before the per-target execution loop, filter `unique_targets` the same way, passing `opt_distribute`/`opt_as_table`.

**5. `scistack_gui/services/layout_service.py`** — add, following `delete_layout`'s self-notifying pattern:
- `hide_variant_combo(db, function_name, node_id, variant_key) -> dict` — calls `execution_service.resolve_combo_call_ids`, then `pipeline_store.hide_combo` for each resulting call_id, then `_notify_dag_updated()`.
- `unhide_variant_combo(db, node_id) -> dict` — `pipeline_store.unhide_combo` + `_notify_dag_updated()`.
- `get_hidden_combos(db, function_name) -> dict` — thin wrapper over `pipeline_store.list_hidden_combos`.

**6. `scistack_gui/api/pipeline.py`** — three new endpoints near the existing pending-constant routes (~line 970), using the `Depends(get_db)` pattern already used elsewhere in this file (`get_pipeline`, and `api/layout.py`'s `put_node_config`) since these need direct DB access:
- `POST /functions/{function_name}/hidden_combos` (body: `{node_id: str | None, variant_key: dict}`) → `hide_variant_combo`.
- `DELETE /functions/hidden_combos/{node_id}` → `unhide_variant_combo`.
- `GET /functions/{function_name}/hidden_combos` → `get_hidden_combos`.

**7. `scistack_gui/server.py`** — mirror as JSON-RPC handlers (`_h_hide_combo`, `_h_unhide_combo`, `_h_list_hidden_combos`), added to the dispatch dict near `put_pending_constant`/`delete_pending_constant`. No separate `notify(...)` call needed (matches `_h_delete_layout`'s pattern — the service layer self-notifies).

**Backend verification point**: run tests below before starting frontend work.

## Frontend changes

**`frontend/src/components/Sidebar/FunctionSettingsPanel.tsx`**:
- On selection, fetch `list_hidden_combos` for the function.
- In the Variants table render, filter out rows whose constant-only subset matches a hidden combo's `variant_key`; add a per-row hide button (disabled + tooltip when the row's uniqueness includes an input-type column, per the v1 scope cut) calling `hide_combo` and locally splicing the row (same idiom as `ConstantSettingsPanel.tsx`'s `removeValue`).
- Add a minimal `"{N} hidden — show"` toggle revealing hidden rows with an "unhide" button calling `unhide_combo`.

No changes needed to `Sidebar.tsx`'s `cartesian()` — it stays fully local; only the settings panel needs the hidden-set overlay, matched structurally (constants dict equality) so the frontend never computes or compares a call_id hash itself.

## Tests

- `tests/test_variant_resolver.py` (pure, no fixtures, matches existing style): `compute_call_id` matches `call_id_from_version_keys` called directly with the same shape; `None` return for multi-type input; `__as_table` list-sorting. `hidden_call_ids_for_fn`. `filter_hidden_targets`, explicitly covering the "target was touched by an override, must recompute rather than trust stale `call_id`" case.
- New `tests/test_pipeline_store.py` (first direct coverage of this module — use the `db` fixture from `conftest.py`): `hide_combo`/`unhide_combo`/`list_hidden_combos` round-trip; confirm `hide_combo` also lands in `get_hidden_node_ids`, and `unhide_combo` removes from both tables.
- `tests/test_api.py`: extend the existing `TestRunEndpoint` (`fake_for_each` monkeypatch capture pattern already used there) with a case that hides a combo then posts `/api/run`, asserting `for_each` is never called with those constants — the direct regression test for the execution-time gap this plan closes.
- A `build_backend_pipeline`/`run_pipeline` test (pattern from `test_endpoints_gui.py`) with a hidden combo, asserting the compiled pipeline excludes it — covers the Run Pipeline / plan-preview path independently from the per-node Run path above.

## Verification

1. Backend: `python -m pytest scistack-gui/tests/test_variant_resolver.py scistack-gui/tests/test_pipeline_store.py scistack-gui/tests/test_api.py scistack-gui/tests/test_endpoints_gui.py -v` (commands to be handed to the user — this environment has no Python).
2. Frontend, manually via the `run` skill: hide a never-run combo row → confirm it disappears from Variants and is skipped by both "Run" and "Run Pipeline"; hide an already-run row → confirm it disappears from the canvas node's variant chips and isn't re-run; use the restore toggle to unhide both → confirm they reappear and run normally again.
