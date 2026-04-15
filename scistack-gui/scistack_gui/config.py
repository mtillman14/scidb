"""
Parse [tool.scistack] configuration from pyproject.toml or scistack.toml.

Supports multi-source pipeline discovery: explicit .py modules,
pip-installed packages, auto-discovered entry-point plugins, and
MATLAB .m files.
"""

import glob as _glob
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]

logger = logging.getLogger(__name__)


@dataclass
class SciStackConfig:
    """Parsed [tool.scistack] configuration."""

    project_root: Path
    """Directory containing the pyproject.toml or scistack.toml."""

    modules: list[Path] = field(default_factory=list)
    """Resolved absolute paths to user .py files."""

    variable_file: Path | None = None
    """The .py file where ``create_variable`` writes new classes."""

    packages: list[str] = field(default_factory=list)
    """Explicit pip-installed package names to scan."""

    auto_discover: bool = True
    """Whether to scan ``scistack.plugins`` entry points."""

    # MATLAB support
    matlab_functions: list[Path] = field(default_factory=list)
    """Resolved absolute paths to MATLAB .m function files."""

    matlab_variables: list[Path] = field(default_factory=list)
    """Resolved absolute paths to MATLAB .m classdef files (BaseVariable subclasses)."""

    matlab_addpath: list[Path] = field(default_factory=list)
    """MATLAB path entries (auto-derived from parent dirs of functions, variables, and variable_dir)."""

    matlab_variable_dir: Path | None = None
    """Directory where ``create_variable`` writes new .m classdef files."""


def load_config(project_path: Path | None, db_path: Path) -> SciStackConfig:
    """Load a SciStackConfig from a pyproject.toml.

    Parameters
    ----------
    project_path
        Explicit path to a pyproject.toml file *or* a directory containing one.
        If ``None``, searches upward from *db_path* for a pyproject.toml that
        contains a ``[tool.scistack]`` section.
    db_path
        Path to the .duckdb file (used as fallback search root).

    Raises
    ------
    FileNotFoundError
        If no pyproject.toml can be located.
    ValueError
        If the located pyproject.toml has no ``[tool.scistack]`` section or
        the section is invalid.
    """
    toml_path = _locate_pyproject(project_path, db_path)
    project_root = toml_path.parent

    with open(toml_path, "rb") as f:
        data = tomllib.load(f)

    section = _extract_scistack_section(data, toml_path.name)
    if section is None:
        logger.info("%s has no [tool.scistack] section; using defaults.", toml_path)
        section = {}

    # --- modules ---
    raw_modules = section.get("modules", [])
    if not isinstance(raw_modules, list):
        raise ValueError("[tool.scistack] modules must be a list of file paths.")
    modules: list[Path] = []
    for entry in raw_modules:
        if any(c in entry for c in ("*", "?", "[")):
            # Glob pattern (e.g. "pipelines/*.py")
            matched = sorted(
                Path(m) for m in _glob.glob(
                    str(project_root / entry), recursive=True,
                )
                if m.endswith(".py")
            )
            if not matched:
                logger.warning("modules glob matched no .py files: %s", entry)
            modules.extend(matched)
        else:
            p = (project_root / entry).resolve()
            if p.is_dir():
                # Recursively discover all .py files in the directory.
                found = sorted(p.rglob("*.py"))
                if not found:
                    logger.warning(
                        "modules directory contains no .py files: %s", p,
                    )
                modules.extend(found)
            else:
                if not p.exists():
                    logger.warning(
                        "Module listed in [tool.scistack] not found: %s", p,
                    )
                modules.append(p)

    # --- variable_file ---
    variable_file: Path | None = None
    raw_vf = section.get("variable_file")
    if raw_vf is not None:
        variable_file = (project_root / raw_vf).resolve()

    # --- packages ---
    packages = section.get("packages", [])
    if not isinstance(packages, list):
        raise ValueError("[tool.scistack] packages must be a list of package names.")

    # --- auto_discover ---
    auto_discover = section.get("auto_discover", True)
    if not isinstance(auto_discover, bool):
        raise ValueError("[tool.scistack] auto_discover must be true or false.")

    # --- MATLAB section ([tool.scistack.matlab] or [matlab] in scistack.toml) ---
    matlab_section = section.get("matlab", {})
    matlab_functions = _resolve_glob_paths(
        project_root, matlab_section.get("functions", []), "matlab.functions"
    )
    matlab_variables = _resolve_glob_paths(
        project_root, matlab_section.get("variables", []), "matlab.variables"
    )
    matlab_variable_dir: Path | None = None
    raw_mvd = matlab_section.get("variable_dir")
    if raw_mvd is not None:
        matlab_variable_dir = (project_root / raw_mvd).resolve()

    # Derive addpath from parent directories of all MATLAB file paths.
    addpath_set: set[Path] = set()
    for p in matlab_functions:
        addpath_set.add(p.parent)
    for p in matlab_variables:
        addpath_set.add(p.parent)
    if matlab_variable_dir is not None:
        addpath_set.add(matlab_variable_dir)
    matlab_addpath = sorted(addpath_set)

    config = SciStackConfig(
        project_root=project_root,
        modules=modules,
        variable_file=variable_file,
        packages=packages,
        auto_discover=auto_discover,
        matlab_functions=matlab_functions,
        matlab_variables=matlab_variables,
        matlab_addpath=matlab_addpath,
        matlab_variable_dir=matlab_variable_dir,
    )
    logger.info(
        "Loaded config from %s: %d modules, %d packages, auto_discover=%s, "
        "%d MATLAB functions, %d MATLAB variables",
        toml_path, len(modules), len(packages), auto_discover,
        len(matlab_functions), len(matlab_variables),
    )
    return config


def _resolve_glob_paths(
    project_root: Path, raw_entries: list, label: str,
) -> list[Path]:
    """Resolve a list of file paths / glob patterns relative to project_root.

    Each entry can be a single ``.m`` file, a directory (recursively walked
    for ``.m`` files), or a glob pattern (only ``.m`` matches are kept).
    """
    if not isinstance(raw_entries, list):
        raise ValueError(f"[tool.scistack] {label} must be a list of file paths.")
    result: list[Path] = []
    for entry in raw_entries:
        if any(c in entry for c in ("*", "?", "[")):
            # Glob pattern — expand and keep only .m files.
            matched = sorted(
                Path(p) for p in _glob.glob(
                    str(project_root / entry), recursive=True,
                )
                if p.endswith(".m")
            )
            if not matched:
                logger.warning("%s glob matched no .m files: %s", label, entry)
            result.extend(matched)
        else:
            p = (project_root / entry).resolve()
            if p.is_dir():
                # Recursively discover all .m files in the directory.
                found = sorted(p.rglob("*.m"))
                if not found:
                    logger.warning(
                        "%s directory contains no .m files: %s", label, p,
                    )
                result.extend(found)
            else:
                if not p.exists():
                    logger.warning("%s file not found: %s", label, p)
                result.append(p)
    return result


def _locate_pyproject(project_path: Path | None, db_path: Path) -> Path:
    """Find the pyproject.toml or scistack.toml to use."""
    if project_path is not None:
        p = project_path.resolve()
        if p.is_file():
            return p
        if p.is_dir():
            # Prefer pyproject.toml, fall back to scistack.toml
            for name in ("pyproject.toml", "scistack.toml"):
                candidate = p / name
                if candidate.exists():
                    return candidate
            raise FileNotFoundError(
                f"No pyproject.toml or scistack.toml found in directory: {p}"
            )
        raise FileNotFoundError(f"Path does not exist: {p}")

    # Search upward from the database file's directory.
    search_dir = db_path.resolve().parent
    while True:
        for name in ("pyproject.toml", "scistack.toml"):
            candidate = search_dir / name
            if candidate.exists():
                try:
                    with open(candidate, "rb") as f:
                        data = tomllib.load(f)
                    section = _extract_scistack_section(data, name)
                    if section is not None:
                        return candidate
                except Exception:
                    pass  # skip unparseable files
        parent = search_dir.parent
        if parent == search_dir:
            break
        search_dir = parent

    raise FileNotFoundError(
        f"No pyproject.toml/scistack.toml with [tool.scistack] found "
        f"in ancestors of {db_path}."
    )


def _extract_scistack_section(data: dict, filename: str) -> dict | None:
    """Extract the scistack config section from parsed TOML data.

    For pyproject.toml the section is at ``[tool.scistack]``.
    For scistack.toml the section is at the top level (the whole file).
    """
    if filename == "scistack.toml":
        # The entire file IS the scistack config.
        return data  # empty file → {} → valid all-defaults config
    # pyproject.toml
    return data.get("tool", {}).get("scistack")
