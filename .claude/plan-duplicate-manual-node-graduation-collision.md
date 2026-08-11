# Bug: disconnected duplicate function node vanishes on run

## Symptom (user-reported)

Two manual `compute_rolling_vo2` function nodes on the canvas: one wired up
(signal/constants connected) and one left completely disconnected. Running
the wired one causes the disconnected sibling to disappear from the canvas
— even though it was never run and nothing was done to it directly.

## Root cause

Two independent, individually-reasonable pieces of graduation logic combine
badly when **two manual nodes share the same function label** and only one
of them is wired:

1. `graph_builder.merge_manual_nodes` (`scistack_gui/domain/graph_builder.py:1503`)
   matches a manual node to a DB-derived node by `(type, label)` alone. Once
   the wired node runs, exactly **one** DB node named `compute_rolling_vo2`
   exists, so *both* manual placeholders (wired and disconnected) resolve to
   the same single candidate.
2. `api/pipeline.py`'s wiring-conflict validation (`_wiring_conflicts_with_candidate`,
   `api/pipeline.py:186`) deliberately treats "no wiring info yet" as **not**
   a conflict — this is intentional, existing, tested behavior
   (`test_unwired_manual_node_still_graduates_immediately` in
   `tests/test_pipeline_call_sites.py:290`): a single bare, freshly-placed
   node with no edges has no way to prove it's "different," so it graduates
   into the one real call site immediately. That's correct **when it's the
   only manual node with that label**.

Neither check accounts for a **second manual node with the same label also
present**. Both the wired node and the disconnected node pass Pass 1
("not a conflict") and both get a `GraduationAction` pointing at the *same*
`new_id`. `pipeline_store.graduate_manual_node` (`pipeline_store.py:464`)
just deletes the manual DB row for `old_id` — it doesn't create anything at
`new_id` (that node already exists, built from real DB data). So the second
graduation is effectively "delete this manual node, nothing replaces it,"
which is exactly the observed disappearance.

Confirmed by tracing `scidb.log`: at 15:42:44, `merge_manual_nodes` reports
"processing 7 manual node(s) against 5 existing node(s)" → "6 to graduate",
and the final graph has only **1** functionNode where 2 manual function
placeholders existed a moment before.

## Fix (GUI layer only — `scistack-gui`)

Add a target-collision guard in `api/pipeline.py`, after both graduation
passes (Pass 1 reject / Pass 2 promote) have produced the final
`graduations` list, right before executing the side effects (~line 801):

- Group `graduations` by `new_id`.
- If more than one action targets the same `new_id`, it's a collision: keep
  the graduation with actual resolved wiring evidence (non-empty
  `inferred_inputs`/`output_types` — i.e. one that passed Pass 2's explicit
  wiring match) over one that only passed because "absence of wiring is not
  a conflict." If multiple/none have wiring evidence, keep exactly one
  deterministically and demote the rest back into `to_add` so they're
  rendered as their own separate (red, unrun) manual nodes instead of being
  silently deleted.
- Log a warning when a collision is detected and resolved, including which
  node kept the target and which were demoted — this is exactly the kind of
  case that's invisible without a log line, per project convention.

This doesn't touch `merge_manual_nodes`'s candidate-matching (still fine for
the single-manual-node case) or weaken the existing "no wiring info yet
still graduates" UX — it only kicks in when two manual nodes would otherwise
collide on one target.

## Regression test

New test in `tests/test_pipeline_call_sites.py`, alongside the existing
graduation tests: two manual `bandpass_filter` nodes sharing a label, one
wired to `RawSignal` end-to-end (matching an executed call site) and one
left with **no edges at all**. Assert both survive as two separate
`functionNode`s after a graph build — the wired one graduated/green, the
disconnected one still manual/red — mirroring
`test_differently_wired_manual_node_does_not_graduate_or_show_green` but for
the *unwired* sibling instead of a differently-wired one.

## Logging

Existing logging in `merge_manual_nodes` and the pipeline graduation loop
already traces candidate counts and graduation actions in detail (visible in
`scidb.log`) — sufficient to diagnose this. The only addition is the
collision-detected warning described above.
