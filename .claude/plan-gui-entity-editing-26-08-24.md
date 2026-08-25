# Plan: editable entities in the GUI, without giving up source-as-truth

Date: 2026-08-24
Supersedes the options doc `.claude/plan-gui-source-cohesion-26-08-24.md`
(kept for the rejected-alternatives record).
Status: **awaiting approval.**

## Decisions locked by the user (2026-08-24)

1. **GUI writes stay confined to the designated entities file**
   (`config.variable_file`, default `src/scistack_entities.py`) — minimal
   surprise. The GUI never edits a user's hand-written module.
2. **Implicit writes are acceptable** — a GUI edit may reach source without
   a separate explicit "commit" gesture.
3. **`export = eject`, `import = adopt`** — wiring/DAG round-tripping is out
   of scope.
4. **MATLAB and Python are equally necessary** — no Python-first pass.
5. **MATLAB gets a single entities file — a plain script**, one
   `NAME = scidb.Sweep(...)` line per entity, structurally parallel to
   Python. Not the one-getter-file-per-entity convention, and not a
   classdef container (see D1 below).
6. **`scidb.Constant` is added to `scimatlab`** as a real MATLAB class
   (see D2 below).

## Goal

Editing a Sweep's values, a PathInput's template, or a Constant's value from
the GUI rewrites the real declaration in the entities file and re-scans it,
so the file remains the single source of truth and the GUI stops being
read-only. Nothing new becomes authoritative; no overlay layer is added.

## Consequence of decision 1: two classes of entity, made explicit

An entity declared **in the entities file** is editable in the GUI. An
entity declared **anywhere else** stays read-only, permanently and by
design. That is the contract, not a gap to close later.

Today's read-only panels give a generic hint ("edit the declaration in
source"). Since Stage 1 computes the exact declaration location anyway, the
read-only case gets strictly better:

> `WINDOW_SECONDS` is declared in `src/analysis/params.py:42` — edit it
> there and hit 🔄 Refresh Code.

with a click-to-open link when the VS Code extension is the host.

**Explicitly rejected: an "Adopt into the entities file" action.** Moving a
declaration requires deleting it from the user's file (violates decision 1);
copying it creates a duplicate name across two scanned modules, which
`_register_constant`'s last-loaded-wins-with-a-warning path resolves
arbitrarily.

**Superseded 2026-08-25 — value getters were removed entirely** (see the
Stage 3 follow-up below). An interim version of this rule kept them as a
read-only discovery path; the paragraph below records that reasoning, but
the getter mechanism no longer exists.

~~This same rule absorbs the existing MATLAB value getters at zero
conceptual cost: a getter file is simply "declared outside the entities
file" → read-only, exactly like a Python hand-written module. Existing
MATLAB projects keep working, discovery is unchanged, nothing is deleted
(`feedback_never_delete_mark_hidden`), and no second *writable* convention
is introduced.~~

The read-only concept itself is unaffected by the removal: it is carried by
Python declarations outside `variable_file`, and on the MATLAB side by a
folder-scan-discovered entities script that isn't the configured
`entities_file`.

## Consequence of decision 2: no staging layer at all

Since implicit writes are sanctioned, the git-index/staging model from the
options doc is dropped entirely:

**edit committed in the panel (blur/Enter) → write source → refresh registry
→ broadcast `dag_updated`.**

Exactly the shape `target_file_service.append_and_refresh` already
implements for creation, with a splice instead of an append. No
`_pipeline_pending_*` table, no dirty state, no commit-on-run hook, no "run
with uncommitted edits" question. Every recorded run still corresponds to
source that existed on disk — the invariant the original migration was
protecting.

---

## D1 (resolved) — MATLAB's entities file is a plain script

The getter convention is not forced. Neither is a classdef container (an
earlier draft of this plan proposed one; the user correctly cut it as
overcomplicated). The entities file is a **script**: one top-level binding
per line, a direct line-for-line analogue of the Python file.

```matlab
% scistack_entities.m
% Auto-created by the SciStack GUI -- new Sweep/PathInput/Constant
% declarations created from the GUI are appended here.
test_path_input = scidb.PathInput('{subject}/{subject}_{session}.csv');
test_sweep      = scidb.Sweep(0, 1, 2);
test_const      = scidb.Constant(2);
```

Pipeline code runs `scistack_entities;` and the names are in scope — the
ordinary MATLAB idiom for a script of parameter definitions.

**Why getters exist today:** MATLAB has no module-level variable bindings,
so Python's `NAME = scidb.Sweep(...)` has no translation *as an importable
binding*. A zero-arg function returning the constructed object was the
workaround (`code-discovery-categories.md` §4/§5). But the GUI never needed
an importable binding — it needs a **statically parseable declaration**,
and a script line is exactly that.

This collapses the design rather than adding to it:

- **One grammar concept, two syntaxes.** "Top-level binding of a
  construction call" is the same rule in both languages; only the surface
  syntax differs. Stage 1's Python `find_binding_span` and Stage 2's MATLAB
  span extraction become the same shape.
- **No caching caveat.** The classdef draft needed a `clear classes`
  mitigation, because `properties (Constant)` are evaluated once per
  session. A script is re-read every time it runs, so a GUI write-back is
  live immediately with no mitigation anywhere.
- **No scanner-ordering wrinkle.** The classdef draft collided with the
  existing rule that *any* `classdef` file is never scanned for
  functions/getters, so the entities class would have had to be recognized
  before that short-circuit. A script has no `function` and no `classdef`,
  so `classify_matlab_file` currently returns `None` for it — adding an
  "entities script" classification collides with nothing.

The classes already exist: `+scifor/PathInput.m`, `+scifor/Sweep.m` and
`+scifor/EachOf.m` are real, shipped MATLAB classes, and `Sweep < EachOf`,
so every `isa(x, 'scifor.EachOf')` check in `+scidb/for_each.m` picks a
Sweep up unchanged.

### Namespace

`+scidb/` ships no `PathInput.m` / `Sweep.m` — only `+scifor/` does — even
though `matlab_parser`'s regexes already accept a `scidb.` prefix. Since
the entities file is written as `scidb.Sweep(...)` / `scidb.PathInput(...)`
for parity with Python, add two one-line subclass shims,
`classdef Sweep < scifor.Sweep` and `classdef PathInput < scifor.PathInput`
in `+scidb/`. Inheritance keeps every `isa` check working, and the two
languages' entities files then read identically.

## D2 (resolved) — `scidb.Constant` becomes a real MATLAB class

Closes `code-discovery-categories.md` §3's "MATLAB has no equivalent" and
gives MATLAB constants the source-declared *identity* they lack today.

- **`+scidb/Constant.m`** — a value holder (`value`, optional
  `description`), constructed `scidb.Constant(30)` /
  `scidb.Constant(30, 'description', '...')`.
  Deliberately **not** a full operator-overloading proxy: Python's
  `Constant` proxies attribute/operator access so it reads naturally in
  arbitrary user code, but a MATLAB constant's only real entry point is the
  `for_each` constants struct. A holder plus unwrapping at that boundary
  covers the actual use, and avoids a fragile `subsref`/arithmetic-overload
  surface.
- **`+scidb/for_each.m`** unwraps `scidb.Constant` wherever a plain value is
  accepted.
- **Provenance parity is a hard requirement**: the value recorded into
  `version_keys` must be byte-identical to what Python records for the same
  constant, or the same pipeline run from MATLAB and from Python diverges in
  history. Test this directly, in the spirit of
  `project_matlab_gui_hash_recipes_agree`.
- **Discovery**: scan the entities classdef's `properties (Constant)` block
  for `= scidb.Constant(...)` and register into the shared
  `scistack_gui.registry` via the existing `_register_constant` path — the
  same way MATLAB PathInputs/Sweeps already register through
  `_register_path_input`, so nothing downstream needs MATLAB branching.

## D3 (new, user-requested 2026-08-24) — the GUI drives a MATLAB engine

**Correction to an earlier statement in this plan's discussion:** the claim
that GUI-driven MATLAB execution is only "generated commands the user
pastes, with no engine the GUI controls" was wrong. A GUI-controlled,
kept-warm MATLAB process already exists.

### What already exists

`scistack_gui/matlab_sidecar.py` — `MatlabSidecar`, a lazily-started
`matlab -nodesktop -nosplash -nodisplay` process driven over its own
stdin/stdout REPL, with:

- a sentinel protocol (`__SCISTACK_SIDECAR_DONE__` /
  `__SCISTACK_SIDECAR_ERROR__`) wrapping every command in an outer
  try/catch, so completion and failure are unambiguous;
- a background reader thread relaying stdout line-by-line, surfaced as real
  `run_output` / `run_done` websocket messages (`api/run.py`
  `_run_matlab_pipeline_in_thread`);
- cancellation by killing the process (`force_cancel_run`), with the queue
  drained so the next `start()` begins clean;
- `sidecar_capable()` for a cheap up-front availability check.

It is wired as **Tier 3 of a fallback ladder**
(`.claude/plan-matlab-pipeline-execution.md` Stage 4): MathWorks VS Code
extension available → Tier 2 terminal; else `matlab` on PATH → sidecar;
else → copy-paste command.

The generated command is already self-contained — `api/matlab_command.py`
emits a guarded `pyenv` preamble plus `addpath` entries before any `py.*`
call — so the same text works identically across all three tiers.

### What the user wants changed

The engine should be the **primary** execution path, not the third rung of
a fallback ladder that only fires when the MathWorks extension is missing.

### Resolved sub-decision (user, 2026-08-24)

**Tier 2 stays preferred inside VS Code.** The MathWorks terminal gives a
visible MATLAB session with breakpoints, workspace inspection and the
user's own scrollback — a real debugging affordance an invisible sidecar
cannot offer.

This resolves the ladder question by **leaving the existing ordering
untouched**: MathWorks extension → terminal; else `matlab` on PATH →
engine; else copy-paste. No reordering, no user-facing setting, no tier
selection work at all.

So "the GUI controls a MATLAB engine" scopes precisely to **the
browser/standalone context, plus VS Code without the MathWorks extension**
— exactly where the sidecar already serves. What is missing there is not
routing but **robustness**: the sidecar was built as a rarely-hit fallback
and is not yet good enough to be someone's normal way of running MATLAB.
That, and only that, is Stage 9's scope.

### Why this matters to *this* plan specifically

The sidecar is **kept warm**, so its workspace persists across commands.
After a GUI write-back to `scistack_entities.m`, a warm session would still
hold the old `test_sweep` value.

The script form chosen in D1 makes the fix trivial: re-running the script
rebinds every name from the file's current contents. So the generated
command gets a `scistack_entities;` line right after its `addpath` block —
one place (`api/matlab_command.py`), serving all three tiers identically,
idempotent, and correct even if the sidecar just restarted. No `clear`, no
cache invalidation, no write-back→session notification channel.

This is the concrete payoff of D1's script-over-classdef choice: with
`properties (Constant)` a warm engine would have needed explicit cache
clearing on every edit.

### Known risk

`matlab_sidecar.py`'s own docstring records that **no real MATLAB
environment existed when it was written** — it is covered only by mocked
`subprocess.Popen` tests. Promoting it to the primary path means its first
real-world exercise is also the default experience. Stage 9 therefore
carries a real-MATLAB verification gate, run by the user
(`feedback_user_runs_tests`).

## D4 (edge case, user-raised 2026-08-24) — adding a second value to a Constant changes the *source form only*

Scenario: `test_const = scidb.Constant(2);` exists in the entities file; in
the GUI the user adds a second value so the function node fans out over
both.

In **source** this changes the entity's form. `scidb.Constant` is
single-valued by definition (in Python it proxies the one wrapped value);
`scidb.Sweep` — sugar for `EachOf` — *is* the multi-value concept. So there
is no coherent "Constant with two values" to write. Rejected alternatives:
making `Constant` variadic (duplicates Sweep and breaks Python's value
proxying), or holding the extra value in an overlay (the
two-sources-of-truth model this plan exists to avoid).

In the **GUI** nothing moves — see D6. The two kinds are presented as one
"Parameter" concept, so the node keeps its identity, its position and its
tab; only the emitted line changes.

### What happens in the script

The declaration is rewritten in place — same name, same line:

```matlab
test_const = scidb.Constant(2);     % before
test_const = scidb.Sweep(2, 5);     % after
```

**This needs no new machinery.** `find_binding_span` (Stage 1) locates the
*whole RHS* — the entire call expression, constructor included — so
swapping `Constant(2)` for `Sweep(2, 5)` is the same splice as changing a
value, with `render_sweep` instead of `render_constant`. Identical on the
Python side.

### What happens in the GUI

Nothing relocates. Under D6 the node is a Parameter node before and after;
its id, position, tab and per-value controls are untouched. The value list
gains a row, exactly as it would on a Sweep that already had two values.

**Run history survives — no recompute.** `EachOf` is resolved at the top of
`for_each()` by expanding into recursive calls with concrete values, so
*all* downstream machinery (version_keys, branch_params, rid expansion)
only ever sees the scalar `2` — identical whether it arrived as a Constant
or as one arm of a Sweep
(`docs/claude/each-of-variant-expansion.md`). The already-computed combo
for `2` stays green; only the new value `5` actually runs. This holds by
construction rather than by coincidence, but **assert it in a test anyway**
— it is the load-bearing assumption of the whole merge.

### Silent is fine here

An earlier draft proposed a "Convert to Sweep" confirmation, on the
grounds that changing an entity's *kind* is a bigger deal than changing its
value. D6 removes that reasoning: from the user's side no kind changes at
all, so the write is as implicit as any other value edit (decision 2). The
new source line is visible in the panel; no dialog.

### The reverse direction

Deleting a Sweep back down to one value **does not** convert back to
`Constant`. A one-element Sweep is valid and behaves identically, and
auto-converting in both directions would make the source churn under the
user as they edit. Converting back stays a deliberate action if it is ever
wanted at all.

## D5 — the same logic across every entity kind

D4 generalizes. There is **one axis**: a declaration is either single-valued
or `EachOf`-wrapped multi-valued, and "add a value" always means wrapping.

| GUI concept | Single form | Multi form | Node changes? |
|---|---|---|---|
| **Parameter** | `scidb.Constant(2)` | `scidb.Sweep(2, 5)` | no (D6) |
| **Path Input** | `scidb.PathInput(t1)` | `scidb.EachOf(scidb.PathInput(t1), scidb.PathInput(t2))` | no |
| Variable | *(a type, no value)* | — | — |

Constant's multi-form is a different class only because `Sweep` **is** the
named `EachOf` sugar for scalars; PathInput has no such sugar, so it wraps
explicitly. Both are the same operation underneath. The
`EachOf(PathInput(...), ...)` rendering already exists —
`path_input_service.create_path_input`'s `alternate_templates` emits
exactly it, so `render_path_input` covers the multi case for free.

### Rule 1 — adding a value is always additive and never orphans history

Prior run history keeps resolving in every case, and under D6 the node
never changes identity for any kind — a Parameter stays a Parameter whether
it emits `Constant(2)` or `Sweep(2, 5)`, and the registry scanner already
accepts "an `EachOf` whose every alternative is a `PathInput`" as a
PathInput. Same node id, same position, same tab, same controls,
throughout.

### Rule 2 — editing a value in place is safe for Constant/Sweep, destructive for PathInput

This is the real asymmetry, and it is not obvious from the UI:

- **Constant / Sweep**: run history is keyed by the *concrete value* in
  `version_keys`, and the node displays every historical value alongside
  the current source value. Editing `2` → `5` adds a value row; the runs
  recorded against `2` stay visible and stay green. **Non-destructive.**
- **PathInput** *(as things stand today)*: identity in history is resolved
  by **content-matching the template**, because `PathInput.to_key()`
  serializes only template/root_folder and never the bound name
  (`graph_builder.resolve_path_input_name`). Editing the template means no
  registry entry matches the old recorded value any more, so every prior
  run collapses to a synthetic `__unresolved__:{old_template}` node with a
  WARN — destructive to traceability, though the data itself is untouched.

**D7 removes this asymmetry** rather than warning about it: a GUI-owned
name↔value history lets prior runs keep following their node across a
template edit. With D7 in place, Rule 2 reads the same for every kind —
**editing in place is non-destructive, full stop** — and no confirmation
dialog is needed anywhere.

Adding an alternate template never had the problem in the first place: the
original template still content-matches, so its history is preserved.

### Rule 3 — removing a value never unwraps

A Sweep pared back to one value stays a one-element Sweep; an
`EachOf(PathInput(...))` pared back to one stays wrapped. Behaviour is
identical either way, and auto-unwrapping would make the source churn as
the user edits (D4's reverse-direction rule, generalized).

### Variables are not editable

A Variable is a *type*, not a value — there is nothing to splice. Renaming
one is a genuinely different operation (run history is keyed by the type
name, so a rename orphans records far more severely than a PathInput edit),
and is out of scope here. Variables stay create-only, as they are today.

### D7 — fixing the PathInput orphaning (in scope)

**First: the provenance half of this behavior is correct and must not
change.** An earlier draft of this plan (and
`entity-editability-model.md`'s first version) suggested recording the
bound name in `PathInput.to_key()`. That would be a bug:

- `to_key()` feeds `version_keys` and
  `provenance.compute_pathinput_record_id(spec)`, which content-addresses
  the PathInput's **node in the bipartite provenance graph**
  (`_sha16(PATHINPUT_TYPE, f"spec:{spec}")`).
- `foreach_config._serialize_inputs` spells out why: without a
  content-derived identity "two different templates would collapse into the
  same version-key group."

Keying on the name would make two runs with the same name and different
templates collide into one provenance node — exactly the failure that
comment guards against. A template change **is** a different input, so a
different provenance node, and no cache hit, is right.

**The actual defect is attribution, not identity.** The GUI uses the
provenance key as the *only* way to decide which canvas node a historical
run belongs to (`graph_builder.resolve_path_input_name` content-matches
template+root_folder against the registry). That conflates "what computed
this" with "which node should display it" — and it is a pure GUI concern,
fixable with no scidb change at all.

#### The fix: a GUI-owned name↔value history

New GUI-owned table (same family as `_pipeline_hidden_*`):

```
_pipeline_path_input_history (pipeline_id, name, template, root_folder)
```

Append-only, deduped on the full tuple, never deleted
(`feedback_never_delete_mark_hidden`).

Populated from **two** moments, which together cover both edit paths:

1. **On every registry scan** — record each currently-declared
   `(name, template, root_folder)`. Cheap (a handful of rows per Refresh
   Code), and it means a template the GUI has *ever seen* under a name is
   remembered. This is what covers edits made directly in source: the
   pre-edit template was already recorded by the previous scan.
2. **On write-back** (Stage 5) — record the previous value before splicing.
   Redundant with (1) in the normal case, but exact, and it covers a value
   that never survived a scan.

`resolve_path_input_name` then resolves in order:

1. content-match against the live registry (current behaviour, unchanged) →
   current source value;
2. else content-match against `_pipeline_path_input_history` → attribute to
   that name, flagged as a **historical** value;
3. else `__unresolved__:{template}` + WARN — now genuinely rare, and
   meaning what it was designed to mean (declaration removed or renamed
   beyond recognition).

#### What this buys

- **Template edits stop orphaning history.** The node keeps its prior runs.
- **PathInput finally obeys the same display rule as Parameters** — the node
  shows historical values alongside the current source-declared one
  (decision #2 of `.claude/plan-constant-source-of-truth-26-08-22.md`),
  which until now it structurally could not.
- **Renames are covered by the same table**, from the other direction: a
  renamed declaration keeps the same template, so strategy (1) still
  matches. Name-change and template-change are each recoverable; only
  changing both at once is genuinely unresolvable, which is correct.
- **No migration.** Pre-existing history has no recorded name and falls
  through to strategy (1)/(3) exactly as today.

#### Consequence for D5's Rule 2

The "stronger confirmation for replacing a PathInput template" becomes
**unnecessary**. Once history follows the node, a template edit is as
non-destructive as a Parameter value edit, and needs no dialog. Rule 2's
asymmetry disappears rather than being papered over with a warning.

#### Accepted limitation

The GUI can only remember values it has observed. A template edited *and*
renamed in source between two Refresh Code cycles — so the GUI never saw
the intermediate state — still orphans. Correct behaviour for a genuinely
untraceable change, and it logs at WARN.

## D6 (decided by user 2026-08-24) — Constant and Sweep merge into one GUI concept: **Parameters**

### The problem it solves

`EditTab.tsx` groups entities into six categories behind an icon tab strip
(Submodules, Functions, Variables, Constants, Path Inputs, Sweeps). Under
D4's source-form change, adding a second value would make an entity vanish
from **Constants**, reappear under **Sweeps**, and change node type on the
canvas — for what the user experiences as "I added a value." Unacceptable.

### The decision

**Constant and Sweep are one GUI concept, labelled "Parameters."** A
Parameter is a named thing with one or more values. The *source form*
follows from the value count and is otherwise invisible as a distinction:

- 1 value → `scidb.Constant(v)`
- N values → `scidb.Sweep(v1, ..., vN)`

The six-category tab strip becomes five: Submodules, Functions, Variables,
**Parameters**, Path Inputs.

### Why this is the right direction, not just the kinder one

`build_constant_nodes` **already** renders multiple value rows per constant
node, with per-value checkboxes and the `is_current_source_value` badge
(`89f4f35`). The constant node is already a multi-value widget;
`build_sweep_nodes` is the impoverished one (`{label, values}` — no
`checked`, no history rows). So the merge direction is "sweeps adopt the
constant node's model," not a new invention.

It also makes the entity model uniform: **every node type is stable, and
only the number of values varies** — which is already true of PathInput,
whose node stays a PathInput whether it holds one template or an `EachOf`
of several.

### It removes work rather than adding it

Three items from D4's earlier draft disappear entirely, because they were
all consequences of the node changing kind:

- position carry-over across an id change,
- the per-value-checkbox regression on conversion,
- the historical-value display rule diverging between node types.

### Costs, accepted

- **Vocabulary.** A user who writes `scidb.Sweep(...)` will look for a
  "Sweeps" tab and find "Parameters". Mitigated by the panel showing the
  actual declaration; the API names are unchanged in source.
- **Node-id migration.** `const__{name}__{suffix}` (placement-qualified)
  and `sweep__{name}` + scope must merge into one scheme, with a layout
  migration for existing position keys. Precedent:
  `placements_migrated` / `pipeline_db_migrated` sentinels in
  `*.layout.json`.
- **A mild source/UI mismatch** — one GUI concept, two source
  constructors. Judged acceptable: it is just "one value vs many," and the
  panel shows the emitted line.

## Open questions — now resolved

### Is `_pipeline_pending_constants` vestigial?

**Mostly, but not entirely — keep it, narrow it, document the narrowed
role.** Pending constants existed because constants had no source home
worth editing: MATLAB had no `Constant` concept at all, and a never-run
Python constant needed somewhere to stage a value. D2 removes the first
reason and in-place editing removes the second — "try a value" is now just
an edit.

What genuinely remains: a MATLAB (or Python) `for_each` call that passes an
**inline, unnamed literal** in its constants struct has no named declaration
to edit. `pipeline_discovery.py` surfaces exactly these as constant nodes
with a staged pending value, and that path stays valid.

So: role narrows from "the constant staging mechanism" to "values for
inline, unnamed constants discovered from source or history". Don't remove
it (`feedback_never_delete_mark_hidden`); re-evaluate after Stage 8 with
real usage.

### Should `scimatlab` grow a real `scidb.constant`?

**Resolved: yes** — that is D2, now in scope rather than deferred. It also
upgrades the MATLAB story from "getter convention" to real identity, which
is what made D1's single entities file worth doing.

### `matlab.variable_dir` → `entities_dir` rename friction

**Resolved: no rename. Add a separate field instead.** The earlier plan
proposed renaming `variable_dir` → `entities_dir`; D1 makes that wrong.

MATLAB `BaseVariable` subclasses are *types*, and MATLAB requires one
public classdef per file named after the file — they **cannot** live in the
entities script. So the two settings serve genuinely different purposes and
both must exist:

| Setting | Hosts | Shape |
|---|---|---|
| `[matlab] variable_dir` (existing, unchanged) | `BaseVariable` classdefs | one file per variable |
| `[matlab] entities_file` (**new**) | Sweeps, PathInputs, Constants | one shared script |
| `[tool.scistack] variable_file` (existing, Python) | all four kinds | one shared module |

No breaking rename, no `_render_scistack_toml` round-trip hazard beyond
adding one field to it — but that field **must** be added there in the same
stage, or the Paths popup will silently drop it on every save (the exact
bug that function has already had once).

Optional consistency tidy, low priority: Python's `variable_file` is
already a misnomer (it hosts all four kinds and defaults to
`scistack_entities.py`). Renaming it `entities_file` is sanctioned by
`feedback_beta_no_deprecation`, but it touches the bootstrap wizard,
`config.py`, `api/bootstrap.py`, `api/project.py` and the frontend
placeholder — worth doing as its own commit, not folded into this plan.

---

## Architecture / layering (CLAUDE.md NOTE 3)

Split by *who owns the grammar* vs. *who owns the policy*:

- **`scidb`** owns what a declaration looks like, because it defines
  `constant()`, `Sweep`, `PathInput`. New pure module
  `scidb/src/scidb/source_edit.py`:
  - `find_binding_span(text, name) -> Span | None` — locate the RHS of the
    top-level `Assign`/`AnnAssign` binding `name` via `ast`
    (`lineno/col_offset/end_lineno/end_col_offset`), as absolute character
    offsets.
  - `render_constant/render_sweep/render_path_input(...) -> str` — the
    `repr()`-based emitters, extracted from the **two** hand-written copies
    in `constant_service.create_constant` and
    `path_input_service._path_input_call`/`create_sweep`
    (`feedback_avoid_scifor_scidb_duplication`). *Correction to an earlier
    draft, which said three:* `code_export_service._py_literal` is **not** a
    third copy — it delegates to each object's `__repr__`. See the note
    under Stage 1 for the latent wart that leaves behind.
  - `splice(text, span, replacement) -> str`.
  No I/O, no GUI imports.
- **`scistack_gui/matlab_parser.py`** owns the MATLAB grammar (the scan
  already lives there). Gains top-level-binding parsing for the entities
  script and span-returning extraction. (Arguably this module belongs in
  `scimatlab`; that move is not in scope.)
- **`scimatlab`** owns `+scidb/Constant.m` and the `for_each` unwrap — the
  MATLAB-runtime half of D2.
- **`scistack_gui/services/target_file_service.py`** owns policy: is this
  entity in the designated entities file, is the file unchanged since the
  graph was built, write atomically, re-scan, verify, log.

## Stages

### Stage 1 — `scidb.source_edit` (Python grammar, pure) — **DONE, uncommitted (2026-08-24)**

`scidb/src/scidb/source_edit.py`: `Span`, `find_binding_span`, `splice`,
`render_constant`/`render_sweep`/`render_path_input`. Pure — no I/O, no
registry, no GUI imports. Repointed `constant_service.create_constant`,
`path_input_service.create_path_input` and `create_sweep`;
`_path_input_call` deleted from the GUI layer. Tests:
`scidb/tests/test_source_edit.py` (24 cases). **Not yet run by the user.**

Decisions made while building it, worth not re-deriving:

- **The span covers the whole RHS expression**, not the literal inside the
  call. That is what makes D4/D5's form change (`constant(2)` →
  `Sweep(2, 5)`) the *same* operation as a value edit, with no special case.
- **`ast` reports `col_offset` as a UTF-8 byte offset**, not a character
  offset. A naive character-index conversion silently mislocates the span
  on any line containing non-ASCII — and a splice at a wrong offset
  corrupts the file. `_char_offset` re-encodes the line to convert.
  Regression tests cover non-ASCII both inside the declaration and on an
  earlier line.
- **Last top-level binding wins** on rebinding, matching what discovery
  sees (`vars(module)` after import). Chained (`a = b = ...`) and tuple
  targets return `None` — there is no single RHS belonging to that name.
- **Syntax errors return `None`**, so a half-written file degrades to "not
  editable" rather than raising into the caller.
- `render_*` take a `qualifier` argument (default `"scidb."`) because an
  entities file needs the qualified form — `ensure_scidb_import` only
  guarantees a bare `import scidb` — while a generated standalone script
  imports names directly.

**Latent wart, deliberately not fixed here:** `code_export_service._py_literal`
relies on `__repr__`, and `Sweep` inherits `EachOf.__repr__`, so an exported
script renders a Sweep as `EachOf(0, 1, 2)` — losing the declaration form.
`Constant.__repr__` likewise emits `Constant(...)`, which is not even the
public factory (`scidb.constant`). Harmless today (the export preamble
imports `EachOf`/`PathInput` directly and `EachOf` is semantically
equivalent), but the reprs are load-bearing for export output and should
eventually route through `render_*` too. Doing it now would change exported
script output, which is outside this stage's refactor-only remit.

### Stage 2 — MATLAB span extraction (prerequisite fix) — **DONE, uncommitted (2026-08-25)**

`matlab_parser.py`: `_preprocess_for_parsing` is now length-preserving;
`_getter_context` returns a `_GetterContext` dataclass carrying
`body_start` and the decoded `text`; `_extract_call_args` is now a thin
wrapper over a new `_extract_call_args_span`; new public
`extract_path_input_span` / `extract_sweep_span` / `read_source_text`.
`scidb.source_edit` gained `line_number(text, offset)` — language-agnostic,
used by both sides for "declared in `foo.m:5`" messages. Tests:
`test_matlab.py::TestPreprocessingIsLengthPreserving` and
`::TestValueGetterSpans`, plus two `line_number` cases in
`test_source_edit.py`. **Not yet run by the user.**

Decisions made while building it:

- **Block comments are masked to spaces but keep their newlines**; line
  continuations are masked *including* the newline. The asymmetry is
  deliberate: blanking a block comment in place preserves line numbering,
  while a continuation must still collapse onto one logical line or `...`
  and the next line's indentation leak into captured parameter names (the
  behaviour `TestLineContinuation` pins).
- **`Span` is imported from `scidb.source_edit`**, not redefined — one span
  type across both languages, so Stage 5's write-back can be generic. Safe
  at module level: `registry.py` and `db.py` already import `scidb` that
  way and `scistack-db` is a declared dependency.
- Spans are returned in **absolute offsets into the file's decoded text**,
  which is only meaningful because of the length-preservation fix — hence
  `read_source_text`, so callers slice the same string the span was
  computed against.

**One deliberate behaviour change, untested either way before or after:** a
block comment sitting *between* a function signature and its help text used
to be deleted, joining the help text onto the signature so
`_extract_docstring` found it. It now becomes blank lines, and
`_extract_docstring` stops at the first blank line — so that docstring
comes back `None`. This is arguably the more correct reading (MATLAB's own
`help` stops at a blank line, which the extractor explicitly mirrors), and
no test covers the case in either direction, but it is a real difference
worth knowing if a docstring ever goes missing.

#### Original plan text, for reference

`_preprocess_for_parsing` currently **deletes** text (block comments →
`""`, line continuations → `" "`), so offsets into the preprocessed body do
not map back to the real file — span-based write-back is impossible until
this changes.

Fix: make it **length-preserving** — substitute an equal number of spaces
instead of removing. Every existing regex behaves identically (they only
search for declarations and construction calls; runs of spaces are inert),
and offsets become directly usable against the original text. Line numbers
for user-facing messages come from the original text via the offset, so
collapsing a continuation's newline is harmless.

Then: `_getter_context` returns the body's absolute start offset alongside
`(fn_name, body)`, and new `extract_*_span` helpers return the
argument-text span of the construction call — reusing `_extract_call_args`'
existing paren-matching scan, which already computes those indices and
currently discards them.

Tests: `len(_preprocess_for_parsing(t)) == len(t)` for block comments,
continuations, and both; spans point at the right substring for a getter
with a leading help block, a block comment above the call, and a continued
argument list; **every existing `matlab_parser` test passes unchanged** —
this is the regression risk of the whole plan, since this function sits
under all MATLAB discovery.

### Stage 3 — MATLAB entities script (D1) — **DONE, uncommitted (2026-08-25)**

`matlab_parser`: `MatlabBinding`, `parse_matlab_entities_script`,
`is_matlab_entities_script`, `binding_path_input_literal` /
`binding_sweep_literal`, and `classify_matlab_file` gains an
`("entities_script", path)` result. `matlab_registry`:
`load_entities_script`, plus `_register_matlab_path_input_object` /
`_register_matlab_sweep_object` factored out so the getter path and the
entities path produce identical registrations. `config`:
`matlab_entities_file` (`[matlab] entities_file`), wired through
`load_config` and all four `_render_scistack_toml` call sites.
`+scidb/Sweep.m` and `+scidb/PathInput.m` subclass shims. Tests:
`test_matlab.py::TestParseMatlabEntitiesScript` (18 cases),
`::TestLoadEntitiesScript` (6), `test_config.py` (3). **Not yet run.**

Decisions made while building it:

- **The entities-script check runs LAST in `classify_matlab_file`.** It is
  the only classification requiring neither `function` nor `classdef`, so
  everything else has already been ruled out and it cannot steal a file
  from an existing category. A regression test pins that a value getter
  still classifies as `sweep`, not `entities_script`.
- **The entities script loads AFTER the getter files** in
  `load_from_config`, so on a name collision the entities script wins — it
  is the file the GUI writes, so it must be the one the GUI displays.
- **`_matching_paren` extracted** from `_extract_call_args_span` and made
  offset-based, so the entities parser scans many calls in one file without
  copying the remainder of the text per call.
- **`_BINDING_RE` excludes `==`** so a comparison in a script is not read as
  a binding; `_statement_end` scans for a top-level `;`/newline outside
  quotes and brackets, because MATLAB's `;` is optional and only suppresses
  echo.
- **A non-entity line is skipped silently.** An entities script is allowed
  to contain ordinary MATLAB (`n = 5;`); only a *malformed* entity
  declaration warns.
- **A missing `entities_file` is not an error** — the GUI creates it on
  first write, so "configured but not yet created" is a normal state.
- `_path_input_args_to_literal` / `_sweep_args_to_literal` are shared
  helpers rather than duplicated per declaration form.

#### Stage 7 follow-up — Parameter class replaces Constant + Sweep (2026-08-25)

User-directed after Stage 7 landed: the presentation merge left the SPLIT
intact underneath (two source constructs, two registries, two scanners, a
`source_kind` field). Replaced by one real class.

`scidb.Parameter(EachOf)` with varargs, `description`, `.values`/`.value`,
and the single-value transparent proxy. `scidb.constant`/`Constant` and
`scifor.Sweep` deleted. One `is_parameter`, one `_parameters` registry, one
`_scan_module_parameters`, one `build_parameter_nodes(source_parameters=)`,
one `parameter_service`, one `/api/parameters` route family, one
`ParameterNode.tsx`. MATLAB: `+scidb/Parameter.m` subclassing
`scifor.EachOf`; `Constant.m`, `+scidb/Sweep.m`, `+scifor/Sweep.m` deleted,
and Stage 4's explicit unwrap loop in `for_each.m` removed (the EachOf path
handles it).

The load-bearing fact: **EachOf expansion has no branch for a single
alternative**, so `Parameter(30)` records byte-identical `version_keys`/
`call_id` to a bare `30`. Verified in `foreach.py` and pinned by a test.
That is what makes D4 disappear as a concept — there is no form change, so
no conversion, no confirmation dialog, no position carry-over.

**Six real product bugs surfaced while doing it**, each now covered by a
regression test:

1. `_infer_wired_constants` used `.value`, taking ONE value of a fan-out —
   would have silently turned a multi-combo run into a single one.
2. `Parameter.__hash__` hashed the alternatives tuple, so `Parameter(42) ==
   42` was True while their hashes differed — silently breaking every
   dict/set lookup.
3. `__getattr__` raised `TypeError` for multi-valued Parameters;
   `hasattr()` only swallows `AttributeError`, and `foreach._is_loadable`
   probes with `hasattr(var_spec, "load")` — every `for_each` carrying one
   would have crashed.
4. `registry._scan_module_path_inputs` still referenced the removed `Sweep`
   at runtime — one `NameError` that broke every module import.
5. `_format_sweep` emitted `scifor.Sweep(...)`, a MATLAB class that no
   longer exists — every generated command with a multi-valued parameter
   would have failed at paste time.
6. Exported Python scripts printed `Parameter(...)` via `repr()` but the
   generated header did not import it — `NameError` on every export.

**The checkbox filter** (Stage 7 follow-up, user-requested): unchecking a
value now reaches EXECUTION for multi-valued Parameters, not just display.
Scalars were already filtered upstream by
`filter_hidden_constant_value_targets`, but a multi-valued Parameter is
handed to `for_each` whole and fanned out inside scidb, where the GUI's
hidden state is invisible. `build_run_inputs` now filters and rebuilds
`Parameter(*kept)`; unchecking EVERY value raises rather than running the
full set. `_is_hidden_value` matches int/float spellings both ways —
without that, a value declared `20` arriving as `20.0` never matched a
hidden `'20'` and the checkbox silently did nothing.

#### Stage 3 follow-up — value getters removed entirely (2026-08-25)

Decided after the stage landed: keeping getters as a read-only discovery
path meant **two discovery conventions for one concept**, which contradicts
`feedback_beta_no_deprecation` and buys nothing — the read-only concept is
already carried by Python declarations outside `variable_file` and by a
folder-scan-discovered entities script that isn't the configured
`entities_file`.

Deleted: `_getter_context` / `_GetterContext`, `_parse_value_getter`,
`parse_matlab_path_input` / `parse_matlab_sweep`,
`extract_path_input_literal` / `extract_sweep_literal`,
`extract_path_input_span` / `extract_sweep_span` / `_getter_args_span`,
`_PATHINPUT_VALUE_RE` / `_SWEEP_VALUE_RE`, `_extract_call_args` /
`_extract_call_args_span` (both became unused once the entities parser used
`_matching_paren` directly), the `_register_matlab_path_input` /
`_register_matlab_sweep` wrappers, the `matlab.path_inputs` / `matlab.sweeps`
config fields and their `load_config` / `_render_scistack_toml` handling and
dedupe pass, and the two `classify_matlab_file` / `load_from_sources`
branches. Five test classes removed.

Kept and adapted:
- `_matlab_path_inputs` / `_matlab_sweeps` and
  `_deregister_stale_matlab_path_inputs_and_sweeps` — they now track
  entities-script declarations, and the deregistration test was converted
  rather than deleted (it guards a real bug: a removed declaration's object
  lingering in the shared registry forever).
- `classify_matlab_file`'s ordering guard, rewritten: a function that
  constructs a Sweep now correctly classifies as a **function**.
- `matlab_entities_file.parent` was added to `matlab_addpath`, replacing the
  getter files' contribution, so a generated command can `run` the script.

`has_matlab_config` now keys off `entities_file` instead of the removed
lists.

**Pre-existing bug found and fixed here (not an entities-script issue):**
`_path_input_args_to_literal` only parsed the name-value *pair* form
(`'root_folder', '/data'`), not MATLAB R2021b+ `name=value`
(`root_folder='/data'`) — even though `api.matlab_command._format_path_input`
**generates** the name=value form, and scimatlab's README requires R2021b
specifically for it. A PathInput getter written the way the GUI itself
emits would fail literal extraction and silently degrade to name-only
tracking: no `pathInput__` canvas node, no execution resolution, just a
load-error entry. Both forms are now accepted (`_parse_named_arg`), with a
regression test on the *getter* path as well as the entities path, and a
test that an `=` inside a quoted template is not mistaken for a named
argument.

**Deferred to Stage 4**: `constant` bindings parse and are recognised, but
are not registered — that needs `+scidb/Constant.m`. `each_of` bindings
(alternate templates) likewise parse but have no MATLAB registration path;
worth revisiting when PathInput alternates matter on the MATLAB side.

#### Original plan text, for reference

- `matlab_parser`: parse top-level `NAME = <ctor>(...)` bindings out of a
  script into `{name: (construction_call_text, span)}` — the same shape
  Stage 1's `find_binding_span` produces for Python. `classify_matlab_file`
  gains an "entities script" result (a file with no `function` and no
  `classdef`, currently classified as `None`, so nothing collides).
- `matlab_registry`: register the parsed Sweeps/PathInputs/Constants into
  the shared `scistack_gui.registry`, reusing the existing literal
  extraction so real `scifor.Sweep`/`PathInput` objects are constructed,
  exactly as the getter path does today.
- `config`: new `[matlab] entities_file`, **including
  `_render_scistack_toml` round-trip support**.
- `+scidb/Sweep.m` / `+scidb/PathInput.m` subclass shims, so the entities
  script reads `scidb.*` identically to Python.
- Existing getter files keep working, read-only (see decision 1's
  consequence).

### Stage 4 — `scidb.Constant` in MATLAB (D2) — **DONE, uncommitted (2026-08-25)**

`+scidb/Constant.m` (immutable `value`/`description`, static `unwrap`,
`disp`); `+scidb/for_each.m` unwraps every input at the very top;
`matlab_parser.binding_constant_literal`; `matlab_registry._matlab_constants`
+ `_register_matlab_constant_object` + `get_all_constant_names`, wired into
`load_entities_script` and the stale-deregistration pass. Tests:
`test_constant.py::TestVersionKeyIdentity` (5), `test_matlab.py` constant
cases (6). **Python tests not yet run; the MATLAB code is unverified — no
MATLAB in this environment, so `+scidb/Constant.m` and the `for_each.m`
unwrap need the user's own run.**

Decisions made while building it:

- **Not a transparent proxy.** Python's `Constant` forwards
  arithmetic/comparison/attribute access; replicating that in MATLAB means
  overloading the whole operator surface plus `subsref` for no real gain,
  since a MATLAB constant's only true entry point is the `for_each`
  constants struct. Plain value holder; `C.value` in ordinary code.
- **Unwrap at the very top of `for_each`**, before EachOf expansion, so
  every downstream path only ever sees plain values and no other site needs
  to know the wrapper exists. Bonus: a Constant nested inside an EachOf
  alternative is unwrapped for free, because each expansion branch
  re-enters `scidb.for_each` and unwraps again at its own top.
- **`+scifor/for_each.m` deliberately left alone** — scifor is the lower
  layer and shouldn't know about a scidb type; `scidb.for_each` is the
  documented entry point.

**Pre-existing Python bug found and fixed here.** Nothing unwrapped
`Constant` before hashing, so `_get_direct_constants` handed the wrapper to
`canonical_hash`, which raises `ValueError: Unserializable data type` for
any type it doesn't recognise — meaning **passing a declared
`scidb.constant(...)` into `for_each` failed outright**. Confirmed
unreachable-by-accident: `_is_loadable`'s `hasattr(v, "load")` returns False
for a Constant (its `__getattr__` proxies `load` to the wrapped scalar), so
it always landed in the constants dict. `Constant` had 60 unit tests, none
touching `for_each`/`version_keys`/`canonical_hash`. Fixed in
`_get_direct_constants` (the narrowest choke point — the function still
receives the wrapper, preserving the documented transparent-use design),
with regression tests asserting wrapped and bare values produce the same
`__constants` and the same `call_id`, and that description-only edits don't
fork history.

#### Original plan text, for reference

`+scidb/Constant.m`, `for_each.m` unwrapping, discovery via Stage 3's
entities-script scan, registration through `_register_constant`.

Tests: a constant declared in the MATLAB entities file appears as a GUI
constant node with source-declared identity; **version_keys parity with
Python for the same value** (the hard requirement above); `for_each`
accepts a wrapped and unwrapped value identically.

### Stage 5 — write-back with guards (`target_file_service`) — **DONE, uncommitted (2026-08-25)**

`target_file_service.update_declaration(kind, name, python_expr=, matlab_expr=)`
plus `record_source_hash` / `record_path_input_history` / `declaration_source`
/ `_atomic_write`. Public wrappers: `constant_service.update_constant`,
`path_input_service.update_path_input` / `update_sweep`. MATLAB renderers
(`render_matlab_constant` / `_sweep` / `_path_input`, `render_matlab_value`,
`find_entities_binding`) live in `matlab_parser`, next to the parser that
reads them back. D7 storage: `_pipeline_path_input_history` +
`record_path_input_value` / `lookup_path_input_name` /
`list_path_input_history`. Tests: `test_target_file_service.py`
(`TestUpdateDeclaration` 10, `TestPathInputHistory` 5). **Not yet run.**

Decisions made while building it:

- **Callers render both languages; the service picks by file suffix.** Keeps
  the three `update_*` wrappers language-agnostic and puts the one
  language decision in one place.
- **`render_matlab_value` checks `bool` before `int`** — in Python `True` IS
  an `int`, so the obvious ordering silently emits `1` instead of `true`.
- **Guard is a file hash recorded at scan time**, not a value comparison.
  It over-refuses slightly (an unrelated edit elsewhere in the entities file
  also blocks) but that is the honest answer — the file changed, refresh
  first. A file with no recorded hash is treated as unverifiable and allowed
  through, so tests and fresh boots aren't wedged.
- **Rollback on verify failure**, not just on write failure: after the write
  the registry is re-scanned, and if the entity no longer resolves the
  original bytes go back and the registry is re-scanned again. A file the
  scanner can't parse takes down *every* entity in it, so this is the one
  failure that must never be left in place.
- **Verification is kind-agnostic** (`_resolves_as_any_kind`). Checking the
  kind the entity had *before* the edit reports D4's Constant→Sweep rewrite
  as a failure and rolls a perfectly good write back — caught by
  `test_constant_to_sweep_is_the_same_splice`.

**Real bug found by the tests: stale bytecode.** `registry` loads entities
files with `spec_from_file_location` + `exec_module`, and `SourceFileLoader`
validates cached `.pyc` against the source's **mtime (whole seconds) and
size**. An entity edit routinely changes neither — `constant(30)` →
`constant(45)` and `'a.csv'` → `'b.csv'` are the same length, and the
rewrite lands in the same second as the load before it — so Python
re-executed the stale bytecode and the GUI kept showing the old value while
the file on disk was correct. Nothing was logged, because every layer
believed it had succeeded. `_atomic_write` now drops the cached bytecode and
calls `importlib.invalidate_caches()`. Regression test:
`test_same_length_edit_is_not_served_from_stale_bytecode`.

This is worth remembering beyond this stage: **any** feature that rewrites a
scanned source file and expects the next scan to see the change has the same
trap.
- **Atomic write via temp-file + `os.replace`** in the same directory, so a
  crash mid-write can't leave a half-written entities file.
- **`update_sweep([])` is rejected** rather than scaffolding a placeholder
  the way `create_sweep` does — emptying an existing Sweep would silently
  drop every variant it produces.
- **A no-op edit returns `ok` with `unchanged: True`** instead of writing,
  so the UI can distinguish "saved" from "nothing to do".
- **`root_folder` is stored as `''`, never NULL**, in
  `_pipeline_path_input_history`: it is part of the primary key, and a NULL
  there is both rejected by some engines and never equal to itself, which
  would silently defeat the `ON CONFLICT DO NOTHING` dedup.
- **D7 history is recorded from exactly one place** — `target_file_service`,
  immediately before a write-back overwrites a template. Best-effort: no
  open database simply means nothing to record, never a failed edit.

  *Simplified 2026-08-25, on the user's challenge that the table risked an
  overly specific, unmaintainable state.* The first version also recorded on
  every registry scan, to cover a template edited **directly in source** —
  the GUI never sees that edit, so only a prior scan could have remembered
  the old value. Dropped, because:
  - it cost a DB write on every project load for something that matters only
    when a template changes;
  - hand-editing source has *always* detached that history (there was no GUI
    template edit before Stage 5 — see `code-discovery-categories.md` §4),
    and that behaviour is unchanged, visible (WARN + `__unresolved__`), and
    done by the user most likely to understand it.

  The table now pays for exactly the capability Stage 5 introduced, nothing
  more: written from one place, read from one place. `pipeline_id` was
  dropped from it too — what a recorded template *meant* does not vary by
  scope, so carrying a scope column was misleading. No migration: beta.

**Not yet wired**: nothing calls `lookup_path_input_name` — that is D7's
*read* half, which belongs with `resolve_path_input_name` in Stage 7.

#### Original plan text, for reference

`update_entity(kind, name, new_value) -> dict`:

1. Resolve the owning file from `registry`'s recorded `source=`. **If it is
   not `variable_file` (Python) / `entities_file` (MATLAB), refuse** with a
   structured error carrying `{file, line}` so the frontend can render the
   exact-location message.
2. **Stale-file guard**: compare the file's current hash against the hash
   recorded at the last registry scan; on mismatch refuse with "changed on
   disk — hit Refresh Code first" rather than clobbering.
3. Locate span → render → splice → **atomic write** (temp file + replace),
   retaining pre-edit text for undo.
4. Refresh the registry, then **verify** the entity holds the intended
   value; on mismatch restore the pre-edit text and report — never leave a
   file the scanner can no longer parse.
5. Log at INFO: `(kind, name, file, old → new)` (CLAUDE.md NOTE 2).

Per D7, this stage also owns the **write** half of the PathInput name↔value
history: create `_pipeline_path_input_history`, record every
`(name, template, root_folder)` seen at registry-scan time, and record the
previous value before a PathInput splice. Append-only, deduped on the full
tuple.

Tests: happy path per kind × language; refusal for a foreign file with the
right `{file, line}`; stale guard fires on an out-of-band edit; forced write
failure restores original bytes; comments and unrelated declarations in the
entities file survive byte-identical.

### Stage 6 — endpoints — **DONE, uncommitted (2026-08-25)**

REST `PUT /api/constants/{name}` / `/api/path-inputs/{name}` /
`/api/sweeps/{name}` with `ConstantUpdate` / `PathInputUpdate` /
`SweepUpdate` models; JSON-RPC `_h_update_constant` / `_h_update_path_input`
/ `_h_update_sweep` registered in `METHODS`; `layout_service.update_*`
pass-throughs that broadcast `dag_updated` on success; `api.ts` routes.
`api/matlab_command.py` gains `_entities_script_lines`, emitted after the
addpath block in **both** generators, fed by
`matlab_command_service._entities_script()`. Tests:
`test_entity_update_endpoints.py` (16). **Not yet run**; `tsc --noEmit`
clean.

Decisions made while building it:

- **PUT, not PATCH**: an update replaces the whole declaration (the span
  covers the entire RHS), so it is a replacement, not a partial edit.
- **`layout_service` wrappers broadcast `dag_updated`** on success, matching
  every other wiring mutation, so the canvas refetches and shows the new
  value without the frontend having to know.
- **`update_*` returns `ok: False` with HTTP 200**, like the create
  endpoints, rather than raising an HTTPException — `read_only` and `stale`
  are expected outcomes carrying structured data the UI renders, not
  transport errors.
- **The entities script is re-run on every generated command**, not once per
  session. A MATLAB script is re-read from disk each time, so this is
  precisely what makes a GUI edit visible to a kept-warm sidecar with no
  cache-clearing — the property that justified D1's script-over-classdef
  choice. It goes after `addpath` (the script lives on one of those
  directories) and before `configure_database`.
- **Both** MATLAB generators emit it — the single-function one and
  `generate_matlab_pipeline_command`. Wiring only the first would leave
  whole-pipeline runs silently unable to resolve a declared entity.

Transport parity is tested three ways, because a field-name mismatch between
REST and JSON-RPC is invisible in the browser and breaks only the VS Code
extension (the `const_name` vs `name` bug from
`.claude/plan-constant-source-of-truth-26-08-22.md` Phase 4): every method
exists in `METHODS`; each RPC handler accepts the exact REST body plus
`name`; and optional fields really are optional over RPC. A fourth test
compares `layout_service`'s signatures against the underlying services, so a
drifted pass-through can't silently drop an argument.

#### Original plan text, for reference

Restore `update_sweep` / `update_path_input` / `update_constant` (removed in
`066cc53`), now backed by Stage 5 rather than the layout writes they used to
do. REST + `server.py` JSON-RPC handlers for the VS Code extension, with the
**same params object shape on both transports** — the exact mismatch
(`const_name` vs `name`) Phase 4 of
`.claude/plan-constant-source-of-truth-26-08-22.md` had to fix.

`api/matlab_command.py` emits `scistack_entities;` immediately after the
`addpath` block of every generated command, so the script's bindings are in
the executing session's workspace — warm sidecar, VS Code terminal, or
hand-paste alike (see D3). No cache-clearing needed: a script is re-read on
every run.

### Stage 7 — merge Constant and Sweep into Parameters (D6) — **DONE, uncommitted (2026-08-25)**

Backend: `build_sweep_nodes` folded into `build_parameter_nodes` (renamed
from `build_constant_nodes`, new `sweeps=` param); `PARAM_ID_PREFIX =
"param__"` defined once in `graph_builder` and referenced everywhere;
`constantNode`/`sweepNode` → `parameterNode` across `graph_builder`,
`edge_resolver`, `layout`, `pipeline_discovery`, `portability_service`,
`scope_service`, `matlab_command_service`, `execution_service`,
`layout_service`, `api/pipeline`. Frontend: `ParameterNode.tsx` replaces
`ConstantNode.tsx` + `SweepNode.tsx`; `SweepSettingsPanel.tsx` deleted;
`EditTab` down to five tabs with a unioned Parameters list;
`SidebarItemKind` merged. D7 read half wired: `resolve_path_input_name`
gains a history fallback, fed by new
`pipeline_store.path_input_history_index`. Tests: renamed across 12 files,
plus `TestParameterMerge` (6) and 4 new resolver cases. **Not yet run**;
`tsc --noEmit` clean.

Decisions made while building it:

- **Clean break on the id prefix, no migration** (user instruction). An
  interim version kept `const__` as the shared prefix precisely to avoid
  migrating saved positions/hidden rows — with migrations off the table
  that argument evaporates, so the honest name won. Old `const__`/`sweep__`
  positions and hidden rows simply stop matching; nodes reappear at (0,0).
- **`PARAM_ID_PREFIX` had to move above `_DB_DERIVED_PREFIXES`** in
  `graph_builder` — the tuple references it at module scope, so defining it
  further down was an import-time `NameError`.
- **The merge went in the constant node's direction**, because it was
  already the richer widget: the old sweep node had no per-value
  checkboxes, no `src` badge and no DB-history rows. Sweeps inherit all
  three; there are tests pinning each.
- **A Sweep's registry values are its "current source values"** — the same
  slot a Constant's single value occupies — so `is_current_source_value`
  badging, the keep-historical-values rule and hidden-value filtering all
  work unchanged for both.
- **`data.source_kind`** ("constant"/"sweep") is emitted for display only.
  The node is identical either way; the panel uses it to show how source
  currently spells the declaration.
- **Portability PARTITIONS one referenced-name set between the two
  bundles** — `_GLOBAL_NODE_TYPES` is now `("parameterNode",
  "pathInputNode")`, and a referenced Parameter bundles as a sweep if the
  registry has one, else as a constant. The first cut fed the same set into
  both, so every sweep also appeared in `constants` with an empty pending
  list — a polluted document that import would then try to materialise as
  constants. Caught by
  `test_globals_created_fresh_when_absent_locally`; the partition (`if name
  not in sweep_registry`) is the fix, and required moving the `constants`
  build below the sweep-registry lookup.

**Known consequence of the clean break, worth stating plainly:** existing
`*.layout.json` positions and `_pipeline_hidden_nodes` rows keyed
`const__X`/`sweep__X` no longer resolve, so on first load after this change
Parameters land at (0,0) and anything previously hidden comes back. Manual
edges stored against those ids likewise no longer match. Acceptable in beta
per the standing instruction; it is the one user-visible cost.

#### Original plan text, for reference

Independent of the write-back work; could land before or after Stages 1–6,
but must precede Stage 8's panel work.

- **`graph_builder`**: `build_sweep_nodes` folds into `build_constant_nodes`
  (renamed `build_parameter_nodes`), so sweeps gain per-value `checked`,
  `is_current_source_value`, and the keep-historical-values rule for free.
- **Node ids**: one scheme for both, plus a `*.layout.json` position
  migration behind a sentinel, following the `placements_migrated`
  precedent. Check every `const__` / `sweep__` id-prefix assumption —
  edge resolution and hidden-node/placement code both key off these.
- **Per-value hiding** (`_pipeline_hidden_constant_values`,
  `filter_hidden_constant_value_targets`) now applies to former sweeps too;
  it is keyed by entity name, so this should be storage-compatible as-is —
  verify rather than assume.
- **Frontend**: `EditTab.tsx`'s tab strip drops to five categories with a
  "Parameters" entry; `ConstantNode.tsx` and the sweep node collapse into
  one component; `PipelineDAG.tsx`'s node-type registry updated.
- **Registry/discovery is untouched** — `scidb.Constant` and `scidb.Sweep`
  remain distinct source kinds, scanned exactly as they are now. This is
  purely a presentation merge.

Per D7, this stage also owns the **read** half: `resolve_path_input_name`
gains its second strategy (registry content-match → history content-match →
`__unresolved__`), and the PathInput node adopts the same
show-historical-values-beside-the-current-one rule the Parameter node uses.
This is the natural home for it — Stage 7 is already where that display
rule gets unified.

Tests: a one-value Parameter and a many-value Parameter render from the
same builder; existing layouts migrate with positions preserved; per-value
hiding excludes targets for a former sweep; `Sidebar.tsx`'s `cartesian()`
still fans out correctly over merged nodes. For D7: a template edited via
the GUI keeps its prior runs attributed to the node; a template edited
directly in source between two scans likewise (covered by scan-time
recording); a declaration removed outright still lands in
`__unresolved__`; and a same-template rename still resolves via strategy 1.

### Stage 8 — frontend — **DONE, uncommitted (2026-08-25)**

`useSourceEdit.ts` (shared submit/error hook) +
`ParameterSettingsPanel.tsx` rewritten as a real editor +
`PathInputSettingsPanel.tsx` template/root_folder/alternates now editable.
`tsc --noEmit` and `npm run build` both clean; bundle rebuilt into
`scistack_gui/static/`. **Not clicked through in a browser** — needs the
user's visual pass.

Decisions made while building it:

- **One shared hook, not per-panel error handling.** Every entity edit now
  has failure modes a layout.json write never had (`read_only` with
  file:line, `stale`), and both arrive as `ok: false` with HTTP 200. The
  hook makes "show the refusal, never silently revert" structural rather
  than something each panel remembers to do — which is precisely the
  regression the old panels had (Save wired to a removed RPC, no-opping
  silently, so the field appeared to revert).
- **The Parameter panel writes the WHOLE value list** via
  `update_parameter`, not per-value pending stages. Adding a value is
  literally adding an argument to the declaration.
- **Values no longer declared in source render as "history"** with no
  remove button — removing one would be a no-op against source, and the
  row exists because the DB records what actually ran.
- **The last declared value has no remove button**, mirroring the backend's
  empty-list guard locally so the user sees why before a round-trip.
- **Panel inputs are text; values are coerced** (`"20"` → `20`, `true` →
  bool) before being sent, so a Parameter holds real numbers and its
  `version_keys` match a bare literal.
- **PathInput's hint distinguishes the two edits** — replacing the template
  re-points existing runs (D7's history table is what makes that safe);
  adding an alternate never does. That asymmetry is invisible from the UI
  otherwise.
- **Both panels are keyed by node id** in `Sidebar.tsx`. They seed local
  draft state from props, so without a remount React would reuse the
  instance across a selection change and carry one node's half-typed edit
  onto another.

#### Original plan text, for reference

`SweepSettingsPanel` and `PathInputSettingsPanel` become editors again (they
were editors before `066cc53`; their docstrings record that every Save
silently failed against the removed RPC). `ConstantNode`'s value gains an
edit affordance alongside the existing include/exclude checkbox.

Non-negotiable: a failed write must **surface the backend error**, not
silently revert — the precise failure mode called out in
`SweepSettingsPanel.tsx`'s current docstring. Read-only entities render the
file:line message instead of an input.

Per D4/D6: adding a value to a one-value Parameter is a plain edit with no
dialog — the node does not move and the panel shows the resulting line.

Per D5 + D7: **no edit needs a confirmation dialog.** Once the PathInput
name↔value history follows the node, every in-place edit is
non-destructive, so replacing a template is as plain as changing a
Parameter value. Historical values render as extra rows beside the
source-declared one, uniformly across Parameter and Path Input nodes.

### Stage 9 — MATLAB engine as the primary execution path (D3) — **DONE, uncommitted (2026-08-25)**

`matlab_sidecar`: `SidecarBusyError` + `_busy` guard, `status()`,
`restart()`, `check_health()`, `_drain_queue()`. `api/run.py`: health probe
before every sidecar run, `GET /api/matlab-engine`,
`POST /api/matlab-engine/restart`. JSON-RPC + `api.ts` routes. Tests:
`test_matlab_sidecar.py` — `TestBusyGuard` (4), `TestRestartAndStatus` (3),
`TestHealthProbe` (4). **Not yet run; still unverified against real
MATLAB.**

Tier selection is untouched, per D3's resolved sub-decision — this stage is
robustness only.

Decisions made while building it:

- **Concurrency is refused, not queued.** Two writers on one stdin/stdout
  pair interleave their command text and then race for each other's
  sentinels, corrupting both runs and reporting whichever finishes first as
  the answer to both. Queueing would hide that behind a wait; raising says
  what happened. The flag is checked and set under one lock so two threads
  can't both see "free".
- **`stop()` clears `_busy` unconditionally, before its early return.** An
  in-flight `run_command`'s own `finally` only runs once its blocked stdout
  read unblocks — which happens *after* the process dies. Without the
  unconditional clear, `restart()` could observe a stale "busy" and refuse
  the very command it was recycled to accept.
- **`start()` drains the queue when replacing a dead process.** A crashed
  process's reader thread pushes an EOF `None` when the pipe closes; left
  queued, the NEXT `run_command` reads it and aborts a perfectly healthy
  engine with "process exited before completion". `stop()` already drained
  for the explicit path; this covers the implicit auto-restart one. Both now
  share `_drain_queue`.
- **The health probe is a `pyenv` check, cached per process.** Run before
  each sidecar run, but the probe itself only executes once per MATLAB
  process — `pyenv` cannot change under a running engine, so re-probing
  every run would add a full round-trip for an answer that cannot have
  changed. `start()` clears the cache, so a restart re-probes.
  `start()` only proves `matlab` is on PATH; a MATLAB with no `pyenv`
  configured fails on the first `py.*` call, deep inside
  `scihist.configure_database`, and reads as a pipeline error rather than
  the setup problem it is. A probe that arrives mid-run returns "healthy"
  rather than disturbing the run or reporting the refusal as ill health.

**Deliberately not built:** warm-start on project open. It trades a
guaranteed MATLAB launch (slow) on every project open — including for
Python-only projects that happen to have a `.m` file lying around — for
saving that cost on the first run only. The status endpoint plus explicit
restart give the user the same control without the unconditional cost;
revisit if first-run latency actually proves annoying in practice.

#### Original plan text, for reference

Tier selection is **unchanged** (see D3's resolved sub-decision) — no
reordering, no setting, no frontend work. This stage is entirely about
making the engine solid enough to be the normal path in browser/standalone
and in VS Code without the MathWorks extension (see D3's resolved
sub-decision, which sets Stage 9's scope). Scope:

- **Lifecycle.** Today the sidecar starts lazily on first run, so the user
  pays MATLAB's (slow) startup on their first Run with no signal that
  anything is happening. Add: warm-start on project open when the project
  has MATLAB sources and `matlab` is on PATH; a visible engine-status
  indicator (starting / ready / busy / dead); explicit restart; and
  auto-restart after a crash or a `force_cancel_run` kill.
- **Health and diagnostics.** `start()` currently only checks
  `shutil.which("matlab")`. A MATLAB that launches but has no `pyenv`
  configured will fail on the first `py.*` call with an error that reads as
  a pipeline failure, not a setup problem. Add a one-time post-start probe
  and surface a setup-level message, in the spirit of
  `docs/claude/phase-8-startup-diagnostics.md`.
- **Concurrency.** `MatlabSidecar` is explicitly not safe for concurrent
  `run_command` calls; today that is held by the one-run-at-a-time
  execution model. Promoting it to primary makes this load-bearing, so make
  it explicit — a lock plus a clear "engine busy" error rather than an
  interleaved-stdin corruption.
- **Verification gate (user-run, real MATLAB).** Warm start; run a
  single-node and a whole-pipeline run; cancel mid-run and confirm the
  process dies and restarts clean; kill MATLAB externally and confirm the
  next run recovers; edit an entity in the GUI and confirm the very next
  run picks up the new value **without** restarting the engine (the D3
  payoff); confirm the copy-paste tier still works with MATLAB off PATH.

### Stage 10 — round-trip tests — **DONE, uncommitted (2026-08-25)**

`scistack-gui/tests/test_entity_round_trip.py` — 16 tests across six
classes: `TestGuiEditRoundTrip` (4), `TestSourceEditRoundTrip` (3),
`TestStaleGuardRoundTrip` (2), `TestReadOnlyRoundTrip` (1),
`TestExportRoundTrip` (2), `TestMatlabEntitiesRoundTrip` (3).
**Not yet run.**

What these add over the existing unit tests: those check each link in
isolation (span finder, renderers, guards, registry scan). These check the
LOOP — edit → file on disk → re-scan → what the GUI shows — so a break
anywhere in the chain surfaces even while every individual piece still
passes its own test.

Decisions made while building it:

- **Assertions read the FILE, then force a re-scan**, rather than trusting
  the in-memory registry the edit just updated. Checking the registry alone
  would pass even if nothing were written to disk.
- **Both directions are covered.** Source-edit → Refresh Code is what the
  original source-of-truth migration bought; the write-back machinery must
  not regress it, and nothing else asserts that end-to-end (add, edit and
  remove by hand).
- **The stale-guard test asserts the file is byte-identical** to what the
  other writer left — "refused" is not enough; a partial merge or clobber
  would also be a refusal by return value. Same for the read-only test on
  the foreign file.
- **MATLAB round-trips need no MATLAB**: parse → splice → re-parse is a
  file operation. `test_registry_reads_back_the_rewritten_file` closes the
  loop through `matlab_registry` to the GUI-visible object. This is the one
  part of the MATLAB work that CAN be verified here; the runtime half
  (`+scidb/Parameter.m`, `for_each.m`) still cannot.
- **`test_exported_header_imports_what_repr_emits`** pins the coupling that
  bit during the Parameter migration: `repr()` emits `Parameter(...)`, so
  the generated script's header must import it or every exported script
  with a Parameter dies with `NameError`. Asserted against the source text,
  since the failure is a missing import rather than a wrong value.

#### Original plan text, for reference

- Edit in GUI → read file from disk → re-scan → value matches (per kind ×
  language).
- Edit in source → Refresh Code → GUI shows the new value (guards against
  regressing what `89f4f35` just added for Constants).
- Edit in GUI → `code_export_service` export → exported script carries the
  new value (the eject path stays truthful).
- Concurrent edit → stale guard fires, file untouched.
