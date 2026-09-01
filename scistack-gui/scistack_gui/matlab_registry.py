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
    binding_parameter_literal,
    binding_path_input_literal,
    classify_matlab_file,
    collect_matlab_literal_scope,
    parse_matlab_entities_script,
    parse_matlab_function,
    parse_matlab_variable,
    read_source_text,
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
"""PathInput name -> the entities script declaring it (see
docs/claude/entity-editability-model.md).

Tracked here by name, and — when the declaration's construction call is a
simple literal — ALSO registered as a real ``scifor.PathInput`` object into
``scistack_gui.registry``'s shared ``_path_inputs`` dict
(:func:`_register_matlab_path_input_object`), which is what makes it show
up as a ``pathInput__`` canvas node and resolve in execution/generated
MATLAB commands — every consumer of ``registry.get_path_inputs_registry()``
is language-agnostic once an object lands there. A declaration whose args
reference a MATLAB variable/expression can't be statically evaluated (no
MATLAB run here) — it stays name-only in THIS dict, with a load error
recorded so the gap is visible rather than silent.
"""

_matlab_parameters: dict[str, Path] = {}
"""Parameter name -> the entities script declaring it — same
name-only-vs-registered treatment as _matlab_path_inputs above, via
:func:`_register_matlab_parameter_object`."""

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
    ``_matlab_path_inputs``/``_matlab_parameters``.

    Only removes an entry whose recorded SOURCE exactly matches the ``.m``
    file this module registered it from — never a same-named entry that
    "last write wins" collision handling has since attributed to a
    different (e.g. Python) source; see ``registry._register_path_input``/
    ``_register_parameter``'s shadowing warning.
    """
    from scistack_gui import registry

    for name, path in _matlab_path_inputs.items():
        if registry._path_input_sources.get(name) == str(path):
            registry._path_inputs.pop(name, None)
            registry._path_input_sources.pop(name, None)
    for name, path in _matlab_parameters.items():
        if registry._parameter_sources.get(name) == str(path):
            registry._parameters.pop(name, None)
            registry._parameter_sources.pop(name, None)


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
    # own name-tracking dicts below — otherwise a renamed or deleted
    # declaration's registered PathInput/Sweep object would linger forever
    # (matlab_registry.clear() only ever touched its own dicts, not the
    # registry it registers INTO). Names that get re-registered further
    # down in this same call simply overwrite these removals; this only
    # matters for ones that DON'T come back.
    _deregister_stale_matlab_path_inputs_and_sweeps()
    _matlab_path_inputs.clear()
    _matlab_parameters.clear()
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

    # --- Entities script ([matlab] entities_file) ---
    if config.matlab_entities_file is not None:
        load_entities_script(config.matlab_entities_file)

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
        len(_matlab_parameters),
    )
    return {
        "matlab_functions": sorted(_matlab_functions.keys()),
        "matlab_variables": sorted(_matlab_variables.keys()),
        "matlab_path_inputs": sorted(_matlab_path_inputs.keys()),
        "matlab_parameters": sorted(_matlab_parameters.keys()),
    }


def load_entities_script(path: Path) -> None:
    """Register every entity declared in a MATLAB entities script.

    The MATLAB counterpart of Python's ``variable_file`` scan: a plain
    script of ``NAME = scidb.Sweep(...)`` top-level bindings (see
    docs/claude/entity-editability-model.md). Registers into the SAME
    ``scistack_gui.registry`` the Python scanners use, so nothing downstream
    — canvas nodes, ``build_run_inputs``, command generation — needs to know
    which form a MATLAB entity was declared in.

    A missing file is not an error: the GUI creates it on the first entity
    it writes, so "configured but not yet created" is a normal state.
    """
    if not path.exists():
        logger.info(
            "[matlab_registry] entities_file %s does not exist yet; nothing to load",
            path,
        )
        return

    text = read_source_text(path)
    if text is None:
        _record_load_error(str(path), "Entities file could not be read")
        return

    bindings = parse_matlab_entities_script(path)
    if not bindings:
        logger.info(
            "[matlab_registry] entities_file %s declares no entities", path
        )
        return

    # Last binding of a name wins, matching how a MATLAB script actually
    # executes (and scidb.source_edit.find_binding_span on the Python side).
    latest = {b.name: b for b in bindings}

    # Plain `name = 'literal'` helper bindings, so a template assembled from a
    # base directory (`PathInput([baseDir '/6MWT.csv'])`) still resolves
    # statically instead of being dropped as non-literal.
    scope = collect_matlab_literal_scope(text)

    registered = 0
    for name, binding in latest.items():
        if binding.kind == "path_input":
            literal = binding_path_input_literal(binding, text, scope)
            if literal is None:
                _warn_non_literal(name, path, "PathInput")
                continue
            template, root_folder = literal
            _register_matlab_path_input_object(name, path, template, root_folder)
            registered += 1
        elif binding.kind == "parameter":
            literal = binding_parameter_literal(binding, text)
            if literal is None:
                _warn_non_literal(name, path, "Parameter")
                continue
            values, description = literal
            _register_matlab_parameter_object(name, path, values, description)
            registered += 1
        else:
            # "each_of" (alternate PathInput templates) parses but has no
            # MATLAB registration path yet.
            logger.info(
                "[matlab_registry] entities_file %s: '%s' is a %s declaration, "
                "which is parsed but not yet registered",
                path,
                name,
                binding.kind,
            )

    # Baseline for the stale-write guard — see registry.load_from_config's
    # matching call for the Python entities file.
    from scistack_gui.services.target_file_service import record_source_hash

    record_source_hash(path)

    logger.info(
        "[matlab_registry] Loaded %d entit%s from %s",
        registered,
        "y" if registered == 1 else "ies",
        path,
    )


def _warn_non_literal(name: str, path: Path, kind: str) -> None:
    logger.warning(
        "[matlab_registry] %s '%s' in entities file %s is not a simple "
        "literal construction (references a MATLAB variable/expression) -- "
        "cannot statically extract its value, so it won't appear as a canvas "
        "node or resolve in generated MATLAB commands.",
        kind,
        name,
        path,
    )
    _record_load_error(
        str(path), f"{kind} '{name}' is not a literal construction"
    )


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
        elif kind == "entities_script":
            # A folder scan can turn up an entities script that isn't the
            # configured entities_file (e.g. a second project's, or one
            # written before the setting existed). Its declarations are
            # still real, so register them — read-only, since only the
            # configured file is GUI-writable.
            load_entities_script(path)
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


def _register_matlab_path_input_object(
    name: str, path: Path, template: str, root_folder: "str | None"
) -> None:
    """Construct a real ``scifor.PathInput`` and register it into the shared
    Python registry. Used by the entities-script loader
    so both produce an identical registration — nothing downstream can tell
    which form declared it."""
    from scifor import PathInput

    from scistack_gui import registry

    _matlab_path_inputs[name] = path
    pi = PathInput(template, root_folder=root_folder)
    registry._register_path_input(name, pi, source=str(path))
    logger.info(
        "[matlab_registry] Registered MATLAB PathInput: %s (%s) "
        "template=%r root_folder=%r",
        name,
        path,
        template,
        root_folder,
    )


def _register_matlab_parameter_object(
    name: str, path: Path, values: list, description: str = ""
) -> None:
    """Construct a real ``scidb.Parameter`` and register it into the shared
    Python registry, so a MATLAB-declared Parameter is indistinguishable
    from a Python-declared one downstream — ``build_parameter_nodes``
    renders it, and it carries source-declared identity rather than being an
    anonymous value in a for_each struct."""
    from scidb import Parameter

    from scistack_gui import registry

    _matlab_parameters[name] = path
    param = Parameter(*values, description=description)
    param.source_file = str(path)
    registry._register_parameter(name, param, source=str(path))
    logger.info(
        "[matlab_registry] Registered MATLAB Parameter: %s (%s) %d value(s)",
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
            "matlab_parameters": [],
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
    """Return sorted list of all registered MATLAB PathInput names."""
    return sorted(_matlab_path_inputs.keys())


def get_all_parameter_names() -> list[str]:
    """Return sorted list of all registered MATLAB Parameter names."""
    return sorted(_matlab_parameters.keys())


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
        or _config.matlab_sources
        or _config.matlab_entities_file
    )
