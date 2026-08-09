# Plan: Per-Scope Placements for DB-Derived Nodes (the "full rework")

## Context

`duplicate_pipeline` (shipped and committed in `79acaff`) deliberately skips
already-executed ("graduated") DB-derived nodes, because a real test failure
showed that creating a second manual node with the same label in a
different scope causes the *next* graph build to graduate it too — and
since a canonical id (`var__{Type}`, `fn__{fn}__{wiring_id}`,
`const__{name}`, `pathInput__{name}`) has exactly ONE position (one scope)
system-wide today, graduation **transfers** that position rather than
creating an independent copy, silently stealing the node from wherever it
was.

The user wants duplicate (and, more generally, any two pipelines that
happen to compute the same wiring) to each show a fully independent,
correctly-stated graduated node — not one "winning" and the other
permanently stuck as a plain manual placeholder. That requires DB-derived
nodes to support genuine **multi-scope placement**: the same real,
already-computed data can be independently displayed (own run-state,
own variant chips) in more than one pipeline scope at once.

Research already done this session (2 Explore agents, full reads of
`domain/graph_builder.py`, `domain/scope_filter.py`, `api/pipeline.py`'s
`_build_graph`, `services/execution_service.py`, and a frontend grep):

- `wiring_id`/`fn_node_id` (`domain/graph_builder.py:77-136`) are pure,
  scope-blind functions of `(fn_name, input_types, output_types)` — a
  **GUI-only invention**, no backend/scidb counterpart (confirmed via
  `grep -rn wiring_id /workspace/scidb/src` — zero hits). Safe to extend.
- `call_id` (the actual scidb for-each call-site identity,
  `/workspace/scidb/src/scidb/foreach_config.py`) is a **real backend
  concept** embedded in some legacy node ids — must not be reshaped, only
  wrapped in an additional GUI-side string suffix.
- `_build_graph` (`api/pipeline.py:298-752`) builds the ENTIRE node/edge
  graph globally and unscoped (run-states, wiring-grouping, variant chips
  — steps 1-12) and applies scope as the **very last** step,
  `filter_graph_to_scope` (line 719-721). This is exactly where the fix
  belongs — nothing upstream of it needs to change.
- `merge_manual_nodes` (`domain/graph_builder.py:1008-1074`) is called
  **once globally** across every scope's manual nodes simultaneously
  (`api/pipeline.py:572-579`), matching purely on `(type, label)` against
  a **flattened, scope-blind** `saved_positions` dict
  (`api/pipeline.py:564-566`: `for scope_map in positions_by_scope.values():
  saved_positions.update(scope_map)`). This is the exact root cause: two
  manual nodes in different scopes with the same label both see the same
  unclaimed `saved_positions` state and race for the same canonical slot.
- Manual nodes already carry their own `pipeline_id` (`meta["pipeline_id"]`,
  `pipeline_store.get_manual_nodes`) — the scope info needed to fix this is
  already sitting right there, just not being used when picking the
  graduation target.
- `execution_service.py`'s `_scope_function_labels`/`derive_fn_targets`/
  `build_backend_pipeline` resolve everything by **label/function-name**
  against real DB history, never by node id — confirmed zero changes
  needed there beyond a shared parser fix (below).
- Frontend node ids are fully **opaque strings** (grep confirmed zero
  prefix-parsing in `frontend/src`) — safe to change format; no frontend
  changes needed.

## Design: placement-qualified ids

A DB-derived canonical id gets a **placement suffix** identifying which
scope's independent copy it is: `{canonical_id}::{pipeline_id}`, e.g.
`fn__bandpass_filter__ac8254f9::main` vs. `fn__bandpass_filter__ac8254f9::pipe_99c73`.
`::` is safe (never appears in a pipeline_id `main`/`pipe_{hex}` or in a
function/variable/constant label). Manual nodes are untouched — they
already carry `pipeline_id` explicitly and never had this problem.

This is deliberately **not** a new `_node_placements` table or a rewrite
of the position-storage format — `positions_by_scope` (JSON layout file)
can *already* hold the same bare id in two different scope buckets today;
nothing currently stops that at the storage layer. The only things that
collapse two placements into one are (1) the id string itself being
ambiguous/shared, and (2) `merge_manual_nodes`'s flattened, scope-blind
membership check. Fixing both is a **small, surgical, localized** change,
not a structural rework of the position model.

### Stage A — placement-id helpers + one-time migration

- `domain/graph_builder.py`: two new small functions next to
  `fn_node_id`/`parse_fn_node_id`:
  ```python
  PLACEMENT_SEP = "::"
  def placement_id(canonical_id: str, pipeline_id: str) -> str:
      return f"{canonical_id}{PLACEMENT_SEP}{pipeline_id}"
  def parse_placement_id(node_id: str) -> tuple[str, str] | None:
      if PLACEMENT_SEP not in node_id: return None
      bare, _, scope = node_id.rpartition(PLACEMENT_SEP)
      return (bare, scope) if bare else None
  ```
- `layout.py`'s `_load()`: one-time, sentinel-guarded migration (same
  pattern as the existing `positions_scoped` migration at lines 62-76):
  for every `(scope, position_dict)` in `positions`, rewrite any key that
  looks like a DB-derived id (`var__`/`fn__`/`const__`/`pathInput__`
  prefix, per the existing prefix table at `layout.py:238-241`) and does
  NOT already contain `::` into `placement_id(key, scope)`. Flag:
  `"placements_migrated": true`. Existing single-placement documents are
  unaffected in behavior — they just get an explicit scope suffix instead
  of an implicit one.

### Stage B — scope-aware graduation (the actual root-cause fix)

`domain/graph_builder.py`'s `merge_manual_nodes` — minimal change: when a
manual node's label matches exactly one existing canonical node, the
graduation target becomes **that manual node's own placement**, not the
bare canonical id:
```python
if len(candidates) == 1:
    canonical_id = candidates[0]
    target_id = placement_id(canonical_id, meta.get("pipeline_id") or ROOT)
    if target_id not in saved_positions:
        graduations.append(GraduationAction(old_id=node_id, new_id=target_id))
        continue
```
That's the entire fix for the race: two manual nodes in different scopes
with the same label now compute **different** `target_id`s (different
`pipeline_id` suffix), so they never collide — no shared slot to fight
over. `layout.graduate_manual_node` (`layout.py:439-450`) needs **zero**
changes — it already writes the new id into whichever scope bucket held
the manual node's old position, which is already correct.

### Stage C — scope resolution (replaces `filter_graph_to_scope`)

- `domain/scope_filter.py`'s `node_scope`: add a fast, unambiguous path
  before the existing position-scan fallback:
  ```python
  parsed = parse_placement_id(node_id)
  if parsed:
      return parsed[1]
  ```
  (checked after the existing `manual_nodes` lookup, before the
  position-scan fallback which stays as a safety net for any
  not-yet-migrated or edge-case bare id).
- New function (replaces the call to `filter_graph_to_scope` in
  `api/pipeline.py:719`), e.g. `resolve_scope_view(nodes, edges,
  pipeline_id, manual_nodes, positions_by_scope)`: for the ONE requested
  `pipeline_id`, build a `{bare_or_manual_id: resolved_id}` map —
  - a DB-derived node resolves to `placement_id(bare_id, pipeline_id)` if
    that placement exists in `positions_by_scope[pipeline_id]`;
  - else, if the bare id has **no placement anywhere** at all, it
    resolves to itself ONLY when `pipeline_id == ROOT` (preserves today's
    "unplaced defaults to root" behavior exactly for untouched/legacy
    data);
  - else it's not visible in this scope (dropped).
  - manual nodes with `(meta.get("pipeline_id") or ROOT) == pipeline_id`
    map to themselves.
  Rewrite kept nodes' `id` to the resolved id; keep an edge only when
  both endpoints resolve within this scope, rewriting `source`/`target`
  to the resolved ids. This one function is the only real algorithmic
  change beyond Stage B — `filter_graph_to_scope` itself can stay
  (unused by `_build_graph` after this, but leave it for any other
  caller found during implementation — grep confirmed only
  `api/pipeline.py:719` calls it today).
- `domain/scope_filter.py`'s `document_interface`: needs the same
  resolved-view logic for its `scope_nodes` computation (currently keys
  off bare `manual_nodes`/`positions_by_scope` membership directly) —
  factor the shared "what does scope X see" resolution into one helper
  both `resolve_scope_view` and `document_interface` call, rather than
  duplicating the logic.

### Stage D — shared parser fix

`parse_fn_node_id` (`domain/graph_builder.py:82-101`) must strip a
placement suffix before applying its strict 16-hex-char validation:
```python
def parse_fn_node_id(node_id):
    bare, _ = parse_placement_id(node_id) or (node_id, None)
    if not bare.startswith("fn__"): return None
    ...  # existing logic, unchanged, operating on `bare`
```
This is the ONLY change needed in `services/execution_service.py`'s
consumers (`_scope_function_labels` at lines 233/247,
`api/pipeline.py:69`) — they all import this shared function, and since
they only ever use the returned `fn_name` (never the id itself), fixing
the parser once fixes every caller. `_scope_function_labels`'s own
`node_scope(nid, ...) == pipeline_id` check (execution_service.py:236)
already works correctly once Stage C's `node_scope` fast path is in place
— no separate change needed there.

### Stage E — `duplicate_pipeline` reverts to full parity

Now that graduation is scope-safe, `services/scope_service.py`'s
`duplicate_pipeline` can go back to enumerating the FULL resolved graph
(`services/pipeline_service.get_pipeline_graph`, as originally attempted)
instead of only `get_manual_nodes` — already-executed nodes get a fresh
manual copy in the new scope, which now independently and safely
graduates to its own placement. Remove the "deliberately does not touch
graduated nodes" restriction and its docstring; keep everything else
(submodule placements stay shared via `child_pipeline_id`, config/wiring
copied verbatim). Update `test_duplicate_does_not_touch_graduated_nodes_or_corrupt_original`
to assert the NEW correct behavior: duplicating `main` produces an
independent copy with its own placements, AND the original is still
completely unaffected (both true now, not just the latter).

## Explicitly out of scope (flagged, not silently dropped)

- **Hide/delete stays global.** `_pipeline_hidden_nodes`
  (`pipeline_store.py`) has no scope column, and `filter_hidden` runs on
  the global aggregate *before* nodes are even built
  (`api/pipeline.py:368, 409`) — deleting a node from one pipeline's
  canvas today removes it everywhere, and this rework does not change
  that. Making delete per-placement is a separable, smaller follow-up
  (store placement-qualified ids in `_pipeline_hidden_nodes` instead of
  bare ones, move `filter_hidden` to run after `resolve_scope_view`
  instead of before node-building) — not attempted here since it's not
  required for duplicate/run-state correctness, only for full symmetry.
  Flagging so it isn't mistaken for solved.
- PathInput nodes' DB-derived canonical form gets this fix **for free**
  (graduation matching is type-agnostic, so Stage B covers it
  automatically) — no separate work needed, but worth calling out since
  it wasn't explicitly asked for.

## Test impact (real, non-trivial)

Placement-qualified ids change the exact id string of every graduated
node (`fn__bandpass_filter__{wid}` → `fn__bandpass_filter__{wid}::main`).
Prefix-based assertions (`i.startswith("fn__bandpass_filter__")`) keep
working; **exact-match** assertions do not. Known impact:
- `tests/conftest.py`'s `bp_node_id` fixture computes the bare id via
  `fn_node_id(...)` directly — needs a `pipeline_id` parameter (default
  `"main"`) and to return the placement-qualified form.
- `tests/test_pipeline_scopes.py`'s `TestScopedGraph` class (graduation/
  scope-membership tests) needs re-verification against the new id
  format — expect several assertions need updating from exact-match to
  prefix-match, or to compute the expected placement id explicitly.
- `tests/test_graph_builder.py` and `tests/test_pipeline_call_sites.py`
  likely have direct `merge_manual_nodes`/`fn_node_id`/`parse_fn_node_id`
  unit tests that need updating for the new signature/behavior.
- New tests needed: two manual nodes with the same label in different
  scopes both graduate independently (the core regression test for this
  whole effort) — this replaces/extends the corruption test from the
  previous session.

## Verification

```
cd scistack-gui
pytest tests/test_pipeline_scopes.py -v
pytest tests/test_graph_builder.py -v
pytest tests/test_pipeline_call_sites.py -v
pytest tests/test_layout.py -v
pytest tests/ -v   # full suite as a final safety net
```
Plus a manual GUI check per CLAUDE.md convention: duplicate a hypothesis
that has already been run, run the duplicate too, and confirm both show
correct green states independently — this is the scenario the previous
session's fix explicitly could not support.
