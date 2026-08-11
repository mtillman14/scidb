# Plan: exposed submodule port references (constants + leaf outputs)

## Origin

User report (2026-08-09): extracting a submodule (`rolling_vo2`) lost the
connection between the `RollingVO2` variable node and the downstream
`stat_vo2_summary` function node that stayed on `main`. Root cause (fixed
separately, same session): `extract_to_submodule`'s boundary-edge repair in
`scistack_gui/services/scope_service.py` assumed the *kept* side of a split
edge is always the variable node; it wasn't checking the *moved* side too,
so a moved variable feeding a kept function silently dropped its edge.

Investigating that surfaced a real gap: once nodes move into a submodule,
there's no good way to see or touch two categories of thing from the
parent hypothesis' DAG without descending into the child:

1. **Constants** inside the child — currently invisible from the parent
   entirely. `domain.scope_filter.document_interface` only tracks
   variable-typed edges (`consumed`/`produced`); constants never appear in
   a scope's `inputs`/`outputs`, so `PipelineNode.tsx` never renders a
   port for them.
2. **Leaf outputs** — a child's *true* terminal output variables (produced
   inside, not consumed by anything else inside) are technically already
   connectable via the pipeline node's `out__{label}` handle
   (`document_interface`'s `outputs`), but nothing materializes an actual
   selectable variable node for them by default — you have to manually
   drag a wire out and build one, or descend into the child to click the
   real node (e.g. to open `FunctionSettingsPanel`/plot it).

## What already exists to build on

- **`binding.params`** (`pipeline_store.py`, `_pipeline_uses.binding_json`)
  already lets a *use* (a specific placement of a child pipeline) override
  the child's constants per-placement — this mirrors scidb's
  `Pipeline.bind()` and is exactly a "read/write reference" mechanism for
  constants, just not currently surfaced as a node — only as a compact
  text badge (`bindingSummary` in `ScopeContext.tsx`) on the pipeline node.
  Per-use binding also means two placements of the same child pipeline can
  independently override the same constant — a property any node-based UI
  must preserve (the reference is scoped to the USE, not the child
  pipeline itself).
- **`document_interface`** (`scope_filter.py`) already computes a scope's
  produced variable set (`outputs`). It does NOT currently distinguish
  leaf (terminal, uninspectable-from-outside-without-a-port) outputs from
  outputs that are also consumed by another node inside the same scope —
  today's `outputs` includes both. A new "leaf outputs" computation is
  needed (see Design below).
- **`_pipeline_hidden_nodes` + `filter_hidden`** (referenced in
  [[project_pending_constant_combo_hiding]]) is the existing hide-without-
  delete mechanism already used for per-call-site combo hiding. The same
  table/pattern should back "I don't want to see this reference stub"
  rather than any delete affordance — consistent with
  [[feedback_never_delete_mark_hidden]].

## Design

### Both reference kinds: read-only structurally, distinct rendering

**User has explicitly ruled out delete AND write for exposed leaf-output
reference nodes** — a leaf output is derived data; there is no defined
meaning for "editing" or "removing" it from the parent's DAG. Concretely:
- No delete affordance in the GUI for an output-reference stub. If the
  user wants it out of view, that's the existing hide mechanism (still
  reversible, still visible via an "unhide" list), not a delete.
- No write/edit affordance — the stub is a pure read/inspect surface
  (click to open the same inspector/plot view the real node would show).
- These stubs are auto-generated from `document_interface`'s leaf-output
  set, not independently stored nodes — so "deleting" one isn't even a
  meaningful action against stored state; it would just reappear on next
  graph read. This should be enforced at the derivation layer (never
  written as a real manual node), not merely hidden in the UI.

**Constant references** stay read/write (per original ask) since editing
one already has defined, existing semantics: it writes into that
placement's `binding.params`, identical to what typing into the (currently
text-only) binding editor already does. No new backend write path needed
— only a node-shaped UI surface over the existing `update_use_binding` API.

### Visual/identity distinction from owned nodes

Both reference kinds render as a **new node type** (not `variableNode` /
`constantNode`) — a stub that visually reads as "pointing at" content
owned elsewhere, e.g. dashed border + a small ↦ badge naming the child
pipeline, similar to how `PipelineNode.tsx` already uses a distinct
double-border/purple treatment for placed submodules. Must not be
draggable into a "real" node role (no rewiring its identity, no using it
as a target for unrelated edges) — it is purely: constants -> read/write
one field; leaf outputs -> read/click-to-inspect.

### Computing "leaf" outputs

New pure function alongside `document_interface` in `scope_filter.py`,
e.g. `leaf_outputs(scope_id, ...) -> set[str]`: a produced variable label
is a leaf iff no edge inside `scope_id` (or any of its nested child uses)
consumes it as a `var -> fn` source. This is `produced - consumed_anywhere
_internally`, distinct from today's `document_interface` outputs (which is
just `produced`, unfiltered). Needs its own test coverage (a produced var
that's also consumed internally must NOT show as a leaf; a produced var
consumed only externally/by nothing must show).

### Default visibility + toggle

Auto-materialize (append to the parent scope's rendered graph, not stored
as manual nodes — same "derived, not owned" principle as leaf-output
computation) one reference stub per:
- constant declared anywhere in the child's own scope (not recursing into
  grandchild submodules — matches `binding.params`' own flat shape), and
- leaf output per `leaf_outputs` above,

wired to the pipeline node's `in__`/`out__` port respectively. Default ON;
togglable off per-use (hide, not delete) via the same
`_pipeline_hidden_nodes` mechanism, keyed by a derived id (e.g.
`ref__{use_id}__{const_or_var_label}`) so hiding is stable across graph
rebuilds.

## Open questions for the user before implementation

1. Should constant references only cover the child's OWN constants, or
   recurse into grandchild submodules' constants too (mirrors the
   `binding.params` recursion question — scidb's `Pipeline.bind()`
   semantics should settle this; needs a quick check against
   `scidb/README.md` before assuming).
2. Click-to-inspect on a leaf-output stub — same panel as a real variable
   node (`FunctionSettingsPanel`-adjacent), or a lighter read-only viewer?
3. Confirm the per-use scoping of constant references (two placements of
   the same child pipeline show independently-editable stubs, not a
   shared one) — this follows directly from `binding.params` living on
   the use row, just confirming before build.

## Implementation stages (draft, pending answers above)

1. `scope_filter.leaf_outputs` + tests.
2. Backend: extend the scope graph-read endpoint to append derived
   reference-stub nodes/edges (constants + leaf outputs), respecting
   `_pipeline_hidden_nodes`.
3. Backend: reuse `update_use_binding` for constant-stub writes (no new
   write path — just a new caller).
4. Frontend: new stub node component (read/write constant variant,
   read-only leaf-output variant), toggle-hide action wired to the
   existing hide mechanism, no delete/edit affordance on the output
   variant.
5. Visual + functional check in the GUI: extract a submodule with a
   constant and a leaf output, confirm both appear by default in the
   parent, confirm constant edit round-trips through `binding.params`,
   confirm output stub has no delete/edit UI.

Not started — this file is the plan only, per the user's request to draft
it now and implement later.
