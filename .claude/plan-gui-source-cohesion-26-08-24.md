# Design options: making GUI-authored and script-authored pipelines cohere

Date: 2026-08-24
Status: **discussion / options only** — nothing decided, nothing implemented.

## Problem as stated by the user

Two authoring surfaces are supposed to be first-class for the same pipeline:

1. **GUI-first**: create and manage entities entirely in the GUI; export
   either to a GUI-compatible document (`portability_service`) or to a
   script-only pipeline that runs and is editable with no GUI at all
   (`code_export_service`).
2. **Script-first**: develop a pipeline in plain `scidb` code, then import
   it into the GUI for ongoing management (`pipeline_discovery`).

The recent "source is truth, DB is run history" migration (commits
`066cc53`, `6738212`, `89f4f35`) made Sweeps, PathInputs, Constants,
Variables and source-declared Submodules **source-declared**. The side
effect the user dislikes: those entities are now **read-only in the GUI**.
Creating appends a declaration to the configured entities file; editing a
value requires leaving the GUI, hand-editing source, and hitting Refresh
Code; deleting only hides a node.

The question: is there a better way to make the two management modes work
together, rather than paying for source-of-truth with a read-only GUI?

## What is actually true today

Four distinct kinds of state are in play, and only one of them is in
dispute:

| State | Owner today | In dispute? |
|---|---|---|
| **Declarations** — which Sweeps/PathInputs/Constants/Variables exist and their literal values | Source files (`registry.py` scanners) | **Yes — this is the read-only complaint** |
| **Wiring / composition** — the DAG, manual nodes/edges, submodule bindings | DuckDB (`_pipeline_nodes`, `_pipeline_edges`, `_pipeline_uses`) | Not raised, but see Axis 3 |
| **Run history / provenance** | DuckDB | No |
| **View state** — positions, hidden nodes/edges/combos, pending values | `*.layout.json` sidecar + GUI-only DB tables | No |

Relevant mechanics already built:

- `target_file_service.append_and_refresh` — the GUI **already writes real
  Python source** on every entity create (`constant_service`,
  `path_input_service`, `variable_service`), then refreshes the registry.
  So "the GUI writes source" is an established, working capability; only
  *targeted rewriting* is missing.
- `registry._register_{constant,path_input,sweep}` record a `source=` file
  path per entity — but no line/column span.
- `matlab_parser.extract_path_input_literal` / `extract_sweep_literal`
  already do a char-by-char scan that locates the argument spans inside a
  MATLAB value getter — the read half of a MATLAB write-back.
- `_pipeline_pending_constants` is an existing **staging overlay** for
  exactly one entity kind (constants), with override-at-run semantics.
- `code_export_service` exports the DAG to a flat script (submodule
  composition flattened; PathInput/Sweep values inlined as literals).
- `pipeline_discovery.discover_and_seed_pipelines` imports source-declared
  `scidb.Pipeline`s into GUI state — **create-once, never resynced**.

## Diagnosis

"Source is the single source of truth" does **not** imply "the GUI is a
read-only viewer." It implies the *file* is where the value lives. A GUI
that edits the file is still fully consistent with the principle — that is
what an IDE is. The read-only state is an artifact of having built only
the append path, not a consequence of the decision.

The real design question is therefore narrower and more tractable:

> **How does a GUI edit reach the source file, and which files may it touch?**

Plus one deeper question the user didn't ask but which determines whether
the two modes ever *really* cohere (Axis 3).

---

## Axis 1 — When does a GUI edit reach source?

### Option A: Direct write-back (edit → immediate surgical source rewrite)

GUI edit resolves the declaration to `(file, span)`, replaces just the
value span, rewrites the file, refreshes the registry. One source of truth,
always, with zero new concepts.

- **A1 — `ast` span replacement (recommended mechanism).** Parse the owning
  file, find the `Assign`/`AnnAssign` whose target is the entity name, take
  `value.lineno/col_offset/end_lineno/end_col_offset`, splice new text.
  Comments, formatting and the rest of the file are untouched. Serializer
  already exists in spirit — `repr()`-based, same as
  `constant_service.create_constant` and `code_export_service`'s literal
  inlining.
- **A2 — `ast.unparse` round-trip.** Rejected: destroys comments and
  formatting of the whole file.
- **A3 — LibCST.** Format-preserving concrete syntax tree. Correct but a
  heavyweight new dependency for what is a single-statement RHS edit.
- **MATLAB**: reuse the existing literal-extraction scan to get the arg
  spans in the value getter body and splice the same way.

Required guards:
- **Stale-file guard.** Record the file's mtime+hash when the graph was
  built; refuse the write (with a "file changed on disk — Refresh Code
  first" error) rather than clobbering a concurrent hand edit.
- **Re-scan verification.** After writing, re-import and confirm the
  registry now holds the intended value; if not, report it rather than
  leaving a silently-broken file.
- **Undo.** Keep the pre-edit text (in-session or a `.bak`) so a bad edit
  is one click back.

Trade-offs: maximum ergonomics, no new state, no divergence possible.
Cost: real (if small) source-mutation machinery, and it fails outright when
source is not writable (installed package, packaged project).

### Option B: Permanent overlay (edits live in the DB; source never written)

Generalize `_pipeline_pending_constants` to all entity kinds. The overlay
wins at run time; the node badges "overrides source: 30".

Rejected as a primary design: it reintroduces exactly the two-sources-of-
truth problem the migration just removed, and produces DB rows whose
constants appear in no code anywhere. Worth keeping only as the fallback
mode for genuinely read-only source (see "Read-only source" below).

### Option C: Staged edits with commit to source (hybrid, git-index model)

Edits land in a staging overlay and are visibly *dirty*; a materialize step
writes them into source via Option A's machinery. The existing pending-
constants table is the precedent, and `feedback_never_delete_mark_hidden`'s
ethos fits (nothing is destroyed until an explicit act).

Sub-decision — **can a run proceed with uncommitted staged edits?**

- **C-i — No.** Must write to source first. Purest; every DB row traces to
  code that existed on disk. Most friction.
- **C-ii — Yes, and the run writes the edits to source first (commit-on-
  run).** Preserves the invariant *and* removes the friction — the user
  never sees a separate "save" step, and the file is correct by the time
  anything is recorded. **Recommended.**
- **C-iii — Yes, run from staged values without writing.** True scratchpad,
  but creates run history whose parameters exist in no source file — the
  provenance hole the migration closed.

### Recommendation on Axis 1

**A1 as the mechanism, C-ii as the policy.** Editing a Sweep/Constant/
PathInput value in the GUI marks it dirty and writes it to source either
immediately (simple fields) or at the moment of Run (edits made in a burst).
The invariant "every recorded run corresponds to source that existed on
disk" holds; the user never leaves the GUI. Option B survives only as the
degraded mode described below.

---

## Axis 2 — Which files may the GUI write to?

- **B1 — Entities file only** (`config.variable_file`, default
  `src/scistack_entities.py`). Smallest blast radius; that file already
  carries an "auto-created by the SciStack GUI" header, so treating it as
  GUI-writable is no change in contract. Declarations living in the user's
  hand-written modules stay read-only, which reintroduces the complaint for
  script-first projects — mitigated by an **"Adopt into entities file"**
  action (move the declaration, or re-declare and let the old one go).
- **B2 — Any discovered source file, surgically.** Best ergonomics and the
  only thing that fully serves the script-first user. Needs the full guard
  set from A1. Since the edit is a single-RHS splice, the actual risk is
  low — the risk is *perceived* invasiveness, addressed by showing a diff
  preview before the first write to a file the GUI has never touched.
- **B3 — Tiered**: write freely to the entities file, ask for confirmation
  (with diff) the first time a given foreign file is edited, refuse when
  the file is inside a site-packages/installed distribution.

**Recommendation: B3.** It costs one confirmation dialog and one path
predicate over B2, and removes the "the GUI edited my repo behind my back"
objection entirely.

### Read-only source (packaged projects, installed packages)

`target_file_service.get_or_create_target_file` already refuses to write to
a packaged project's `pyproject.toml` and returns a hand-edit message. The
same tier applies here: when a declaration's owning file is not writable,
fall back to **Option B overlay semantics with an explicit, badged
"unbacked override"** — and refuse to *export a script* from a pipeline
holding unbacked overrides (or emit them with a loud comment), so the
snapshot never silently lies.

---

## Axis 3 — Does the wiring round-trip too? (the deeper cohesion question)

The user asked about entities, but the two modes cannot fully cohere while
**wiring lives in DuckDB and declarations live in source**. Today:

- Script → GUI import is **create-once**: re-editing the script and hitting
  Refresh Code does not resync the GUI (`code-discovery-categories.md` §6).
- GUI → script export **flattens** submodule composition and inlines
  values, so the exported script is a one-way snapshot, not a
  representation the GUI could read back and recognize as the same
  pipeline.

So "develop in scripts, then manage in the GUI" is a **one-time
onboarding**, and "manage in the GUI, export to scripts" is an **eject**.
Neither is a loop. Three postures:

- **A3-a — Accept and label it.** Export is "eject to a standalone script";
  import is "adopt an existing script". Both one-way, documented as such.
  Zero new work; honest; but the user's stated goal ("import to the GUI for
  management there", "editable entirely without the GUI") is only half met.
- **A3-b — Make import idempotent/mergeable.** Give discovered pipelines a
  stable identity (the `pipeline_id` mechanism from
  `pipeline-import-identity.md` is the obvious model) and let Refresh Code
  reconcile source changes into existing GUI state, three-way-merge style,
  with conflicts surfaced. Medium effort; makes script-first a real ongoing
  workflow rather than a one-shot.
- **A3-c — Move the pipeline definition into source entirely** — the DAG
  becomes a real `scidb.Pipeline` file that the GUI reads *and writes*, the
  same way Axis 1 proposes for entity values. `_pipeline_nodes`/
  `_pipeline_edges`/`_pipeline_uses` become a derived cache, positions stay
  in the existing `*.layout.json` sidecar, and DuckDB is left holding only
  run history + view state. Export becomes "here is the file"; import
  becomes "open the file"; the two modes stop being two modes.

**A3-c is the coherent end state** and is the natural completion of the
principle the migration already committed to. It is also substantially more
work than Axis 1 (bidirectional codegen for the whole DAG, unflattened
submodule composition, merge/conflict UX). It does not need to be decided
now — Axis 1 is a strict prerequisite either way, since editing a value in
source is the smallest instance of the same capability.

---

## Suggested staging (if Axis 1 = A1 + C-ii + B3)

1. **Declaration→span index.** New source-editing module (see "Layering"
   below): given an entity name + kind, find the owning file and the exact
   RHS span. Python via `ast`; MATLAB via the existing literal scan.
   Pure and unit-testable with no GUI involved.
2. **Value serializer + splice + guards.** `repr`-based emit (shared with
   `code_export_service`'s existing inlining), stale-file check, atomic
   write, undo snapshot, post-write re-scan verification. Log every write
   at INFO with `(entity, file, old→new)`.
3. **Backend update endpoints**, restoring the deliberately-removed
   `update_sweep` / `update_path_input` / `update_constant` — but now
   implemented as source writes, not layout writes.
4. **Writability tiering** (B3) + read-only fallback badging.
5. **Frontend**: turn `SweepSettingsPanel` / `PathInputSettingsPanel` /
   `ConstantNode` back into editors, with a dirty indicator, diff preview
   on first foreign-file write, and an error path that surfaces the
   stale-file guard instead of silently reverting (the exact failure mode
   called out in `SweepSettingsPanel.tsx`'s current docstring).
6. **Round-trip tests**: edit-in-GUI → read file → re-scan → value matches;
   edit-in-source → Refresh → GUI matches; concurrent-edit → guard fires.

## Layering note (CLAUDE.md NOTE 3)

"Find/rewrite a declaration in source" is not a GUI concern — it is the
write half of the discovery capability that already lives in `scidb`
(`discover.py`) and `scistack_gui/registry.py`. Per
`feedback_avoid_scifor_scidb_duplication` and NOTE 3, the span-finding and
splicing belong in the layer that owns discovery (`scidb`, alongside
`discover.py`/`is_test_path`), with `scistack-gui` only orchestrating.
MATLAB span-finding stays with `matlab_parser`, which already has the scan.

## Open questions for the user

1. Is the "GUI may edit files in my repo" contract acceptable at all, or
   must GUI writes stay confined to the designated entities file?
2. Should a Run be allowed to write to source implicitly (C-ii), or must
   committing be an explicit user action (C-i)?
3. Is Axis 3 (wiring round-trip) in scope as a direction to build toward,
   or is "export = eject, import = adopt" the intended contract?
4. Does MATLAB need write-back at parity in the first pass, or is
   Python-only acceptable to start?
