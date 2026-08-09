# Plan: Deletable edges with idempotent state/execution ("disconnect" a wiring)

## Problem (restated after investigation)

1. `PipelineDAG.tsx:392-401` blocks Delete/Backspace for any edge that
   isn't a manually-drawn one (`manual__` prefix) — which is nearly every
   edge on a real canvas, since DB-derived edges (variable→function,
   function→variable, constant→function, pathInput→function) are rebuilt
   fresh from DB variant data on every fetch and there was no persistence
   layer to make a deletion stick.
2. Deleting/hiding an edge must be more than cosmetic: deleting the edge
   from a required input into a function must make that function (and
   everything downstream) turn red **and become un-runnable**, and
   reconnecting the *exact same* source must make it green again —
   recomputed fresh from real DB state, not from any cached "previous
   color". Connecting a *different*, never-before-used source should stay
   red (unconfirmed) but remain runnable.

Investigated and confirmed: `run_state` (`domain/run_state.py`) and
execution (`services/execution_service.py`) both derive purely from DB
history (`fn_input_params`/`fn_outputs`/DB freshness checks via
`scihist.check_node_state`) and are **completely independent of the
rendered edge list** — `_build_graph` even computes run_states *before*
`build_edges` runs. So "hide an edge" as pure rendering would have zero
effect on color or runnability. This plan wires a new "disconnected
wiring" concept through both.

## Core concept: disconnected wirings

A DB-derived inbound edge id (`e__{var_type}__{fn}__{wid}`,
`e__{const_name}__{fn}__{wid}`, `e__{param_name}__{fn}__{wid}`) already
deterministically encodes `(fn_name, wiring_id)` — `wiring_id` is a pure
SHA-256 hash of the function's *variable* input/output types only
(`graph_builder.wiring_id`), **not constants** — this is why the existing
"wiring grouping" design already puts every constant-value variant of the
same variable wiring in one canvas node. That fact does exactly what's
needed for the constant-input example: hiding a `const__sample_interval →
compute_rolling_vo2` edge does not change the wiring hash, so re-drawing
the *same* connection reproduces the *same* candidate edge id — and
connecting a structurally different source (different `const__` name, or
different variable type) produces a *different* candidate id, which was
never hidden, so it's treated as a genuinely new/unconfirmed wiring
instead (already reds itself out naturally via existing DB-history-empty
behavior — no new code needed for that half).

New pure helper, `graph_builder.hidden_wirings(fn_input_params,
fn_outputs, fn_constants, path_inputs, hidden_edge_ids) -> set[(fn_name,
wiring_id)]`: for every function call site, reconstructs its candidate
inbound edge ids (var/const/pathInput → fn) the same way `build_edges`
does, and returns the `(fn_name, wiring_id)` pairs that have at least one
such id in the hidden set. This is the single source of truth consumed
by both state and execution below. Output-edge (fn→var) hiding is
explicitly excluded from this set — confirmed as cosmetic-only.

## Backend changes (scistack-gui layer only)

### 1. `pipeline_store.py` — hidden-edges table (mirrors hidden nodes/combos)
- `_pipeline_hidden_edges (edge_id PK, source, target, source_handle,
  target_handle)`.
- `hide_edge`, `unhide_edge`, `get_hidden_edge_ids`, `list_hidden_edges`.

### 2. `graph_builder.py`
- `build_edges(..., hidden_edge_ids)`: skip appending an edge whose id is
  hidden, at each of the 4 construction points.
- `hidden_wirings(...)` (new, described above).
- `wiring_disconnected_fkeys(fn_input_params, fn_outputs, wirings) ->
  set[FnKey]`: maps the wiring set back to raw pre-grouping call-site
  keys, for feeding `propagate_run_states`.
- `candidate_edge_id(source_id, target_id) -> str | None`: reconstructs
  the deterministic DB-derived edge id from a bare `(source, target)`
  node-id pair (uses `parse_fn_node_id`/`strip_placement`, already
  exported) — no hash recomputation needed since `wiring_id` is already
  embedded in the function node's own id. Returns `None` for pairs that
  aren't a recognized DB-derived category (i.e., a genuinely new manual
  connection).

### 3. `domain/run_state.py`
- `propagate_run_states(..., disconnected_fkeys: set[FnKey] | None =
  None)`: forces `fn_own_state[fkey] = "red"` for members of this set
  (after the existing pending-constant downgrade, before the fixed-point
  DAG loop) — the existing propagation loop already cascades that
  redness downstream through `var_state`, no new cascade logic needed.

### 4. `domain/variant_resolver.py` — execution-side filtering
- `filter_disconnected_targets(targets, function_name, disconnected_wirings)`:
  same shape as the existing `filter_hidden_targets`/`hidden_call_ids_for_fn`
  pair (which already does this exact job for hidden combos) — drops any
  target whose recomputed `wiring_id(function_name, v["input_types"],
  {v["output_type"]})` is in `disconnected_wirings`.

### 5. `services/execution_service.py`
- `derive_fn_targets` / `derive_target_for_node`: apply
  `filter_disconnected_targets` to `fn_variants` before returning, same
  seam `build_backend_pipeline` already uses for hidden combos — this
  single change blocks the per-node "▶ Run" button (`start_run` →
  `derive_target_for_node`), "Run until here", and "Run endpoints"
  uniformly, since they all bottom out here.
- Pre-flight validation surfaced through the run report: before
  compiling, compute `run_states` + `disconnected_wirings` the same way
  `_build_graph` does, and inject a per-function "skipped: input 'X'
  disconnected" entry (direct) or "skipped: upstream unavailable"
  (cascaded, using the already-computed red set) into the run/plan
  report for anything in the requested scope that would otherwise
  silently vanish from the compiled pipeline. Exact integration point
  into `pipe.last_run_report` / `plan_pipeline`'s entry list to be
  finalized against scidb's `Pipeline` API during implementation — the
  data (which functions are blocked and why) is already fully known from
  the above.

### 6. `api/pipeline.py::_build_graph`
- Fetch `hidden_edge_ids` alongside `hidden_ids`. Compute `hidden_wirings`
  from the pre-grouping `agg`, then `wiring_disconnected_fkeys`, and pass
  into `_compute_run_states` → `propagate_run_states`. Pass
  `hidden_edge_ids` into `build_edges`.
- Function node data gains a `disconnected: bool` flag (from the same
  `hidden_wirings` set) so the frontend can distinguish "plain stale red,
  click Run" from "disconnected red, reconnect first" without
  re-deriving it client-side.

### 7. `services/layout_service.py` + `api/layout.py`
- `delete_edge`: `manual__` edges hard-delete as today; everything else
  now calls `hide_edge` (currently silently no-ops).
- `put_edge` (→ `onConnect`): before writing a new manual edge, compute
  `graph_builder.candidate_edge_id(source, target)`. If it matches a
  currently-hidden id, call `unhide_edge` instead of creating a
  redundant manual edge — this is what makes reconnecting the *exact
  same* nodes idempotent: the original DB-derived edge id comes back,
  state recomputes fresh next graph fetch, no manual-edge residue.
- New endpoints: list/unhide hidden edges (restore-list affordance for
  edges the user forgot they hid).

## Frontend changes

1. **`PipelineDAG.tsx:392-401`**: remove the DB-derived block; forward
   every edge removal to `delete_edge` (with source/target/handles from
   local state) and to `onEdgesChangeBase`; `bumpGraph()` on backend
   failure (mirrors `onNodesDelete`'s existing failure handling).
2. **`FunctionNode.tsx`**: read the new `disconnected` flag.
   - Visually distinguish disconnected-red from stale-red (e.g. a broken-
     link glyph or dashed border on top of the existing red styling).
   - `handleRun`/the "▶ Run" button: still calls `start_run` as today —
     the backend now returns the clear per-function error from the
     pre-flight check above instead of silently doing nothing; surface
     that error in the run log the same way other run failures show up.
3. **Restore UI**: small "N hidden edges" panel mirroring the existing
   hidden-combos restore list in `FunctionSettingsPanel.tsx:340-385`.
4. **`api.ts`**: route `delete_edge` (updated payload), `unhide_edge`,
   `get_hidden_edges`.

## Tests (mandatory per project NOTE 2)

- **`tests/test_pipeline_store.py`**: hide/unhide/list round-trip for
  edges (mirrors the existing `TestHiddenCombos` class).
- **`tests/test_graph_builder.py`**:
  - `build_edges` excludes hidden ids per category.
  - `hidden_wirings` / `wiring_disconnected_fkeys` correctly identify
    affected call sites for var/const/pathInput hides, and correctly
    exclude fn→var (output) hides.
  - `candidate_edge_id` round-trips against `build_edges`' own id
    construction for all 4 categories, including a placement-qualified
    target.
- **`domain/run_state.py` tests**: a disconnected fkey forces red
  regardless of its own DB state, and cascades to dependents; a pending
  constant on a disconnected fkey stays red (disconnect wins).
- **`domain/variant_resolver.py` tests**: `filter_disconnected_targets`
  drops only the matching wiring's variants, leaves other wirings of the
  same function name untouched.
- **`tests/test_api.py`** (end-to-end):
  - Delete a DB-derived input edge → target function (and a downstream
    consumer) report red in `GET /api/pipeline`; reconnecting the exact
    same source/target restores green, matching pre-delete state exactly.
  - Connecting a *different*, never-run source stays red but is not
    flagged `disconnected`.
  - `start_run` on a disconnected node returns the clear error instead of
    silently no-op'ing; a manual edge delete still hard-deletes as today.

## Explicitly out of scope (per your answers)

- Hiding a function→variable (output) edge: cosmetic only, no state or
  execution effect.
- No silent skip on run — a disconnected function always surfaces an
  explicit per-function error in the run report, never a quiet omission.
