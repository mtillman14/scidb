# Discovery side-effect guard (A + B)

Stop folder-scan discovery from *executing* stray scripts it finds.

## Problem

Discovery must import to work — the registry stores live callables
(`_functions: dict[str, callable]`) because the backend needs real objects to
reconstruct `for_each` calls. `spec.loader.exec_module()` runs the whole module
body, and `_suppress_user_code_output()` only redirects stdout/stderr; it does
not stop execution.

Observed in a real scan (`test_logs.md`, 20:07:21–20:07:36):

- `plot_gait_speeds.py:90` — bare `plot_gait(sex, age, speed)` at module level
  rendered a matplotlib figure and tried `plt.savefig()` to a hardcoded Linux
  path from another machine → `FileNotFoundError`.
- `plot_tug_times.py:82` — same shape.
- **13 of the ~15 second startup** was these two scripts rendering plots to
  nowhere.

### Why this got more urgent

The sibling-import (`sys.path`) fix means 6 previously-dead imports now
succeed. Files that used to die at line ~11 on `ModuleNotFoundError` will now
run their full module body for the first time. Without this guard, that fix
converts 6 fast failures into 6 slow side-effecting imports.

## A. AST pre-screen — warn and refuse

New in `scifor.discovery` (generic mechanic, per CLAUDE.md NOTE 3; usable by
`scidb.discover` later):

```python
@dataclass
class TopLevelSideEffect:
    lineno: int
    call: str          # rendered callee, e.g. "plot_gait"

def find_top_level_side_effects(source, *, allow=BENIGN_TOPLEVEL_CALLS) -> list[TopLevelSideEffect]
```

**The rule — two forms:**

1. **A bare call**: module-body `ast.Expr` whose `.value` is an `ast.Call`. The
   result is discarded, so it runs purely for effect. `plot_gait(sex, age,
   speed)` is exactly this.
2. **An assignment calling a function `def`'d in the same file**:
   `data = plot_gait(sex, age, speed)`.

Form 2 exists because **statement form is not a sufficient discriminator**.
`RATE = Parameter(1, 2, 3)` and `data = plot_gait(...)` are both
Assign-of-Call; what separates them is that `Parameter` is *imported* while
`plot_gait` is `def`'d right there. A file that defines work and then does it
is the shape we're catching.

Consequence worth keeping: **entity construction needs no allowlist**.
`Parameter`, `PathInput`, `EachOf`, `Sweep` — and any entity type added later —
are imported names, so they never match. Nothing to maintain.

Deliberately *not* flagged:

| Form | Why |
|---|---|
| `RATE = Parameter(1, 2, 3)` | imported callee. Must execute — it is the point. |
| `RAW = PathInput('{s}.mat')` | same |
| `logger = logging.getLogger(__name__)` | imported callee; assignments flag *only* local functions so this stays silent with zero maintenance |
| `CONFIG = Config()` for a local class | classes excluded — instantiation is usually cheap, functions are where work lives |
| `print(...)`, `logger.info(...)` | **output-only** — see below |
| docstrings | `Expr` wrapping a `Constant`, not a `Call` |
| `if __name__ == "__main__": main()` | the `If` is the module-body child; we never descend into it |
| imports, `def`, `class` | definitions only |

### Output-only calls are benign

Caught by `test_print_in_discovered_file_does_not_reach_console` failing: the
first rule conflated *writes to the console* with *does work*, and refused

```python
print('hello from noisy module')

def noisy_fn(x):
    return x
```

Three reasons that's wrong: a stray `print` says nothing about whether a file
does work; refusing costs every function the file defines; and
`_suppress_user_code_output()` already exists to handle exactly this, so the
guard was overriding machinery that was doing the right job.

Allowed: `print`, `pprint`, `pprint.pprint`, `sys.stdout.write`,
`sys.stderr.write`, plus any **dotted** callee whose last segment is a logging
method (`debug`/`info`/`warning`/`warn`/`error`/`exception`/`critical`/`log`) so
`logger.info(...)` passes whatever the logger is named. The dot is required, so
a local `def error(...)` invoked bare is still flagged.

**Allowlist** (`BENIGN_TOPLEVEL_CALLS`) — common harmless top-of-file config,
matched on the rendered dotted callee and its last two segments:
`matplotlib.use`, `matplotlib.style.use`, `plt.style.use`, `logging.basicConfig`,
`logging.captureWarnings`, `logging.disable`, `warnings.filterwarnings`,
`warnings.simplefilter`, `pandas.set_option`, `pd.set_option`, `numpy.seterr`,
`np.seterr`, `seaborn.set_theme`/`set_style`/`set_context`/`set_palette` (and
`sns.` forms), `sys.setrecursionlimit`.

**Known gaps** (documented, not fixed in v1 — all chosen for a low
false-positive rate):

- A bare top-level `for` / `while` / `with` executes and is not reported.
- `df = pd.read_csv("huge.csv")` reads a file, but flagging *imported* callees
  in assignments would also flag every `logging.getLogger` and `Path(...)` in
  the wild — far too noisy.
- **Factory helpers are a false positive**: `RAW = make_path("emg")` where
  `make_path` is a local `def` returning a `PathInput` gets refused. Escape
  hatch is an open decision (see below).

**Unparseable files:** record the `SyntaxError` as a load error and skip the
import entirely — importing a file that does not parse gains nothing and the
user-visible outcome is the same.

### Wiring

In `registry._exec_file_modules`, screen before `spec_from_file_location`. On a
hit: `_record_load_error` (surfaces in the 📁 Paths → Discovered Code panel) and
`continue` — never execute.

Message:

```
Skipped: top-level call plot_gait() at line 90 would execute on import.
Wrap it in `if __name__ == "__main__":` to make this file discoverable.
```

Log at **INFO**, not WARNING/ERROR. Matches the existing deliberate choice at
`registry.py:344-348` — a stray script in a folder-scanned tree is routine and
must not read as a GUI failure on the console. The load-error panel is the
place this surfaces to the user.

Scope: loose files only. Packaged code (`_load_packages`) is curated and
imported by name; not screened.

## B. Headless matplotlib during discovery

New in `scifor.discovery`:

```python
@contextlib.contextmanager
def headless_matplotlib(): ...
```

- Sets `MPLBACKEND=Agg` so matplotlib imported *during* the scan picks Agg.
- If `matplotlib` is **already** in `sys.modules`, `mpl.use("Agg", force=True)`
  and restore the previous backend on exit.
- Never imports matplotlib itself — no new hard dependency, no import cost.
- Restores the env var on exit.

Does not stop `savefig`/file writes (A handles that); it stops GUI windows
popping up mid-scan and speeds rendering. Cheap, no downside.

Note: matplotlib first imported *during* discovery stays on Agg afterward.
That is the correct steady state for a server process, and is documented in
the docstring rather than fought.

Wraps both `_load_file_modules` and `_load_packages`.

## Tests

`scifor/tests/test_discovery.py`
- flags bare `Expr(Call)` with correct lineno + rendered callee
- does NOT flag `Parameter(...)`/`PathInput(...)` assignments, docstrings,
  imports, `def`/`class`, `if __name__ == "__main__":` blocks
- allowlist suppresses `matplotlib.use("Agg")`, `logging.basicConfig()`
- multiple offenders all reported, in line order
- `headless_matplotlib`: sets/restores `MPLBACKEND`; restores a pre-existing
  backend; no-op when matplotlib absent

`scistack-gui/tests/test_registry.py`
- **the regression**: a file whose top-level code writes a sentinel file is
  refused — sentinel must not exist afterward
- refusal recorded in `get_load_errors()` with line number and the
  `__main__`-guard hint
- a clean sibling-importing file alongside it still registers
- `if __name__ == "__main__":` file imports fine and registers its functions
- unparseable file → load error, not executed
- refusal logs at INFO, not ERROR/WARNING

## Open decision: escape hatch

The local-function rule has one realistic false positive — an entity built by a
helper defined in the same file:

```python
def make_path(name):
    return PathInput(f"{name}.mat")

RAW = make_path("emg")      # refused, but legitimate
```

Options: leave it (users inline the construction — the error message says so),
or add a marker comment (`# scistack: allow-toplevel`) that suppresses the
refusal for a line or a file. The marker keeps the guard strict by default
while making refusal recoverable, but it is a new user-facing convention.
Not implemented pending a decision.

## Files

- `scifor/src/scifor/discovery.py` — screen + `headless_matplotlib`
- `scifor/src/scifor/__init__.py` — exports
- `scistack-gui/scistack_gui/registry.py` — wiring
- `scifor/tests/test_discovery.py`, `scistack-gui/tests/test_registry.py`
