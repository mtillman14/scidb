"""
Project config panel endpoints.

GET  /api/project/code       — scanned exports from src/{project}/
GET  /api/project/libraries  — scanned exports from uv.lock packages
POST /api/project/refresh    — re-run both scans
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter

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
            getattr(getattr(f, "fcn", None), "__name__", str(f))
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


@router.get("/libraries")
def get_project_libraries() -> dict:
    """Return scanned exports from uv.lock packages (non-empty only)."""
    global _last_result
    if _last_result is None:
        _run_scan()
    non_empty = _last_result.non_empty_libraries()
    return {
        "libraries": {
            name: _serialise_package_result(pkg)
            for name, pkg in non_empty.items()
        },
        "total_libraries": len(_last_result.libraries),
        "shown_libraries": len(non_empty),
    }


@router.post("/refresh")
def refresh_project() -> dict:
    """Re-run the discovery scan and return a summary."""
    _run_scan()
    return {
        "ok": True,
        "project_code": _serialise_package_result(_last_result.project_code),
        "libraries_shown": len(_last_result.non_empty_libraries()),
        "libraries_total": len(_last_result.libraries),
    }


def _run_scan() -> None:
    """Run the discovery scanner and cache the result."""
    global _last_result
    from scidb.discover import scan_project

    root = _project_root()
    logger.info("Running discovery scan on %s", root)

    # Skip scidb/scifor/etc. framework packages — they're infrastructure,
    # not user-facing libraries.
    _last_result = scan_project(
        root,
        skip_dists=[
            "scidb",
            "scifor",
            "sciduckdb",
            "scilineage",
            "scipathgen",
            "canonicalhash",
            "scirun",
            "scihist",
            "scistack",
            "scistack-gui",
        ],
    )
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
