"""
Project config panel endpoints.

GET    /api/project/code    — scanned exports from src/{project}/
GET    /api/project/paths   — resolved [tool.scistack] path config (Paths popup)
POST   /api/project/paths   — add a discovery path (loose-script projects only)
DELETE /api/project/paths   — remove a discovery path (loose-script projects only)
POST   /api/project/refresh — re-run both scans
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter

from scistack_gui.api import ws
from scistack_gui.db import get_db_path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/project", tags=["project"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _project_root() -> Path:
    """Derive the project root from the open database path.

    Standard layout places the .duckdb in the project root. If
    ``pyproject.toml`` exists next to the database, that directory is the
    root. Otherwise we walk upward.
    """
    db_path = get_db_path()
    candidate = db_path.parent
    if (candidate / "pyproject.toml").exists():
        return candidate
    # Walk up (e.g. user put .duckdb in a subdir).
    for parent in candidate.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    # Fallback to the db's parent directory even without pyproject.toml.
    return candidate


def _serialise_module_exports(mod) -> dict:
    return {
        "module_name": mod.module_name,
        "variables": [cls.__name__ for cls in mod.variables],
        "functions": [
            # @scistack functions are PLAIN callables (name on the function
            # itself); the .fcn fallback covers any legacy wrapper object.
            getattr(f, "__name__", None)
            or getattr(getattr(f, "fcn", None), "__name__", str(f))
            for f in mod.functions
        ],
        "constants": [
            {
                "name": name,
                "value": repr(c.value),
                "description": c.description,
                "source_file": c.source_file,
                "source_line": c.source_line,
            }
            for name, c in mod.constants
        ],
        "variable_count": len(mod.variables),
        "function_count": len(mod.functions),
        "constant_count": len(mod.constants),
    }


def _serialise_module_error(err) -> dict:
    return {
        "module_name": err.module_name,
        "traceback": err.traceback,
    }


def _serialise_package_result(pkg) -> dict:
    return {
        "name": pkg.name,
        "modules": [_serialise_module_exports(m) for m in pkg.modules],
        "errors": [_serialise_module_error(e) for e in pkg.errors],
        "variable_count": pkg.variable_count,
        "function_count": pkg.function_count,
        "constant_count": pkg.constant_count,
        "is_empty": pkg.is_empty,
    }


# Cache the last scan result so GET calls are fast after a refresh.
_last_result = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("/code")
def get_project_code() -> dict:
    """Return scanned exports from ``src/{project}/``."""
    global _last_result
    if _last_result is None:
        _run_scan()
    return _serialise_package_result(_last_result.project_code)


@router.get("/paths")
def get_project_paths() -> dict:
    """Return the resolved [tool.scistack] paths for the header's Paths popup.

    Reads the same pyproject.toml/scistack.toml that project mode loaded at
    startup (re-parsed here since the GUI doesn't keep the SciStackConfig
    around after registry load). Single-file mode has no such config, so
    that case is reported as ``configured: False`` rather than an error.

    Also reports ``packaged`` (pyproject.toml present -- read-only in the
    Paths popup) and ``managed_paths`` (the raw, pre-discovery ``modules``
    entries as written to scistack.toml -- what the popup's editable add/
    remove list actually displays; empty until the first path is added via
    :func:`add_project_path`, even in folder-scan mode).
    """
    from scistack_gui.config import describe_managed_paths, load_config

    db_path = get_db_path()
    managed_info = describe_managed_paths(db_path)

    try:
        config = load_config(None, db_path)
    except FileNotFoundError:
        logger.info(
            "[project.paths] no [tool.scistack] config found near %s "
            "(single-file mode)",
            db_path,
        )
        return {
            "configured": False,
            "project_root": str(db_path.parent),
            **managed_info,
        }

    logger.info(
        "[project.paths] resolved config at %s: %d modules, %d packages, "
        "%d matlab functions, %d matlab variables, %d matlab sources",
        config.project_root,
        len(config.modules),
        len(config.packages),
        len(config.matlab_functions),
        len(config.matlab_variables),
        len(config.matlab_sources),
    )
    return {
        "configured": True,
        "project_root": str(config.project_root),
        "modules": [str(p) for p in config.modules],
        "variable_file": str(config.variable_file) if config.variable_file else None,
        "packages": config.packages,
        "auto_discover": config.auto_discover,
        "matlab_functions": [str(p) for p in config.matlab_functions],
        "matlab_variables": [str(p) for p in config.matlab_variables],
        "matlab_addpath": [str(p) for p in config.matlab_addpath],
        "matlab_variable_dir": (
            str(config.matlab_variable_dir) if config.matlab_variable_dir else None
        ),
        **managed_info,
    }


def _reload_config_and_rescan() -> None:
    """Re-read scistack.toml from disk and reload both registries against
    the fresh config, then rebuild the cached scan result.

    Deliberately NOT the same as ``_run_scan(force_refresh=True)`` /
    ``_refresh_registries()`` -- those replay ``registry.refresh_all()`` /
    ``matlab_registry.refresh_all()`` against the *stale* in-memory
    ``_config`` object captured at the last load (see registry.py:
    ``refresh_all`` calls ``load_from_config(_config)``, it never re-parses
    the TOML file). That's fine for the existing "Refresh" button, which
    only needs to pick up *content* changes in already-configured files.
    But after :func:`~scistack_gui.config.add_path`/``remove_path`` change
    *which paths are configured*, reusing the stale config would silently
    fail to discover the new path until the server restarts. So this
    re-runs ``load_config`` fresh first.
    """
    from scistack_gui import matlab_registry, registry
    from scistack_gui.config import load_config

    db_path = get_db_path()
    new_config = load_config(None, db_path)
    try:
        registry.load_from_config(new_config)
    except Exception:
        logger.exception("Failed to reload Python registry after path change")
    try:
        matlab_registry.load_from_config(new_config)
    except Exception:
        logger.exception("Failed to reload MATLAB registry after path change")
    _run_scan(force_refresh=False)


@router.post("/paths")
def add_project_path(body: dict) -> dict:
    """Add a directory to scistack.toml and re-scan (loose-script projects
    only). Body: ``{"path": "/absolute/path/to/folder"}``.
    """
    from scistack_gui.config import add_path

    path_str = body.get("path", "")
    try:
        add_path(get_db_path(), Path(path_str))
    except (ValueError, FileNotFoundError, NotADirectoryError) as e:
        logger.warning("[project.paths] add_project_path failed: %s", e)
        return {"ok": False, "error": str(e)}

    _reload_config_and_rescan()
    result = get_project_paths()
    result["ok"] = True
    return result


@router.delete("/paths")
def remove_project_path(path: str) -> dict:
    """Remove a directory from scistack.toml and re-scan (loose-script
    projects only). ``path`` is a query parameter."""
    from scistack_gui.config import remove_path

    try:
        remove_path(get_db_path(), Path(path))
    except (ValueError, FileNotFoundError) as e:
        logger.warning("[project.paths] remove_project_path failed: %s", e)
        return {"ok": False, "error": str(e)}

    _reload_config_and_rescan()
    result = get_project_paths()
    result["ok"] = True
    return result


def refresh_project_sync() -> dict:
    """Re-run the discovery scan and return a summary.

    In registry-backed mode (no pyproject.toml — loose-script/folder-scan
    projects) this also re-imports the configured files from disk first,
    so "Refresh" here does real work instead of just re-reporting stale
    in-memory state — see ``_run_scan(force_refresh=True)``.

    Transport-agnostic core, deliberately synchronous: the FastAPI route
    below awaits ``ws.broadcast`` afterward, while the JSON-RPC path (VS
    Code extension, ``server.py: _h_refresh_project``) calls this same
    function through ``services/project_service.py`` and notifies via the
    sync ``notify()`` instead — that path runs in a plain thread with no
    event loop, so this function itself must never be a coroutine.
    """
    _run_scan(force_refresh=True)
    return {
        "ok": True,
        "project_code": _serialise_package_result(_last_result.project_code),
        "libraries_shown": len(_last_result.non_empty_libraries()),
        "libraries_total": len(_last_result.libraries),
    }


@router.post("/refresh")
async def refresh_project() -> dict:
    result = refresh_project_sync()
    await ws.broadcast({"type": "dag_updated"})
    return result


def _run_scan(*, force_refresh: bool = False) -> None:
    """Run the discovery scanner and cache the result.

    Two data sources, chosen by whether a ``pyproject.toml`` exists at the
    detected project root:

    - **Packaged projects** (``pyproject.toml`` present): the scidb-layer
      ``scan_project`` walks ``src/{name}/`` + ``uv.lock`` libraries, same
      as always.
    - **Loose-script / folder-scan projects** (no ``pyproject.toml``): there
      is no ``src/{name}/`` to walk, and ``scan_project`` would report
      everything empty even though the registry actually has working
      functions/variables loaded — see docs/claude/multi-source-discovery.md
      and the "Discovered Code" panel would otherwise silently disagree
      with what's actually runnable. Build the result from
      ``registry``/``matlab_registry`` instead, which is the single source
      of truth for what's actually loaded either way.
    """
    global _last_result
    root = _project_root()
    logger.info("Running discovery scan on %s (force_refresh=%s)", root, force_refresh)

    if (root / "pyproject.toml").exists():
        from scidb.discover import scan_project

        # KNOWN GAP: scan_project's own re-imports (scan_package) also
        # register scidb.Pipeline objects into scidb.pipeline._all_pipelines
        # as a side effect, same as _refresh_registries' path below — but
        # this branch never calls discover_and_seed_pipelines, so a
        # packaged-project pipeline file only gets (re-)seeded via the
        # initial bootstrap.open_or_create_project pass, not via this
        # scan/refresh path. Not fixed here — pre-dates this work and
        # scan_project's relationship to the FUNCTIONAL registry (vs. just
        # this display panel) needs its own look first.
        # Skip scidb/scifor/etc. framework packages — they're
        # infrastructure, not user-facing libraries.
        _last_result = scan_project(
            root,
            skip_dists=[
                "scidb",
                "scifor",
                "sciduckdb",
                "scilineage",
                "scipathgen",
                "scicanonicalhash",
                "scirun",
                "scihist",
                "scistack",
                "scistack-gui",
            ],
        )
    else:
        logger.info(
            "No pyproject.toml at %s; using registry-backed discovery "
            "(loose-script/folder-scan mode)",
            root,
        )
        if force_refresh:
            _refresh_registries()
        _last_result = _build_registry_backed_result(root)

    logger.info(
        "Scan complete: project=%s (vars=%d, fns=%d, consts=%d), "
        "libraries=%d (shown=%d)",
        _last_result.project_code.name,
        _last_result.project_code.variable_count,
        _last_result.project_code.function_count,
        _last_result.project_code.constant_count,
        len(_last_result.libraries),
        len(_last_result.non_empty_libraries()),
    )


def _refresh_registries() -> None:
    """Re-import configured files from disk (registry-backed mode only)."""
    from scistack_gui import matlab_registry, registry

    try:
        if registry._config is not None:
            registry.refresh_all()
        else:
            registry.refresh_module()
    except RuntimeError:
        logger.debug("Nothing to refresh in registry (no config/module loaded)")
    except Exception:
        logger.exception("Failed to refresh Python registry before discovery scan")

    try:
        matlab_registry.refresh_all()
    except Exception:
        logger.exception("Failed to refresh MATLAB registry before discovery scan")

    # Re-importing above may have re-registered scidb.Pipeline objects
    # (source -> GUI pipeline import — see pipeline_discovery.py); seed any
    # new ones now that the registry reflects the current source files.
    try:
        from scistack_gui.db import get_db, is_loaded
        from scistack_gui.pipeline_discovery import discover_and_seed_pipelines

        if is_loaded():
            discover_and_seed_pipelines(get_db())
    except Exception:
        logger.exception("Failed to discover/seed pipelines from source")


def _build_registry_backed_result(root: Path):
    """Build a ``scidb.discover.DiscoveryResult`` from ``registry``/
    ``matlab_registry`` state, for projects with no ``pyproject.toml`` to
    scan. Reuses scidb's own result dataclasses so the existing
    ``_serialise_*`` helpers (and the frontend rendering code built for
    ``scan_project``'s output) work completely unchanged.

    Full parity with ``scan_project``: functions, ``BaseVariable``
    subclasses, and ``scidb.constant()`` instances are all covered — the
    last of those via ``registry.get_constants_registry()``, which
    ``registry._scan_module_constants`` populates alongside functions at
    every registry load. (This is separate from the GUI-native "Constant
    node" concept — ``get_constants()``/EditTab's palette — which is about
    user-created per-run values, not code-level named constants.)
    """
    from scidb import BaseVariable
    from scidb.discover import DiscoveryResult, ModuleError, ModuleExports, PackageResult
    from scistack_gui import matlab_registry, registry

    by_source: dict[str, ModuleExports] = {}

    def module_for(source: str) -> ModuleExports:
        if source not in by_source:
            by_source[source] = ModuleExports(module_name=source)
        return by_source[source]

    for name, fn in registry._functions.items():
        source = registry._function_sources.get(name, "<unknown>")
        module_for(source).functions.append(fn)

    # BaseVariable._all_subclasses already contains BOTH real Python
    # variable classes AND the Python surrogate classes matlab_registry
    # creates for each MATLAB variable (see _register_matlab_variable) — a
    # separate pass over matlab_registry.get_all_variable_names() would
    # double-count them. Just re-attribute the MATLAB ones to their real
    # .m file path instead of the surrogate's (uninformative) __module__.
    matlab_var_paths = {
        name: str(path) for name, path in matlab_registry._matlab_variables.items()
    }
    for name, cls in BaseVariable._all_subclasses.items():
        if name in matlab_var_paths:
            source = matlab_var_paths[name]
        else:
            source = registry.resolve_module_source(
                getattr(cls, "__module__", None) or "<unknown>"
            )
        module_for(source).variables.append(cls)

    for fn_name in matlab_registry.get_all_function_names():
        info = matlab_registry.get_matlab_function(fn_name)
        source = str(info.file_path) if info.file_path is not None else "<matlab builtin>"
        # Not a real object with __name__ — _serialise_module_exports falls
        # back to str(f) for anything without one, which is already fn_name.
        module_for(source).functions.append(fn_name)

    for name, const in registry.get_constants_registry().items():
        source = registry._constant_sources.get(name, "<unknown>")
        module_for(source).constants.append((name, const))

    errors = [
        ModuleError(module_name=e["source"], traceback=e["error"])
        for e in [*registry.get_load_errors(), *matlab_registry.get_load_errors()]
    ]

    modules = sorted(by_source.values(), key=lambda m: m.module_name)
    project_code = PackageResult(name=root.name, modules=modules, errors=errors)
    return DiscoveryResult(project_code=project_code, libraries={})
