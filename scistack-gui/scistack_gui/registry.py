"""
Function and variable class registry.

Supports two modes:
  1. **Single-file mode** (legacy): populated via --module at startup.
  2. **Project mode**: populated from a [tool.scistack] config that lists
     multiple .py files, pip packages, and auto-discovered entry-point plugins.

Gives the backend access to the actual Python objects needed to reconstruct
for_each calls.
"""

from __future__ import annotations

import contextlib
import importlib
import importlib.metadata
import importlib.util
import inspect
import io
import logging
import pkgutil
from pathlib import Path
from typing import TYPE_CHECKING

from scidb import BaseVariable, Constant

if TYPE_CHECKING:
    from scistack_gui.config import SciStackConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_functions: dict[str, callable] = {}
_function_sources: dict[str, str] = {}  # function_name -> source description
_constants: dict[str, Constant] = {}
_constant_sources: dict[str, str] = {}  # constant_name -> source description
_module_paths: dict[str, str] = {}
"""Synthetic module name (``scistack_user_{i}_{stem}``, from
``_load_file_modules``) -> source file path. A BaseVariable subclass's
``__module__`` is that synthetic name, not the file path — this lets
callers (e.g. api/project.py's registry-backed discovery panel) resolve it
back to something human-readable, matching how functions are already
attributed via ``_function_sources``.
"""
_load_errors: list[dict] = []
"""Discovery failures from the most recent load/refresh — [{"source", "error"}, ...].

The DEBUG-level log line next to each of these only lands in scidb.log
(Log.set_level("DEBUG", sink="file")) — this list is what actually surfaces
a failed import to the user, queryable via ``get_load_errors``/
``api/project.py`` (📁 Paths -> Discovered Code), so a failure doesn't just
vanish with the user none the wiser about why a function didn't show up.
"""

# Single-file mode state (legacy)
_module_path: Path | None = None
_module_name: str = "user_pipeline"

# Project mode state
_config: SciStackConfig | None = None

ENTRY_POINT_GROUP = "scistack.plugins"


@contextlib.contextmanager
def _suppress_user_code_output():
    """Redirect stdout/stderr while executing discovered/imported user code.

    Discovery only wants a file's top-level definitions, but there is no
    side-effect-free way to inspect a module in Python -- importing it also
    *runs* it. If that file has real top-level code (a stray debug script,
    a missing ``if __name__ == "__main__":`` guard, ...), its print()s and
    any console-sink log lines it triggers (scidb/scifor route through
    scistacklog's console handler, which resolves ``sys.stderr`` dynamically
    at emit time -- see scistacklog._StderrHandler -- so they're caught by
    this redirect too) would otherwise land in the GUI's own terminal and
    read as if the GUI itself had broken.

    Captured text is logged at DEBUG rather than discarded, so it's still
    recoverable via ``scidb.log`` (``Log.set_level("DEBUG", sink="file")``)
    if a user's script misbehaves and someone needs to see why.

    Best-effort: redirect_stdout/stderr swap process-wide streams, so a
    concurrent request producing console output during the same brief
    window would have it captured too. Discovery runs are short and
    infrequent (startup, explicit "Refresh Code"), so this is an accepted
    tradeoff rather than a correctness concern here.
    """
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            yield
    finally:
        if out.getvalue():
            logger.debug(
                "[registry] captured stdout during import:\n%s", out.getvalue()
            )
        if err.getvalue():
            logger.debug(
                "[registry] captured stderr during import:\n%s", err.getvalue()
            )


# ---------------------------------------------------------------------------
# Single-file mode (legacy, backward-compatible)
# ---------------------------------------------------------------------------


def register_module(module, *, module_path: Path | None = None) -> None:
    """
    Scan a user module for pipeline functions and BaseVariable subclasses.

    Functions: any top-level callable that doesn't start with '_'.
    Variable classes: all BaseVariable subclasses currently in memory
      (they self-register on definition via BaseVariable._all_subclasses).

    If module_path is provided, it is stored so that refresh_module() can
    re-import the file later without restarting the server.
    """
    logger.info("[registry] Registering module from %s", module_path or "<unknown>")
    global _module_path
    if module_path is not None:
        _module_path = module_path
        logger.debug("[registry] Stored module path for refresh: %s", module_path)

    _scan_module_functions(module, source=str(module_path or "<unknown>"))
    _scan_module_constants(module, source=str(module_path or "<unknown>"))
    logger.info(
        "[registry] Module registration complete - %d functions registered",
        len(_functions),
    )


def refresh_module() -> dict:
    """
    Re-import the user module from disk and re-register all functions.

    Returns a summary dict with the old and new function/variable counts
    so the caller can log what changed.
    """
    logger.info("[registry] Starting module refresh from %s", _module_path)
    if _module_path is None:
        raise RuntimeError(
            "No module was loaded at startup (--module not passed). Nothing to refresh."
        )

    old_fns = set(_functions.keys())
    old_vars = set(BaseVariable._all_subclasses.keys())
    logger.debug(
        "[registry] Before refresh: %d functions, %d variables",
        len(old_fns),
        len(old_vars),
    )

    # Clear the function registry so removed functions don't linger.
    logger.info("[registry] Clearing function registry")
    _functions.clear()
    _function_sources.clear()
    _constants.clear()
    _constant_sources.clear()
    _load_errors.clear()

    # Re-execute the module file. This will re-define all functions and
    # BaseVariable subclasses (which auto-register via the metaclass).
    logger.info("[registry] Re-importing module from %s", _module_path)
    spec = importlib.util.spec_from_file_location(_module_name, _module_path)
    user_mod = importlib.util.module_from_spec(spec)
    with _suppress_user_code_output():
        spec.loader.exec_module(user_mod)

    logger.info("[registry] Scanning module for functions")
    _scan_module_functions(user_mod, source=str(_module_path))
    _scan_module_constants(user_mod, source=str(_module_path))

    new_fns = set(_functions.keys())
    new_vars = set(BaseVariable._all_subclasses.keys())
    logger.debug(
        "[registry] After refresh: %d functions, %d variables",
        len(new_fns),
        len(new_vars),
    )

    logger.info("[registry] Module refresh complete")
    return _diff_summary(old_fns, new_fns, old_vars, new_vars)


# ---------------------------------------------------------------------------
# Project mode (multi-source)
# ---------------------------------------------------------------------------


def load_from_config(config: SciStackConfig) -> dict:
    """
    Load all functions and variables from a [tool.scistack] config.

    This is the project-mode equivalent of register_module(). It loads
    from three sources in order:

      1. Explicit .py module files listed in ``config.modules``
      2. Explicit pip-installed packages listed in ``config.packages``
      3. Auto-discovered ``scistack.plugins`` entry points (if enabled)

    Returns a summary dict with discovered function/variable names.
    """
    logger.info("[registry] Loading from config at %s", config.project_root)
    global _config
    _config = config

    old_fns = set(_functions.keys())
    old_vars = set(BaseVariable._all_subclasses.keys())
    logger.debug(
        "[registry] Before load: %d functions, %d variables",
        len(old_fns),
        len(old_vars),
    )

    logger.info("[registry] Clearing function registry")
    _functions.clear()
    _function_sources.clear()
    _constants.clear()
    _constant_sources.clear()
    _module_paths.clear()
    _load_errors.clear()

    logger.info("[registry] Loading %d file modules", len(config.modules))
    _load_file_modules(config.modules)

    logger.info("[registry] Loading %d packages", len(config.packages))
    _load_packages(config.packages)

    if config.auto_discover:
        logger.info("[registry] Auto-discovering entry points")
        _load_entry_points()
    else:
        logger.info("[registry] Skipping entry point discovery (disabled)")

    new_fns = set(_functions.keys())
    new_vars = set(BaseVariable._all_subclasses.keys())
    logger.debug(
        "[registry] After load: %d functions, %d variables", len(new_fns), len(new_vars)
    )

    logger.info("[registry] Config loading complete")
    return _diff_summary(old_fns, new_fns, old_vars, new_vars)


def refresh_all() -> dict:
    """
    Re-load everything from the stored config (project mode).

    Equivalent of refresh_module() but for multi-source configs.
    """
    logger.info("[registry] Starting refresh_all")
    if _config is None:
        raise RuntimeError("No project config loaded. Nothing to refresh.")
    return load_from_config(_config)


def _load_file_modules(paths: list[Path]) -> None:
    """Import each .py file and scan for functions."""
    logger.debug("[registry] Importing %d module files", len(paths))
    for i, path in enumerate(paths):
        logger.debug("[registry] Processing module %d/%d: %s", i + 1, len(paths), path)
        if not path.exists():
            logger.warning("[registry] Skipping missing module: %s", path)
            _record_load_error(str(path), "File does not exist")
            continue
        mod_name = f"scistack_user_{i}_{path.stem}"
        _module_paths[mod_name] = str(path)
        try:
            spec = importlib.util.spec_from_file_location(mod_name, path)
            mod = importlib.util.module_from_spec(spec)
            with _suppress_user_code_output():
                spec.loader.exec_module(mod)
            fn_count_before = len(_functions)
            _scan_module_functions(mod, source=str(path))
            fn_count_after = len(_functions)
            _scan_module_constants(mod, source=str(path))
            logger.info(
                "[registry] Loaded module file: %s (%d functions)",
                path,
                fn_count_after - fn_count_before,
            )
        except Exception as e:
            # DEBUG, not ERROR: a failed import during discovery is routine
            # (framework/example/debug files sitting in a folder-scanned
            # tree were never meant to be pipeline code) and must not read
            # as a GUI failure on the console. Still fully recorded via
            # _record_load_error for the 📁 Paths -> Discovered Code panel,
            # and the traceback is recoverable via scidb.log at DEBUG.
            logger.debug(
                "[registry] Failed to load module file: %s", path, exc_info=True
            )
            _record_load_error(str(path), str(e))


def _load_packages(names: list[str]) -> None:
    """Import each named package and walk its submodules for functions."""
    logger.debug("[registry] Importing %d packages", len(names))
    for pkg_idx, pkg_name in enumerate(names):
        logger.debug(
            "[registry] Processing package %d/%d: %s", pkg_idx + 1, len(names), pkg_name
        )
        try:
            with _suppress_user_code_output():
                pkg = importlib.import_module(pkg_name)
        except ImportError as e:
            logger.debug(
                "[registry] Failed to import package: %s", pkg_name, exc_info=True
            )
            _record_load_error(f"package:{pkg_name}", str(e))
            continue

        # Scan the top-level package module itself.
        fn_count_before = len(_functions)
        _scan_module_functions(pkg, source=f"package:{pkg_name}")
        fn_count_after = len(_functions)
        _scan_module_constants(pkg, source=f"package:{pkg_name}")
        logger.info(
            "[registry] Loaded package: %s (%d functions from top level)",
            pkg_name,
            fn_count_after - fn_count_before,
        )

        # Walk submodules if it's a package (has __path__).
        pkg_path = getattr(pkg, "__path__", None)
        if pkg_path is not None:
            submodule_count = 0
            for _importer, modname, _ispkg in pkgutil.walk_packages(
                pkg_path, prefix=pkg_name + "."
            ):
                try:
                    logger.debug("[registry] Importing submodule: %s", modname)
                    with _suppress_user_code_output():
                        submod = importlib.import_module(modname)
                    _scan_module_functions(submod, source=f"package:{modname}")
                    _scan_module_constants(submod, source=f"package:{modname}")
                    submodule_count += 1
                except Exception as e:
                    logger.debug(
                        "[registry] Failed to import submodule: %s",
                        modname,
                        exc_info=True,
                    )
                    _record_load_error(f"package:{modname}", str(e))
            logger.debug(
                "[registry] Walked %d submodules in package %s",
                submodule_count,
                pkg_name,
            )


def _load_entry_points() -> None:
    """Auto-discover installed packages with scistack.plugins entry points."""
    logger.debug("[registry] Discovering entry points in group: %s", ENTRY_POINT_GROUP)
    try:
        eps = importlib.metadata.entry_points(group=ENTRY_POINT_GROUP)
    except TypeError:
        # Python 3.9/3.10 compat: entry_points() doesn't accept group kwarg
        all_eps = importlib.metadata.entry_points()
        eps = all_eps.get(ENTRY_POINT_GROUP, [])

    eps_list = list(eps)
    logger.debug("[registry] Found %d entry points", len(eps_list))
    for ep_idx, ep in enumerate(eps_list):
        logger.debug(
            "[registry] Processing entry point %d/%d: %s",
            ep_idx + 1,
            len(eps_list),
            ep.name,
        )
        try:
            with _suppress_user_code_output():
                mod = ep.load()
            # entry point value can be a module or a callable; if it's a
            # module we scan it, otherwise we treat it as a single function.
            if inspect.ismodule(mod):
                fn_count_before = len(_functions)
                _scan_module_functions(mod, source=f"entrypoint:{ep.name}")
                fn_count_after = len(_functions)
                _scan_module_constants(mod, source=f"entrypoint:{ep.name}")
                logger.info(
                    "[registry] Loaded entry point: %s = %s (%d functions)",
                    ep.name,
                    ep.value,
                    fn_count_after - fn_count_before,
                )
            elif callable(mod):
                _register_function(ep.name, mod, source=f"entrypoint:{ep.name}")
                logger.info(
                    "[registry] Loaded entry point: %s = %s (1 function)",
                    ep.name,
                    ep.value,
                )
        except Exception as e:
            logger.debug(
                "[registry] Failed to load entry point: %s", ep.name, exc_info=True
            )
            _record_load_error(f"entrypoint:{ep.name}", str(e))


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _record_load_error(source: str, error: str) -> None:
    entry = {"source": source, "error": error}
    _load_errors.append(entry)
    logger.debug("[registry] Recorded load error: %s", entry)


def get_load_errors() -> list[dict]:
    """Return discovery failures from the most recent load/refresh."""
    return list(_load_errors)


def resolve_module_source(module_name: str) -> str:
    """Map a (possibly synthetic, file-import-only) module name back to a
    human-readable source: the file path for file-imported modules, or the
    module name itself for real importable modules (packages/entry
    points already have a meaningful ``__module__``)."""
    return _module_paths.get(module_name, module_name)


def _scan_module_functions(module, *, source: str) -> None:
    """Scan a module for top-level callables and register them.

    Only callables actually *defined* in ``module`` are registered — objects
    merely imported into its namespace (e.g. a pipeline file doing
    ``from scidb import for_each, configure_database``) are skipped by
    comparing ``__module__``. Without this, internal scistack helpers
    re-exported into a user file leak into the GUI's discovered-functions
    list as if they were pipeline steps. Mirrors the same filter already
    used by :func:`scidb.discover.discover_module`.
    """
    module_name = getattr(module, "__name__", None)
    logger.debug("[registry] Scanning module for functions: %s", source)
    discovered = []
    skipped_reexports = []
    for name, obj in inspect.getmembers(
        module, lambda o: callable(o) and not inspect.isclass(o)
    ):
        if name.startswith("_"):
            continue
        if getattr(obj, "__module__", None) != module_name:
            skipped_reexports.append(name)
            continue
        _register_function(name, obj, source=source)
        discovered.append(name)
    if discovered:
        logger.debug(
            "[registry] Discovered %d functions from %s: %s",
            len(discovered),
            source,
            discovered,
        )
    if skipped_reexports:
        logger.debug(
            "[registry] Skipped %d imported/re-exported callables from %s (not defined there): %s",
            len(skipped_reexports),
            source,
            skipped_reexports,
        )


def _scan_module_constants(module, *, source: str) -> None:
    """Scan a module for ``scidb.Constant`` instances (``scidb.constant()``
    values) and register them.

    Unlike functions/variable classes, a ``Constant`` is attributed to
    wherever its name is *exposed*, not filtered by ``__module__`` —
    ``Constant`` doesn't reliably expose one (unknown attribute access
    proxies through to the wrapped value via ``__getattr__``, so
    ``getattr(const, "__module__", None)`` would silently return the
    *wrapped value's* ``__module__`` if it happens to have one, which is
    meaningless here). This mirrors the same documented tradeoff already
    made by :func:`scidb.discover.discover_module` — a Constant imported
    into multiple scanned modules can appear attributed to more than one
    of them, on purpose.
    """
    logger.debug("[registry] Scanning module for constants: %s", source)
    discovered = []
    for name, obj in vars(module).items():
        if name.startswith("_"):
            continue
        if isinstance(obj, Constant):
            _register_constant(name, obj, source=source)
            discovered.append(name)
    if discovered:
        logger.debug(
            "[registry] Discovered %d constants from %s: %s",
            len(discovered),
            source,
            discovered,
        )


def _register_constant(name: str, const: Constant, *, source: str) -> None:
    """Register a single discovered Constant, warning on name collisions."""
    existing_source = _constant_sources.get(name)
    if existing_source is not None and existing_source != source:
        logger.warning(
            "[registry] Constant '%s' from %s shadows previous definition from %s",
            name,
            source,
            existing_source,
        )
    _constants[name] = const
    _constant_sources[name] = source
    logger.debug("[registry] Registered constant: %s from %s", name, source)


def get_constants_registry() -> dict[str, Constant]:
    """Return all discovered ``scidb.constant()`` values, keyed by name.

    Used by ``api/project.py``'s registry-backed "Discovered Code" panel
    for loose-script/folder-scan projects — the equivalent of what
    ``scidb.discover.scan_project`` already provides for packaged projects.
    """
    return dict(_constants)


def register_builtin_function(name: str, fn) -> None:
    """Register a manually-declared reference to a built-in/library
    function (validated by scistack_gui.api.builtin_functions) — e.g.
    ``numpy.mean``. Distinct from ``_scan_module_functions``' discovery
    path: this is a deliberate, user-initiated registration for something
    the user did NOT write themselves, not something found by scanning a
    file. Survives registry refreshes via
    scistack_gui.api.builtin_functions.replay_persisted_builtins, since
    (unlike file-based functions) there's no file on disk to rediscover it
    from.
    """
    _register_function(name, fn, source="builtin")


def _register_function(name: str, fn, *, source: str) -> None:
    """Register a single function, warning on name collisions."""
    existing_source = _function_sources.get(name)
    if existing_source is not None and existing_source != source:
        logger.warning(
            "[registry] Function '%s' from %s shadows previous definition from %s",
            name,
            source,
            existing_source,
        )
    _functions[name] = fn
    _function_sources[name] = source
    logger.debug("[registry] Registered function: %s from %s", name, source)


def _diff_summary(
    old_fns: set[str],
    new_fns: set[str],
    old_vars: set[str],
    new_vars: set[str],
) -> dict:
    """Build a summary dict of what changed."""
    added_fns = new_fns - old_fns
    removed_fns = old_fns - new_fns
    added_vars = new_vars - old_vars

    logger.info(
        "[registry] Registry summary: %d functions, %d variables",
        len(new_fns),
        len(new_vars),
    )
    if added_fns:
        logger.info("[registry] Added functions: %s", sorted(added_fns))
    if removed_fns:
        logger.info("[registry] Removed functions: %s", sorted(removed_fns))
    if added_vars:
        logger.info("[registry] Added variable classes: %s", sorted(added_vars))

    return {
        "functions": sorted(new_fns),
        "variables": sorted(new_vars),
        "added_functions": sorted(added_fns),
        "removed_functions": sorted(removed_fns),
        "added_variables": sorted(added_vars),
    }


# ---------------------------------------------------------------------------
# Lookup API (unchanged)
# ---------------------------------------------------------------------------


def get_function(name: str):
    fn = _functions.get(name)
    if fn is None:
        raise KeyError(
            f"Function '{name}' not found in registry. "
            f"Did you pass --module or --project with the script that defines it?"
        )
    return fn


def get_variable_class(name: str) -> type:
    cls = BaseVariable._all_subclasses.get(name)
    if cls is None:
        raise KeyError(
            f"Variable class '{name}' not found. "
            f"Did you pass --module or --project with the script that defines it?"
        )
    return cls
