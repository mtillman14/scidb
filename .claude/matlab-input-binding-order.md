# Plan: MATLAB function-node inputs are dropped and bound in the wrong order

## Symptom (2026-09-02, scidb.log)

`filterDelsys(loaded_data, config, Fs)` was wired on the canvas to three
inputs — the `RawEMG` variable (output of `loadDelsysEMGOneFile`), Parameter
`delsys_config`, Parameter `delsys_sampling_frequency`. At the breakpoint only
two arguments arrived, and they were shifted:

```
argument 1 (loaded_data) <- 2000        (the sampling frequency)
argument 2 (config)      <- the config  (correct by luck)
argument 3 (Fs)          <- <missing>
```

The log states it exactly:

```
14:18:36 generate_matlab_command: fn=filterDelsys, total_variants=3, fn_variants=0, path_input_params=0, ...
14:18:36 _collect_var_types: 0 variable type(s) [] (excluded 0 PathInput param(s))
14:18:41 loaded 2 inputs in 0.000s
14:18:41 inputs: {Fs: 2000, config: '...'}
         Error in filterDelsys (line 12): muscle_names = fieldnames(loaded_data);
```

Two separate defects stacked.

## Defect 1 — variable inputs are never collected for a never-run function

`services/matlab_command_service.generate_matlab_command` builds the inputs
for a MATLAB function from exactly two edge sources:

* `_collect_edge_path_inputs` -> PathInput bindings
* `_collect_sweep_params`     -> Parameter bindings

There is no third call for **variable** bindings. When the function has DB
history (`fn_variants`) the variable inputs come in via each variant's
`input_types`, which hides the gap; `filterDelsys` had `fn_variants=0`, so
`api/matlab_command.generate_matlab_command` took its template branch, which
seeds the struct from `path_inputs` and `sweeps` only. `loaded_data` was
dropped on the floor.

`edge_resolver.resolve_function_edges` already resolves all three kinds into
one `bindings` dict, and the Python run path (`execution_service.build_run_inputs`)
consumes all three. Only the MATLAB generator's hand-rolled collection is
missing one — the exact duplication hazard `feedback_avoid_scifor_scidb_duplication`
records.

## Defect 2 — the inputs struct is not ordered by the MATLAB signature

`+scifor/for_each.m` binds inputs to arguments **by struct field order**:

```matlab
input_names = fieldnames(inputs);     % line 367
...
loaded{p} = prepare_input(...)        % in field order
call_args = loaded;                   % line 825
result = {fn(call_args{:})};          % line 859
```

MATLAB has no keyword arguments, so the field *names* are documentation only.
Both generator paths build the dict in collection order, never signature
order:

* template branch: `path_inputs` then `sweeps`
* `_for_each_call_lines`: `input_types` then `path_inputs` then `sweeps` then `constants`

So even with defect 1 fixed, a canvas whose edges were drawn in a different
order than the signature silently shuffles the call. This is why `Fs` landed
in argument 1.

## Fix

### `scistack-gui/scistack_gui/api/matlab_command.py`

1. `_matlab_signature_params(function_name)` — ordered param names from
   `matlab_registry.get_matlab_function(...).params`, `[]` when unknown.
2. `_order_inputs_by_signature(function_name, inputs_dict)` — reorder to
   signature order; log the resulting positional binding at INFO; **warn**
   when a signature param before the last bound one is unbound (a gap shifts
   every later argument) and when a field is not in the signature at all.
3. `_format_variable_input(type_names)` — `Type()` / `scifor.EachOf(A(), B())`.
4. `generate_matlab_command(..., variable_inputs=None)` — seed the template
   branch's struct with the edge-derived variable inputs, and pass them
   through to `_for_each_call_lines`. Include their class names in the
   unresolvable-classdef preflight.
5. `_for_each_call_lines(..., variable_inputs=None)` — overlay edge-derived
   variables the way `path_inputs`/`sweeps` already overlay, then order the
   assembled dict by signature.

### `scistack-gui/scistack_gui/services/matlab_command_service.py`

6. `_collect_variable_inputs(function_name, manual_edges, manual_nodes)` —
   `{param: [type names]}` from the shared resolver's `input_types` view.
7. Call it from both `generate_matlab_command` and
   `generate_matlab_pipeline_command` (per step), log the result, and pass it
   down. Add the types to the diagnostics `checked` set.

### `scimatlab/src/scimatlab/matlab/+scifor/for_each.m`

8. Arity preflight next to the existing `inputs:` log: compare
   `numel(fieldnames(inputs))` against `nargin(fn)` and warn when they differ,
   naming the fields and stating that binding is positional. `nargin(fn) < 0`
   (varargin) and un-introspectable handles are skipped. This is the
   observation that would have turned "silently wrong results" into one log
   line, and it belongs in scifor because scifor is what does the positional
   binding.

## Tests

`scistack-gui/tests/test_matlab.py`

* `TestCollectVariableInputs` — variable edge collected; declared name vs
  param name; other functions ignored; PathInput/Parameter sources excluded.
* `TestMatlabInputOrdering` — template branch emits all three inputs in
  signature order (the regression); `_for_each_call_lines` orders a DB-variant
  call; unknown function falls back to insertion order; extra/missing params
  warn.
