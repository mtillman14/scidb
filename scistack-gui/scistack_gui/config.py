"""
Parse [tool.scistack] configuration from pyproject.toml or scistack.toml.

Supports multi-source pipeline discovery: explicit .py modules,
pip-installed packages, auto-discovered entry-point plugins, and
MATLAB .m files.
"""

import glob as _glob
import logging
import os
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


def _normalize(p) -> Path:
    """Return *p* as an absolute, normalized :class:`Path` without following
    symlinks or canonicalizing Windows mapped drives.

    ``Path.resolve()`` on Windows rewrites mapped-drive paths like
    ``y:\\foo`` to their UNC target ``\\\\server\\share\\foo``. VS Code 1.75+
    refuses to open UNC paths unless the host is in
    ``security.allowedUNCHosts`` — which means every file opened via the
    GUI's ``reveal_in_editor`` would fail with "UNC host … access is not
    allowed".

    ``os.path.abspath`` + ``os.path.normpath`` make the path absolute and
    collapse ``.``/``..`` segments while preserving the drive-letter form
    the user supplied, so stored paths continue to work anywhere VS Code
    can open them (and MATLAB accepts either form).

    Callers that genuinely need canonical-form comparison (e.g. the
    variables-vs-functions dedupe set) should still use ``.resolve()``
    directly — that's comparison-only and doesn't leak into stored paths.
    """
    return Path(os.path.normpath(os.path.abspath(str(p))))


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

    matlab_path_inputs: list[Path] = field(default_factory=list)
    """Resolved absolute paths to MATLAB PathInput getter files (see
    matlab_parser.parse_matlab_path_input and
    docs/claude/code-discovery-categories.md)."""

    matlab_sweeps: list[Path] = field(default_factory=list)
    """Resolved absolute paths to MATLAB Sweep getter files (see
    matlab_parser.parse_matlab_sweep)."""

    matlab_addpath: list[Path] = field(default_factory=list)
    """MATLAB path entries (auto-derived from parent dirs of functions, variables, and variable_dir)."""

    matlab_variable_dir: Path | None = None
    """Directory where ``create_variable`` writes new .m classdef files."""

    matlab_sources: list[Path] = field(default_factory=list)
    """Unclassified .m files, from folder-scan fallback OR an explicit
    ``[matlab] sources = [...]`` config entry. Each file is classified
    per-content (variable vs. function) by
    :func:`scistack_gui.matlab_parser.classify_matlab_file` rather than
    being pre-sorted into ``matlab_functions``/``matlab_variables`` by the
    user. This is the field the GUI's Paths popup writes to (via
    :func:`add_path`) so a single added directory works for MATLAB without
    the user declaring function-vs-variable up front."""


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
        If an explicit ``project_path`` was given and does not exist on disk.
        (When no pyproject.toml/scistack.toml can be *located*, this function
        no longer raises — it falls back to scanning the project root for
        ``.py``/``.m`` files directly. See :func:`_folder_scan_config`.)
    ValueError
        If the located pyproject.toml has no ``[tool.scistack]`` section or
        the section is invalid.
    """
    logger.info(
        "[config] Locating config file (project_path=%s, db_path=%s)",
        project_path,
        db_path,
    )
    toml_path = _locate_pyproject(project_path, db_path)
    if toml_path is None:
        root = _normalize(project_path) if project_path is not None else _normalize(db_path).parent
        logger.info(
            "[config] No pyproject.toml/scistack.toml found; falling back to "
            "folder-scan discovery rooted at %s",
            root,
        )
        return _folder_scan_config(root)
    project_root = toml_path.parent
    logger.info("[config] Found config at %s", toml_path)

    logger.info("[config] Loading TOML file")
    with open(toml_path, "rb") as f:
        data = tomllib.load(f)

    logger.info("[config] Extracting [tool.scistack] section")
    section = _extract_scistack_section(data, toml_path.name)
    if section is None:
        logger.info(
            "[config] %s has no [tool.scistack] section; using defaults.", toml_path
        )
        section = {}
    else:
        logger.debug(
            "[config] Found config section with keys: %s", list(section.keys())
        )

    # --- modules ---
    logger.info("[config] Processing modules list")
    raw_modules = section.get("modules", [])
    if not isinstance(raw_modules, list):
        raise ValueError("[tool.scistack] modules must be a list of file paths.")
    logger.debug("[config] Found %d module entries in config", len(raw_modules))
    modules: list[Path] = []
    for entry_idx, entry in enumerate(raw_modules):
        logger.debug(
            "[config] Processing module entry %d/%d: %s",
            entry_idx + 1,
            len(raw_modules),
            entry,
        )
        if any(c in entry for c in ("*", "?", "[")):
            # Glob pattern (e.g. "pipelines/*.py")
            logger.debug("[config] Entry is a glob pattern")
            matched = sorted(
                Path(m)
                for m in _glob.glob(
                    str(project_root / entry),
                    recursive=True,
                )
                if m.endswith(".py")
            )
            if not matched:
                logger.warning("[config] modules glob matched no .py files: %s", entry)
            else:
                logger.debug("[config] Glob matched %d .py files", len(matched))
            modules.extend(matched)
        else:
            p = _normalize(project_root / entry)
            if p.is_dir():
                # Recursively discover all .py files in the directory,
                # pruning noise dirs (.venv, node_modules, etc.) the same
                # way folder-scan mode does -- otherwise a bare directory
                # entry sweeps in far more than the user intended.
                logger.debug("[config] Entry is a directory, searching for .py files")
                found = _walk_source_files(p, ".py")
                if not found:
                    logger.warning(
                        "[config] modules directory contains no .py files: %s",
                        p,
                    )
                else:
                    logger.debug("[config] Found %d .py files in directory", len(found))
                modules.extend(found)
            else:
                if not p.exists():
                    logger.warning(
                        "[config] Module listed in [tool.scistack] not found: %s",
                        p,
                    )
                else:
                    logger.debug("[config] Adding module file: %s", p)
                modules.append(p)
    logger.info("[config] Resolved %d module files total", len(modules))

    # --- variable_file ---
    logger.info("[config] Processing variable_file")
    variable_file: Path | None = None
    raw_vf = section.get("variable_file")
    if raw_vf is not None:
        variable_file = _normalize(project_root / raw_vf)
        logger.debug("[config] variable_file set to: %s", variable_file)
    else:
        logger.debug("[config] No variable_file configured")

    # --- packages ---
    logger.info("[config] Processing packages list")
    packages = section.get("packages", [])
    if not isinstance(packages, list):
        raise ValueError("[tool.scistack] packages must be a list of package names.")
    logger.debug("[config] Found %d packages: %s", len(packages), packages)

    # --- auto_discover ---
    logger.info("[config] Processing auto_discover setting")
    auto_discover = section.get("auto_discover", True)
    if not isinstance(auto_discover, bool):
        raise ValueError("[tool.scistack] auto_discover must be true or false.")
    logger.debug("[config] auto_discover = %s", auto_discover)

    # --- MATLAB section ([tool.scistack.matlab] or [matlab] in scistack.toml) ---
    logger.info("[config] Processing MATLAB configuration")
    matlab_section = section.get("matlab", {})
    if matlab_section:
        logger.debug(
            "[config] Found MATLAB section with keys: %s", list(matlab_section.keys())
        )
    else:
        logger.debug("[config] No MATLAB section found")

    matlab_functions = _resolve_glob_paths(
        project_root, matlab_section.get("functions", []), "matlab.functions"
    )
    matlab_variables = _resolve_glob_paths(
        project_root, matlab_section.get("variables", []), "matlab.variables"
    )
    matlab_path_inputs = _resolve_glob_paths(
        project_root, matlab_section.get("path_inputs", []), "matlab.path_inputs"
    )
    matlab_sweeps = _resolve_glob_paths(
        project_root, matlab_section.get("sweeps", []), "matlab.sweeps"
    )
    # Unified, unclassified .m paths -- same auto-classify-per-file behavior
    # as folder-scan mode's matlab_sources (see classify_matlab_file), just
    # reachable from an explicit config too. This is what lets a single
    # GUI-added directory work for MATLAB without the user having to
    # declare "functions" vs. "variables" up front.
    matlab_sources = _resolve_glob_paths(
        project_root, matlab_section.get("sources", []), "matlab.sources"
    )
    matlab_variable_dir: Path | None = None
    raw_mvd = matlab_section.get("variable_dir")
    if raw_mvd is not None:
        matlab_variable_dir = _normalize(project_root / raw_mvd)
        logger.debug("[config] matlab_variable_dir set to: %s", matlab_variable_dir)
    else:
        logger.debug("[config] No matlab_variable_dir configured")

    # Dedupe: any file in matlab.variables/path_inputs/sweeps must not
    # ALSO be parsed as a plain function. This handles the common case
    # where matlab.functions points at a parent directory (e.g. "src/")
    # that contains those files as a subtree.
    logger.info("[config] Deduplicating MATLAB functions vs variables/path_inputs/sweeps")
    non_function_path_set = {
        p.resolve() for p in (*matlab_variables, *matlab_path_inputs, *matlab_sweeps)
    }
    original_fn_count = len(matlab_functions)
    matlab_functions = [
        p for p in matlab_functions if p.resolve() not in non_function_path_set
    ]
    excluded = original_fn_count - len(matlab_functions)
    if excluded:
        logger.info(
            "[config] Excluded %d file(s) from matlab.functions because they are "
            "also declared in matlab.variables/path_inputs/sweeps.",
            excluded,
        )

    # Derive addpath from parent directories of all MATLAB file paths.
    logger.info("[config] Deriving MATLAB addpath from file locations")
    addpath_set: set[Path] = set()
    for p in matlab_functions:
        addpath_set.add(p.parent)
    for p in matlab_variables:
        addpath_set.add(p.parent)
    for p in matlab_path_inputs:
        addpath_set.add(p.parent)
    for p in matlab_sweeps:
        addpath_set.add(p.parent)
    for p in matlab_sources:
        addpath_set.add(p.parent)
    if matlab_variable_dir is not None:
        addpath_set.add(matlab_variable_dir)
    matlab_addpath = sorted(addpath_set)
    logger.debug("[config] MATLAB addpath contains %d directories", len(matlab_addpath))

    logger.info("[config] Building final configuration")
    config = SciStackConfig(
        project_root=project_root,
        modules=modules,
        variable_file=variable_file,
        packages=packages,
        auto_discover=auto_discover,
        matlab_functions=matlab_functions,
        matlab_variables=matlab_variables,
        matlab_path_inputs=matlab_path_inputs,
        matlab_sweeps=matlab_sweeps,
        matlab_addpath=matlab_addpath,
        matlab_variable_dir=matlab_variable_dir,
        matlab_sources=matlab_sources,
    )
    logger.info(
        "[config] Configuration loaded from %s: %d modules, %d packages, auto_discover=%s, "
        "%d MATLAB functions, %d MATLAB variables, %d MATLAB path inputs, "
        "%d MATLAB sweeps, %d MATLAB sources",
        toml_path,
        len(modules),
        len(packages),
        auto_discover,
        len(matlab_functions),
        len(matlab_variables),
        len(matlab_path_inputs),
        len(matlab_sweeps),
        len(matlab_sources),
    )
    return config


def _resolve_glob_paths(
    project_root: Path,
    raw_entries: list,
    label: str,
) -> list[Path]:
    """Resolve a list of file paths / glob patterns relative to project_root.

    Each entry can be a single ``.m`` file, a directory (recursively walked
    for ``.m`` files), or a glob pattern (only ``.m`` matches are kept).
    """
    if not isinstance(raw_entries, list):
        raise ValueError(f"[tool.scistack] {label} must be a list of file paths.")
    logger.debug("[config] Resolving %d entries for %s", len(raw_entries), label)
    result: list[Path] = []
    for entry_idx, entry in enumerate(raw_entries):
        logger.debug(
            "[config] Processing %s entry %d/%d: %s",
            label,
            entry_idx + 1,
            len(raw_entries),
            entry,
        )
        if any(c in entry for c in ("*", "?", "[")):
            # Glob pattern — expand and keep only .m files.
            logger.debug("[config] Entry is a glob pattern")
            matched = sorted(
                Path(p)
                for p in _glob.glob(
                    str(project_root / entry),
                    recursive=True,
                )
                if p.endswith(".m")
            )
            if not matched:
                logger.warning("[config] %s glob matched no .m files: %s", label, entry)
            else:
                logger.debug("[config] Glob matched %d .m files", len(matched))
            result.extend(matched)
        else:
            p = _normalize(project_root / entry)
            if p.is_dir():
                # Recursively discover all .m files in the directory,
                # pruning noise dirs and MATLAB private/@class/+package
                # dirs the same way folder-scan mode does.
                logger.debug("[config] Entry is a directory, searching for .m files")
                found = _walk_source_files(p, ".m", matlab=True)
                if not found:
                    logger.warning(
                        "[config] %s directory contains no .m files: %s",
                        label,
                        p,
                    )
                else:
                    logger.debug("[config] Found %d .m files in directory", len(found))
                result.extend(found)
            else:
                if not p.exists():
                    logger.warning("[config] %s file not found: %s", label, p)
                else:
                    logger.debug("[config] Adding .m file: %s", p)
                result.append(p)
    logger.debug("[config] Resolved %d total paths for %s", len(result), label)
    return result


def _locate_pyproject(project_path: Path | None, db_path: Path) -> Path | None:
    """Find the pyproject.toml or scistack.toml to use.

    Returns ``None`` (rather than raising) when no config file can be found —
    callers treat that as "use folder-scan discovery instead." An explicit
    ``project_path`` that doesn't exist on disk at all is still a hard error
    (that's a typo, not a missing-config situation).
    """
    if project_path is not None:
        logger.debug("[config] Explicit project_path provided: %s", project_path)
        p = _normalize(project_path)
        if p.is_file():
            logger.debug("[config] project_path is a file: %s", p)
            return p
        if p.is_dir():
            logger.debug(
                "[config] project_path is a directory, searching for config file"
            )
            # Prefer pyproject.toml, fall back to scistack.toml
            for name in ("pyproject.toml", "scistack.toml"):
                candidate = p / name
                if candidate.exists():
                    logger.debug("[config] Found %s in directory", name)
                    return candidate
            logger.info(
                "[config] No pyproject.toml or scistack.toml found in directory: %s",
                p,
            )
            return None
        raise FileNotFoundError(f"Path does not exist: {p}")

    # Search upward from the database file's directory.
    logger.debug(
        "[config] No explicit project_path, searching upward from db_path: %s", db_path
    )
    search_dir = _normalize(db_path).parent
    search_count = 0
    while True:
        search_count += 1
        logger.debug("[config] Searching directory %d: %s", search_count, search_dir)
        for name in ("pyproject.toml", "scistack.toml"):
            candidate = search_dir / name
            if candidate.exists():
                logger.debug(
                    "[config] Found %s, checking for [tool.scistack] section", name
                )
                try:
                    with open(candidate, "rb") as f:
                        data = tomllib.load(f)
                    section = _extract_scistack_section(data, name)
                    if section is not None:
                        logger.debug(
                            "[config] %s contains [tool.scistack] section", name
                        )
                        return candidate
                    else:
                        logger.debug(
                            "[config] %s has no [tool.scistack] section, continuing search",
                            name,
                        )
                except Exception:
                    logger.debug("[config] Failed to parse %s, continuing search", name)
                    pass  # skip unparseable files
        parent = search_dir.parent
        if parent == search_dir:
            logger.debug("[config] Reached filesystem root, search failed")
            break
        search_dir = parent

    logger.info(
        "[config] No pyproject.toml/scistack.toml with [tool.scistack] found "
        "in ancestors of %s",
        db_path,
    )
    return None


def _extract_scistack_section(data: dict, filename: str) -> dict | None:
    """Extract the scistack config section from parsed TOML data.

    For pyproject.toml the section is at ``[tool.scistack]``.
    For scistack.toml the section is at the top level (the whole file).
    """
    logger.debug("[config] Extracting scistack section from %s", filename)
    if filename == "scistack.toml":
        # The entire file IS the scistack config.
        logger.debug("[config] scistack.toml: entire file is config")
        return data  # empty file → {} → valid all-defaults config
    # pyproject.toml
    section = data.get("tool", {}).get("scistack")
    if section is None:
        logger.debug("[config] pyproject.toml: no [tool.scistack] section found")
    else:
        logger.debug("[config] pyproject.toml: found [tool.scistack] section")
    return section


# ---------------------------------------------------------------------------
# Folder-scan fallback (no pyproject.toml/scistack.toml present)
# ---------------------------------------------------------------------------

# Directories never worth walking into, for either language.
_NOISE_DIR_NAMES = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    "build",
    "dist",
}


def _is_noise_dir(name: str) -> bool:
    return name in _NOISE_DIR_NAMES or name.startswith(".")


def _is_matlab_skip_dir(name: str) -> bool:
    """MATLAB directory conventions that must never be swept in as if their
    contents were standalone pipeline functions: ``private/`` helpers,
    ``@ClassName/`` method files, and ``+package/`` namespace folders.
    Proper support for the latter two is tracked as follow-on work — for
    folder-scan discovery the safe default is to skip them entirely rather
    than mis-register a class method or namespaced function."""
    return name == "private" or name.startswith("@") or name.startswith("+")


def _walk_source_files(root: Path, suffix: str, *, matlab: bool = False) -> list[Path]:
    """Recursively find files ending in *suffix* under *root*, pruning noise
    directories (and, for MATLAB, private/class/package folders) as we go."""
    results: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d
            for d in dirnames
            if not _is_noise_dir(d) and not (matlab and _is_matlab_skip_dir(d))
        ]
        for fname in filenames:
            if fname.endswith(suffix):
                results.append(_normalize(Path(dirpath) / fname))
    return sorted(results)


def _folder_scan_config(root: Path) -> SciStackConfig:
    """Build a :class:`SciStackConfig` by scanning *root* directly for
    ``.py``/``.m`` files, with no config file at all.

    Python files become ``modules`` — identical to how an explicit
    ``modules = ["some_dir"]`` entry is already resolved, so
    :func:`scistack_gui.registry._load_file_modules` needs no changes.

    MATLAB files become ``matlab_sources`` — a single unified list, since a
    folder scan has no way to know in advance which files are functions vs.
    ``BaseVariable`` classdefs. Each file is classified individually by
    :func:`scistack_gui.matlab_parser.classify_matlab_file` when
    :func:`scistack_gui.matlab_registry.load_from_sources` runs.
    """
    logger.info("[config] Folder-scan: walking %s for .py/.m files", root)
    py_files = _walk_source_files(root, ".py")
    m_files = _walk_source_files(root, ".m", matlab=True)
    logger.info(
        "[config] Folder-scan found %d .py file(s), %d .m file(s)",
        len(py_files),
        len(m_files),
    )

    addpath = sorted({p.parent for p in m_files})

    config = SciStackConfig(
        project_root=root,
        modules=py_files,
        matlab_sources=m_files,
        matlab_addpath=addpath,
    )
    logger.info(
        "[config] Folder-scan configuration built for %s: %d modules, "
        "%d MATLAB sources",
        root,
        len(py_files),
        len(m_files),
    )
    return config


# ---------------------------------------------------------------------------
# Writing scistack.toml (GUI Paths popup, loose-script projects only)
# ---------------------------------------------------------------------------
#
# pyproject.toml-based ("packaged") projects are out of scope for this
# write path -- see add_path/remove_path's explicit rejection below. This
# is deliberately not a general-purpose TOML editor: scistack.toml has no
# [project]/[build-system] noise to preserve, its entire content is keys
# this module already knows about, so every write regenerates the whole
# file from those known keys rather than attempting comment/formatting
# preservation (which would need a TOML round-trip library this codebase
# doesn't otherwise depend on).


def _toml_str(s: str) -> str:
    """Render *s* as a quoted TOML basic string, escaping backslashes
    (important for Windows paths) and double quotes."""
    escaped = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _toml_array(items: list) -> str:
    if not items:
        return "[]"
    inner = ",\n    ".join(_toml_str(str(item)) for item in items)
    return f"[\n    {inner},\n]"


def _render_scistack_toml(
    *,
    modules: list,
    variable_file,
    packages: list,
    auto_discover: bool,
    matlab_functions: list,
    matlab_variables: list,
    matlab_path_inputs: list,
    matlab_sweeps: list,
    matlab_sources: list,
    matlab_variable_dir,
) -> str:
    """Render a complete scistack.toml from known [tool.scistack] fields.

    Round-trips every field this module understands (not just modules/
    matlab.sources) so that add_path/remove_path never silently drop
    hand-authored packages/auto_discover/variable_file/etc.
    """
    lines = [
        "# Written by the SciStack GUI's Paths popup.",
        "# Hand-editing is fine -- this file is re-read on every scan.",
        "",
        f"modules = {_toml_array(modules)}",
    ]
    if variable_file is not None:
        lines.append(f"variable_file = {_toml_str(str(variable_file))}")
    if packages:
        lines.append(f"packages = {_toml_array(packages)}")
    if not auto_discover:
        lines.append("auto_discover = false")
    if (
        matlab_functions
        or matlab_variables
        or matlab_path_inputs
        or matlab_sweeps
        or matlab_sources
        or matlab_variable_dir
    ):
        lines.append("")
        lines.append("[matlab]")
        if matlab_functions:
            lines.append(f"functions = {_toml_array(matlab_functions)}")
        if matlab_variables:
            lines.append(f"variables = {_toml_array(matlab_variables)}")
        if matlab_path_inputs:
            lines.append(f"path_inputs = {_toml_array(matlab_path_inputs)}")
        if matlab_sweeps:
            lines.append(f"sweeps = {_toml_array(matlab_sweeps)}")
        if matlab_sources:
            lines.append(f"sources = {_toml_array(matlab_sources)}")
        if matlab_variable_dir is not None:
            lines.append(f"variable_dir = {_toml_str(str(matlab_variable_dir))}")
    lines.append("")
    return "\n".join(lines)


def _load_raw_scistack_section(toml_path: Path) -> dict:
    with open(toml_path, "rb") as f:
        data = tomllib.load(f)
    return _extract_scistack_section(data, toml_path.name) or {}


def _resolve_raw_entry(entry: str, project_root: Path) -> Path:
    p = Path(entry)
    return _normalize(p) if p.is_absolute() else _normalize(project_root / entry)


def _reject_packaged_project(toml_path: Path | None) -> None:
    if toml_path is not None and toml_path.name == "pyproject.toml":
        raise ValueError(
            "Packaged project (pyproject.toml found at "
            f"{toml_path}) -- the Paths popup's add/remove UI only manages "
            "loose-script projects (scistack.toml). Edit [tool.scistack] "
            "in pyproject.toml by hand instead."
        )


def describe_managed_paths(db_path: Path) -> dict:
    """Info the Paths popup needs to pick its rendering mode: whether the
    resolved config is a packaged (pyproject.toml) project -- read-only in
    the popup -- and, for loose-script projects, the raw (pre-discovery)
    ``modules`` entries currently written to scistack.toml. Empty until the
    first path is added via :func:`add_path`, even if folder-scan discovery
    is already finding files implicitly.
    """
    toml_path = _locate_pyproject(None, db_path)
    packaged = toml_path is not None and toml_path.name == "pyproject.toml"
    managed_paths: list[str] = []
    if toml_path is not None and toml_path.name == "scistack.toml":
        section = _load_raw_scistack_section(toml_path)
        managed_paths = list(section.get("modules", []))
    return {"packaged": packaged, "managed_paths": managed_paths}


def add_path(db_path: Path, new_path: Path) -> Path:
    """Add *new_path* (a directory) to scistack.toml's ``modules`` and
    ``[matlab] sources`` lists, creating the file if none exists yet, and
    return the file that was written.

    Only valid for loose-script projects (no pyproject.toml at the
    resolved project root) -- see :func:`_reject_packaged_project`.

    On the very first write (no scistack.toml/pyproject.toml found at all,
    i.e. the project was previously running on pure folder-scan discovery),
    seeds both lists with the project root itself first, so the code that
    was implicitly discovered under folder-scan mode doesn't silently
    disappear the moment an explicit config file exists -- from that point
    on, discovery is exclusively config-driven (see load_config).
    """
    raw_new_path = Path(new_path)
    logger.info("[config] add_path: db_path=%s, new_path=%s", db_path, raw_new_path)
    if not raw_new_path.is_absolute():
        raise ValueError(f"Path must be absolute: {new_path}")
    if not raw_new_path.exists():
        raise FileNotFoundError(f"Path does not exist: {new_path}")
    if not raw_new_path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {new_path}")

    toml_path = _locate_pyproject(None, db_path)
    _reject_packaged_project(toml_path)

    is_first_write = toml_path is None
    if is_first_write:
        target_path = _normalize(db_path).parent / "scistack.toml"
        section: dict = {}
        project_root = target_path.parent
        logger.info(
            "[config] add_path: no config found, will create %s", target_path
        )
    else:
        target_path = toml_path
        section = _load_raw_scistack_section(toml_path)
        project_root = toml_path.parent

    raw_modules = list(section.get("modules", []))
    matlab_section = dict(section.get("matlab", {}))
    raw_sources = list(matlab_section.get("sources", []))

    if is_first_write:
        root_str = str(project_root)
        raw_modules.append(root_str)
        raw_sources.append(root_str)
        logger.info(
            "[config] add_path: seeding new scistack.toml with project root %s",
            root_str,
        )

    normalized_new = _normalize(new_path)
    new_str = str(normalized_new)

    existing_modules_resolved = {_resolve_raw_entry(e, project_root) for e in raw_modules}
    if normalized_new not in existing_modules_resolved:
        raw_modules.append(new_str)

    existing_sources_resolved = {_resolve_raw_entry(e, project_root) for e in raw_sources}
    if normalized_new not in existing_sources_resolved:
        raw_sources.append(new_str)

    content = _render_scistack_toml(
        modules=raw_modules,
        variable_file=section.get("variable_file"),
        packages=list(section.get("packages", [])),
        auto_discover=section.get("auto_discover", True),
        matlab_functions=list(matlab_section.get("functions", [])),
        matlab_variables=list(matlab_section.get("variables", [])),
        matlab_path_inputs=list(matlab_section.get("path_inputs", [])),
        matlab_sweeps=list(matlab_section.get("sweeps", [])),
        matlab_sources=raw_sources,
        matlab_variable_dir=matlab_section.get("variable_dir"),
    )
    target_path.write_text(content)
    logger.info("[config] add_path: wrote %s (added %s)", target_path, new_str)
    return target_path


def remove_path(db_path: Path, path_to_remove: Path) -> Path:
    """Remove *path_to_remove* from scistack.toml's ``modules`` and
    ``[matlab] sources`` lists, and return the file that was written.

    Raises FileNotFoundError if no scistack.toml exists yet (never creates
    a file on remove). Only valid for loose-script projects.
    """
    logger.info(
        "[config] remove_path: db_path=%s, path_to_remove=%s", db_path, path_to_remove
    )
    toml_path = _locate_pyproject(None, db_path)
    if toml_path is None:
        raise FileNotFoundError(
            f"No scistack.toml/pyproject.toml found near {db_path}; nothing to remove."
        )
    _reject_packaged_project(toml_path)

    section = _load_raw_scistack_section(toml_path)
    project_root = toml_path.parent
    target = _normalize(path_to_remove)

    raw_modules = [
        e for e in section.get("modules", [])
        if _resolve_raw_entry(e, project_root) != target
    ]
    matlab_section = dict(section.get("matlab", {}))
    raw_sources = [
        e for e in matlab_section.get("sources", [])
        if _resolve_raw_entry(e, project_root) != target
    ]

    content = _render_scistack_toml(
        modules=raw_modules,
        variable_file=section.get("variable_file"),
        packages=list(section.get("packages", [])),
        auto_discover=section.get("auto_discover", True),
        matlab_functions=list(matlab_section.get("functions", [])),
        matlab_variables=list(matlab_section.get("variables", [])),
        matlab_path_inputs=list(matlab_section.get("path_inputs", [])),
        matlab_sweeps=list(matlab_section.get("sweeps", [])),
        matlab_sources=raw_sources,
        matlab_variable_dir=matlab_section.get("variable_dir"),
    )
    toml_path.write_text(content)
    logger.info("[config] remove_path: wrote %s (removed %s)", toml_path, target)
    return toml_path
