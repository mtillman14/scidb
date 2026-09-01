# The MATLAB Output-Handle Contract

Companion to [matlab-output-name-vs-variable-type.md](matlab-output-name-vs-variable-type.md),
which establishes that MATLAB **output parameter names** (`loaded_data`) and
scidb **variable types** (`RawEMG`) are two distinct name spaces that must never
be conflated.

This note covers the part that doc does not: the **third** participant, edges,
and the machinery that translates between the name spaces for them. Three pieces
of code independently decide what an output handle is called, and if any two
disagree the canvas silently loses a wire.

## The three participants

For a MATLAB function node with one output, all three of these must agree on one
string:

| Producer | Where | Emits |
|---|---|---|
| The **node's** output handles | `graph_builder.build_function_nodes` | `out__{param}` — MATLAB signature order, param names |
| The **edge's** `sourceHandle` | `graph_builder.build_edges` | `out__{param}` if `matlab_param_to_class` has an entry, else `out__{Class}` |
| The **frontend** handle ids | `frontend/src/components/DAG/FunctionNode.tsx` | renders one handle per `data.output_types` entry |

Python function nodes are not affected: they use class names directly for both
handles and edges, so the fallback is already correct for them. The mismatch is
MATLAB-specific because MATLAB is the only language where the handle name and the
variable type differ by design.

## `matlab_param_to_class` is the translator

`build_edges` cannot name a handle on its own — it knows the output *class*
(`RawEMG`) but the node renders the *param* (`loaded_data`). The bridge is
`matlab_param_to_class`: `{fn_name: {param_name: class_name}}`, built once per
graph build in `api/pipeline.py` and passed to both builders.

It has **two independent sources**, merged with DB first and edges filling gaps:

1. **DB variants' `output_num`** — the 0-based position of the output in the
   function signature, recorded in `_invocation_output` and surfaced through
   `provenance_query.pipeline_variants` → `get_aggregated_variants`. Combined
   with `matlab_output_order[fn]` (the parsed signature) this yields
   `names[output_num] → output_type`.
2. **Manual edges** — a canvas edge from the fn node carries the param in its
   `sourceHandle` (`out__loaded_data`) and the class via its target
   (`var__RawEMG`). This is `infer_manual_fn_param_to_class`.

**When both come up empty, `p2c = {}`, and the node/edge disagree.** That is the
entire failure mode.

## Why the failure is invisible

React Flow **silently drops** an edge whose `sourceHandle` names no handle on its
source node. No console error, no warning, no fallback rendering — the wire is
simply not drawn.

Meanwhile `run_state.propagate_run_states` works on **node ids, not handles**, so
it still walks the edge, still finds the producer, and still marks the output
variable green.

The user-visible result is the confusing part: *the function appears disconnected
from an output variable that is demonstrably green.* Every backend signal says
"connected"; only the picture disagrees. It is easy to misread as a layout or
state bug rather than a handle-naming bug.

## The placement-id rule

`infer_manual_fn_param_to_class` matches an edge to a function by set membership:

```python
if strip_placement(edge.get("source", "")) not in fn_ids:
    continue
```

The `strip_placement` call is load-bearing, and its absence caused a real bug on
2026-09-01. Node ids come in two forms:

- **bare / canonical** — `fn__loadDelsysEMGOneFile__076c46199b238a69`, what
  `graph_builder.fn_node_id()` returns
- **placement-qualified** — `fn__loadDelsysEMGOneFile__076c46199b238a69::main`,
  the same wiring *placed* on a specific pipeline scope

Callers assemble `fn_node_ids` from mixed sources (`fn_node_id()` returns bare;
manual-node keys and edge endpoints may carry a suffix), so **an exact `==` or
`in` comparison between them is always a latent bug**. `strip_placement`'s own
docstring states the rule:

> For every ad-hoc `var__`/`param__`/`pathInput__`/`fn__` prefix-parser that only
> ever wants the bare id (never the scope), call this FIRST.

This is now enforced centrally by `edge_resolver.bare_fn_node_ids()`, which all
three `fn_node_ids` consumers in that module route through
(`resolve_function_edges`, `infer_manual_fn_output_types`,
`infer_manual_fn_param_to_class`). Do not reintroduce a raw membership test.

### Why it only breaks *after* the first successful run

This is what made the bug hard to see. A never-run function's manual edge names
the *manual* node id, which is in `fn_node_ids` verbatim, so matching works.

Then the first run succeeds and **graduation** rewrites the edge's endpoints onto
the DB-derived node ids via `pipeline_store.rename_edge_endpoints` — in the
placement-qualified form. From that moment the exact match fails.

Note the manual edge is **not deleted**. `drop_superseded_manual_edges` hides a
superseded manual edge from the response but leaves the row in the DB ("hide,
never delete"). So the mapping data was still on disk the whole time; only the
*lookup* stopped finding it.

## Worked example (2026-09-01 log)

Two graph builds three seconds apart, around one MATLAB run of
`loadDelsysEMGOneFile` (signature output `loaded_data`, wired to `RawEMG`):

| | 17:10:30 | 17:10:33 |
|---|---|---|
| edges | 4 (2 DB-derived, 2 manual) | 2 (2 DB-derived, 0 manual) |
| `have no declared param mapping` | absent | **present**, `matlab_param_to_class={}` |
| node handle | `out__loaded_data` | `out__loaded_data` |
| edge `sourceHandle` | `out__loaded_data` | **`out__RawEMG`** |
| rendered? | yes | **no** |
| `RawEMG` run state | green | green |

At 17:10:30.835 graduation rewrote the manual edge endpoints to
`fn__loadDelsysEMGOneFile__076c46199b238a69::main`. On the next build,
`infer_manual_fn_param_to_class` no longer matched it, source 1 had contributed
nothing, and `p2c` was empty.

## The invariant, and where it is enforced

> **Every edge's `sourceHandle` must exist among its source node's rendered
> output handles.**

Tested by `scistack-gui/tests/test_graph_builder.py::TestMatlabOutputHandleInvariant`,
which builds nodes and edges from the same inputs and asserts agreement — rather
than testing either side alone, since either side drifting produces the bug.
Placement normalization is tested by
`test_edge_resolver.py::TestPlacementQualifiedEndpoints`, including a negative
case asserting normalization did not widen matching across different call sites.

## Diagnostics

`api/pipeline.py` logs the translator at INFO, attributed per source:

```
[pipeline] matlab_param_to_class: fn=%s from_db_output_num=%s from_manual_edges=%s merged=%s
```

An empty `merged` is the precondition for the disappearing edge. The two source
fields say which half failed — this was previously logged at DEBUG showing only
the empty result, which is why the cause had to be re-derived from scratch.

`graph_builder`'s orphan warning now names the consequence and both handle sets:

```
[graph_builder] matlab fn=... : DB variants [...] have no declared param mapping
(matlab_param_to_class={}) — its output edge(s) will target handle(s) ['out__RawEMG']
while this node renders ['out__loaded_data'], and will not render
```

## Open question

Source 1 (DB `output_num`) should have produced `loaded_data → RawEMG` on its own
even with the edge lookup broken, and it did not. `output_num` is recorded in
`_invocation_output` and survives `get_aggregated_variants`, so either it is
`None` for MATLAB batch saves or `matlab_output_order[fn]` was empty/too short to
index. The INFO logging above now reports both cases explicitly; one GUI-driven
MATLAB run will settle it.

Until then, treat the manual-edge source as **load-bearing rather than a
fallback**, and be wary of any change that assumes source 1 covers MATLAB
functions.

## Rules of thumb

- Comparing node ids? `strip_placement` first — or better, use
  `edge_resolver.bare_fn_node_ids()`.
- Adding a consumer of `matlab_param_to_class`? Assume it can be empty and make
  the degraded behavior *visible*, not silent.
- Changing either handle producer? Change both, or the invariant test will fail —
  which is the point.
