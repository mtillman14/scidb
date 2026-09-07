# Plan — a Parameter may hold zero values

## The problem

Creating a Parameter from the GUI writes a value of `0` into source:

```python
# scistack-gui/scistack_gui/services/parameter_service.py:59-67
values = list(values or [])
if not values:
    values = [0]
    logger.info("... scaffolding a placeholder %r", values)
```

The "New parameter" form only collects a name, so every parameter created
that way lands in `scistack_entities.toml` (or the `.py`/`.m` entities file)
as `NAME = 0`. That `0` is indistinguishable from a real declared value: it
shows on the node as a checked value, it feeds `for_each`, and a run started
before the user notices writes records stamped with `0`.

A Parameter that has been *declared but not yet valued* is a legitimate,
nameable state. Nothing should have to invent a value for it.

## Decision

**A Parameter may hold zero values.** Legal at rest (source, entities file,
registry, canvas), an error at execution.

Two decisions confirmed with the user:

- **D1 — emptying is allowed.** Removing the last value of an existing
  Parameter is permitted, not blocked. One rule at every surface: the value
  set may be empty at any time. Values with run history stay listed on the
  node as `history` rows (the DB is the record of what actually ran).
- **D2 — running an empty Parameter raises.** `for_each` and the GUI run
  path both refuse with a message naming the parameter. This mirrors
  `_apply_hidden_values`, which already raises when every value is unchecked,
  and replaces today's silent failure mode (see "The zero-axis trap").

## The zero-axis trap (why this is more than deleting four lines)

`EachOf` expansion is a Cartesian product over each axis's alternatives. An
axis with **zero** alternatives makes `itertools.product` yield nothing, so:

- `results` stays empty, `pd.concat` is skipped, `for_each` returns `None`;
- no records are written, no exception is raised, the GUI reports success.

That is exactly the class of bug `build_run_inputs`' docstring already
records ("iterating zero times and writing no records while reporting
success"). Allowing an empty Parameter without a guard would re-introduce it,
so every expansion site gets an explicit check.

There are four expansion sites, and they must agree — Python and MATLAB
version keys have to match:

| Site | File |
| --- | --- |
| scifor (pure) | `scifor/src/scifor/foreach.py:176` |
| scidb | `scidb/src/scidb/foreach.py:421` |
| scifor MATLAB | `scimatlab/src/scimatlab/matlab/+scifor/for_each.m:98` |
| scidb MATLAB | `scimatlab/src/scimatlab/matlab/+scidb/for_each.m:85` |

## Why `EachOf` itself has to allow empty

`Parameter` IS an `EachOf` in both languages, and `EachOf.__init__` currently
raises on zero alternatives. In Python a subclass could sidestep that; in
MATLAB it cannot — a superclass constructor call may not sit in a conditional
branch, so `+scidb/Parameter.m` has exactly one `obj@scifor.EachOf(args{:})`
call and `args` may be empty.

So the invariant moves rather than being duplicated with an exception:
`EachOf` may be constructed empty; **expanding** an empty axis is the error.
The check lands where the harm actually occurs, and the message can name the
offending input instead of just saying "at least one alternative". A bare
`EachOf()` typed by hand still fails — one call later, with a better message.

This is a scifor-layer change made for a scidb-layer feature, and it is
defensible on its own terms: the current behaviour of a zero-length axis that
slips past construction is a silent no-op, and this converts it into a loud
error.

## Changes

### scifor

1. `each_of.py` — drop the constructor guard; `alternatives` may be `[]`.
   Document that an empty `EachOf` is a placeholder and that expansion is
   where it is refused.
2. `foreach.py` — before building the product, raise `ValueError` for any
   axis with no alternatives, naming the input (or `where=`).
3. `+scifor/EachOf.m`, `+scifor/for_each.m` — the same two changes, same
   message.

### scidb

4. `parameter.py` — `Parameter()` with no values is constructible.
   `.values` → `[]`. `_single()` gets a dedicated message for the zero case
   ("'X' has no value yet") rather than the generic count message.
   `__getattr__` keeps raising `AttributeError` (never `TypeError`) for the
   empty case — `foreach._is_loadable` probes with `hasattr`, and only
   `AttributeError` is swallowed there.
5. `foreach.py` — the zero-axis guard, with the parameter name in the
   message.
6. `discover.py` — **vacuous-truth bug**: `is_path_input` is
   `isinstance(obj, EachOf) and all(isinstance(alt, PathInput) for alt in
   obj.alternatives)`. `all([])` is `True`, so an empty `Parameter` would
   classify as a PathInput. Require non-empty alternatives.
7. `entities.py::_load_parameters` — `NAME = []` currently appends
   `EntityError("a Parameter needs at least one value")`. It now loads as an
   empty Parameter and logs at debug. `render_parameter_value([])` already
   emits `[]`; add the round-trip test.
8. `source_edit.py::render_parameter` — already emits
   `scidb.Parameter(description='')` for an empty list. Covered by a test,
   no code change.
9. `+scidb/Parameter.m` — drop the `scidb:Parameter:NoValues` error;
   `values` → `{}`; `value` errors with the no-value message.
   `+scidb/entities.m` already splats `values{:}`, so an empty list flows
   through unchanged once `Parameter` accepts it.

### scistack-gui

10. `services/parameter_service.py::create_parameter` — delete the `[0]`
    scaffold. Log at INFO that the Parameter was created with no values yet.
    Update the docstring, which currently explains the placeholder.
11. `services/parameter_service.py::update_parameter` — drop the
    empty-values rejection (D1). Log at INFO when a Parameter is emptied,
    including how many values were dropped: this is the one edit that can
    take a running pipeline back to un-runnable, so it should be visible in
    `scidb.log`.
12. `api/layout.py:130` — the docstring describing the placeholder.
13. `services/execution_service.py::_infer_wired_constants` — an empty
    declared list must **not** enter `inferred`. `_inferred_targets` builds
    `product(*inferred_constants.values())`, so one empty list there yields
    zero targets and the node silently reports "no targets derivable". It
    falls through to the existing warning branch instead, with the message
    distinguishing "declared but has no value yet" from "not declared at
    all". The target is still produced, so the run reaches (14).
14. `services/execution_service.py::build_run_inputs` — raise `ValueError`
    when a wired Parameter has no values (D2), shaped like
    `_apply_hidden_values`' existing raise: names the declared parameter,
    the function, and what to do about it.
15. `api/matlab_command.py::_format_sweep` — same guard on the
    command-generation path, so the MATLAB route fails with the same message
    at generation time instead of emitting `scidb.Parameter()` into a script.
16. `frontend/src/components/DAG/ParameterNode.tsx` — a dimmed "no value
    yet" line when `values` is empty, so an unvalued node reads as
    deliberately empty rather than broken. (The node currently renders the
    name and nothing else.)
17. `frontend/src/components/Sidebar/ParameterSettingsPanel.tsx` — remove
    the local `removeValue` block on the last declared value (D1). The
    "No values yet" empty state already exists.

---

# Part 2 — generated value sets show as one checkable row

## The ask

Values added one at a time keep exactly their current presentation, in both
the sidebar and on the canvas node: one pill / one checkbox per value.
Values produced by the **Generate** section's "Replace values" button are a
*set*, and should read as one compact row — the same repr in the sidebar list
and on the canvas node — with a single checkbox that includes or excludes the
whole set.

## How "generated" is known

The write path already distinguishes them, which is the whole answer:

| Button | Handler | Meaning |
| --- | --- | --- |
| **Add** | `addValue` → `update_parameter(values: [...declared, v])` | one individual value |
| **Replace values** | `applyGenerated` → `update_parameter(values: preview)` | a generated set |

The only thing missing is persistence. `update_parameter` writes a flat list
to source and the registry re-reads source, so by the next graph fetch the
provenance is gone. It gets recorded in the GUI's own store instead of in
source — this is a *display* concern (how to group values a user is looking
at), not a scidb concern, so per CLAUDE.md NOTE 3 it belongs in the GUI
layer. Source stays a flat list of values: no entities-file grammar change,
no change to `render_parameter` / `render_parameter_value` /
`render_matlab_parameter`, no change to `version_keys`, and nothing for the
MATLAB side to mirror.

D3: **at most one generated group per Parameter.** "Replace values" replaces
*every* value, so a generation always defines the whole set; individually
added values afterwards sit alongside it as ordinary rows.

## Storage

New table, alongside the existing `_pipeline_*` GUI state in
`pipeline_store._ensure_tables`:

```sql
CREATE TABLE IF NOT EXISTS _pipeline_parameter_value_groups (
    param_name    VARCHAR PRIMARY KEY,  -- one group per Parameter (D3)
    kind          VARCHAR NOT NULL,     -- 'range' | 'list'
    spec          VARCHAR NOT NULL,     -- JSON: {start,end,step} | {members}
    member_values VARCHAR NOT NULL      -- JSON: ordered members, as rendered strings
)
```

(As built: the column is `member_values`, not `values` — `VALUES` is a SQL
keyword and would need quoting at every reference. The range spec stores the
resolved `step` and the **last generated value** as `end`, so a 0/7/step-2
generation labels itself `0:2:6`, naming only values that are really in the
set.)

`values` is stored as the same rendered strings the node already uses
(`str(v)` in `build_parameter_nodes`, matching what `hide_parameter_value`
stores), so membership, hidden-state and history rows all key alike.

`spec` is kept, not just the member list, for two reasons: the repr is
rendered *from* it, and reopening Generate can re-seed its start/end/step
inputs with the generation that produced the values currently on screen.

New store functions: `set_parameter_value_group`,
`get_parameter_value_groups`, `clear_parameter_value_group`.

## Reconciliation with source

Source is still the truth for which values exist. On every rebuild,
`build_parameter_nodes` checks the recorded member set against the declared
values:

- **every member still declared** → the group renders as one row;
- **any member gone** (a hand edit to the entities file, or a removal from
  the panel) → the group is stale. Drop the record, log at INFO, and fall
  back to individual rows. Values are never invented or hidden by a stale
  group.

An "Add value" after a generation leaves the group intact — a superset is
fine, the extra value is just an individual row.

## Rendering — one repr, computed once

The repr is built **backend-side** in `build_parameter_nodes` and shipped in
the node's `data`. `ParameterSettingsPanel` already receives the node's
`values` array as a prop, so the sidebar and the canvas render the identical
string by construction — there is no second implementation to drift.

Format (from `spec`):

- range → `0:2:20 — 11 values` (colon notation, familiar to the MATLAB half
  of this project);
- list → up to 6 members, then `1, 2, 5, 10, 20, 50 — 12 values`.

Row shape in `data.values`. Individual rows are **byte-identical to today**,
which is what keeps their presentation unchanged:

```jsonc
// individual — unchanged
{"value": "0.05", "record_count": 3, "checked": true, "is_current_source_value": true}
// generated group — new, additive
{"kind": "generated", "repr": "0:2:20 — 11 values", "members": ["0","2",...],
 "record_count": 33, "checked": true, "is_current_source_value": true}
```

`ParameterNode.tsx` and `ParameterSettingsPanel.tsx` branch on `kind`;
absent `kind` takes exactly the path it takes now.

- `record_count` for a group is the sum over its members, so the existing
  `N rec` badge reads as the set's total.
- The panel's per-row `×` (remove) on a group removes the whole set from the
  declaration, and clears the group record.

## Checkbox semantics (D2 from your answer: whole set)

- `checked` is true when **no** member is hidden; any hidden member renders
  the group unchecked (no tri-state — an explicit decision, since the only
  way to reach a mixed set is hiding values individually before a
  generation, and the next toggle resolves it).
- Unchecking hides every member; checking unhides every member.
- One round-trip, not N: add batched `hide_parameter_values` /
  `unhide_parameter_values` store functions and a
  `set_parameter_group_checked` RPC. Per-value `hide_parameter_value` stays
  for individual rows. (`project_batched_provenance_hot_paths` — this is the
  same N+1 shape.)

Execution is untouched: source still holds a flat list, hidden values still
filter per value in `_apply_hidden_values`, so a group is display plus a bulk
toggle and nothing more.

## Additional changes for Part 2

18. `pipeline_store.py` — the table in `_ensure_tables`, plus
    `set_parameter_value_group` / `get_parameter_value_groups` /
    `clear_parameter_value_group` and the batched hide/unhide pair.
19. `services/parameter_service.py::update_parameter` — accept an optional
    `group` argument (`{kind, spec}`); record it when present. "Add" sends no
    group, so appending a value never claims one — and, **as built**, also
    never *clears* one: an edit with no group drops the record only if it
    leaves a member undeclared, so adding a value alongside a generated set
    keeps the set intact (which is what the reconciliation rule above says
    should happen).
20. `domain/graph_builder.py::build_parameter_nodes` — read the groups,
    reconcile against declared values, collapse members into one row, render
    the repr, sum `record_count`, derive `checked`.
21. `api/*` + `server.py` — plumb `group` through `update_parameter` and add
    `set_parameter_group_checked`.
22. `frontend/.../ParameterNode.tsx` — render a `kind: "generated"` row as
    one checkbox + repr; individual rows unchanged.
23. `frontend/.../ParameterSettingsPanel.tsx` — same branch in the Values
    list; `applyGenerated` sends the `group`; `addValue` does not; Generate's
    inputs re-seed from an existing group's `spec`.

## Additional tests for Part 2

- `test_pipeline_store.py` — group round-trip; one group per name (D3);
  batched hide/unhide.
- `test_graph_builder.py` — a group collapses to one row with the right repr
  and summed `record_count`; a group plus a later individually-added value
  yields one group row and one individual row; **a stale group (a member no
  longer declared in source) is dropped and every value renders
  individually**; `checked` is false when one member is hidden.
- `test_parameter_service.py` — `update_parameter` with a `group` records it;
  without one clears it.

## Out of scope for Part 2

- Exporting a project (`portability_service`) carries the values but not the
  grouping — the group is GUI display state, and the values it describes
  survive intact.
- Multiple groups per Parameter (D3), and appending a generated set to
  existing values rather than replacing them.

## Diagnostics

Per CLAUDE.md NOTE 2, the observable trail for the new state:

- `create_parameter`: INFO — created with no values.
- `update_parameter`: INFO — emptied, N value(s) dropped.
- `_load_parameters`: DEBUG — declared with 0 value(s) (the existing line
  already prints the count).
- `_infer_wired_constants`: WARNING — wired but declared with no value yet.
- `build_run_inputs` / `for_each`: the raised error itself, which
  `scidb.log` already captures on the run path.

## Tests

Python (handed over as commands — I do not run pytest here):

- `scifor/tests/test_each_of.py` — `EachOf()` constructs empty (replaces the
  `at least one alternative` assertion); `for_each` with an empty axis raises
  and names the input.
- `scidb/tests/test_each_of.py:109` — same replacement.
- `scidb/tests/test_parameter.py` — `Parameter()` constructs; `.values ==
  []`; `.value` / `int()` / `bool()` raise with the no-value message;
  `hasattr(p, "load")` is `False` and does not raise `TypeError`; `repr`.
- `scidb/tests/test_entities_toml.py` — `NAME = []` loads without error as a
  0-value Parameter; `render_parameter_value([])` round-trips.
- `scidb/tests/test_source_edit.py` — `render_parameter([]) ==
  "scidb.Parameter(description='')"`.
- `scidb/tests/test_discover.py` — `is_path_input(Parameter())` is `False`
  (the vacuous-truth regression).
- `scistack-gui/tests/test_parameter_service.py` — replace
  `test_default_value_is_placeholder_zero`: creating with no values writes an
  empty declaration and no `0`; `update_parameter(name, [])` empties it.
- `scistack-gui/tests/test_execution_service.py` — an empty wired Parameter
  still derives a target (not zero targets) and `build_run_inputs` raises
  naming it.
- `scistack-gui/tests/test_matlab*.py` — `render_matlab_parameter([]) ==
  "scidb.Parameter()"`; command generation refuses an empty Parameter.

MATLAB (`scimatlab/tests/matlab/scidb/TestParameter.m`, run by the user):
empty construction, `values` is `{}`, `value` errors, and a `for_each`
empty-axis error test alongside the existing EachOf tests.

## Out of scope

- Hidden/unchecked-value semantics are untouched: unchecking every value
  still raises its own distinct error, which is a different state from "no
  values declared".
- No migration for parameters already written as `0` — beta, no shims
  (`feedback_beta_no_deprecation`). Existing `NAME = 0` declarations stay
  valid single-valued Parameters; the user edits or removes them.
