"""
MATLAB function and variable registry.

Mirrors the role of :mod:`scistack_gui.registry` for Python code, but for
MATLAB .m files declared in ``[tool.scistack.matlab]``.

Module-level state tracks discovered MATLAB functions and variables.
On load, Python surrogate classes are created for each MATLAB variable via
:func:`scimatlab.bridge.register_matlab_variable` so they participate in
the DAG graph (which is built from DB history that references these types).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from scistack_gui.matlab_parser import (
    MatlabFunctionInfo,
    classify_matlab_file,
    extract_path_input_literal,
    extract_sweep_literal,
    parse_matlab_function,
    parse_matlab_path_input,
    parse_matlab_sweep,
    parse_matlab_variable,
)

if TYPE_CHECKING:
    from scistack_gui.config import SciStackConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_matlab_functions: dict[str, MatlabFunctionInfo] = {}
"""function_name -> parsed info."""

_matlab_variables: dict[str, Path] = {}
"""variable_class_name -> .m file path."""

_matlab_path_inputs: dict[str, Path] = {}
"""PathInput getter name -> .m file path (see matlab_parser.
parse_matlab_path_input and docs/claude/code-discovery-categories.md).

Always tracked here by name (this dict), and — when the getter's
construction call is a simple literal (see
matlab_parser.extract_path_input_literal) — ALSO registered as a real
``scifor.PathInput`` object into ``scistack_gui.registry``'s shared
``_path_inputs`` dict (:func:`_register_matlab_path_input`), which is what
makes it show up as a ``pathInput__`` canvas node and resolve in
execution/generated MATLAB commands — every consumer of
``registry.get_path_inputs_registry()`` is language-agnostic once an
object lands there. A getter whose args reference a MATLAB
variable/expression (not a literal) can't be statically evaluated (no
MATLAB run here) — it stays name-only in THIS dict, with a load error
recorded so the gap is visible rather than silent.
"""

_matlab_sweeps: dict[str, Path] = {}
"""Sweep getter name -> .m file path — same name-only-vs-registered
treatment as _matlab_path_inputs above, via
:func:`_register_matlab_sweep`/matlab_parser.extract_sweep_literal."""

_config: SciStackConfig | None = None
"""Stored config for refresh_all()."""

_load_errors: list[dict] = []
"""Discovery failures from the most recent load/refresh — [{"source", "error"}, ...].

Only real misconfigurations/failures land here: a file explicitly listed
in ``matlab.functions``/``matlab.variables`` that doesn't parse as one, a
missing file, or a surrogate-registration exception. An ordinary script.m
that folder-scan discovery can't classify as either is NOT an error (most
real MATLAB projects have plenty of non-function scripts) — see
``load_from_sources``.
"""


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _deregister_stale_matlab_path_inputs_and_sweeps() -> None:
    """Remove any PathInput/Sweep this module PREVIOUSLY registered into
    the shared ``scistack_gui.registry``, before a fresh scan replaces
    ``_matlab_path_inputs``/``_matlab_sweeps``.

    Only removes an entry whose recorded SOURCE exactly matches the ``.m``
    file this module registered it from — never a same-named entry that
    "last write wins" collision handling has since attributed to a
    different (e.g. Python) source; see ``registry._register_path_input``/
    ``_register_sweep``'s shadowing warning.
    """
    from scistack_gui import registry

    for name, path in _matlab_path_inputs.items():
        if registry._path_input_sources.get(name) == str(path):
            registry._path_inputs.pop(name, None)
            registry._path_input_sources.pop(name, None)
    for name, path in _matlab_sweeps.items():
        if registry._sweep_sources.get(name) == str(path):
            registry._sweeps.pop(name, None)
            registry._sweep_sources.pop(name, None)


def load_from_config(config: SciStackConfig) -> dict:
    """Scan configured MATLAB paths, parse .m files, populate registries.

    Also creates Python surrogate classes for each MATLAB variable so the
    DAG graph builder can reference them.

    Returns a summary dict.
    """
    logger.info("[matlab_registry] Loading MATLAB config")
    global _config
    _config = config

    logger.info("[matlab_registry] Clearing registries")
    _matlab_functions.clear()
    _matlab_variables.clear()
    # Deregister from the SHARED scistack_gui.registry BEFORE clearing our
    # own name-tracking dicts below — otherwise a renamed/deleted getter's
    # old registered PathInput/Sweep object would linger there forever
    # (matlab_registry.clear() only ever touched its own dicts, not the
    # registry it registers INTO). Names that get re-registered further
    # down in this same call simply overwrite these removals; this only
    # matters for ones that DON'T come back.
    _deregister_stale_matlab_path_inputs_and_sweeps()
    _matlab_path_inputs.clear()
    _matlab_sweeps.clear()
    _load_errors.clear()

    # --- Function files (explicit matlab.functions config) ---
    logger.info(
        "[matlab_registry] Parsing %d MATLAB function files",
        len(config.matlab_functions),
    )
    for idx, path in enumerate(config.matlab_functions):
        logger.debug(
            "[matlab_registry] Parsing function file %d/%d: %s",
            idx + 1,
            len(config.matlab_functions),
            path,
        )
        info = parse_matlab_function(path)
        if info is not None:
            _register_matlab_function(info)
        else:
            logger.warning(
                "[matlab_registry] Could not parse MATLAB function from %s", path
            )
            _record_load_error(str(path), "No function declaration found")

    # --- Variable classdef files (explicit matlab.variables config) ---
    logger.info(
        "[matlab_registry] Parsing %d MATLAB variable files",
        len(config.matlab_variables),
    )
    for idx, path in enumerate(config.matlab_variables):
        logger.debug(
            "[matlab_registry] Parsing variable file %d/%d: %s",
            idx + 1,
            len(config.matlab_variables),
            path,
        )
        var_name = parse_matlab_variable(path)
        if var_name is not None:
            _register_matlab_variable(var_name, path)
        else:
            logger.warning(
                "[matlab_registry] Could not parse MATLAB variable classdef from %s",
                path,
            )
            _record_load_error(str(path), "No BaseVariable classdef found")

    # --- PathInput getter files (explicit matlab.path_inputs config) ---
    logger.info(
        "[matlab_registry] Parsing %d MATLAB PathInput getter files",
        len(config.matlab_path_inputs),
    )
    for idx, path in enumerate(config.matlab_path_inputs):
        pi_name = parse_matlab_path_input(path)
        if pi_name is not None:
            _register_matlab_path_input(pi_name, path)
        else:
            logger.warning(
                "[matlab_registry] Could not parse MATLAB PathInput getter from %s",
                path,
            )
            _record_load_error(str(path), "No PathInput getter found")

    # --- Sweep getter files (explicit matlab.sweeps config) ---
    logger.info(
        "[matlab_registry] Parsing %d MATLAB Sweep getter files",
        len(config.matlab_sweeps),
    )
    for idx, path in enumerate(config.matlab_sweeps):
        sw_name = parse_matlab_sweep(path)
        if sw_name is not None:
            _register_matlab_sweep(sw_name, path)
        else:
            logger.warning(
                "[matlab_registry] Could not parse MATLAB Sweep getter from %s", path
            )
            _record_load_error(str(path), "No Sweep getter found")

    # --- Unified sources (folder-scan fallback: no functions/variables
    # split available, each file classified individually by content) ---
    if config.matlab_sources:
        load_from_sources(config.matlab_sources)

    logger.info(
        "[matlab_registry] MATLAB registry loading complete - %d functions, "
        "%d variables, %d path inputs, %d sweeps",
        len(_matlab_functions),
        len(_matlab_variables),
        len(_matlab_path_inputs),
        len(_matlab_sweeps),
    )
    return {
        "matlab_functions": sorted(_matlab_functions.keys()),
        "matlab_variables": sorted(_matlab_variables.keys()),
        "matlab_path_inputs": sorted(_matlab_path_inputs.keys()),
        "matlab_sweeps": sorted(_matlab_sweeps.keys()),
    }


def load_from_sources(paths: list[Path]) -> None:
    """Classify and register each .m file in *paths* individually.

    Used for folder-scan discovery, where files haven't been pre-sorted
    into ``matlab.functions``/``matlab.variables`` by an explicit config.
    """
    logger.info("[matlab_registry] Classifying %d unified MATLAB source file(s)", len(paths))
    for idx, path in enumerate(paths):
        logger.debug(
            "[matlab_registry] Classifying source file %d/%d: %s",
            idx + 1,
            len(paths),
            path,
        )
        result = classify_matlab_file(path)
        if result is None:
            # NOT recorded as a load error — an ordinary non-function
            # script.m in a folder scan is expected, not a misconfiguration.
            logger.debug(
                "[matlab_registry] Skipping non-function/non-variable MATLAB "
                "file (folder-scan): %s",
                path,
            )
            continue
        kind, payload = result
        if kind == "variable":
            _register_matlab_variable(payload, path)
        elif kind == "path_input":
            _register_matlab_path_input(payload, path)
        elif kind == "sweep":
            _register_matlab_sweep(payload, path)
        else:
            _register_matlab_function(payload)


def register_builtin_function(info: MatlabFunctionInfo) -> None:
    """Register a manually-declared reference to a MATLAB built-in/toolbox
    function (validated by scistack_gui.api.builtin_functions via a real
    MATLAB installation) — e.g. ``mean``. ``info.file_path`` is ``None``:
    there is no backing .m file. Survives registry refreshes via
    scistack_gui.api.builtin_functions.replay_persisted_builtins.
    """
    _register_matlab_function(info)


def _register_matlab_function(info: MatlabFunctionInfo) -> None:
    """Register a single parsed MATLAB function, warning on name collisions."""
    if info.name in _matlab_functions:
        logger.warning(
            "[matlab_registry] MATLAB function '%s' from %s shadows previous definition from %s",
            info.name,
            info.file_path,
            _matlab_functions[info.name].file_path,
        )
    _matlab_functions[info.name] = info
    logger.info(
        "[matlab_registry] Registered MATLAB function: %s (%s)",
        info.name,
        info.file_path,
    )


def _register_matlab_variable(var_name: str, path: Path) -> None:
    """Register a single MATLAB BaseVariable classdef and create its Python
    surrogate so the DAG builder can reference it."""
    # Store the path as-is (already absolute & normalized by
    # config._normalize). Calling .resolve() here would undo that
    # by canonicalizing mapped drives → UNC on Windows.
    _matlab_variables[var_name] = path
    logger.debug(
        "[matlab_registry] Creating Python surrogate for MATLAB variable: %s",
        var_name,
    )
    try:
        from scimatlab.bridge import register_matlab_variable

        register_matlab_variable(var_name)
        logger.info(
            "[matlab_registry] Registered MATLAB variable: %s (%s)", var_name, path
        )
    except Exception as e:
        logger.exception(
            "[matlab_registry] Failed to create surrogate for MATLAB variable '%s'",
            var_name,
        )
        _record_load_error(str(path), str(e))


def _register_matlab_path_input(name: str, path: Path) -> None:
    """Register a single MATLAB PathInput getter: always name-tracked here,
    and — when its construction call is a simple literal — ALSO registered
    as a real ``scifor.PathInput`` into the shared Python registry (see
    _matlab_path_inputs' docstring)."""
    _matlab_path_inputs[name] = path
    literal = extract_path_input_literal(path)
    if literal is None:
        logger.warning(
            "[matlab_registry] PathInput getter '%s' (%s) does not construct "
            "a simple literal (references a MATLAB variable/expression) -- "
            "cannot statically extract its value, so it won't appear as a "
            "pathInput__ canvas node or resolve in execution/generated "
            "MATLAB commands. Name-tracked only.",
            name,
            path,
        )
        _record_load_error(
            str(path), "PathInput getter is not a simple literal construction"
        )
        return

    template, root_folder = literal
    from scifor import PathInput

    from scistack_gui import registry

    pi = PathInput(template, root_folder=root_folder)
    registry._register_path_input(name, pi, source=str(path))
    logger.info(
        "[matlab_registry] Registered MATLAB PathInput getter: %s (%s) "
        "template=%r root_folder=%r",
        name,
        path,
        template,
        root_folder,
    )


def _register_matlab_sweep(name: str, path: Path) -> None:
    """Register a single MATLAB Sweep getter: always name-tracked here,
    and — when its construction call is all simple literals — ALSO
    registered as a real ``scifor.Sweep`` into the shared Python registry
    (see _matlab_sweeps' docstring)."""
    _matlab_sweeps[name] = path
    values = extract_sweep_literal(path)
    if values is None:
        logger.warning(
            "[matlab_registry] Sweep getter '%s' (%s) does not construct "
            "all-literal values (references a MATLAB variable/expression) "
            "-- cannot statically extract them, so it won't appear as a "
            "sweep__ canvas node or resolve in execution/generated MATLAB "
            "commands. Name-tracked only.",
            name,
            path,
        )
        _record_load_error(
            str(path), "Sweep getter is not an all-literal construction"
        )
        return

    from scidb import Sweep

    from scistack_gui import registry

    sw = Sweep(*values)
    registry._register_sweep(name, sw, source=str(path))
    logger.info(
        "[matlab_registry] Registered MATLAB Sweep getter: %s (%s) %d value(s)",
        name,
        path,
        len(values),
    )


def refresh_all() -> dict:
    """Re-scan all configured MATLAB paths."""
    logger.info("[matlab_registry] Starting refresh_all")
    if _config is None:
        logger.warning("[matlab_registry] No MATLAB config loaded; nothing to refresh.")
        return {
            "matlab_functions": [],
            "matlab_variables": [],
            "matlab_path_inputs": [],
            "matlab_sweeps": [],
        }
    return load_from_config(_config)


# ---------------------------------------------------------------------------
# Lookup API
# ---------------------------------------------------------------------------


def get_matlab_function(name: str) -> MatlabFunctionInfo:
    """Return info for a registered MATLAB function, or raise KeyError."""
    info = _matlab_functions.get(name)
    if info is None:
        raise KeyError(f"MATLAB function '{name}' not found in registry.")
    return info


def is_matlab_function(name: str) -> bool:
    """Return True if *name* is a registered MATLAB function."""
    return name in _matlab_functions


def get_all_function_names() -> list[str]:
    """Return sorted list of all registered MATLAB function names."""
    return sorted(_matlab_functions.keys())


def get_all_variable_names() -> list[str]:
    """Return sorted list of all registered MATLAB variable names."""
    return sorted(_matlab_variables.keys())


def get_all_path_input_names() -> list[str]:
    """Return sorted list of all registered MATLAB PathInput getter names."""
    return sorted(_matlab_path_inputs.keys())


def get_all_sweep_names() -> list[str]:
    """Return sorted list of all registered MATLAB Sweep getter names."""
    return sorted(_matlab_sweeps.keys())


def get_mismatched_function_names() -> list[str]:
    """Return sorted list of MATLAB function names where the function name
    does not match the stem of its .m file (a MATLAB requirement).

    Builtin references (``file_path is None`` — no backing .m file) have
    nothing to mismatch against and are always excluded.
    """
    mismatched = [
        name
        for name, info in _matlab_functions.items()
        if info.file_path is not None and info.file_path.stem != name
    ]
    return sorted(mismatched)


def _record_load_error(source: str, error: str) -> None:
    entry = {"source": source, "error": error}
    _load_errors.append(entry)
    logger.debug("[matlab_registry] Recorded load error: %s", entry)


def get_load_errors() -> list[dict]:
    """Return discovery failures from the most recent load/refresh."""
    return list(_load_errors)


def has_matlab_config() -> bool:
    """Return True if a MATLAB config section was loaded."""
    return _config is not None and bool(
        _config.matlab_functions
        or _config.matlab_variables
        or _config.matlab_path_inputs
        or _config.matlab_sweeps
        or _config.matlab_sources
    )
