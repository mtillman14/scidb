"""
Generic package-walking harness for code discovery.

This module knows nothing about scidb-specific concepts (``BaseVariable``,
``Constant``, ``@scistack``-tagged functions, ...) — it only knows how to
import a package and its submodules, capture per-module errors without
aborting, skip test-only modules/files by naming convention, and manage
``sys.path``/``sys.modules`` for repeated scans. Consumers (``scidb.discover``,
``scistack_gui.registry``) supply their own per-module callback to decide
what "discovery" means for them.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import pkgutil
import re
import sys
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Generic, TypeVar

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    try:
        import tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

T = TypeVar("T")

_PY_TEST_FILE_RE = re.compile(r"^(test_.+|.+_test)\.py$", re.IGNORECASE)
_TEST_DIR_NAMES = {"test", "tests"}


def is_test_path(path: Path | str) -> bool:
    """True if *path* belongs to a test suite by naming convention: any
    directory component (case-insensitive) is ``test``/``tests``, or the
    filename matches a Python test-file convention (``test_*.py`` /
    ``*_test.py``)."""
    p = Path(path)
    if any(part.lower() in _TEST_DIR_NAMES for part in p.parts[:-1]):
        return True
    return bool(_PY_TEST_FILE_RE.match(p.name))


def is_test_modname(modname: str) -> bool:
    """Same rule as :func:`is_test_path`, applied to a dotted module name.

    ``pkgutil.walk_packages`` only ever yields dotted names, not filesystem
    paths, so this mirrors the directory-component and filename checks
    against the name's dot-separated parts.
    """
    parts = modname.split(".")
    last = parts[-1]
    if any(part.lower() in _TEST_DIR_NAMES for part in parts[:-1]):
        return True
    if last.lower() in _TEST_DIR_NAMES:
        return True
    return bool(_PY_TEST_FILE_RE.match(last + ".py"))


def read_project_name(project_root: Path) -> str | None:
    """Return ``project.name`` from ``project_root/pyproject.toml``, or
    None if absent/unparseable."""
    pyproject = project_root / "pyproject.toml"
    if not pyproject.exists():
        return None
    try:
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        logger.warning("Failed to parse %s", pyproject, exc_info=True)
        return None
    name = data.get("project", {}).get("name")
    return name if isinstance(name, str) else None


@dataclass
class PathInsert:
    """Context manager that inserts a directory onto sys.path.

    Idempotent: does nothing on enter/exit if the directory was already on
    sys.path. Always invalidates import caches on exit so a subsequent
    import sees any newly-visible modules.
    """

    directory: str
    _inserted: bool = False

    def __enter__(self) -> "PathInsert":
        if self.directory not in sys.path:
            sys.path.insert(0, self.directory)
            self._inserted = True
        return self

    def __exit__(self, *exc) -> None:
        if self._inserted:
            try:
                sys.path.remove(self.directory)
            except ValueError:
                pass
        importlib.invalidate_caches()


def purge_module(package_name: str) -> None:
    """Remove a package and all its submodules from ``sys.modules``.

    Needed so that two successive scans of projects that happen to share a
    package name don't return stale cached modules — a rescan should pick
    up any edits made since the last one.
    """
    prefix = package_name + "."
    to_drop = [
        name for name in sys.modules if name == package_name or name.startswith(prefix)
    ]
    for name in to_drop:
        sys.modules.pop(name, None)


@dataclass
class ModuleWalkError:
    """Import (or callback) failure for a single module; the walk continues."""

    module_name: str
    traceback: str


@dataclass
class WalkResult(Generic[T]):
    """Result of :func:`walk_package`."""

    package_name: str
    per_module: list[tuple[str, T]] = field(default_factory=list)
    errors: list[ModuleWalkError] = field(default_factory=list)


def walk_package(
    package_name: str, on_module: Callable[[ModuleType], T]
) -> WalkResult[T]:
    """
    Import ``package_name`` and all its submodules, calling ``on_module`` on
    each importable, non-test module.

    ``on_module`` may return a value (recorded per-module in the result) or
    mutate external state and return None — either way its return value is
    stored alongside the module's dotted name. Import failures and
    exceptions raised by ``on_module`` are both captured as
    :class:`ModuleWalkError` entries; the walk never aborts on a single bad
    module. If the top-level package itself cannot be imported, the result
    contains a single error entry and no modules.

    Callers that need output suppression around imports (e.g. a discovered
    file with stray top-level ``print()`` calls) should wrap the entire
    call in their own redirect, since that only needs to be scoped for the
    duration of this call, not per-import.
    """
    result: WalkResult[T] = WalkResult(package_name=package_name)

    try:
        pkg = importlib.import_module(package_name)
    except Exception:
        logger.debug(
            "Failed to import top-level package %s", package_name, exc_info=True
        )
        result.errors.append(
            ModuleWalkError(module_name=package_name, traceback=traceback.format_exc())
        )
        return result

    try:
        result.per_module.append((package_name, on_module(pkg)))
    except Exception:
        logger.exception("on_module failed for %s", package_name)
        result.errors.append(
            ModuleWalkError(module_name=package_name, traceback=traceback.format_exc())
        )

    pkg_path = getattr(pkg, "__path__", None)
    if pkg_path is None:
        return result

    for _importer, modname, _ispkg in pkgutil.walk_packages(
        pkg_path, prefix=package_name + "."
    ):
        if is_test_modname(modname):
            logger.debug("Skipping test module during discovery: %s", modname)
            continue

        try:
            submod = importlib.import_module(modname)
        except Exception:
            logger.debug("Failed to import submodule %s", modname, exc_info=True)
            result.errors.append(
                ModuleWalkError(module_name=modname, traceback=traceback.format_exc())
            )
            continue

        try:
            result.per_module.append((modname, on_module(submod)))
        except Exception:
            logger.exception("on_module failed for %s", modname)
            result.errors.append(
                ModuleWalkError(module_name=modname, traceback=traceback.format_exc())
            )

    return result
