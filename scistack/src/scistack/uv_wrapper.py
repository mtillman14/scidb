"""
Thin Python wrapper around the ``uv`` CLI.

The scistack project scaffolder and GUI both need to drive ``uv`` to manage
the per-project virtual environment and lockfile. This module centralises
that so callers never shell out directly and always get structured results.

All operations are stateless: pass ``project_root`` and we ``uv``-away in that
directory. Errors from ``uv`` are **captured and returned**, not raised — the
GUI wants to surface uv's raw stderr to the user, and raising would make that
harder to plumb through the FastAPI layer cleanly. The one exception is
:class:`UvNotFoundError`, raised when ``uv`` itself is missing from ``PATH``
(distinct from ``uv`` returning a non-zero exit).

Typical use::

    from scistack import sync, add, read_lockfile, is_lockfile_stale

    if is_lockfile_stale(project_root):
        result = sync(project_root)
        if not result.ok:
            show_error(result.stderr)

    add_result = add(project_root, "mylab-preprocessing", version="0.2.1")
    for pkg in read_lockfile(project_root):
        print(pkg.name, pkg.version)
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    try:
        import tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
class UvNotFoundError(RuntimeError):
    """Raised when the ``uv`` executable cannot be found on PATH.

    This is distinct from a non-zero exit from ``uv`` (e.g. a version
    conflict). That case is surfaced through the ``.ok`` attribute on the
    returned result object.
    """


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------
@dataclass
class _UvResult:
    """Common fields shared by every uv_wrapper result."""

    ok: bool
    returncode: int
    stdout: str
    stderr: str
    command: tuple[str, ...]

    @property
    def combined_output(self) -> str:
        """stdout + stderr concatenated, convenient for error dialogs."""
        parts = [p for p in (self.stdout, self.stderr) if p]
        return "\n".join(parts)


@dataclass
class SyncResult(_UvResult):
    """Result of a ``uv sync`` call."""


@dataclass
class AddResult(_UvResult):
    """Result of a ``uv add`` call."""

    package: str = ""
    version: str | None = None


@dataclass
class RemoveResult(_UvResult):
    """Result of a ``uv remove`` call."""

    package: str = ""


@dataclass
class LockedPackage:
    """One entry in ``uv.lock``."""

    name: str
    version: str
    source: dict[str, Any] = field(default_factory=dict)

    @property
    def is_registry(self) -> bool:
        """True if this came from a registry (pypi-like) source."""
        return "registry" in self.source

    @property
    def is_editable(self) -> bool:
        """True for local editable installs."""
        return "editable" in self.source

    @property
    def is_virtual(self) -> bool:
        """True for virtual packages (dep groups)."""
        return "virtual" in self.source

    @property
    def registry_url(self) -> str | None:
        """Return the registry URL for registry-sourced packages, else None."""
        reg = self.source.get("registry")
        return reg if isinstance(reg, str) else None


# ---------------------------------------------------------------------------
# Internal: locating and running uv
# ---------------------------------------------------------------------------
def _find_uv() -> str:
    """Return the absolute path to the ``uv`` executable or raise."""
    uv_path = shutil.which("uv")
    if uv_path is None:
        raise UvNotFoundError(
            "The 'uv' executable was not found on PATH. Install uv from "
            "https://github.com/astral-sh/uv and make sure it's on PATH."
        )
    return uv_path


def _run_uv(
    args: Sequence[str],
    project_root: Path,
    *,
    timeout: float | None = None,
) -> tuple[int, str, str, tuple[str, ...]]:
    """Invoke ``uv`` with ``args`` in ``project_root``.

    Returns ``(returncode, stdout, stderr, full_command)``. Does **not**
    raise on non-zero exit codes — callers inspect ``returncode``. Does
    raise :class:`UvNotFoundError` if uv itself is missing, and may raise
    :class:`subprocess.TimeoutExpired` if ``timeout`` is exceeded.
    """
    uv = _find_uv()
    cmd: tuple[str, ...] = (uv, *args)
    logger.debug("Running uv: %s (cwd=%s)", " ".join(cmd), project_root)

    # Avoid interactive prompts that would deadlock subprocess.run.
    env = os.environ.copy()
    env.setdefault("UV_NO_PROGRESS", "1")

    proc = subprocess.run(
        cmd,
        cwd=str(project_root),
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
        check=False,
    )
    return proc.returncode, proc.stdout or "", proc.stderr or "", cmd


# ---------------------------------------------------------------------------
# Public operations
# ---------------------------------------------------------------------------
def sync(project_root: Path, *, timeout: float | None = 300.0) -> SyncResult:
    """Run ``uv sync`` in ``project_root`` to reconcile the venv with the lockfile.

    This is the safe, non-destructive operation to run on project open when
    ``is_lockfile_stale`` reports True. On failure, inspect
    ``result.stderr`` / ``result.combined_output`` — uv's error messages
    are typically actionable.
    """
    returncode, stdout, stderr, cmd = _run_uv(
        ("sync",), Path(project_root), timeout=timeout
    )
    return SyncResult(
        ok=returncode == 0,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        command=cmd,
    )


def add(
    project_root: Path,
    package: str,
    *,
    version: str | None = None,
    index: str | None = None,
    dev: bool = False,
    timeout: float | None = 300.0,
) -> AddResult:
    """Run ``uv add`` to install a package into the project.

    Args:
        project_root: Directory containing ``pyproject.toml``.
        package: PyPI-style distribution name.
        version: Optional version spec. If provided, passed as ``name==version``.
        index: Optional index URL to pull from (passed via ``--index``).
        dev: If True, add to the dev dependency group.
        timeout: Seconds before the subprocess is killed. None disables.
    """
    spec = f"{package}=={version}" if version else package
    args: list[str] = ["add", spec]
    if index is not None:
        args.extend(["--index", index])
    if dev:
        args.append("--dev")

    returncode, stdout, stderr, cmd = _run_uv(
        tuple(args), Path(project_root), timeout=timeout
    )
    return AddResult(
        ok=returncode == 0,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        command=cmd,
        package=package,
        version=version,
    )


def remove(
    project_root: Path,
    package: str,
    *,
    timeout: float | None = 300.0,
) -> RemoveResult:
    """Run ``uv remove`` to uninstall a package from the project."""
    returncode, stdout, stderr, cmd = _run_uv(
        ("remove", package), Path(project_root), timeout=timeout
    )
    return RemoveResult(
        ok=returncode == 0,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        command=cmd,
        package=package,
    )


# ---------------------------------------------------------------------------
# Lockfile reading & staleness
# ---------------------------------------------------------------------------
def read_lockfile(project_root: Path) -> list[LockedPackage]:
    """Parse ``uv.lock`` in ``project_root`` and return its packages.

    Returns an empty list if the lockfile doesn't exist. Raises
    :class:`ValueError` if the file exists but is not valid TOML or
    doesn't have the expected ``[[package]]`` structure.
    """
    lock_path = Path(project_root) / "uv.lock"
    if not lock_path.exists():
        return []

    try:
        with open(lock_path, "rb") as f:
            data = tomllib.load(f)
    except Exception as e:
        raise ValueError(f"Failed to parse {lock_path}: {e}") from e

    raw_packages = data.get("package", [])
    if not isinstance(raw_packages, list):
        raise ValueError(
            f"{lock_path} has a 'package' field that is not a list"
        )

    packages: list[LockedPackage] = []
    for entry in raw_packages:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        version = entry.get("version", "")
        if not isinstance(name, str) or not name:
            continue
        source = entry.get("source") or {}
        if not isinstance(source, dict):
            source = {}
        packages.append(
            LockedPackage(
                name=name,
                version=str(version),
                source=source,
            )
        )
    return packages


def is_lockfile_stale(project_root: Path) -> bool:
    """Return True if ``uv.lock`` is out of date relative to ``pyproject.toml``.

    The check is a best-effort heuristic:

    1. If ``uv.lock`` doesn't exist → stale (needs to be created).
    2. If ``pyproject.toml`` doesn't exist → not stale (nothing to be
       stale *against*; caller shouldn't be calling this in that state).
    3. If ``pyproject.toml`` has been modified more recently than
       ``uv.lock`` → stale.
    4. Also recomputes a hash of the ``[project]`` and ``[dependency-groups]``
       sections of ``pyproject.toml`` and compares against the
       ``lock-version`` metadata; this catches the case where the user
       restored an older ``pyproject.toml`` without updating mtimes.

    The GUI will use this to decide whether to auto-``uv sync`` on project
    open (Phase 8). False positives (reporting stale when it isn't) are
    OK — worst case is an unnecessary sync. False negatives would mean
    running with a stale venv, which is bad, so the heuristic prefers
    reporting stale.
    """
    project_root = Path(project_root)
    lock_path = project_root / "uv.lock"
    pyproject_path = project_root / "pyproject.toml"

    if not lock_path.exists():
        return True
    if not pyproject_path.exists():
        return False

    # Cheap mtime check first.
    try:
        if pyproject_path.stat().st_mtime > lock_path.stat().st_mtime:
            return True
    except OSError:
        return True

    # Content hash check: extract [project] + [dependency-groups] from the
    # pyproject and compare against whatever hash uv stored in the lockfile.
    try:
        with open(pyproject_path, "rb") as f:
            py_data = tomllib.load(f)
    except Exception:
        return True

    relevant = {
        "project": py_data.get("project", {}),
        "dependency-groups": py_data.get("dependency-groups", {}),
        "tool.uv": py_data.get("tool", {}).get("uv", {}),
    }
    current_hash = _hash_mapping(relevant)

    try:
        with open(lock_path, "rb") as f:
            lock_data = tomllib.load(f)
    except Exception:
        return True

    # uv stores a content hash under the "manifest" table in recent versions;
    # if the key is absent we treat the mtime check as authoritative (which
    # we already passed).
    manifest = lock_data.get("manifest") or {}
    stored_hash = manifest.get("scistack-content-hash") or manifest.get("content-hash")
    if stored_hash is None:
        return False
    return stored_hash != current_hash


def _hash_mapping(obj: Any) -> str:
    """Deterministic hash of a nested TOML-derived dict."""
    canonical = _canonicalize(obj)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _canonicalize(obj: Any) -> str:
    """Serialize a TOML-derived value into a stable string representation."""
    if isinstance(obj, dict):
        items = sorted(obj.items(), key=lambda kv: kv[0])
        inner = ",".join(f"{k}={_canonicalize(v)}" for k, v in items)
        return "{" + inner + "}"
    if isinstance(obj, (list, tuple)):
        return "[" + ",".join(_canonicalize(x) for x in obj) + "]"
    if isinstance(obj, bool):
        return "true" if obj else "false"
    if isinstance(obj, (int, float)):
        return repr(obj)
    if obj is None:
        return "null"
    return repr(str(obj))
