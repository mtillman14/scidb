# Plan: one answer to "which directory is this project?"

## The bug (from test_logs.md, 2026-09-01)

Adding a code path in the Paths popup wrote the config file correctly and
then failed to read it back, leaving discovery empty:

```
10:26:43 [config] add_path: wrote y:\...\aging-well-abilitylab\scistack.toml (added Y:\...\libraries)
10:26:43 [config] No explicit project_path, searching upward from db_path: C:\Users\...\test_afl.duckdb
10:26:43 [config] No pyproject.toml/scistack.toml found; falling back to folder-scan rooted at C:\Users\mtillman\Datasets\AbilityForLife
10:26:43 [config] Folder-scan found 0 .py file(s), 0 .m file(s)
10:26:43 [registry] After load: 0 functions, 0 variables
```

Two resolvers disagreed about where the project is:

| | Function | Anchor | Knows `--project-root`? |
| --- | --- | --- | --- |
| **write** | `infer_project_root` (config.py:589) | ladder incl. the hint | yes |
| **read** | `_locate_pyproject` (config.py:512) | upward walk from `db_path` | **no** |

The database is on `C:\Users\mtillman\Datasets\...`; the project is on
`Y:\LabMembers\...`. Different drives — walking up from the DB can never
reach the project, so the read path was structurally incapable of finding
the file the write path had just created.

Second-order: `add_path` decides `is_first_write` from the same db-rooted
`_locate_pyproject` (config.py:902), so it never sees the file it wrote.
Every add re-seeds from an empty section — **adding a second path silently
discards the first.**

## The rule (decided with the user)

**The project root is the folder you opened. Strictly.** No walking, from
either anchor. A config file is read from that folder and nowhere else.

Precedence, highest first:

1. Explicit `--project` / `--module` argument (`load_config`'s
   `project_path`) — the user naming a project outright.
2. `--project-root` (the VS Code workspace folder).
3. `cwd` (browser/CLI, where the user launched from).
4. The database's directory — last resort only, logged as a warning.

The database's location never influences the answer except as (4).

This also brings the GUI in line with the rest of the stack:
`scidb/entities.py:444` already resolves from `Path.cwd()`, not the DB.

### Making `cwd` mean what the user expects

`pythonProcess.ts:98` spawns the server with no `cwd`, so it inherits the
VS Code extension host's working directory — usually VS Code's install
directory, not the workspace. That is why rule 2 exists and cannot simply
be replaced by rule 3. The extension will also pass
`cwd: workspaceFolder.uri.fsPath`, so that "the folder you opened" is true
of *both* signals rather than only the flag.

## Changes

### `scistack_gui/config.py`

- **New `resolve_project_root(project_path, db_path) -> Path`** — the one
  answer, implementing the precedence above. Logs which rule fired.
- **New `locate_config_at(root) -> Path | None`** — `pyproject.toml` then
  `scistack.toml`, **in that directory only**.
- **Delete `_locate_pyproject` and `infer_project_root`.** Per
  `feedback_beta_no_deprecation`, a clean break — no aliases. Every caller
  moves to the pair above:
  - `load_config` (163) — and its folder-scan fallback roots at the project
    root, not `db_path.parent` (the other half of the same bug).
  - `describe_managed_paths` (869), `add_path` (902), `remove_path` (968),
    `set_entities_file` (1071), `clear_entities_file` (1165).
- `add_path`'s `is_first_write` now reflects reality, which fixes the
  clobber bug for free.
- `scifor.discovery.find_project_config` (the upward walk) is no longer
  called by the GUI. It stays for `scidb.entities`, which walks from cwd —
  a correct anchor.

### `extension/src/pythonProcess.ts`

- Spawn with `cwd: workspaceFolder.uri.fsPath` when a workspace folder
  exists.

## Failure modes

| # | Risk | Effect | Mitigation |
| --- | --- | --- | --- |
| 1 | User opens a **subfolder** of a packaged repo | `pyproject.toml` above is no longer found; discovery looks wrong | Accepted (user's call). The resolved root is logged on every load and shown in the Paths popup, so it is diagnosable; opening the repo root fixes it |
| 2 | Existing project with DB **inside** the project, opened at the root | None — root is the same either way | Covered by tests |
| 3 | Existing project with DB inside, but VS Code opened elsewhere | Root changes; previously-working discovery breaks | Loudly logged. This is the same class of surprise the old rule caused in reverse, and the new one is at least predictable |
| 4 | No workspace folder open in VS Code (single loose file) | No hint; falls to cwd, now the extension host's dir | Rule 4 warning already exists; the Paths popup lets the user set it explicitly |
| 5 | Setting the child `cwd` changes relative-path resolution for user pipeline code | Discovered modules resolving relative paths behave differently | Arguably a fix (project root beats VS Code's install dir), but it is a behavior change worth calling out in the handover |
| 6 | Stale `scistack.toml` at the old, db-adjacent location | Silently ignored from now on | `describe_managed_paths` reports the resolved config path, so the Paths popup shows which file is live |

## Tests

`tests/test_config.py` (extends the existing `infer_project_root` block,
which must be rewritten for the new name and rules):

- Precedence: explicit arg > hint > cwd > db dir, one test each.
- **The regression itself**: hint on one drive, db on another → `add_path`
  writes a config *and* the next `load_config` reads it back with the added
  path present. This is the exact scenario in the log and nothing covered
  it.
- **The clobber**: two successive `add_path` calls → both paths survive.
- Folder-scan fallback roots at the project root, not the db directory.
- `locate_config_at` does not walk upward (a config in the parent is *not*
  found).

Existing tests to check: `test_project_api.py:39` references
`_locate_pyproject` in a comment; `tests/conftest.py:203`'s
`_pin_project_root` fixture already pins the hint, which now matters for
every test rather than only entities-file placement.
