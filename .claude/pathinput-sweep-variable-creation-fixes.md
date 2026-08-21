# Fix PathInput/Sweep/Variable creation bugs in scistack-gui

All changes are GUI-layer only (`scistack-gui/`), per CLAUDE.md's layering rule — nothing here touches scidb/scifor/etc.

## Bugs and root causes

1. **Creating a PathInput or Sweep shows nothing in the list.** `commitPiDraft`/`commitSweepDraft` in `EditTab.tsx` never check the backend response's `ok`/`error` field (unlike `commitVarDraft`, which does) — a failed create is silently swallowed.
2. **Creating a Constant works.** `create_constant` writes to `layout.json`, not source — no `variable_file` dependency, so it's unaffected by the bug below.
3. **`test_var` (lowercase) rejected: "Variable names should start with an uppercase letter."** Hardcoded PEP8-style check in `api/variables.py`'s `create_variable` — not a technical requirement (lowercase is a syntactically valid Python class name), just an opinionated rule. Remove it.
4. **`Test_var` (uppercase) rejected: "No module file was loaded at startup (--module not passed)."** All three creators (PathInput/Sweep/Variable) append a real declaration to `SciStackConfig.variable_file`, which is `None` unless the user hand-edits `variable_file = "..."` into `scistack.toml`/`pyproject.toml`. There's currently no GUI control to set it. Bug #1's silent-swallow means PathInput/Sweep hit this exact same failure without telling you.

**Bonus finding while reading the Sweep path:** `commitSweepDraft` only ever sends `{name}` to `POST /api/sweeps`, but `SweepCreate.values: list[float]` has no default, and `path_input_service.create_sweep` explicitly rejects an empty values list — so Sweep creation is broken independent of the `variable_file` issue. There's no "enter sweep values" UI at all today.

## Fix plan

### Backend (`scistack-gui/scistack_gui/`)

1. **`api/variables.py`** — delete the `if not name[0].isupper()` check.
2. **`config.py`** — add `set_variable_file(db_path, file_path=None) -> Path`, mirroring the existing `add_path`/`remove_path` pattern:
   - Rejects packaged projects (`pyproject.toml`) via the existing `_reject_packaged_project` — those stay hand-edit-only, consistent with how `ManagedPathsList` already treats them.
   - For loose-script projects: defaults to `<project_root>/scistack_variables.py` if no explicit path given, creates the file on disk if missing (never overwrites an existing file), ensures the path is covered by `modules` so it gets scanned, and writes it into `scistack.toml`'s `variable_file` key (creating the toml if this is the very first write, same as `add_path`).
3. **New `services/registry_reload_service.py`** — extract the "re-read config from disk, reload `registry` + `matlab_registry`" logic that `api/project.py`'s `_reload_config_and_rescan` already does, so it can be reused by both that endpoint and the new auto-create fallback below (avoids duplicating the reload sequence).
4. **New `services/target_file_service.py`** — `get_or_create_target_file() -> (Path | None, str | None)`:
   - Returns `_config.variable_file` or legacy `_module_path` if already set (today's working path, untouched).
   - If project-mode config exists but `variable_file` is unset: calls `config.set_variable_file(db_path, None)` to auto-create the default file, reloads registries, and returns the new path.
   - If the project is packaged and can't be auto-written, returns a clear error pointing at hand-editing `pyproject.toml`'s `[tool.scistack]` section — replacing today's confusing "--module not passed" message in this case.
5. **`services/path_input_service.py`** — `_target_file()` calls the new shared helper instead of its current inline `registry._config`/`registry._module_path` check.
6. **`api/variables.py`** — same swap for its inline target-file lookup.
7. **Sweep values default** — `SweepCreate.values: list[float] = []` in `api/layout.py`; `create_sweep` defaults an empty list to a single placeholder value (`[0]`) instead of erroring, logging that it did so — mirrors how `PathInput('')` already scaffolds an empty template for the user to hand-fill and Refresh.
8. **`api/project.py`** — add `POST /project/variable-file` (body `{"path": str | null}`, null = auto-default) and `DELETE /project/variable-file` (clears the toml key only, never deletes the file — never-delete-mark-hidden ethos), both reusing the shared reload helper from #3.

### Frontend (`scistack-gui/frontend/src/`)

9. **`api.ts`** — register `set_variable_file` / `clear_variable_file` routes.
10. **`PathsPopup.tsx`** — in the loose-project (non-packaged) branch, add a small editable "Variable file" row next to `ManagedPathsList`: shows the current value (or "not set"), with a way to type an explicit path, use the auto-default, or clear it.
11. **`EditTab.tsx`**:
    - `commitPiDraft`/`commitSweepDraft` — check `ok`/`error` like `commitVarDraft` does; on failure, show the error inline and keep the draft input open instead of silently closing it; on success, clear/close as today.
    - Add `piError`/`sweepError` state + inline error `<div>` under each input, matching the existing `varError` pattern.

## What's explicitly out of scope
- No "enter Sweep values" input UI — the fix keeps Sweep creation a name-only scaffold (`Sweep(0)`) that the user then hand-edits in source, consistent with how PathInput creation already works. Building a real values-entry UI would be a separate feature request.
- Packaged (`pyproject.toml`) projects still require hand-editing `variable_file` — no GUI writes to `pyproject.toml`, consistent with the existing `ManagedPathsList` restriction.
