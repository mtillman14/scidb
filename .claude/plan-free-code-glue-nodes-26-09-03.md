# Plan: "Free code" glue nodes (2026-09-03)

**Status: all six stages implemented 2026-09-03, uncommitted. The Python
test suites have NOT been run** (the user runs tests); the MATLAB runtime
half needs a real MATLAB run, the standing gap. Concept doc:
`docs/claude/free-code-glue-nodes.md`.

## Where the implementation departs from this plan

Two deliberate deviations, both recorded here rather than silently absorbed:

1. **Stage 5's editor is not Monaco (yet).** `GlueCodeEditor.tsx` is a
   self-contained monospace buffer with a line gutter and Tab-inserts-indent.
   Monaco is still the intended end state and the component exists precisely
   to be the swap seam, but it is a multi-megabyte dependency with worker and
   CSP implications that could not be verified from the implementation
   environment. Everything else in D1a holds: the panel is the primary
   surface, the file is invisible plumbing, and the round-trip works.

2. **Stage 6 emits `glue=` on the `for_each` call, not a bare
   `df = glue_x(df)` statement.** §4's `df = glue_x(df)` sketch is the
   *conceptual* picture of what happens inside a run; as literal exported
   code it does not work — there is no `df` in scope at that point, since the
   table only exists inside `for_each`'s load step. Such a script would
   neither run nor reproduce its records, failing the export contract the
   stage's own first test states. The export instead emits `glue={...}` (the
   faithful spelling of the same fusion) plus a comment line naming the
   reshaping, so "glue appears inline, not as a `for_each` step" stays
   visibly true.

3. **Glue on a `Merge` param works, but its identity is not tracked.** The
   plan's Stage 1 test list asks for it and it does reshape correctly — but
   only per combo, and with no virtual glue record, so an edited body will not
   invalidate downstream results. This is structural, not an oversight: a
   Merge stays a set of constituent frames until scifor joins them per combo,
   and `_load_input` strips every `__`-prefixed column from the constituents,
   so there is no rid to route through. It is logged at WARNING and the
   warning is asserted by a test, since silent staleness is exactly what the
   virtual record exists to prevent. Same applies to a `PerComboLoader` input.

Two smaller notes: multi-input glue is supported in `scidb.glue`
(`GlueSpec.extra_inputs`) but the canvas has no way to wire the extra inputs
yet — a glue node's extra incoming edges are warned about, not folded in. And
the node-state prediction's `input_set_signature` is computed from *current*
records, so a run narrowed by `where=`/`schema_filter` reads as falsely red
(conservative, never falsely green); both signatures are logged at DEBUG.

## The need

Function nodes are project-agnostic computations. Between them, projects need
one-off reshaping: rename a column, change a dtype, drop/append a column,
restructure a dict. Today that forces the user to write a real pipeline
function with a declared output variable type, which pollutes the DB and the
graph with data that is purely transitional.

## User decisions (asked and answered, 2026-09-03)

| # | Decision | Chosen |
|---|---|---|
| D1 | Where the code lives | **A real source file per node** in a GUI-owned directory (`src/scistack_glue/`), not GUI-state text and not a TOML string |
| D1a | How it is edited | **In a code panel inside the GUI** (2026-09-03). The file is persistence, not a place the user navigates to — no scaffolding, no boilerplate, no directory to manage |
| D2 | Graph attachment | **Standalone node wired by edges** (not an edge-attached transform) |
| D3 | Output persistence | **Not saved; fused in-memory into the consuming function's call**, with the glue's hash folded into that function's identity |
| D4 | Iteration | **Whole loaded table by default**, per-schema-key opt-in toggle |
| D5 | Runnability | **No run button, no own run state.** A glue node is never independently executable; it runs only as part of a consuming function's run |
| D6 | Sidebar presentation | **A function-role filter**, not a separate list. One dropdown over the Functions category: Process / Plots / Stats / Glue / All, defaulting to Process (2026-09-03) |

## Naming, and the function-role concept (D6)

`glue_` **name prefix**, following the existing `plot_`/`stat_` convention.
That convention is already the stack's cross-language function-role marker
(`scidb/foreach.py:3708-3710`, `scidb/inspect/report.py:183`) and it is checked
on the *name*, which arrives over the MATLAB bridge identically — so it needs no
decorator (Python-only) and no classdef (MATLAB-only). The GUI applies the
prefix automatically when creating a node.

Adding a fourth prefix makes the implicit concept worth naming. **Function role**
becomes a first-class, shared classification:

| Role | Identified by | Note |
|---|---|---|
| `process` | **No recognized prefix** — the default bucket | The ordinary pipeline step |
| `plot` | `plot_` | Existing |
| `stat` | `stat_` — **singular**, not `stats_` | Existing; the sidebar label may read "Stats", the prefix may not |
| `glue` | `glue_` | New |

**One classifier, in `scidb`, not the GUI**: `scidb.discover.function_role(name)
-> Literal["process", "plot", "stat", "glue"]`. The prefixes already drive real
execution behaviour in scidb, so the GUI must not own a second copy of the
strings — that is the `feedback_avoid_scifor_scidb_duplication` rule, and the
same choke-point reasoning as the discovery consolidation.

Incidental win: this replaces the three hardcoded `startswith("plot_")` /
`startswith("stat_")` sites with one call, so a fifth role later touches one
function.

**The dropdown itself is pure display and lives in the GUI layer** (CLAUDE.md
NOTE 3) — exactly the precedent of `_pipeline_parameter_value_groups`, which is
GUI-only because grouping is a display concern. The GUI filters on the role
`scidb` reports; it never decides what a role is.

---

## The mechanism

### 1. Fusion point

Glue is applied to the **bulk-loaded input DataFrame for one parameter of the
consuming function**, between Step 10 (`_convert_inputs` / `_load_var_type_all`)
and Step 11 (rid rename) of `scidb/foreach.py`.

This location is what makes the feature nearly free:

- the loaded table already carries schema-key columns, so the consumer's own
  per-combo slicing (Steps 12/15/17) keeps working unchanged;
- it is *before* `__record_id` → `__rid_{param}` renaming, so provenance
  bookkeeping is untouched;
- **MATLAB gets Python glue for free**: `+scidb/for_each.m` delegates all
  pre-loop work to `scimatlab.bridge.for_each_prepare` (see its header comment,
  lines 8–18 — "MATLAB owns only step 2"), so anything done in `_convert_inputs`
  applies to a MATLAB run too.

The per-schema-key opt-in (D4) uses a different site: the existing
`PerComboLoader` function wrapper (Step 16), applied to the already-sliced value
just before `fn` is called.

### 2. The row-preservation contract

**A glue node may change the column space; it may not change the row set.**

Add/remove/rename/retype columns, restructure cell values — all fine. Filtering
rows, aggregating, exploding, re-indexing — refused.

Why this is the right line, not a limitation to apologize for:

- it is exactly the stated use case (D-list above);
- it makes re-attaching the hidden `__record_id` / `__branch_params` columns
  provably safe, so per-row provenance survives glue with zero user awareness;
- anything that *does* change the row set is a real computation with a real
  result, which is what an ordinary function node with a saved output is for.

Implementation: hide every `__`-prefixed column from the user's function, call
the glue, then verify `len(out) == len(in)` **and** index equality, and re-attach
the hidden columns by index. Violations raise `GlueRowsChangedError`
(MATLAB identifier `scidb:glue:rowsChanged`) naming the glue, the param, and the
before/after row counts — never a silent partial re-attach.

Scalar (non-DataFrame) inputs skip the check; there are no rows to preserve.

### 3. Identity — the part that must not be got wrong

Two separate identity systems must both learn about glue, or an edited glue
leaves stale downstream results looking green.

**a. Version keys** (`ForEachConfig.to_version_keys`, `scidb/foreach_config.py`).
Add `__glue`: `{param_name: [(glue_name, glue_hash), ...]}` in application order.
Follow the existing `__fn` / `__fn_hash` split precisely — the glue *names*
contribute to `call_id`, the glue *hashes* do not. Same reasoning as the existing
`__fn_hash` exclusion: a different glue chain is a different call site; an edit to
a glue body is a new version at the same call site.

**b. The provenance graph** — this is the one that drives `skip_computed` and
node state, and it does **not** read version keys. `invocation_id = sha16(fn_hash
| as_table | distribute | sorted(bindings))`, and `stored_invocation_signature`
compares input record_ids binding-by-binding. So glue must change a *binding*.

The design: **the data is not saved, but the provenance node is.**

For each input record flowing through a glue chain, write a **virtual record** —
a `_record` row with `type = '__glue__'`, the same `schema_id`, and

```
virtual_rid = sha16(glue_chain_hash | input_record_id | input_set_signature)
```

plus one `_invocation` for the glue and its two edge rows. `input_set_signature`
is `sha16` of the sorted full input rid set, which correctly forces recompute
when a whole-table glue's input set *grows* — the same hole that was already
closed for aggregation `skip_computed`.

No `_record_metadata` row, no data-table row, nothing loadable, nothing in
`scidb report`. The consumer's `__graph_var_bindings` point at the virtual rid
instead of the raw one, so `invocation_id`, `skip_computed` staleness,
`upstream_provenance` BFS and node state all work through **one extra graph hop
with no special-casing**, and `upstream_provenance` reads honestly as
`RawEMG → glue_drop_baseline → analyze_emg`.

Cost is ~4 metadata rows per (glue, input record) and no data bytes. This keeps
the project's audit story intact while honouring "the output is not saved."

### 4. A glue node is not a step (D5)

Glue has **no run button and no own run state**. It is transient by
construction, so there is nothing for a standalone run to produce and nothing
for a node state to be green or red about.

The consequence that must be enforced in code: **`build_backend_pipeline` must
never emit a `StepSpec` for a glue node.** Glue is a property of the consuming
step's *input binding*, not a node in the compiled pipeline. Concretely, when
the user presses Run on `analyze_emg`:

```
load RawEMG                      (bulk load, Step 10)
df = glue_drop_baseline(df)      (fusion, in-memory, not saved)
analyze_emg(df)                  (Steps 11-19, saved as normal)
```

The same holds for a whole-pipeline run: the topological order is over function
nodes only, and each glue node collapses into the input binding of whichever
function it feeds. A glue node that feeds nothing is simply never executed —
it is not an error, and it must not red the canvas.

Two places this has to be right, both of which currently assume "a node on the
canvas is a step":

- `execution_service.build_backend_pipeline` / `derive_fn_targets` — glue
  contributes a `glue_chains` entry to the target dict (alongside
  `path_input_params` / `parameter_params`), never a step of its own.
- `api/run.py`'s per-node Run route — must refuse a glue node id with a clear
  message rather than compiling an empty pipeline and reporting a successful
  run that did nothing (the documented "succeeds while doing no work" failure
  mode).

The D4 per-schema-key toggle therefore only chooses *where inside the consumer's
run* the fusion happens (bulk table vs. post-slice), never whether the glue is
its own execution.

### 5. Calling convention — what glue receives and returns

**All glue is a function definition.** Not a bare statement body with magic
variable names. This falls directly out of D1 + D2: the file is a real
`.py`/`.m` file, so it is found by the ordinary scanner with no new discovery
path, and a node wired by edges needs named parameters for the edges to target.

```python
# src/scistack_glue/glue_drop_baseline.py
def glue_drop_baseline(emg):
    return emg.drop(columns=["baseline"])
```

```matlab
% src/scistack_glue/glue_drop_baseline.m
function out = glue_drop_baseline(emg)
    out = removevars(emg, "baseline");
end
```

MATLAB's one-public-function-per-file rule makes the file layout identical in
both languages, and `matlab_parser._FUNCTION_RE` already extracts the param and
output names — no new parsing.

**Parameter naming is answered by edges, not by names.** The glue's signature
produces `in__{param}` handles exactly like a function node, and
`resolve_function_edges` binds them the same way. A glue parameter called `emg`
can be fed by any variable; the names need not match anything. This is the
governing rule since 2026-08-25 (`function-input-resolution.md`) and glue gets
it for free.

N inputs are supported (N edges → N params). Exactly **one return value**: glue
feeds a single parameter of a single consumer, so there is nothing for a second
output to bind to. Needing two outputs means either two glue nodes or a real
function node with saved outputs.

#### What the *columns* are called — the non-obvious half

The value handed in is the **bulk-loaded long-format table**
(`_load_var_type_all`), and its column names depend on how the variable stores
its data. This is the part a glue author actually has to know, and it is not
guessable:

| Variable's stored data | Columns the glue sees |
|---|---|
| A DataFrame | **The user's own DataFrame columns, under their own names.** There is no column named after the variable class |
| A scalar or array | Schema-key columns **plus one data column named after the class** — `df["RawEMG"]` (from `view_name()`) |

Schema-key columns (`subject`, `session`, …) are present in both cases, and in
aggregation mode schema columns below the lowest iterated level may be dropped
when entirely NULL.

Because this is genuinely hard to guess, **the editing panel shows the wired
input's actual column list beside the editor**, read from `_variables.dtype`
(which records `mode: single_column | multi_column | dataframe` and the column
types). It is deliberately *not* scaffolded into the file as a comment (D1a):
a comment goes stale the moment the node is rewired, while the panel re-reads
it every time it opens. The file stays down to the code the user actually
wrote.

#### Column visibility and protection

- `__`-prefixed columns (`__record_id`, `__branch_params`) are **hidden** from
  glue and re-attached afterwards. They are internal bookkeeping and the user
  must never have to think about them.
- Schema-key columns are **visible but protected**. Visible because a whole-table
  glue may legitimately need them (`df.groupby("subject")`) and because "the
  loaded table" is the user's mental model. Protected because dropping or
  retyping one silently breaks the consumer's per-combo slicing — Step 5
  stringifies schema values, so even an int/str change makes every combo filter
  miss. After the glue returns, schema-key columns are verified present and
  value-identical, else `scidb:glue:schemaKeysAltered` naming the offending key.

### 6. Language rule

**A glue node executes in the language of the run.** A MATLAB pipeline needs
MATLAB glue; a Python pipeline needs Python glue. Mixed chains are refused at
`build_run_inputs` with `scidb:glue:languageMismatch`.

(Python glue in a MATLAB run would technically work for free, since it happens
inside `for_each_prepare`. Rejected anyway: it would make the exported plain
script unfaithful, and one rule is easier to hold than an asymmetric one.)

MATLAB glue cannot run in `for_each_prepare`, so `+scidb/for_each.m` applies it
between prepare and the loop, on the table it already rebuilds from
`for_each_describe_loaded_input` (line ~393). `prepare` gains a `glue_chains`
entry in its returned dict telling MATLAB which params carry MATLAB glue.

---

## Stages

Each stage lands with logging and regression tests (CLAUDE.md NOTE 2).

### Stage 1 — `scidb.glue` core + Python fusion
- `scidb/src/scidb/glue.py`: `GlueSpec(name, fn, language, source_file)`,
  `apply_glue_chain(value, chain, param)`, hide/re-attach, row-preservation check.
- Wire into `_load_input` / `_convert_inputs`; per-key variant into the Step 16
  wrapper.
- **Logging**: `[glue] '<param>': applied <name> (+col, -col, dtype changes) in Ns`
  at DEBUG; the row-preservation refusal at WARN before it raises.
- **Tests**: column add/drop/rename/retype round-trip; `__record_id` survives;
  row-count change raises; chain of two; scalar input; glue on a `Merge` param;
  glue on a PathInput param **refused** (no table exists at prepare time);
  dropping or retyping a schema-key column raises `schemaKeysAltered`;
  both column-naming modes (DataFrame-stored → own column names,
  scalar/array-stored → one column named `view_name()`) reach the glue as
  documented; a 2-parameter glue binds by edge handle, not by name.

### Stage 2 — identity
- `__glue` version key + `call_id` split.
- Virtual glue records, invocations, edges in `scidb/provenance_save.py`;
  exclusions in the `"latest"` collapse, `_current_records_by_schema`, load
  paths, and `scidb report`.
- **Tests**: editing a glue body recomputes the consumer; renaming glue is a new
  call site; unchanged glue → `skip_computed` still skips; input set grows →
  recompute; `upstream_provenance` shows the glue hop; a glue record is never
  returned by `load()`.

### Stage 3 — discovery + the new writable surface
- `scidb.discover.function_role(name)` — the shared four-way classifier (D6),
  at the existing discovery choke point, so test-exclusion covers glue for free.
  Refactor the three hardcoded `plot_`/`stat_` prefix sites onto it in the same
  stage; leaving them behind is how the strings drift apart.
- Role is carried on the discovered-function record so the GUI never re-derives
  it from the name.
- `config.glue_dir`, default `src/scistack_glue/`. This **widens the GUI's
  writable surface** from `entities_file` alone to `entities_file + glue_dir` —
  a deliberate amendment to `entity-editability-model.md`'s confinement rule.
  Still never a hand-written module.
- **Thread `glue_dir` through all four `_render_scistack_toml` call sites** — the
  documented trap where a new field is silently dropped on the next Paths save.
- **Tests**: TOML round-trip preserves `glue_dir`; a `glue_` function in a test
  file is excluded; a hand-written `glue_` function outside `glue_dir` is
  discovered read-only; `function_role` returns the right role for each prefix
  **and classifies `stats_summary` as `process`** (guards the singular-`stat_`
  spelling against exactly the confusion that prompted D6); the refactored
  `plot_`/`stat_` execution sites behave identically before and after.

### Stage 4 — MATLAB
- `for_each_prepare` returns `glue_chains`; `+scidb/for_each.m` applies MATLAB
  glue post-prepare, pre-loop, reusing the same hide/re-attach contract.
- `scidb:glue:rowsChanged` / `scidb:glue:languageMismatch` identifiers.
- **Tests**: file-level round-trip in Python; the runtime half needs a real
  MATLAB run by the user (the standing gap, same as `+scidb/Parameter.m`).

### Stage 5 — GUI
- `glueNode` as a functionNode variant (same `in__{param}` / `out__` handles, so
  `edge_resolver` needs no new branch — only a source-prefix case).
- Create / edit / delete services writing `glue_dir`; delete = hide, never
  unlink the file (project ethos).
- **On create, write the minimum that parses** and nothing more — the two-line
  `def glue_x(param): return param` / four-line MATLAB equivalent. No docstring,
  no comment block, no TODO. A one-line reshape must read as a one-line file.
- **The code editor panel is the primary surface** (D1a) — this is the stage's
  centre of gravity, not an add-on. Monaco, embedded in the node's settings
  panel, in **both** the VS Code extension and the browser: Monaco is a web
  component, so it highlights a buffer without needing the file open in an
  editor tab. (An earlier draft of this plan claimed files were needed for
  highlighting. They are not — the file earns its place on git/diff/breakpoint
  grounds alone.)
  - Python and MATLAB highlighting; save on blur/explicit save, then refresh the
    registry exactly as the entities-file write path does.
  - Live column list for the wired input alongside the editor (§5).
  - "Open in editor" link under the VS Code extension for anyone who wants the
    real file — available, never required.
- **Function-role dropdown on the Functions category** (D6): Process / Plots /
  Stats / Glue / All, defaulting to Process. Filters the sidebar list only —
  never the canvas, which shows whatever is wired.
  - **Show a count per role** (`Process (12) · Plots (3) · Stats (2) · Glue (7)`).
    This is what stops the default from hiding things: filtering to Process is a
    behaviour change from today's show-everything list, and without counts a
    user with existing `plot_` functions sees them vanish. With counts, nothing
    is invisible — only collapsed.
  - Remember the last selection per project (GUI state, same scoping precedent
    as `scistack-gui-scoped-hidden-state.md`); default to Process on first open.
    A glue-heavy session should not re-filter on every panel open.
  - Creating a function of a given role selects that role, so a just-created
    node is never filtered out of view.
- Per-node "iterate per schema key" toggle (D4).
- **No run button on the node, and no state badge** (D5); glue contributes a
  `glue_chains` entry to the target dict, never a `StepSpec`.
- **Tests**: handle-id contract test in the style of
  `TestHandleIdsMatchTheFrontend`; a glue node with no downstream consumer
  renders as inert rather than red; the per-node Run route refuses a glue node
  id instead of reporting a do-nothing success; `build_backend_pipeline` over a
  graph containing glue produces the same step count as the same graph without
  it; **panel round-trip** — edit body in the panel → file written → registry
  refreshed → consuming function's `__glue` hash changes → next run recomputes
  (the end-to-end version of the Stage 2 identity test, and the one a user will
  actually exercise); the role dropdown filters the list and not the canvas, and
  its counts stay correct with every role non-empty.

### Stage 6 — export
- `code_export_service` emits `df = glue_x(df)` inline before the consuming
  `for_each` in both languages.
- **Tests**: an exported script containing glue runs standalone and produces
  byte-identical records to the GUI run it was exported from (the existing
  export contract, extended to cover the fusion step); glue appears inline, not
  as a `for_each` step, matching §4.

---

## Diagnostics (NOTE 4)

The predicted confusing failure is "I edited my glue and nothing recomputed."
Ordered log trail to make it a two-minute read:

1. `[glue] '<param>': chain = [glue_a, glue_b] (hashes …)` at INFO on every run.
2. `[glue] virtual record <rid> for input <rid> (chain <hash>)` at DEBUG.
3. `[skip] '<fn>': binding '<param>' changed (<old rid> → <new rid>)` — the line
   that proves the glue edit propagated.
4. `[glue] '<param>': no glue chain` at DEBUG when the wiring was expected to
   carry one — catches an edge drawn to the wrong handle.

## Open risks

- **Node-state prediction.** `_predict_config_invocations` is "safe because it
  shares the one hash fn." Virtual glue rids must be predicted the same way the
  save path computes them, or nodes go falsely red. Highest-risk part of Stage 2.
- **Glue feeding two consumers** recomputes per consumer. Cheap for reshaping,
  accepted.
- **Glue → variable node** wiring is refused (no saved output).
- **Whole-table glue that depends on other rows** (e.g. mean-centering) is legal
  under the row-preservation contract and correctly captured by
  `input_set_signature`, but it is a computation masquerading as reshaping.
  Consider a WARN if a glue reads across rows — deferred, not in these stages.

## Out of scope

- Row-changing glue (use a function node with a saved output).
- Cross-language glue chains.
- Glue on PathInput-fed params.
- Persisting glue *data* in any form.
- Glue → variable node wiring (nothing to land).
- **Two storage forms** — a one-liner in GUI state *plus* files for multi-line
  glue. Two constructs for one concept is exactly the Constant/Sweep split that
  D6 of `entity-editability-model.md` deleted, and it would fork the hashing and
  MATLAB paths permanently.

---

## Rejected alternatives (preserve the reasoning)

Recorded because each will be re-proposed otherwise. Precedent for keeping these
in the plan file: `.claude/plan-gui-source-cohesion-26-08-24.md`.

### Storing glue code in GUI state / the database instead of files

**Asked directly by the user (2026-09-03): "writing files feels like overkill
for what can frequently be a one line command."** Rejected after costing it out,
but the objection was legitimate and produced D1a — the file became invisible
plumbing and the scaffolding was cut to nothing.

- **Python: roughly a wash.** You delete the discovery path (the scanner never
  needs to know about glue) and add a `compile()`/`exec()`-with-cache path.
  Hashing is unaffected — `compute_function_hash` reads `fn.__code__.co_code`,
  and an exec'd function has real bytecode.
- **MATLAB: the largest new risk in the feature.** MATLAB cannot define a
  callable, hashable, multi-line function from a string. `str2func` handles only
  anonymous single-expression functions, so one-liners would work and anything
  with two statements would not. The general solution is to write a temp `.m`
  to a scratch dir, `addpath`, `rehash` — i.e. **you write files anyway**, just
  ephemeral invisible ones plus a lifecycle, in the area that has already
  produced repeated cwd/path/rehash bugs.
- **Loses breakpoints.** The MATLAB terminal tier is explicitly preferred over
  the sidecar *because* it gives real breakpoints and workspace inspection
  (`entity-editability-model.md`, "Execution and staleness").
- **Loses git.** Glue is executable analysis logic. In a file it diffs, reviews
  and travels with the repo; in the `.duckdb` it does none of those. That cuts
  against README goal #3 (openness / no lock-in) and against the stack's own
  precedent — the entities TOML exists so declarations live in git, and the one
  thing deliberately kept in GUI state
  (`_pipeline_parameter_value_groups`) was justified as a *display* concern.
  Glue is not a display concern.

**Note for anyone re-reading the early drafts:** they claimed files were needed
for syntax highlighting. That was wrong — Monaco highlights a buffer in a
webview regardless of where the text came from. The file earns its place on
git/diff/breakpoint grounds alone.

### A separate "Glue" sidebar category

Rejected in favour of the D6 role filter. A sixth category in `EditTab.tsx`'s
strip would make glue a different *kind* of thing, when it is a function with a
role — the same mistake the Constant/Sweep split made. The filter also
retroactively tidies `plot_`/`stat_`, which the extra category would not.

### An edge-attached transform instead of a node

Rejected at D2. Keeps the canvas tidier but is strictly 1-in/1-out, cannot be
shared by two consumers, and needs a new resolution path in `edge_resolver`
rather than reusing the edges-only rule unchanged.

### Putting the declared name in `PathInput.to_key()`-style identity for glue

Not applicable, but the adjacent trap is worth naming: glue identity must be
**content-derived** (the hash), never the node's display name. Naming-based
identity would let two different glue bodies collide into one provenance node —
the same failure `entity-editability-model.md` documents for PathInput.
