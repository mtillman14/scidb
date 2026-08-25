# Plan: GUI to-do items from `todos_26-08-22.md`

Date: 2026-08-25
Status: **approved by user 2026-08-25** (items 1, 3, 4, 5 answered directly;
item 2 needed no decision).

Source: `todos_26-08-22.md`, written while testing the GUI.

## Decisions locked by the user (2026-08-25)

1. **Item 3 — accept common import aliases.** `pd.` → `pandas.`, `np.` →
   `numpy.`, normalized to the canonical name everywhere (persistence,
   node label, generated code). Rejected: keeping the rejection with a
   better message; keeping the alias as the stored label (two names for
   one function complicates history keying).
2. **Item 4 — full removal.** Python library references stop living in
   `registry._functions` altogether. The DB table records *which*
   references the user added; the callable is imported on demand at every
   use site. Rejected: an import fallback in `get_function` alone, which
   leaves the registry/DB/replay split-brain in place.
3. **Item 1 — the generation controls come back as a second mode**, added
   to today's per-value editor rather than replacing it.
4. **Item 5 — fix with diagnostics** (CLAUDE.md NOTE 2).

---

## Item 1 — Parameter is missing Sweep's programmatic generation

### What was lost

`SweepSettingsPanel.tsx` (deleted in `89f4f35`, when Sweep and Constant
merged into Parameter — see `.claude/plan-gui-entity-editing-26-08-24.md`
D6) had two modes:

- **List** — type/paste `1, 2, 5, 10`, split on commas or whitespace.
- **Range** — `start` + `end` + a third field that is either a **step
  size** or a **target number of steps**, toggled by a pair of buttons.

Both showed a live preview before saving, and generation was purely a
frontend concern: the backend only ever received the final flat list.
`clean()` rounded away float noise (`0.1 + 0.2 → 0.30000000000000004`) at
10 significant decimals.

The Parameter panel that replaced it only has "Add value" — one value at a
time. That is the vector-valued component the to-do is asking for.

### The port

`ParameterSettingsPanel.tsx` keeps its per-value rows (remove buttons,
history/`src` distinction — things the old sweep panel never had) and gains
a collapsible **Generate** section carrying the old List/Range controls
verbatim, including `parseListDraft`, `clean` and `generateRange`.

Committing a generation calls the same `update_parameter` the rest of the
panel uses, with the whole list — so it is the ordinary source rewrite
(Stage 5 of the entity-editing plan), not a new write path.

**Kept from the old panel:** the live preview, and the `EachOf` hint when
the generated list has more than one value.

**Deliberately not kept:** the old panel's "Current Values" block — the
per-value rows above it already are that, better.

---

## Item 2 — ParameterNode canvas chrome

Three removals from `ParameterNode.tsx`, display-only:

| Removed | Was |
|---|---|
| `countBadge` | `"{n} values — EachOf"` under the value list |
| `sourceBadge` | the `src` pill on source-declared rows |
| record count | `" · {n} recs"` appended to every row label |

`is_current_source_value` and `record_count` stay in the node data — the
settings panel still uses both (it distinguishes declared values from
history rows, and only declared ones get a remove button). This is purely
about what the canvas draws.

---

## Items 3 + 4 — library functions resolve by import, not by registry

### The bug behind item 4

`create_builtin_function` does two things for `pandas.read_csv`:

1. `registry.register_builtin_function(...)` — puts the imported callable
   in the in-memory `registry._functions` dict;
2. `_persist_builtin(...)` — writes the name to `_pipeline_builtin_functions`.

`registry._functions` is **cleared** by every `load_from_config` /
`refresh_all` / `refresh_module`. `replay_persisted_builtins` re-imports
from the DB to survive that — but it is called from only three places
(`bootstrap.py:188`, `server.py:1232`, `pipeline_service.py:234`), while
these clear the registry and never replay:

- `api/project.py:357` — project/path changes
- `services/variable_service.py:85,129` — after creating a variable
- `services/target_file_service.py:95,558` — after any GUI entity write-back
- `services/registry_reload_service.py:32`

So editing a Parameter value or creating a Variable silently evicts
`pandas.read_csv`, and the next run produces exactly the logged warning.
Adding a fourth `replay` call patches this instance and re-arms the trap
at the next refresh site anyone adds.

### The shape of the fix

New module **`scistack_gui/library_functions.py`** — pure, no registry or
service imports, so anything may import it without a cycle:

- `canonical_reference(ref)` — expands an alias root (`pd` → `pandas`,
  `np` → `numpy`) and is otherwise identity.
- `validate(ref)` — the strict, user-facing check (identifier shape,
  allowed root, importable, attribute exists, callable), returning the
  same `{ok: False, error}` shape `create_builtin_function` already
  returns. Moved out of `builtin_function_service._resolve_python_builtin`.
- `resolve(ref)` — the cheap, hot-path lookup: canonicalize, import,
  `getattr`, return the callable or `None`. No error dicts, no logging on
  the happy path; `importlib` serves from `sys.modules` after the first
  call.
- `is_library_reference(ref)` — name-shape test used to decide whether a
  missing registry entry is worth an import attempt.

**Allowed roots are unchanged**: numpy, pandas, and the standard library.
This is not a general import backdoor, and the alias map only covers the
two conventional aliases for the two allowed third-party packages.

`registry` gains `lookup_function(name) -> callable | None` — the
registry dict first, then `library_functions.resolve`. `get_function`
becomes "lookup or raise", so **execution goes through the fallback**
(`api/run.py:180` and `execution_service.py:988` both call it). The
`register_builtin_function` entry point is deleted
(`feedback_beta_no_deprecation`: clean break, no shim).

Every other consumer of `registry._functions.get(name)` moves to
`lookup_function`:

| Consumer | Used for |
|---|---|
| `api/pipeline._fn_params_from_registry` | node input handles |
| `pipeline_service.get_function_source` | double-click → open source |
| `pipeline_service.get_function_doc` | sidebar signature/docstring |
| `portability_service._unresolved_labels` | import/export resolution check |

`pipeline_service.get_registry()["functions"]` unions the discovered
functions with the persisted library references read from the DB — that
table is now the only record of which library functions exist, so the
sidebar list must read it.

`replay_persisted_builtins` keeps its **MATLAB** half unchanged (a MATLAB
builtin has no import path and genuinely must be re-registered into
`matlab_registry`). Its Python half stops registering; it re-validates and
reports failures, which is what surfaces "numpy was uninstalled" as a load
error instead of a mystery at run time.

### Why this layer

`library_functions` is GUI-layer on purpose (CLAUDE.md NOTE 3): "which
non-user-authored functions has this user pinned to the canvas" is a GUI
concept. scidb has no notion of it, and the resolution rule is the mirror
of `builtin_function_service`'s validation rule, which is already here.

---

## Item 5 — misplaced input handle on a GUI-created function node

React Flow requires `updateNodeInternals` when a node's handle set changes
after mount. Nothing in the frontend calls it (`grep` for
`updateNodeInternals` across `src/` returns nothing).

A dropped function node hits that case twice:

1. `onDrop` inserts the node immediately, then `buildFnData()`'s
   `get_function_params` resolves **asynchronously** and rewrites
   `input_params` (`PipelineDAG.tsx:469-511`);
2. `put_layout` broadcasts `dag_updated`, and the refetch replaces the
   node's data again.

Both change `leftHandles.length`, which changes every handle's computed
`top` (`((i + 1) / (total + 1)) * 100%`). That matches the symptom and the
"it fixed itself after I dragged another node onto the canvas" clue — a
drag forces the re-measure that should have happened at the data change.

Fix: `useUpdateNodeInternals()` in `FunctionNode` and `PipelineNode` (the
two node types with data-driven handle sets), keyed on a signature string
of the handle ids, plus a dev-only diagnostic logging the id list on each
change.

Also corrected while here: the inline `transform: 'translateY(-50%)'` in
`handleStyle` overrides React Flow's `translate(-50%, -50%)`, dropping the
horizontal centring that sits the dot on the node border. Now
`translate(-50%, -50%)`.

---

## Tests

- `tests/test_library_functions.py` — alias expansion, canonicalization,
  allowed/denied roots, resolution of a stdlib/numpy/pandas reference,
  `None` for junk, and the **regression that matters**: a reference stays
  resolvable across `registry.refresh_all()` (the exact sequence that
  broke).
- `tests/test_builtin_functions.py` — updated for canonical naming
  (`pd.read_csv` → stored/returned as `pandas.read_csv`) and for library
  refs no longer appearing in `registry._functions`.
- Frontend: `tsc --noEmit` and a bundle rebuild.

Python tests are handed to the user to run (`feedback_user_runs_tests`).
