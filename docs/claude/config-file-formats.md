# Config File Formats: `pyproject.toml` vs `scistack.toml`

SciStack GUI reads its project configuration from **one** of two TOML files. They are functionally equivalent — the same fields, same defaults, same behavior. The only difference is where the keys live in the file.

## `pyproject.toml` — nested under `[tool.scistack]`

The scistack section is nested inside the standard Python project file:

```toml
[project]
name = "my_study"
version = "0.1.0"
dependencies = ["scidb"]

[tool.scistack]
modules = ["src/my_study/pipeline.py"]
entities_file = "src/scistack_entities.toml"
packages = ["lab_shared_utils"]
auto_discover = true

[tool.scistack.matlab]
functions = ["matlab/functions/*.m"]
variables = ["matlab/types/*.m"]
variable_dir = "matlab/types"
```

Use this when your project already has a `pyproject.toml` (the common case for Python projects managed with uv, pip, or hatch).

## `scistack.toml` — top-level keys

The entire file IS the scistack config. No `[tool.scistack]` nesting needed:

```toml
modules = ["src/my_study/pipeline.py"]
entities_file = "src/scistack_entities.toml"
packages = ["lab_shared_utils"]
auto_discover = true

[matlab]
functions = ["matlab/functions/*.m"]
variables = ["matlab/types/*.m"]
variable_dir = "matlab/types"
```

Use this when:
- The project doesn't have a `pyproject.toml` (e.g. a pure MATLAB project)
- You want scistack config in a separate file for clarity

## Mapping between formats

| `pyproject.toml` key | `scistack.toml` key |
|---|---|
| `[tool.scistack].modules` | `modules` |
| `[tool.scistack].entities_file` | `entities_file` |
| `[tool.scistack].variable_file` | `variable_file` |
| `[tool.scistack].packages` | `packages` |
| `[tool.scistack].auto_discover` | `auto_discover` |
| `[tool.scistack.matlab].functions` | `[matlab].functions` |
| `[tool.scistack.matlab].variables` | `[matlab].variables` |
| `[tool.scistack.matlab].variable_dir` | `[matlab].variable_dir` |
| `[tool.scistack.matlab].entities_file` | `[matlab].entities_file` |

## The three entity-declaration keys

Easy to confuse, so stated once. Full detail in `entities-toml-format.md`.

| Key | Format | Written by the GUI? |
|---|---|---|
| `entities_file` | TOML | **Yes — the only one.** Default `src/scistack_entities.toml` |
| `variable_file` | `.py` | No. Read-only legacy; folded into `modules` so its declarations stay discovered |
| `[matlab] entities_file` | `.m` script | Read-only in principle; still writable pending a decision |

A top-level `entities_file` (TOML, language-neutral) and a `[matlab]
entities_file` (a MATLAB script) are different keys in different tables.

## Lookup and precedence

When the server resolves which config file to use (`_locate_pyproject` in `config.py`):

1. **Explicit path given** (`--project path`):
   - If `path` is a file, use it directly.
   - If `path` is a directory, look for `pyproject.toml` first, then `scistack.toml`. If neither exists, raise `FileNotFoundError`.

2. **No path given** (auto-search from database location):
   - Walk upward from the `.duckdb` file's directory.
   - At each level, check `pyproject.toml` then `scistack.toml`.
   - Only accept a file if it actually contains a scistack config section (`[tool.scistack]` for pyproject, any content for scistack.toml).

**Key rule**: `pyproject.toml` always wins over `scistack.toml` in the same directory.

The upward walk itself lives in `scifor.discovery.find_project_config`, so
`config.py` and `scidb.entities` (which has to answer the same "which
project is this?" question for `scidb.entities.X`) can never disagree about
the answer.

## Where a NEW config file gets written

Reading finds an existing config. *Writing* one — the first `add_path` or
`set_entities_file` on a project that has none — needs a project root, and
the database is routinely **not** in the project: a `.duckdb` usually lives
in a datasets folder. Writing `scistack.toml` and `src/scistack_entities.toml`
next to it (the behaviour before 2026-08-31) scattered project files across
data directories.

`config.infer_project_root(db_path)` resolves it, most to least
authoritative, logging which rule fired:

1. An existing `pyproject.toml`/`scistack.toml` above the database — an
   established project always wins, so this never relocates one.
2. `--project-root`, i.e. the VS Code workspace folder (passed by
   `extension/src/pythonProcess.ts`).
3. The server's working directory.
4. The database's own directory, as a last resort, with a WARNING.

The first write seeds `modules` with **both** the database's directory and
the project root. Creating a config file switches discovery from folder-scan
mode (which walks the database's directory) to config-driven, so seeding
only the new root would silently stop discovering code the folder scan was
already finding.

Under pytest, rule 3 would make the repo itself the project root — the GUI
test suite pins the hint to `tmp_path` in an autouse fixture
(`scistack-gui/tests/conftest.py::_pin_project_root`) so a test that creates
a project cannot write into the source tree.

## All fields are optional

Every config field has a sensible default. An empty `scistack.toml` (or a `pyproject.toml` with an empty `[tool.scistack]` section, or even a `pyproject.toml` with no `[tool.scistack]` at all) produces a valid config:

| Field | Default | Effect when omitted |
|---|---|---|
| `modules` | `[]` | No local `.py` files loaded explicitly (project source scanner still walks `src/{name}/`). Entries can be files, directories (recursive), or glob patterns. |
| `entities_file` | not set | Auto-created as `src/scistack_entities.toml` in the project root the first time an entity is created from the GUI (or eagerly at project creation) |
| `variable_file` | not set | No legacy `.py` entities file; nothing to fold into `modules` |
| `packages` | `[]` | No extra pip-installed packages scanned |
| `auto_discover` | `true` | `scistack.plugins` entry points are scanned |
| `matlab.functions` | `[]` | No MATLAB `.m` function files loaded |
| `matlab.variables` | `[]` | No MATLAB `.m` classdef files loaded |
| `matlab.variable_dir` | not set | "Create Variable" cannot generate MATLAB classdef files |

**Note**: The MATLAB path (`addpath` directories) is auto-derived from the parent directories of `matlab.functions`, `matlab.variables`, and `matlab.variable_dir`. There is no explicit `matlab.addpath` config field.

## `modules` accepts files, directories, and globs

Each entry in `modules` can be:

- **A `.py` file path**: loaded directly.
- **A directory**: all `.py` files under it are discovered recursively.
- **A glob pattern** (contains `*`, `?`, or `[`): expanded, but only `.py` matches are kept.

These can be mixed freely:

```toml
modules = [
    "pipeline.py",           # single file
    "lib/",                   # all .py files under lib/, recursively
    "extras/**/*.py",         # glob pattern
]
```

An empty directory or a glob that matches no `.py` files logs a warning but is not an error.

## `auto_discover` and `scistack.plugins` entry points

When `auto_discover = true` (the default), SciStack scans all installed Python packages for `scistack.plugins` entry points at startup. This is how shared library packages make their pipeline code visible without every project needing to list them explicitly.

### What makes a package auto-discoverable

A pip-installed package must declare a `scistack.plugins` entry point in its own `pyproject.toml`. This uses the standard Python entry point syntax (PEP 621) — it looks verbose, but it's the same mechanism used by pytest plugins, Flask extensions, etc., and only needs to be written once per library:

```toml
[project.entry-points."scistack.plugins"]
my_filters = "my_package.filters"
```

- **Left side** (`my_filters`): an arbitrary name used for logging. Multiple entry points per package are allowed by using different names.
- **Right side** (`"my_package.filters"`): a dotted Python module path. SciStack imports this module (via `importlib.metadata.entry_points(group="scistack.plugins")`) and scans it for `BaseVariable` subclasses, `@lineage_fcn`-decorated functions, `Constant` instances, and other top-level callables.

A package that does **not** declare this entry point will never be auto-discovered, even if it contains scistack-compatible code. To load such a package, list it explicitly in `packages`.

### When to set `auto_discover = false`

Auto-discovery is almost always what you want. Set it to `false` only if:
- You need full control over which packages are loaded (e.g. to avoid name collisions from a library you installed but don't want active)
- Startup time is a concern and you have many installed packages with entry points

### `packages` vs `auto_discover`

| Mechanism | Who declares it | Where it's configured |
|---|---|---|
| `packages = [...]` | The **project** author lists packages to scan | Project's `scistack.toml` or `pyproject.toml` |
| `auto_discover = true` | The **library** author declares an entry point | Library's own `pyproject.toml` |

Both can be used together. If the same package appears via both `packages` and auto-discovery, it is only scanned once.

## Edge cases

- **Empty `scistack.toml`**: Valid. Parses as `{}`, uses all defaults.
- **`pyproject.toml` without `[tool.scistack]`**: Valid. Uses all defaults. (This was previously a `ValueError` but was fixed to be more forgiving — many projects have a `pyproject.toml` for packaging but haven't added `[tool.scistack]` yet.)
- **No config file at all**: `FileNotFoundError`. The VS Code extension detects this before starting the server and offers to create a `scistack.toml`.
- **Both files in the same directory**: `pyproject.toml` is used; `scistack.toml` is ignored.

## Implementation

- **Parser**: `scistack_gui/config.py` — `load_config()`, `_locate_pyproject()`, `_extract_scistack_section()`
- **VS Code pre-check**: `extension/src/projectInit.ts` — `checkProjectConfig()`, `promptForMissingConfig()`
