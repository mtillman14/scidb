"""
Index & library management endpoints.

GET  /api/indexes                        — list tapped indexes
GET  /api/indexes/{name}/packages?q=...  — search a tap's packages
POST /api/project/libraries              — install a library via uv add
DELETE /api/project/libraries/{name}     — remove a library via uv remove
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    try:
        import tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]

from fastapi import APIRouter

from scistack_gui.db import get_db_path

logger = logging.getLogger(__name__)

router = APIRouter(tags=["indexes"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _project_root() -> Path:
    db_path = get_db_path()
    candidate = db_path.parent
    if (candidate / "pyproject.toml").exists():
        return candidate
    for parent in candidate.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return candidate


def _read_tap_packages(tap_local_path: Path, query: str | None = None) -> list[dict]:
    """Read packages.toml from a tap's local clone and optionally filter by query."""
    packages_file = tap_local_path / "packages.toml"
    if not packages_file.exists():
        return []
    try:
        with open(packages_file, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        logger.warning("Failed to parse %s", packages_file, exc_info=True)
        return []

    packages = data.get("package", [])
    if not isinstance(packages, list):
        return []

    results = []
    for entry in packages:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name", "")
        if not name:
            continue
        if query and query.lower() not in name.lower():
            description = entry.get("description", "")
            if query.lower() not in description.lower():
                continue
        results.append({
            "name": name,
            "description": entry.get("description", ""),
            "versions": entry.get("versions", []),
            "index_url": entry.get("index_url", ""),
        })
    return results


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("/indexes")
def list_indexes() -> dict:
    """List the user's tapped package indexes."""
    from scistack.user_config import list_taps
    taps = list_taps()
    return {
        "indexes": [
            {
                "name": tap.name,
                "url": tap.url,
                "exists_locally": tap.exists_locally,
            }
            for tap in taps
        ]
    }


@router.get("/indexes/{name}/packages")
def search_index_packages(name: str, q: str = "") -> dict:
    """Search a tapped index for available packages."""
    from scistack.user_config import list_taps

    taps = list_taps()
    tap = next((t for t in taps if t.name == name), None)
    if tap is None:
        return {"error": f"No tap named {name!r}.", "packages": []}
    if not tap.exists_locally:
        return {"error": f"Tap {name!r} has not been cloned yet.", "packages": []}

    packages = _read_tap_packages(tap.local_path, query=q or None)
    return {"packages": packages}


@router.post("/project/libraries")
def add_library(body: dict) -> dict:
    """Install a library into the current project via ``uv add``.

    Body: ``{"name": "...", "version": "...", "index": "..."}``
    """
    from scistack.uv_wrapper import add as uv_add

    package = body.get("name", "")
    version = body.get("version")
    index = body.get("index")

    if not package:
        return {"ok": False, "error": "Package name is required."}

    root = _project_root()
    result = uv_add(root, package, version=version, index=index)

    if result.ok:
        # Trigger a re-scan so the sidebar picks up new exports.
        from scistack_gui.api.project import _run_scan
        _run_scan()
        return {"ok": True, "package": package, "version": version}
    else:
        return {"ok": False, "error": result.combined_output}


@router.delete("/project/libraries/{name}")
def remove_library(name: str) -> dict:
    """Remove a library from the current project via ``uv remove``."""
    from scistack.uv_wrapper import remove as uv_remove

    root = _project_root()
    result = uv_remove(root, name)

    if result.ok:
        from scistack_gui.api.project import _run_scan
        _run_scan()
        return {"ok": True, "package": name}
    else:
        return {"ok": False, "error": result.combined_output}
