# Plan: function inputs are built from edges, never from name matching

Date: 2026-08-25
Status: **IMPLEMENTED, uncommitted. Python tests not yet run by the user;
`tsc --noEmit` clean and the frontend bundle is rebuilt.**

Triggered by a real GUI session (`examples/vo2max/scidb.log`, runs
`6ila96uv` / `9lt11d5m`): a `pd.read_csv` node wired to a `test_pi`
PathInput ran with `inputs={}` and produced zero records, leaving both it
and `cpet_data_raw` red while reporting `success=True`.

## The decision (user, 2026-08-25)

**Name matching is not how inputs are built. Inputs are built entirely
from edges.** No fallback, no compatibility shim — beta, so this is a
clean break (`feedback_beta_no_deprecation`).

## Why the current design fails

`build_run_inputs` resolves by *elimination*: whatever signature params
variable/constant resolution left unfilled are looked up by name in the
PathInput/Parameter registries, which are keyed by **declared** name. The
canvas edge — which is the only thing that actually says which parameter a
node feeds — is never consulted.

So `test_pi → read_csv` cannot resolve: `read_csv` has no parameter named
`test_pi`. The docstring already states this as a rule ("a PathInput/Sweep
meant to fill a param here must be named the same as that parameter"). It
is being reclassified from a limitation to a defect.

Two other layers already do it correctly and disagree with the execution
path:

- `matlab_command_service.py:184-207` maps `pathInput__X → in__param` off
  the edge handle.
- `graph_builder.candidate_edge_id:1626` states outright that "a
  PathInput's declared name and the function parameter it fills can
  differ", and `build_edges:1329-1353` encodes **both** names in the
  DB-derived edge id for exactly that reason.

The execution path is the odd one out.

## Inventory — every non-edge inference to remove

| # | Location | What it guesses |
|---|---|---|
| A | `execution_service.py:809` | PathInput by signature-param-name match |
| B | `execution_service.py:820` | Parameter/Sweep by signature-param-name match |
| C | `edge_resolver.py:142-148` | Handle-less edges → remaining sig params **by position** |
| D | `edge_resolver.py:128` | Unrecognized-handle Parameter edge → source node's label |
| E | `edge_resolver.py:87-141` | No `pathInput__` branch exists at all |
| F | `execution_service.py:91` | `constants_registry[cname]` with a *param* name |
| G | `execution_service.py:712` | `hidden.get(param_name)`; store is keyed by declared name |
| H | `matlab_command_service.py:184`, `:451` | Two hand-rolled copies of the edge scan |

**Variables** are already edge-based for the param→class mapping (via
`node_id_to_var_label` on the edge source, or scidb history which records
the class per param). Their only guess is **C**.

Deliberately **out of scope** (they key by declared name for
display/export/source-scanning, where the declared name IS the identity):
`layout_service`, `portability_service`, `code_export_service`,
`pipeline_discovery`.

## Where the param→declared-name mapping comes from

Both sources already exist; neither is a new concept.

1. **Never-run wirings** — the manual edge's `targetHandle`
   (`in__{param}`), with the source node id giving the declared name.
2. **Previously-run wirings** — `db.get_aggregated_variants()["path_inputs"]`
   is keyed by **param name** and carries the spec;
   `graph_builder.convert_scidb_path_inputs:545` already resolves spec →
   declared registry name (including via the D7 history table). Its
   `"functions"` field is `set[(FnKey, param_name)]`, i.e. exactly the
   `(fn, call_id) → param_name` mapping needed.

This matters: without (2), removing the name-match would break
source-declared pipelines that have already run and have no manual edge.

## Design

### 1. `ResolvedEdges` carries the declared name, not just the param name

`edge_resolver.resolve_function_edges` gains two fields:

```python
path_input_params: dict[str, str]   # param_name -> declared PathInput name
parameter_params:  dict[str, str]   # param_name -> declared Parameter name
```

- New `pathInput__` branch (**E**): source prefix `pathInput__` +
  `in__{param}` handle → `path_input_params[param] = pi_name`
  (`strip_placement` first — the log shows both `pathInput__test_pi` and
  `pathInput__test_pi::main` in one session).
- The Parameter branch stops collapsing two namespaces into one
  `constant_names` set. A `param__{declared}` handle (DB-derived,
  `build_edges:1319`) and an `in__{param}` handle (hand-drawn) are
  recorded as *param name* + *declared name* separately.
- **C** and **D** are deleted. An input edge with no usable handle is
  dropped with a WARNING naming the edge id, source, and target — it is
  not guessed at.

`constant_names` stays (callers use it) but is derived from
`parameter_params` rather than being the primary product.

### 2. Targets carry the bindings

`derive_fn_targets` / `derive_target_for_node` attach
`path_input_params` / `parameter_params` to each returned target:

- inferred targets → straight from `ResolvedEdges`;
- DB-history targets → from `convert_scidb_path_inputs`, selecting the
  entries whose `functions` contains this target's `(fn, call_id)`.

**Risk to check, not assume:** `wiring_id` is computed from
`input_types`/`output_type` only, so extra keys must not perturb it —
but `deduplicate_variants` and `filter_hidden_constant_value_targets`
both consume target dicts and need verifying against the wider shape.

### 3. `build_run_inputs` binds from the target, by elimination no more

The `missing = [...]` block (**A**, **B**) is deleted. Instead:

```python
for param, pi_name in target["path_input_params"].items():
    inputs[param] = path_inputs_by_name[pi_name]
for param, decl_name in target["parameter_params"].items():
    inputs[param] = _apply_hidden_values(params_by_name[decl_name], decl_name, ...)
```

A declared name absent from the registry logs WARNING and is skipped
(declaration deleted from source since the edge was drawn).

**F**: `_infer_wired_constants` takes `parameter_params` and looks up the
registry by declared name, keeping the value keyed by param name for
`target["constants"]` (which is what scidb records).

**G**: `_apply_hidden_values` is called with the **declared** name, so it
matches the checkbox store. Fixes a latent bug: today, unchecking a value
on a Parameter node whose declared name differs from the param it feeds
silently does nothing.

### 4. `matlab_command_service` (**H**)

Both copies of the edge scan are replaced by the shared
`resolve_function_edges` result (`feedback_avoid_scifor_scidb_duplication`).

## Logging (CLAUDE.md NOTE 2)

The session's whole failure was invisible: `inputs={}` was logged, and
nothing said why.

- `build_run_inputs` logs at INFO the full binding it built
  (`param -> declared_name (kind)`) and at **WARNING** for any signature
  param left unbound while the node has an incoming edge on that handle.
- **WARNING** when a run completes with `total=0` combos — a run that did
  nothing should never look like a clean success.
- `resolve_function_edges` logs at WARNING for each dropped handle-less
  edge (the C/D deletions).

## Tests (CLAUDE.md NOTE 2)

1. PathInput whose declared name ≠ the param it feeds resolves via the
   edge (the exact `test_pi → read_csv` case from the log).
2. Same for a Parameter (`test → in__sep`).
3. A previously-run source-declared pipeline with **no manual edge**
   still resolves, via `convert_scidb_path_inputs` — the regression the
   removed name-match would otherwise cause.
4. Name coincidence alone no longer resolves: a PathInput named exactly
   like a param, with no edge, produces no input and WARNs.
5. Handle-less edge is dropped + WARNs instead of being positionally
   assigned (C).
6. Unchecking a value on a Parameter whose declared name ≠ param name
   actually filters (G).
7. `matlab_command_service` emits the same param mapping as the shared
   resolver for both its call sites.

## Not part of this plan (found in the same session, listed so they
## aren't mistaken for this bug)

- The edge landed on `in__dtype_backend`, not `in__filepath_or_buffer`:
  `api/pipeline.py:935` emits a handle for every one of `read_csv`'s ~50
  signature params, so the handles are stacked ~4px apart and React Flow
  snapped to a neighbour. Needs its own fix (collapse unwired optional
  params behind a disclosure, or make the handle set configurable).
- `examples/vo2max/src/scistack_entities.py`: `test_pi`'s `root_folder`
  is `examples/vo2max/vo2max`, which does not exist — the data is in
  `examples/vo2max/data/`. Its template's second key is `{trial}` while
  the DB's schema keys are `['subject', 'session']`. Both must be fixed
  to get an end-to-end green run to verify against.

---

## What was actually built (2026-08-25)

### Files changed

- **`domain/edge_resolver.py`** — `ResolvedEdges` swaps `constant_names:
  set` for `path_input_params`/`parameter_params: dict[str, str]`
  (`{param_name: declared_name}`). New `pathInput__` branch; the `sig_params`
  argument is gone along with positional matching; handle-less input edges
  are dropped with a WARNING naming the edge id, source, target and handle.
- **`domain/graph_builder.py`** — added `PATH_INPUT_ID_PREFIX`, so the
  PathInput prefix is a named constant like `PARAM_ID_PREFIX` rather than a
  literal repeated across layers.
- **`services/execution_service.py`** — new `_db_path_input_params` /
  `_attach_db_path_inputs` (the DB-history binding source) and
  `_inferred_targets` (one shared product, replacing two identical copies in
  the two derivation functions). `_infer_wired_constants` now takes
  `parameter_params` and looks the registry up by DECLARED name.
  `build_run_inputs`' resolve-by-elimination block is deleted.
- **`api/pipeline.py`** — two `resolve_function_edges` call sites updated.
- **`services/matlab_command_service.py`** — both hand-rolled edge scans
  replaced by shared `_fn_node_ids` / `_resolve_matlab_wiring` /
  `_collect_edge_path_inputs`; `_collect_sweep_params` reuses the same.
  Roughly 60 lines of duplicated scanning removed, and the two generators
  now agree with the Python execution path by construction.
- **`api/run.py`** — WARNING when a run completes having executed zero
  combinations.
- **`frontend/.../FunctionNode.tsx`** — parameter handle id `const__{c}` →
  `param__{c}` (see below). Rebuilt: `static/assets/index-BnlsfHW5.js`.

### The frontend handle-id bug this surfaced

`FunctionNode.tsx` rendered parameter handles as `const__{name}` while
`PARAM_ID_PREFIX` — and the `targetHandle` `build_edges` writes on every
DB-derived Parameter edge — is `param__{name}`. A leftover from the D6
Constant+Sweep→Parameter merge.

It was invisible because `resolve_function_edges`' removed fallback treated
an unrecognized handle as "use the source node's label", which is correct
only when the declared name and the parameter name coincide. Deleting the
fallback would have turned this latent mismatch into silently-dropped
wiring, so the id is now the real one. Pinned by
`TestHandleIdsMatchTheFrontend`, which asserts the .tsx source uses
`PARAM_ID_PREFIX` — the drift is otherwise unobservable from either side
alone.

**Consequence, accepted (beta, no migration):** a manual Parameter edge
stored with a `const__` handle no longer resolves. It now WARNs with the
edge id and asks for a reconnect, rather than binding by a name guess.

### Tests

New: `test_edge_resolver.py` — `TestResolveFunctionEdgesParameters` (7),
`TestResolveFunctionEdgesPathInputs` (4), `TestHandleIdsMatchTheFrontend`
(2), plus two rewritten handle-less-edge cases.
`test_execution_service.py` — `TestDbHistoryPathInputBinding` (3).
`test_pipeline_scopes.py` — `TestEdgeDrivenBinding` (4, including the
verbatim log scenario and the wrong-handle case), plus new
name-coincidence / differing-name / deleted-declaration /
hidden-value-by-declared-name cases.
`test_matlab.py` — `TestCollectEdgePathInputs` (3) and a rewritten
`TestCollectSweepParams` (6).

Updated for the handle requirement (they wired input edges with no
`target_handle`, relying on positional matching): `test_execution_service.py`,
`test_code_export.py`, `test_matlab_pipeline_execution.py`, and four sites in
`test_pipeline_scopes.py`. Interface/extract/duplicate tests were checked and
left alone — `document_interface` reads edges directly and never used
`resolve_function_edges`.

### Verification status

- `tsc --noEmit` clean; `npm run build` succeeded.
- LSP diagnostics clean on every changed Python file.
- **Python tests NOT run** (`feedback_user_runs_tests`). Command:
  `pytest scistack-gui/tests -x -q`

## Follow-up from the first test run (2026-08-25)

Six failures. Four were test-side; two were real.

**Real — the hidden-value filter had the same declared-vs-parameter bug one
layer deeper (G, second half).** `_apply_hidden_values` was fixed, but a
WIRED Parameter never reaches it: `_infer_wired_constants` materializes every
declared value into its own target, so the value arrives as a **scalar in
`constants`, keyed by the PARAMETER name**, and is filtered by
`filter_hidden_constant_value_targets` instead — which compared
`hidden_values` (declared name) against `constants` (param name) directly.
When the two differed, unchecking a value matched nothing and ran anyway.
Now translated via the target's `parameter_params`. Three cases added to
`test_variant_resolver.py`, one end-to-end in `TestEdgeDrivenBinding`.

This is worth remembering as the shape of the whole class of bug: **any code
comparing a name against `constants` must ask which of the two namespaces it
is holding.**

**Real — my own test asserted the wrong shape**, which is what surfaced the
above. A wired Parameter is fanned out at derivation (N scalar targets), not
handed to `for_each` as one `EachOf`. Both routes exist and produce the same
runs; the doc now has a table distinguishing them, because reading either
code path alone suggests the other doesn't exist.

**Test-side — a stub `db` too thin for the code under test.** The
`TestDbHistoryPathInputBinding` fake implemented only
`get_aggregated_variants`, but the path also reads the D7 history through
`pipeline_store`. Replaced with `monkeypatch.setattr` on the real
`populated_db` rather than growing the stub into a second, drifting
implementation of the store.

**Test-side — three more handle-less input edges** in
`test_pipeline_call_sites.py` and `test_pipeline_scopes.py`
(`test_compile_gives_each_sibling_wiring_its_own_step`,
`test_manual_node_graduates_after_running_despite_shared_label_ambiguity`).
Both fed `bandpass_filter`'s `signal` positionally. Worth noting the failure
signature: a dropped input edge changes the computed `wiring_id`, so the
symptom was "the manual node won't graduate" and `KeyError: 'signal'` — not
anything that named an edge.

### Second test run — one failure, one more real inconsistency

`test_unchecking_a_value_filters_a_differently_named_parameter` failed
`{5, 10} == {10.0}`: the declared values are **ints**, and the test hid
`'5.0'`. The surface fix would have been to hide `'5'` — but the reason the
mismatch was possible at all is that **the two hidden-value filters used
different matching rules**:

- `_apply_hidden_values` used `_is_hidden_value`, which deliberately matches
  a value against BOTH its int and float spelling (added earlier for exactly
  this reason);
- `filter_hidden_constant_value_targets` used a naive
  `str(value) in hidden`.

`/api/layout.py`'s `ParameterCreate.values` is `list[float | int | str |
bool]` and preserves the distinction on purpose (its own comment says so),
so the same checkbox worked on one route and silently did nothing on the
other, decided only by whether the value was written `5` or `5.0`.

Fixed by moving the matcher to the pure domain layer as
`variant_resolver.is_hidden_value` and using it in both. `execution_service`
imports it; the stale comment in `api/layout.py` now points at the new home.

**Both real bugs in this change's two test runs were the same shape** — one
concept (a Parameter value; a Parameter name) represented two ways, with a
translation missing at one of the two places that needed it. Worth checking
for a third whenever another route to execution is added.
