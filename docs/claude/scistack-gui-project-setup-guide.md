# SciStack GUI Project Setup Guide

A step-by-step guide for structuring your files and directories to work with the SciStack GUI.

---

## Table of Contents

1. [Choose Your Mode](#1-choose-your-mode)
2. [Quick Start: Scaffolded Project (Recommended)](#2-quick-start-scaffolded-project-recommended)
3. [Quick Start: Single-File Mode](#3-quick-start-single-file-mode)
4. [Quick Start: VS Code Extension Wizard (No Terminal Required)](#4-quick-start-vs-code-extension-wizard-no-terminal-required)
5. [Quick Start: Browser Wizard (No VS Code Required)](#5-quick-start-browser-wizard-no-vs-code-required)
6. [Full Project Directory Layout](#6-full-project-directory-layout)
7. [Configuration Files Reference](#7-configuration-files-reference)
8. [Defining Variables](#8-defining-variables)
9. [Defining Functions](#9-defining-functions)
10. [Defining Constants](#10-defining-constants)
11. [Using Libraries (Shared Packages)](#11-using-libraries-shared-packages)
12. [How the GUI Discovers Your Code](#12-how-the-gui-discovers-your-code)
13. [Launching the GUI](#13-launching-the-gui)
14. [Troubleshooting](#14-troubleshooting)

---

## 1. Choose Your Mode

The SciStack GUI has **two mutually exclusive modes**:

| Mode | Best for | Minimum files |
|------|----------|---------------|
| **Project mode** (recommended) | Real studies, shared code, reproducibility | `pyproject.toml` + `.duckdb` |
| **Single-file mode** | Quick experiments, prototyping | `pipeline.py` + `.duckdb` |

**Use project mode** if you want lockfiles, library dependencies, multi-file organization, or reproducibility snapshots. **Use single-file mode** if you just want to get something on screen fast.

---

## 2. Quick Start: Scaffolded Project (Recommended)

The fastest way to get a correct project layout is the CLI scaffolder:

```bash
scistack project new my_study
```

This creates:

```
my_study/
├── .scistack/
│   ├── project.toml           # Project metadata
│   └── snapshots/             # For publication snapshots (future)
├── pyproject.toml             # Python project config + [tool.scistack]
├── uv.lock                    # Pinned dependency versions (auto-created)
├── src/my_study/
│   └── __init__.py            # Your Variables, Functions, Constants go here
├── data/                      # Raw inputs (gitignored or DVC-tracked)
├── plots/
├── my_study.duckdb            # Your database
├── my_study.layout.json       # Auto-created: DAG node positions
├── .gitignore
└── README.md
```

After scaffolding, open the GUI:

```bash
scistack-gui my_study.duckdb --project pyproject.toml
```

Or in VS Code, use the SciStack extension and select "Select a project (pyproject.toml)".

---

## 3. Quick Start: Single-File Mode

Create two files:

```
my_experiment/
├── experiment.duckdb          # Created by the GUI or scidb.configure_database()
└── pipeline.py                # All your Variables, Functions, Constants
```

**`pipeline.py`:**
```python
from scidb import BaseVariable, constant, configure_database

# --- Variables ---
class RawSignal(BaseVariable):
    pass

class FilteredSignal(BaseVariable):
    pass

# --- Constants ---
CUTOFF_HZ = constant(30.0, description="Low-pass cutoff frequency")

# --- Functions ---
def low_pass_filter(signal, cutoff_hz):
    # your processing logic here
    return filtered
```

Launch:

```bash
scistack-gui experiment.duckdb --module pipeline.py
```

Everything you want the GUI to see must be defined in (or imported by) that one `.py` file.

Single-file mode is CLI-only. The VS Code extension has no equivalent: it
always opens the workspace folder as the project and auto-discovers code
from it (see §4).

---

## 4. Quick Start: VS Code Extension Wizard (No Terminal Required)

If you're using the SciStack VS Code extension, you don't need a terminal or
any pre-existing files at all -- there's an in-editor wizard that creates the
`.duckdb` file and defines its schema for you.

**This wizard is extension-only.** The browser-only frontend (`scistack-gui`
launched from the CLI) has no equivalent screen -- see the note at the end of
this section.

### Steps

1. Run the command **`SciStack: Open Pipeline`** (`scistack.openPipeline`)
   from the Command Palette.
2. Choose **"Create new database"** (vs. "Open existing database").
3. Pick a **folder**, then type a **filename** (`.duckdb` is appended
   automatically if you leave it off).
4. Type **schema keys**, comma-separated, ordered top-down (e.g.
   `subject, session, trial`). This is the schema definition step -- it's
   validated to require at least one key before you can continue.
That's the whole wizard. **There is no step asking how SciStack should
discover your pipeline code.** There used to be one -- a "How should SciStack
discover your pipeline code?" QuickPick offering project / single-module /
no-module -- and it was removed, along with its `projectInit.ts` "create a
scistack.toml?" prompt, because every branch is now handled automatically:

- The project is the **workspace folder you have open**, passed as
  `--project-root` and resolved by `config.resolve_project_root` (rule 2).
- Code under it is discovered by `bootstrap.open_or_create_project`'s
  auto-discovery branch: a `pyproject.toml`/`scistack.toml` at the root if
  there is one, otherwise a folder scan for `.py`/`.m` files.
- A missing config file is created server-side by
  `services.project_init_service.ensure_project_files`, for the browser
  frontend as well as the extension.

The one case the picker covered that nothing else does is having **no folder
open in the VS Code window** -- discovery then has no project root to work
from. `extension.ts`'s `warnIfNoWorkspaceFolder` says so explicitly (Output
channel every start, toast once per session) rather than leaving an
unexplained empty canvas.

### What happens under the hood

The extension spawns the same JSON-RPC backend the rest of the GUI talks to,
passing the schema keys on the command line:

```
python -m scistack_gui.server --db <path> --schema-keys "subject,session,trial" [--project-root <workspace folder>]
```

(argv built by `extension/src/serverArgs.ts`'s `buildServerArgs`, spawned by
`extension/src/pythonProcess.ts`. `--module`/`--project` remain CLI-only
flags; the extension never passes them, and `serverArgs.test.ts` locks that
in.) Because the
`.duckdb` file doesn't exist yet, `scistack_gui/server.py`'s `main()` treats
this as a creation request: it calls `create_db(db_path, schema_keys)`
(`scistack_gui/db.py`), which calls `scidb.configure_database(db_path,
schema_keys)` to create the DuckDB file and its `_schema` table. On an
ordinary "open existing database" run, no `--schema-keys` is passed and the
server calls `init_db()` instead, reading the schema keys back out of the
existing `_schema` table.

Restarting the server later (e.g. `SciStack: Restart Python Process`) reuses
the remembered `dbPath`/`schemaKeys`/`modulePath`/`projectPath` from the first
run (`extension/src/extension.ts`, `lastStartArgs`) and does **not** re-pass
`schemaKeys`, since the database already exists by then.

### What this wizard does *not* do

- It does not scaffold a full project layout (`pyproject.toml` + `uv.lock` +
  `src/{name}/` + `data/`/`plots/` -- see
  [Quick Start: Scaffolded Project](#2-quick-start-scaffolded-project-recommended)).
  It only writes a bare `scistack.toml` if you point it at a project folder
  with no config file at all. For the full scaffolded layout, run
  `scistack project new` from a terminal first, then open the resulting
  folder with the wizard's "Open existing database" path.
- It does not let you define Variable *classes* (i.e. table schemas beyond
  the top-level `subject`/`session`/`trial` schema keys) -- that still
  requires either writing Python or using the GUI's "Create Variable" action
  once a project with an `entities_file` is loaded (see
  [Defining Variables](#8-defining-variables)).

---

## 5. Quick Start: Browser Wizard (No VS Code Required)

If you're launching `scistack-gui` from a terminal rather than through VS
Code, the same open-or-create flow is available as an in-browser wizard --
you don't need to already have a `.duckdb` file.

**This wizard is browser-only.** It never appears inside the VS Code
webview, since the extension always opens or creates a database itself
(§4) before the webview ever mounts.

### Steps

1. Launch with no path: `scistack-gui` (no arguments). The browser opens
   directly onto the wizard instead of the usual DAG canvas.
2. Choose **"Open existing database"** or **"Create new database"**.
   - **Open**: type the full path to an existing `.duckdb` file.
   - **Create**: type a destination **folder** (must already exist),
     a **filename** (`.duckdb` appended automatically), and **schema keys**
     (comma-separated, top-down -- e.g. `subject, session, trial`).
3. Submit. The database is created/opened and the browser transitions
   straight into the normal DAG view -- no page reload.

Unlike the VS Code wizard, there's no third step asking how to discover
pipeline code (project / module / none). Both `POST /api/bootstrap/create`
and `/open` always call `open_or_create_project()` with no `module`/
`project` argument, which puts it on the same auto-discovery path
`config.load_config(None, db_path)` already uses elsewhere in this
codebase -- the loose-script/folder-scan mode: search upward for a
`pyproject.toml`, and if none is found, scan the database's own directory
for `.py`/`.m` files directly. Nothing needs to be typed in up front, and
the header's "Refresh Code" button re-scans once files exist.

### Why plain text paths instead of a file browser

VS Code's wizard gets a native folder/file picker for free
(`vscode.window.showOpenDialog`). A browser has no equivalent that returns
a real filesystem path -- `<input type="file">` sandboxes the selection and
never exposes a usable server-side path, even though the FastAPI server and
the browser are running on the same machine. Building an in-browser
directory navigator (a `GET` endpoint that lists server-side directories,
plus a breadcrumb UI) was considered and deliberately deferred as
unnecessary scope for the first version -- see
`.claude/plan-browser-db-creation-wizard.md`. Every path in this wizard is
typed in directly.

### What happens under the hood

Unlike the VS Code wizard (which passes `--schema-keys` on the command line
before the server process starts -- §4), the browser wizard's two calls
happen **after** `scistack-gui` is already running, from inside a request
handler:

- `POST /api/bootstrap/create` -- `scistack_gui/api/bootstrap.py`
- `POST /api/bootstrap/open` -- `scistack_gui/api/bootstrap.py`

Both wrap `scistack_gui.bootstrap.open_or_create_project()`, the exact same
sequence `__main__.py` runs at CLI startup when you do pass a `db_path`
(import pipeline code, then `create_db()`/`init_db()`,
`replay_persisted_builtins()`, `Log.bridge_python_logging()`,
`check_lockfile_staleness()`). No process restart is needed to pick up the
newly opened database -- `scistack_gui.db._db` is a plain swappable module
global, so setting it from a request handler works identically to setting
it before `uvicorn.run()` starts.

The frontend knows whether to show the wizard at all via `GET /api/info`,
which now returns `{"db_loaded": false}` instead of erroring when nothing
is open yet (`scistack_gui/services/pipeline_service.py`). `App.tsx`
renders `ProjectBootstrapWizard` in that case and re-fetches `/api/info`
once the wizard's POST succeeds.

---

## 6. Full Project Directory Layout

Here is the canonical structure with annotations:

```
my_study/
│
├── .scistack/                         # SciStack project metadata
│   ├── project.toml                   # Version + creation date
│   └── snapshots/                     # Publication snapshots (future)
│       └── 2025-nature.toml           # Pins: git SHA + lockfile hash + record IDs
│
├── pyproject.toml                     # REQUIRED: Python project + [tool.scistack] config
├── uv.lock                            # REQUIRED: Created by `uv sync`
│
├── src/
│   └── my_study/                      # Your project's Python package
│       ├── __init__.py                # Can define Variables/Functions/Constants here
│       ├── variables.py               # Or split into modules
│       ├── preprocessing.py
│       └── analysis.py
│
├── data/                              # Raw input data (typically gitignored)
├── plots/                             # Output plots
│
├── my_study.duckdb                    # The project database (one per project)
├── my_study.layout.json               # Auto-created: node positions on the DAG canvas
│
├── .gitignore
└── README.md
```

### Naming Rules

- **Project name** must be a valid Python package name: lowercase letters, digits, and underscores only, starting with a lowercase letter.
  - `my_study` -- valid
  - `eeg_analysis_v2` -- valid
  - `MyStudy` -- invalid (uppercase)
  - `2nd_experiment` -- invalid (starts with digit)
- **One project = one `.duckdb` file.** The database file is named `{project_name}.duckdb` and lives at the project root.

---

## 7. Configuration Files Reference

### A. `pyproject.toml` -- Main Configuration

This is the only file the GUI strictly requires in project mode. It must contain a `[tool.scistack]` section (which can be empty).

```toml
[project]
name = "my_study"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "scidb",
    # Add shared library packages here:
    # "mylab-preprocessing>=1.0",
]

[dependency-groups]
dev = [
    "scistack-gui",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/my_study"]

# --- SciStack configuration ---
[tool.scistack]
# Local .py files to load (paths relative to pyproject.toml directory)
modules = [
    "src/my_study/variables.py",
    "src/my_study/preprocessing.py",
    "src/my_study/analysis.py",
]

# Where the GUI writes new Variable/Parameter/PathInput declarations
entities_file = "src/scistack_entities.toml"

# Pip-installed packages to scan for Variables/Functions/Constants
packages = ["lab_shared_utils", "eeg_preprocessing"]

# Auto-discover packages with scistack.plugins entry points (default: true)
auto_discover = true
```

**All `[tool.scistack]` fields are optional.** Here's what each does:

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `modules` | list of paths | `[]` | Local `.py` files to import for discovery |
| `entities_file` | path | `src/scistack_entities.toml` | TOML file the GUI writes new Variable/Parameter/PathInput declarations to — the only file it writes (`entities-toml-format.md`) |
| `variable_file` | path | `None` | Legacy `.py` entities file: still discovered, never written |
| `packages` | list of strings | `[]` | Installed packages to scan for scistack exports |
| `auto_discover` | bool | `true` | Scan `scistack.plugins` entry points automatically |

### B. `.scistack/project.toml` -- Project Metadata

Auto-generated. You generally don't edit this by hand.

```toml
[scistack]
version = "0.1.0"
created = "2026-04-13T06:10:00+00:00"
```

### C. `uv.lock` -- Dependency Lockfile

Created automatically by `uv sync`. The GUI checks this on startup:
- If `pyproject.toml` is newer than `uv.lock`, the GUI runs `uv sync` automatically.
- If `uv.lock` is missing, you'll get a startup error.

To create or update it manually:

```bash
uv sync
```

### D. `{name}.layout.json` -- DAG Node Positions

Auto-created by the GUI beside the `.duckdb` file. Stores cosmetic node positions on the pipeline canvas. You don't need to create this -- the GUI manages it.

---

## 8. Defining Variables

Variables are Python classes that subclass `BaseVariable`. Each variable type maps to a table in the DuckDB database.

```python
from scidb import BaseVariable

class RawEMG(BaseVariable):
    """Raw EMG signal from the amplifier."""
    pass

class FilteredEMG(BaseVariable):
    """Band-pass filtered EMG signal."""
    pass

class TrialOnsets(BaseVariable):
    """Timestamps marking the start of each trial."""
    pass
```

### Rules

- Class names must be valid Python identifiers and must **not** start with `_`.
- The class name becomes the database table name exactly as written (no snake_case conversion).
- Variables are discovered by the GUI if they are **defined** in a loaded module (`__module__` must match).
- You can also create variables from the GUI itself -- they get added to the `variables` list in the TOML file specified by `entities_file` (see `entities-toml-format.md`).

---

## 9. Defining Functions

Functions appear in the pipeline DAG when they process variables via `for_each()`.

### Option A: Plain Functions

```python
def bandpass_filter(signal, low_hz, high_hz):
    """Apply a bandpass filter."""
    # ... processing logic ...
    return filtered_signal
```

These are discovered when they run through `for_each()` and their execution is recorded in the database.

### Option B: `@lineage_fcn` Decorated Functions (Recommended for Libraries)

```python
from scilineage import lineage_fcn

@lineage_fcn
def bandpass_filter(signal, low_hz, high_hz):
    """Apply a bandpass filter."""
    # ... processing logic ...
    return filtered_signal
```

The `@lineage_fcn` decorator wraps the function so the discovery scanner can identify it as a pipeline function **before** it has ever been run. This is the recommended approach for shared library code.

### Discovery Rules

- In **single-file mode**: all top-level callables that don't start with `_` and are not classes are discovered.
- In **project mode**: functions are discovered from the three configured sources (modules, packages, entry points).
- If two sources define a function with the same name, the later one wins (with a warning).

---

## 10. Defining Constants

Constants are named scalar values that appear in the pipeline DAG.

```python
from scidb import constant

SAMPLING_RATE_HZ = constant(1000, description="Default sampling rate for all recordings")
DEFAULT_BANDPASS = constant((1.0, 40.0), description="Standard LFP bandpass range")
WINDOW_SIZE_MS = constant(250, description="Analysis window size in milliseconds")
```

### How They Work

- `constant()` returns a `Constant` wrapper with transparent value semantics -- you can use it anywhere you'd use the raw value (`SAMPLING_RATE_HZ + 1` works).
- The wrapper carries `.description`, `.source_file`, and `.source_line` metadata.
- Constants appear as **ConstantNode** elements in the pipeline DAG when passed to `for_each()`.
- The GUI also supports **pending constant values** -- variant values declared in the UI that haven't been run yet.

---

## 11. Using Libraries (Shared Packages)

A library is a plain Python package that happens to contain scistack exports (Variables, Functions, or Constants).

### Creating a Library

```
mylab-preprocessing/
├── pyproject.toml
├── src/mylab_preprocessing/
│   ├── __init__.py
│   ├── filters.py          # @lineage_fcn decorated functions
│   └── constants.py        # constant() definitions
└── README.md
```

There's nothing scistack-specific in the file layout. A package becomes a "scistack library" simply because it contains at least one `BaseVariable` subclass, `LineageFcn` instance, or `Constant` instance.

### Using a Library in Your Project

**Step 1:** Add it to your `pyproject.toml` dependencies:

```toml
[project]
dependencies = [
    "scidb",
    "mylab-preprocessing>=1.0",
]
```

**Step 2:** Run `uv sync` to install it.

**Step 3:** Tell SciStack to scan it (choose one method):

- **Explicit**: Add to `[tool.scistack] packages`:
  ```toml
  [tool.scistack]
  packages = ["mylab_preprocessing"]
  ```

- **Entry point auto-discovery**: The library declares an entry point in its own `pyproject.toml`:
  ```toml
  [project.entry-points."scistack.plugins"]
  mylab_filters = "mylab_preprocessing.filters"
  ```
  Then any project with `auto_discover = true` (the default) will pick it up automatically.

#### How the entry point declaration works

The entry point has two parts separated by `=`:

```toml
[project.entry-points."scistack.plugins"]
mylab_filters = "mylab_preprocessing.filters"
#  ^^ name           ^^ module path
```

- **Left side (name)**: An arbitrary short identifier for this entry point (e.g. `mylab_filters`). This is used mainly for logging and, if the right side points to a single callable rather than a module, as the function's registration name. You can declare multiple entry points per package by using different names:
  ```toml
  [project.entry-points."scistack.plugins"]
  variables = "mylab_preprocessing.variables"
  filters   = "mylab_preprocessing.filters"
  constants = "mylab_preprocessing.constants"
  ```

- **Right side (module path)**: A dotted Python import path that the GUI will `import` and scan. It can point to:
  - A **module** (e.g. `"mylab_preprocessing.filters"`) -- the GUI scans all top-level members for Variables, Functions, and Constants.
  - A **specific callable** (e.g. `"mylab_preprocessing.filters:bandpass_filter"`) -- the GUI registers just that one function.

The advantage of entry points over the explicit `packages` list is that the library author declares discoverability once, and every project that installs the library picks it up automatically -- no per-project configuration needed.

### Library Panel in the GUI

The GUI's library panel lists installed packages from `uv.lock` where the scanner found at least one scistack export. Pure utility packages (like `numpy`, `scipy`) are hidden. Framework packages (`scidb`, `scifor`, `scilineage`, etc.) are also skipped.

### Package Indexes (Homebrew-tap style)

To share libraries across a lab or team, you can set up a package index. The system is modeled after Homebrew taps: a "tap" is a Git repository containing a `packages.toml` file that catalogs available scistack libraries and where to download them.

#### Setting up a tap (index maintainer)

Create a Git repository with a `packages.toml` at the root:

```
mylab-scistack-index/          # the Git repo
└── packages.toml
```

**`packages.toml`:**
```toml
[[package]]
name = "mylab-preprocessing"
description = "Standard preprocessing pipeline for the lab"
versions = ["0.3.0", "0.2.1", "0.1.0"]
index_url = "https://pypi.mylab.org/simple"

[[package]]
name = "mylab-stats"
description = "Statistical analysis helpers"
versions = ["1.0.0"]
index_url = "https://pypi.mylab.org/simple"
```

Each `[[package]]` entry has:
| Field | Required | Purpose |
|-------|----------|---------|
| `name` | yes | PyPI distribution name |
| `description` | no | Human-readable description (used for search in the GUI) |
| `versions` | no | Available version strings |
| `index_url` | no | PEP 503 simple index URL where the package wheels are hosted |

The `index_url` is where the actual package wheels live (a private PyPI server, GitHub Pages simple index, etc.). The tap repo itself only contains the catalog -- not the packages.

Push this repo to a Git host (e.g. `https://github.com/mylab/scistack-index.git`).

#### Adding a tap (end user)

```bash
scistack tap add mylab https://github.com/mylab/scistack-index.git
```

This does three things:
1. Validates the tap name (must be lowercase alphanumeric with hyphens/underscores).
2. Saves the entry to `~/.scistack/config.toml`.
3. Shallow-clones the repo to `~/.scistack/taps/mylab/`.

The resulting `~/.scistack/config.toml`:
```toml
[[tap]]
name = "mylab"
url = "https://github.com/mylab/scistack-index.git"
```

#### Browsing and installing from a tap

In the GUI's library panel, you can search tapped indexes. When you install a package from a tap, the GUI runs:

```bash
uv add mylab-preprocessing==0.3.0 --index https://pypi.mylab.org/simple
```

This writes the dependency and its index URL into the project's `pyproject.toml`, making the project portable -- anyone who clones the project can `uv sync` without needing the tap configured locally, because the index URL is recorded directly in the project.

#### Refreshing a tap

To pull the latest package catalog:

```bash
scistack tap refresh mylab
```

This runs `git pull --ff-only` on the local clone at `~/.scistack/taps/mylab/`.

#### Removing a tap

```bash
scistack tap remove mylab
```

This removes the entry from `~/.scistack/config.toml` and deletes the local clone.

---

## 12. How the GUI Discovers Your Code

Understanding the discovery pipeline helps you debug "why doesn't my variable/function show up?"

### Project Mode Discovery Order

1. **Local modules** -- files listed in `[tool.scistack].modules` are imported by file path
2. **Explicit packages** -- packages listed in `[tool.scistack].packages` are imported by name (all submodules walked recursively)
3. **Entry-point packages** -- if `auto_discover = true`, packages declaring `scistack.plugins` entry points are scanned

At each step, the scanner looks for:
- `isinstance(obj, type) and issubclass(obj, BaseVariable)` -- Variables
- `isinstance(obj, LineageFcn)` -- Functions (decorated with `@lineage_fcn`)
- `isinstance(obj, Constant)` -- Constants
- Other callables that don't start with `_` -- plain Functions

Only objects **defined** in the scanned module (not re-exported from elsewhere) are attributed to that module.

### How the project source scanner walks your code

In project mode, the scanner also walks your project's own `src/{project_name}/` directory and every library in `uv.lock`. Here's how it decides what to scan.

#### Your project code (`src/{project_name}/`)

The scanner reads your project name from `pyproject.toml`, then looks for `src/{name}/`. If found, it:

1. Imports `{name}` (i.e. `src/{name}/__init__.py`) and scans it.
2. Recursively walks **every** `.py` file and sub-package under `src/{name}/` using `pkgutil.walk_packages`.

So with this layout:

```
src/my_study/
├── __init__.py          # scanned (as the top-level import)
├── variables.py         # scanned
├── preprocessing.py     # scanned
├── analysis.py          # scanned
└── utils/
    ├── __init__.py      # scanned
    └── helpers.py       # scanned
```

Every `.py` file is discovered. You don't need to list them in `modules` -- the project scanner finds them automatically.

#### Libraries from `uv.lock`

The scanner reads every `[[package]]` entry from `uv.lock` and scans each one, **except**:

- **Framework packages** are skipped: `scidb`, `scifor`, `sciduckdb`, `scilineage`, `scipathgen`, `canonicalhash`, `scirun`, `scihist`, `scistack`, `scistack-gui`.
- **Your own project name** is skipped (to avoid scanning itself twice).
- Pure utility packages (`numpy`, `scipy`, etc.) are scanned but produce zero exports, so they're hidden in the library panel.

For each non-skipped distribution, the scanner resolves the PyPI distribution name to the actual importable package name (e.g. `mylab-preprocessing` -> `mylab_preprocessing`) and walks all submodules, just like for your project code.

### Discovery example: what gets found vs. what doesn't

Given this project:

```
src/my_study/
├── __init__.py
├── variables.py
└── preprocessing.py
```

**`variables.py`:**
```python
from scidb import BaseVariable

class RawEMG(BaseVariable):       # DISCOVERED -- defined here
    pass

class _InternalHelper(BaseVariable):  # SKIPPED -- name starts with _
    pass
```

**`preprocessing.py`:**
```python
from scilineage import lineage_fcn
from scidb import constant
from my_study.variables import RawEMG  # re-import

class FilteredEMG(BaseVariable):       # DISCOVERED -- defined here
    pass

# Re-exported from variables.py:
# RawEMG is NOT discovered in this module because
# RawEMG.__module__ == "my_study.variables", not "my_study.preprocessing"

@lineage_fcn
def bandpass_filter(signal, low, high):  # DISCOVERED -- defined here
    ...

@lineage_fcn
def _private_helper(x):                 # SKIPPED -- name starts with _
    ...

CUTOFF_HZ = constant(30.0)              # DISCOVERED -- Constants don't have
                                         # the __module__ check, so they're
                                         # attributed to wherever the name appears
```

**`__init__.py`:**
```python
from my_study.variables import RawEMG
from my_study.preprocessing import bandpass_filter

# RawEMG: NOT discovered here (its __module__ is "my_study.variables")
# bandpass_filter: NOT discovered here (its fcn.__module__ is "my_study.preprocessing")
# This is correct -- re-exports don't create duplicates.
```

**Summary of what the scanner sees:**

| Module | Variables | Functions | Constants |
|--------|-----------|-----------|-----------|
| `my_study` (`__init__.py`) | (none) | (none) | (none) |
| `my_study.variables` | `RawEMG` | (none) | (none) |
| `my_study.preprocessing` | `FilteredEMG` | `bandpass_filter` | `CUTOFF_HZ` |

The `__module__` check is the key deduplication mechanism. A Variable or Function is only attributed to the module where it was **originally defined**, even if other modules import and re-export it. This prevents the same item from appearing multiple times in the GUI.

### Pipeline DAG Construction

The DAG you see in the GUI is built from:

1. **`for_each` run history** -- every `for_each` execution records `(function_name, output_type, input_types, constants)` in the database
2. **Known variable types** -- variables that exist in the DB but haven't been run through `for_each`
3. **Manual nodes/edges** -- user-created connections in the GUI
4. **Layout positions** -- from the `.layout.json` file

**Node types**: `variableNode`, `functionNode`, `constantNode`, `pathInputNode`

**Run states** (green/grey/red) are computed per node and propagated through the DAG topologically.

---

## 13. Launching the GUI

### From the Command Line

```bash
# Project mode
scistack-gui my_study.duckdb --project pyproject.toml

# Single-file mode
scistack-gui experiment.duckdb --module pipeline.py

# Auto-detect: searches upward from the .duckdb directory for a pyproject.toml
# with a [tool.scistack] section
scistack-gui my_study.duckdb
```

### From VS Code

1. Install the SciStack VS Code extension.
2. **Open the folder containing your project** -- this is what the extension
   treats as the project root, and it is the only thing that decides which
   code gets discovered.
3. Run **`SciStack: Open Pipeline`** from the command palette and open (or
   create) the `.duckdb` file. Code discovery is automatic; there is no
   project-vs-module prompt. See §4.

---

## 14. Troubleshooting

### "My variable/function doesn't appear in the GUI"

1. **Check the module is listed** -- in project mode, make sure your file is either in `modules`, or the package is in `packages`, or the entry point is registered.
2. **Check `__module__`** -- the scanner only picks up objects *defined* in the scanned module. If you import a Variable from another file, it won't be attributed to the importing module.
3. **Check naming** -- Variable class names must not start with `_`. Function names must not start with `_`.
4. **Hit Refresh** -- in single-file mode, the module is re-executed on "Refresh" to pick up changes. In project mode, use the refresh button or restart the server.

### "Startup error about stale lockfile"

The GUI checks if `pyproject.toml` is newer than `uv.lock` on startup. If so, it runs `uv sync` automatically. If `uv sync` fails, you'll see a blocking error dialog. Fix by running `uv sync` manually in your terminal and checking for dependency conflicts.

### "uv.lock is missing"

Run `uv sync` in your project root to generate it.

### "Functions show up but have no connections"

Functions only get edges in the DAG after they've been run through `for_each()` at least once. The run records which variables were inputs and outputs. Before the first run, functions appear as disconnected nodes (unless you manually add edges in the GUI).

### "Name collision warning"

If two sources define a function with the same name, the later one wins. Rename one of the conflicting functions, or adjust your `modules`/`packages` lists to avoid loading both.
