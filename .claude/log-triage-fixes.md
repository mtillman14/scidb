# Log triage fixes — 2026-09-01 session

Source evidence: `/workspace/scidb.log` (2,169 lines, 17:02:35 → 17:10:33, GUI pid
43304, MATLAB host pid 53772) plus two MATLAB terminal transcripts supplied by the
user (one successful run, one parse failure).

Six defects, five reported by the user plus one found while tracing them. Ordered
by "blocks work / cheap to fix" rather than by the user's original severity list —
Stage 1 and Stage 2 are one-line-ish fixes for hard failures, so they go first.

Every stage follows CLAUDE.md NOTE 2: a logging change to make the failure
observable, then the fix, then a regression test. Stages are independent and can
land separately.

---

## Stage 1 — Second MATLAB run fails to parse (PathInput leaks into `register_variable`)

**Symptom.** First run of a function node succeeds. The second run of the *same*
node fails before executing anything:

```
File: C:\Users\mtillman\AppData\Local\Temp\scistack_run.m Line: 115 Column: 185
Invalid expression. When calling a function or indexing a variable, use
parentheses. Otherwise, check for mismatched delimiters.
```

**Root cause — confirmed.** A first-run/second-run branch flip in the generator.

Run 1 logged `total_variants=0, fn_variants=0`, so `generate_matlab_command` took
the no-variants template branch (`scistack-gui/scistack_gui/api/matlab_command.py:334`),
which emits no `register_variable` lines at all. Run 1 then saved 3 `RawEMG`
records, so run 2 had DB variants and took the variants branch —
`matlab_command.py:379-384`:

```python
all_var_types = _collect_var_types(variants)
for vtype in sorted(all_var_types):
    lines.append(f"scidb.register_variable({vtype}());")
```

`_collect_var_types` (`matlab_command.py:422-434`) does
`all_var_types.update(input_types.values())` with **no PathInput filtering**. For
`loadDelsysEMGOneFile`, `input_types["emgFilePath"]` holds `PathInput.to_key()`
output (`scifor/src/scifor/pathinput.py:243-256`) — a JSON blob. The emitted line is:

```matlab
scidb.register_variable({"__type": "PathInput", "template": "…", "root_folder": null}());
```

MATLAB parses `{…}()` and reports exactly the error above. Column 185 lands at the
tail of that line, consistent with a ~120-char Windows path template.

**Why this is clearly the odd one out.** Every other consumer of the same data
already filters PathInputs:

- `_for_each_call_lines` — `matlab_command.py:494` (`_parse_path_input(...) is None`)
- `scidb.get_aggregated_variants` — `scidb/src/scidb/database.py:3782-3791` routes
  them into a separate `path_inputs` bucket

`_collect_var_types` is the single place that missed the rule, and it is used by
*both* the register block and the preflight diagnostic
(`services/matlab_command_service.py:354`) — so today that diagnostic is also
reporting the JSON blob as an "unresolvable variable type".

**Fix.** Filter inside the collector so both call sites are corrected at once:

```python
def _collect_var_types(variants: list[dict]) -> set[str]:
    from scistack_gui.api.pipeline import _parse_path_input
    all_var_types: set[str] = set()
    for v in variants:
        input_types = v.get("input_types", {})
        if isinstance(input_types, dict):
            for type_val in input_types.values():
                if _parse_path_input(str(type_val)) is None:
                    all_var_types.add(type_val)
        output_type = v.get("output_type", "")
        if output_type:
            all_var_types.add(output_type)
    return all_var_types
```

Note `_collect_var_types` currently takes no imports; `_for_each_call_lines`
already imports `_parse_path_input` from `api.pipeline` locally
(`matlab_command.py:482`), so match that pattern.

**Logging.** At generation time, log the resolved var-type set and the count of
PathInput params excluded, so a future leak is visible without reproducing:

```
generate_matlab_command: fn=%s register_variable types=%s (excluded %d PathInput param(s))
```

**Test** — `scistack-gui/tests/test_matlab.py`:

1. `test_collect_var_types_excludes_path_inputs` — build a variant whose
   `input_types` contains a `PathInput.to_key()` JSON string; assert the returned
   set holds only real class names.
2. `test_generated_command_never_registers_a_path_input` — generate with that
   variant and assert no line matching `register_variable\(` contains `{` or
   `__type`.
3. **Second-run regression** — generate once with `variants=[]` (template branch)
   and once with the DB variants that first run would produce, and assert *both*
   outputs parse-check clean under the same assertion as (2). This is the test
   that would have caught the branch flip; neither branch alone does.

---

## Stage 2 — PathInputs missing from the sidebar until "Refresh code"

**Symptom.** On reopening an existing project, previously created PathInputs render
on the canvas but the sidebar list is empty. Clicking "Refresh code" makes them appear.

**Root cause — confirmed.** The mount effect in
`scistack-gui/frontend/src/components/Sidebar/EditTab.tsx:172-176` omits the fetch:

```tsx
useEffect(() => {
  fetchRegistry()
  fetchParameters()
  fetchNotes()
}, [fetchNotes])
```

`fetchPathInputs()` exists (`EditTab.tsx:208`) and *is* wired to the `dag_updated`
handler (`EditTab.tsx:189`) — which is what "Refresh code" broadcasts. That is the
whole asymmetry. The canvas populates its PathInput nodes from `get_pipeline`, an
independent path, which is why they show there.

Worth confirming while in this file whether any other list has the same gap:
`fetchPipelines` / `fetchHiddenPipelines` are covered by the `graphVersion` effect
(`EditTab.tsx:180-183`), and `fetchParameters` is in the mount effect — so
PathInputs appear to be the only omission, but check the full set of `set*` list
states before closing this out.

**Fix.** Add `fetchPathInputs()` to the mount effect.

**Test.** Frontend has no test harness for this component today, so the guard is
backend-side + manual: verify `get_path_inputs` returns the expected list
immediately after project open with no intervening refresh (a
`scistack-gui/tests/test_path_input_service.py` case asserting the RPC is
correct at rest), then confirm the UI manually. Do not add a frontend test
framework as part of this stage.

---

## Stage 3 — MATLAB function visually disconnects from its output variable after a run

**Symptom.** After a MATLAB function node fires, the edge to its output variable
node disappears from the canvas, but the pipeline is still wired underneath — the
output variable turns green.

**Root cause — confirmed.** A placement-qualified id is compared against a bare id.

The log captures the exact transition across two builds 3s apart:

| | 17:10:30 | 17:10:33 |
|---|---|---|
| edges | 4 (2 DB-derived, 2 manual) | 2 (2 DB-derived, **0 manual**) |
| `have no declared param mapping` warning | absent | **present**, `matlab_param_to_class={}` |

`matlab_param_to_class` has two sources (`api/pipeline.py:568-617`): DB variants'
`output_num`, and manual edges as fallback. Both produced nothing, leaving `p2c = {}`.

The manual-edge source fails like this. At 17:10:30 graduation rewrote the manual
edge's endpoints onto the DB-derived node ids (via
`pipeline_store.rename_edge_endpoints`), producing
`fn__loadDelsysEMGOneFile__076c46199b238a69::main` — **placement-qualified**. But
`infer_manual_fn_param_to_class` matches exactly:

```python
# scistack-gui/scistack_gui/domain/edge_resolver.py:347
if edge.get("source", "") not in fn_node_ids:
    continue
```

and the caller builds `fn_node_ids` from `fn_node_id(fn_name, cid)`
(`api/pipeline.py:598-602`), which returns the **bare** id with no placement
(`graph_builder.py:84-86`). The two never compare equal after graduation, so
`edge_map` comes back empty.

This is the codebase's own documented convention being missed —
`strip_placement`'s docstring (`graph_builder.py:154-161`) says: *"For every ad-hoc
`var__`/`param__`/`pathInput__`/`fn__` prefix-parser that only ever wants the bare
id (never the scope), call this FIRST."* The sibling resolver path handles it:
`matlab_command_service._fn_node_ids` calls `strip_placement`
(`matlab_command_service.py:120`). `api/pipeline.py`'s p2c construction does not.

With `p2c = {}` the two halves of the graph then disagree on the handle name:

- `build_function_nodes` (`graph_builder.py:1346-1356`): the `out_types` filter
  drops everything, falls back to `list(declared)` → node renders **`out__loaded_data`**
  (the MATLAB signature name).
- `build_edges` (`graph_builder.py:1495-1506`): `class_to_param` is empty →
  `source_handle = f"out__{out_type}"` → edge points at **`out__RawEMG`**.

React Flow silently drops an edge whose `sourceHandle` does not exist on the source
node. `propagate_run_states` works on node ids, not handles, so it still reports
`2 green` — exactly "disconnected visually, connected underneath".

**Fix (primary).** Make `infer_manual_fn_param_to_class` placement-aware, in the
resolver rather than at the call site, so every caller benefits:

```python
# edge_resolver.py, inside infer_manual_fn_param_to_class
from scistack_gui.domain.graph_builder import strip_placement
bare_ids = {strip_placement(i) for i in fn_node_ids}
...
if strip_placement(edge.get("source", "")) not in bare_ids:
    continue
```

Audit the rest of `edge_resolver.py` for the same exact-match pattern in the same
pass — `resolve_function_edges` compensates via its caller today, which is fragile;
if it can be made to normalize internally too, do that and drop the caller-side
workaround.

**Fix (secondary, defensive).** Even with p2c populated, `build_edges` and
`build_function_nodes` can still disagree if the mapping is partial. Make
`build_edges` fall back to the handle the node will actually render rather than to
the class name, so a missing mapping degrades to a *visible* edge on the wrong
handle instead of an *invisible* one. Decide this after the primary fix — do not
apply both blind.

**Open question — do not fix blind.** The DB `output_num` source should have mapped
`loaded_data → RawEMG` on its own even with the manual edge gone, and it did not.
`output_num` is populated by `provenance_query.pipeline_variants` and survives
`get_aggregated_variants`, so either it is `None` for MATLAB batch saves or
`matlab_output_order[fn]` is empty. Resolve this with the diagnostics below before
deciding whether it needs its own fix — it is the difference between "the fallback
was load-bearing" and "the primary source is broken and nobody noticed".

**Logging.** `api/pipeline.py:618` logs `matlab_param_to_class` at **DEBUG**, which
is why the INFO-level log shows the empty result but not the cause. Promote to INFO
and attribute each entry to its source:

```
[pipeline] matlab_param_to_class: fn=%s from_db_output_num=%s from_manual_edges=%s merged=%s
```

Also log, per MATLAB fn, when `output_num` is present but `matlab_output_order[fn]`
is empty or too short to index — that is the silent skip at `api/pipeline.py:589`.

**Test** — `scistack-gui/tests/test_edge_resolver.py` and `test_graph_builder.py`:

1. `test_infer_param_to_class_matches_placement_qualified_source` — same manual edge
   with `fn__f__<cid>` and with `fn__f__<cid>::main` as `source`; both must yield
   the same mapping.
2. `test_matlab_output_edge_handle_matches_node_handle` — the real invariant. Build
   nodes and edges from the same inputs and assert every edge's `sourceHandle`
   exists among its source node's rendered output handles. This catches the whole
   class of defect regardless of which of the two sides drifts.
3. Post-graduation integration case in `test_pipeline_call_sites.py`: run the
   graduation path, rebuild, and assert the fn→var edge survives with a handle the
   node actually declares.

---

## Stage 4 — `scidb.Log` double-`sprintf` truncates Windows paths

**Symptom** (visible in the user's MATLAB transcript, not reported separately):

```
Warning: Escaped character '\L' is not valid. See 'doc sprintf' for supported special characters.
> In scidb.Log.info (line 115)
17:10:22 [matlab] [entities] Materialized 1 MATLAB classdef(s) in y:
```

The path is **truncated at `y:`** — everything from `\LabMembers` on is gone from
the log line.

**Root cause — confirmed.** Callers pre-format, then `Log` formats again.
`scimatlab/src/scimatlab/matlab/+scidb/entities.m:140` does
`scidb.Log.info(sprintf('… in %s: %s', …, stub_dir, …))`, and
`+scidb/Log.m:115` then runs `msg = sprintf(fmt, varargin{:})` on the
already-formatted string. The second pass interprets `\L` as an escape. Same at
`entities.m:187`.

This degrades exactly the diagnostics needed for every other stage here, which is
why it is worth fixing early despite being cosmetic in isolation.

**Fix.** In `+scidb/Log.m`, guard the format pass in all four level methods
(`debug`, `info`, `warn`, `err`):

```matlab
if nargin == 1
    msg = fmt;
else
    msg = sprintf(fmt, varargin{:});
end
```

This corrects every caller at once and belongs in scimatlab (CLAUDE.md NOTE 3 —
this is a MATLAB-wrapper concern, not a GUI one). Optionally also clean up
`entities.m:140` and `:187` to pass args through rather than pre-formatting, but
the `Log.m` guard is the load-bearing change.

**Test** — `scimatlab/tests/test_matlab_log_api_surface.py` already exists as the
surface test for this file. Extend it to assert each level method contains the
`nargin == 1` guard. A true behavioral test needs MATLAB, so state that limitation
in the test docstring rather than pretending the guard is executed.

---

## Stage 5 — Excessive code refreshes and slow startup

Lower confidence than Stages 1–4: the diagnosis is solid, the fix is a design
choice that needs your input before implementation.

**Evidence.** Three complete rescans of 141 MATLAB functions inside 90 seconds:
17:04:39–52 (13s), 17:05:04–16 (12s), 17:05:53–17:06:09 (16s). After 17:06 the
remaining 38 `get_registry` calls are free, so the *result* is cached — but each
`refresh_all()` throws that cache away wholesale.

**Cause A — no staleness check anywhere in the scan path.** No `mtime`, size, or
hash comparison in `registry.py`, `matlab_registry.py`, or
`scifor/src/scifor/discovery.py`. `refresh_all()` → `load_from_config()` clears the
registry and re-reads every file. At ~90ms/file against `\\fs2.smpp.local` this is
SMB round-trip latency, not parse cost — so an mtime-keyed cache should remove
nearly all of it. On reopen with the library repo configured, that 12–16s lands
inside startup (this session showed only 3.77s because the libraries were added
later, at 17:04).

**Cause B — full-rescan call sites where a one-file reload would do.**
`api/project.py:364-373`, `services/pipeline_service.py:261-264`,
`api/registry.py:30`, `services/target_file_service.py:707-738`. The narrow pattern
already exists and is already justified in comments:
`services/variable_service.py:128` and `:219` deliberately reload a single file and
say why. This stage is largely about applying that existing decision consistently.

**Proposed approach** (needs approval before implementation):

1. **Instrument first.** Before changing behavior, log per-scan: file count,
   wall-clock, and the trigger (which call site requested the refresh). Without the
   trigger attribution we are guessing at which of the three rescans were
   avoidable. This is cheap and independently useful.
2. **Add mtime+size keyed caching** in the discovery layer
   (`scifor/discovery.py`, per CLAUDE.md NOTE 3 — this belongs in the scistack
   layer that owns discovery, not in the GUI). Cache invalidates per-file, so an
   unchanged library repo costs one `stat` per file instead of a full read+parse.
3. **Convert the Cause-B call sites** to narrow reloads where the trigger affects
   one file, following `variable_service.py`'s pattern.
4. **Consider persisting the MATLAB registry** across restarts keyed by
   (path, mtime, size). Only if 2 and 3 prove insufficient — this adds a cache
   invalidation surface and should not be taken on speculatively.

**Test** — `scistack-gui/tests/test_registry.py` / `test_narrow_reload.py`:
assert a second `refresh_all()` with no file changes performs zero re-parses
(spy on the parse entry point), and that touching one file re-parses exactly that
file.

**Decision needed from you:** is a per-file `stat` on every refresh acceptable over
the network share, or does the cache need to be time-bounded (e.g. trust the cache
for N seconds) to avoid 141 round-trips per refresh? That trade-off depends on how
often you edit library files outside the GUI, which I can't determine from the code.

---

## Cross-cutting note: the DuckDB lock classifier is Windows-blind

Not on the user's list and not causing a visible failure yet, but found in the same
log and cheap to fix — fold into whichever stage lands first, or take separately.

At 17:10:24-25, three RPCs (`list_hypotheses`, `get_hidden_pipelines`,
`get_pipeline`) failed with a raw `_duckdb.IOException` and full tracebacks instead
of the graceful `DatabaseLockedError` path. `_as_locked_error`
(`scistack-gui/scistack_gui/db.py:112`) matches on `"Conflicting lock"` /
`"set lock on file"` — DuckDB's **POSIX** phrasing, as the comment at `db.py:49-51`
documents. Windows reports `"Cannot open file … used by another process"` +
`"File is already open in <exe> (PID n)"`, so the classifier returns `None`, the
5-second retry loop at `db.py:124` never runs, and the raw exception reaches the
frontend.

The retry would have succeeded: `for_each` finished at 17:10:24.669 and MATLAB
released the lock at 17:10:26.946 — a ~2.1s window, well inside
`ACQUIRE_RETRY_TIMEOUT = 5.0`.

Fix: add the Windows message forms to `_as_locked_error` and to `_LOCK_HOLDER_RE`
(`db.py:55`, also POSIX-anchored; `_LOCK_PID_RE` happens to be generic enough
already). Test in `scistack-gui/tests/test_db_lifecycle.py` by feeding both captured
message strings through `_as_locked_error` and asserting holder + PID extraction on
each — this will not reproduce on a Linux CI box any other way, which is why it was
missed.

---

## Suggested landing order

1. **Stage 1** — blocks every second run; ~5 lines plus tests.
2. **Stage 2** — one line.
3. **Stage 4** — protects the diagnostics the remaining stages depend on.
4. **Stage 3** — land the logging change first, read one real run, then fix.
5. **Stage 5** — instrument, then decide.

Stages 1, 2 and 4 are independent and can go in a single pass. Stage 3's fix is
small but its open question (why `output_num` contributed nothing) should be
answered from a real run before closing it out.

---

# Implementation status — 2026-09-01

All five stages plus the cross-cutting item are implemented. Frontend
`tsc --noEmit` passes clean. **Python tests have not been run** — per standing
instruction the user runs those; commands are at the end of this section.

## What shipped

| Stage | Files |
|---|---|
| 1 — PathInput leak | `scistack-gui/scistack_gui/api/matlab_command.py` (`_collect_var_types`) |
| 2 — sidebar PathInputs | `scistack-gui/frontend/src/components/Sidebar/EditTab.tsx` |
| 3 — placement mismatch | `scistack-gui/scistack_gui/domain/edge_resolver.py`, `api/pipeline.py`, `domain/graph_builder.py` |
| 4 — double-sprintf | `scimatlab/.../+scidb/Log.m`, `+scifor/Log.m` |
| 5 — refresh cost | `scistack-gui/scistack_gui/matlab_parser.py`, `matlab_registry.py`, `services/variable_service.py` |
| Cross-cutting | `scistack-gui/scistack_gui/db.py` |

## Deviations from the plan

**Stage 3 — secondary defensive fix NOT applied.** The plan floated having
`build_edges` fall back to the handle the node actually renders. Implementing it
means threading `matlab_output_order` into `build_edges`, which today has no
notion of MATLAB signature order. The primary fix resolves the reported bug, and
the new invariant test (`TestMatlabOutputHandleInvariant`) fails loudly if the two
sides ever diverge again — which is the real protection. Deferred rather than
threading a new parameter through on speculation.

Instead, the existing `[graph_builder]` orphan warning now names the consequence
and both handle sets, so the failure is self-explanatory in the log rather than
requiring this analysis to be redone.

**Stage 3 — fixed in the resolver, not the call site.** All three
`fn_node_ids` consumers in `edge_resolver.py` (`resolve_function_edges`,
`infer_manual_fn_output_types`, `infer_manual_fn_param_to_class`) now normalize
through a new `bare_fn_node_ids()` helper, so no caller has to remember.
`matlab_command_service._fn_node_ids` keeps its own edge scan — that discovers
`__{suffix}` call-site variants, which is separate work from placement
normalization and is still needed.

**Stage 3 — open question is now instrumented, not answered.** Why the DB
`output_num` source contributed nothing is still unresolved; it needs a real run.
`api/pipeline.py` now logs at INFO, per fn, attributed:

```
[pipeline] matlab_param_to_class: fn=%s from_db_output_num=%s from_manual_edges=%s merged=%s
```

plus a line naming any variant whose `output_num` is `None` or out of range for
its declared output names. One MATLAB run through the GUI will say which.

**Stage 5 — caching, not call-site narrowing.** The plan offered both. Only
caching was implemented, deliberately: it is the option that cannot change
behavior. `classify_matlab_file` now memoizes on `(mtime_ns, size)`, so an
unchanged file costs one `stat` instead of three opens plus three parses (the
uncached body reads each file up to three times: variable parse, function parse,
entities-script check). Every existing `refresh_all()` call site is left exactly
as it was — a full refresh stays a full refresh, it is just cheap when nothing
changed. Narrowing call sites would have altered what each one refreshes, which
is the accuracy risk the user ruled out.

Invalidation hooks where a write may land in the same timestamp tick at the same
size — the one blind spot of the stamp key:
- `matlab_registry.reload_source` (the post-edit narrow reload)
- `services/variable_service.py` after writing a variable classdef

`load_entities_script` still re-reads on every scan, so entity *declarations* are
never served from a stale cache — only the file's classification is cached.

**Cross-cutting — markers extracted to a tuple.** `_LOCK_CONFLICT_MARKERS` in
`db.py` now holds all four phrases (two POSIX, two Windows) and
`_LOCK_HOLDER_RE` matches both wordings, so adding a platform means adding a
string rather than editing a condition.

## Tests added

- `scistack-gui/tests/test_matlab.py::TestPathInputNeverRegisteredAsVariable` — 3
  tests, including the both-branches case that is the only one that catches the
  first-run/second-run flip.
- `scistack-gui/tests/test_edge_resolver.py::TestPlacementQualifiedEndpoints` — 5
  tests, including symmetry (placed id set vs placed edge) and a negative case
  asserting normalization did not widen matching across call sites.
- `scistack-gui/tests/test_graph_builder.py::TestMatlabOutputHandleInvariant` — 2
  tests; the first is the general invariant (every edge `sourceHandle` exists on
  its source node), the second pins the mechanism so a regression reports why.
- `scistack-gui/tests/test_db_lifecycle.py::TestWindowsLockMessageIsRecognized` —
  2 tests using the verbatim Windows message from the 2026-09-01 log.
- `scistack-gui/tests/test_registry.py::TestMatlabClassificationCache` — 5 tests
  covering hit, content change, forced invalidation, missing file, and the
  `reload_source` integration.
- `scimatlab/tests/test_matlab_log_api_surface.py::test_level_methods_guard_against_double_sprintf`
  — structural (exercising it needs MATLAB, stated in the docstring).

## Commands to run

```
pytest scistack-gui/tests/test_matlab.py::TestPathInputNeverRegisteredAsVariable -v
pytest scistack-gui/tests/test_edge_resolver.py::TestPlacementQualifiedEndpoints -v
pytest scistack-gui/tests/test_graph_builder.py::TestMatlabOutputHandleInvariant -v
pytest scistack-gui/tests/test_db_lifecycle.py::TestWindowsLockMessageIsRecognized -v
pytest scistack-gui/tests/test_registry.py::TestMatlabClassificationCache -v
pytest scimatlab/tests/test_matlab_log_api_surface.py -v
```

Then the full suites for the touched modules, since Stages 3 and 5 change shared
code paths:

```
pytest scistack-gui/tests/ scimatlab/tests/ -q
```

## What to verify by hand

1. **Stage 5 payoff** — open the project and watch for
   `[matlab_registry] Classified N MATLAB source file(s) in X.XXs (cache: H hit(s), M miss(es))`.
   First scan should be all misses at the old duration; every subsequent refresh
   should be nearly all hits and substantially faster.
2. **Stage 3** — run a MATLAB function node twice and confirm the edge to its
   output variable stays drawn after the run. Capture the new
   `matlab_param_to_class:` INFO lines to close the `output_num` question.
3. **Stage 1** — run the same node twice; the second run should now execute.
4. **Stage 2** — reopen the project; PathInputs should be listed in the sidebar
   without clicking "Refresh code".
