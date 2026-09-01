"""
Variable service — single source of truth for variable creation.

Used by both server.py's JSON-RPC handler (VS Code extension) and
api/variables.py's FastAPI route, so validation/target-file/MATLAB-fallback
behavior can't drift between the two transports.
"""

from __future__ import annotations

import keyword
import logging

logger = logging.getLogger(__name__)


def create_variable(
    name: str, docstring: str | None = None, language: str = "python"
) -> dict:
    """Validate, write a new BaseVariable subclass, and refresh the registry.

    Works for both Python and MATLAB variables.

    Returns:
        {"ok": True, "name": name} on success,
        {"ok": False, "error": message} on failure.
    """
    from scidb import BaseVariable
    from scistack_gui import matlab_registry, registry

    name = name.strip()
    logger.debug("create_variable: name=%r, language=%r", name, language)

    # --- Validation ---
    if not name or not name.isidentifier() or keyword.iskeyword(name):
        return {"ok": False, "error": f"'{name}' is not a valid class name."}
    if name.startswith("_"):
        return {
            "ok": False,
            "error": "Variable names must not start with an underscore.",
        }
    if name in BaseVariable._all_subclasses:
        return {"ok": False, "error": f"A variable named '{name}' already exists."}

    # MATLAB variable creation. When the project has a TOML entities file,
    # the declaration goes THERE and the classdef is materialized from it --
    # one declaration, in the language-neutral file, plus the stub MATLAB
    # needs to reference the type. Without one (a MATLAB-only project that
    # never configured an entities file), the classdef is still the
    # declaration, as before.
    if language == "matlab":
        return _create_matlab_variable(name, docstring)

    # Python variable creation.
    from scistack_gui.services.target_file_service import (
        ensure_scidb_import,
        get_or_create_target_file,
        is_toml_target,
        write_variable,
    )

    target_file, target_err = get_or_create_target_file()

    if target_file is None:
        # No Python target — fall back to MATLAB if configured.
        if matlab_registry.has_matlab_config() and matlab_registry._config is not None:
            # No longer requires a configured variable_dir: the classdef
            # destination falls back to scimatlab.stubs.variable_stub_dir.
            return _create_matlab_variable(name, docstring)
        return {"ok": False, "error": target_err}

    if is_toml_target(target_file):
        if docstring:
            # A value-less list has nowhere to put one (plan D4). Logged
            # rather than dropped silently.
            logger.warning(
                "[variable_service] Dropping docstring %r for %r: the TOML "
                "entities file declares variables as bare names; declare the "
                "class in Python if you need a docstring",
                docstring,
                name,
            )
        logger.info(
            "[variable_service] create_variable: name=%r target=%s", name, target_file
        )
        err = write_variable(target_file, name)
        if err:
            return err
        return {"ok": True, "name": name}

    lines = ["\n"]
    if docstring:
        escaped = docstring.replace('"""', '\\"\\"\\"')
        lines.append(
            f'class {name}(scidb.BaseVariable):\n    """{escaped}"""\n    pass\n'
        )
    else:
        lines.append(f"class {name}(scidb.BaseVariable):\n    pass\n")

    try:
        ensure_scidb_import(target_file)
        with open(target_file, "a") as f:
            f.writelines(lines)
    except OSError as e:
        return {"ok": False, "error": f"Failed to write to module file: {e}"}

    try:
        if registry._config is not None:
            registry.refresh_all()
        else:
            registry.refresh_module()
    except Exception as e:
        return {"ok": False, "error": f"Class was written but refresh failed: {e}"}

    return {"ok": True, "name": name}


def _create_matlab_variable(name: str, docstring: str | None = None) -> dict:
    """Create a MATLAB classdef variable file and register the surrogate.

    With a TOML entities file configured, the *declaration* is written there
    first and the classdef becomes a materialized stub of it -- so the same
    variable is visible to Python without being declared twice. The classdef
    is still written here rather than left to the next scan, because the
    user expects the file to exist the moment they hit create.
    """
    from scistack_gui import matlab_registry
    from scistack_gui.services.target_file_service import (
        get_or_create_target_file,
        is_toml_target,
        write_variable,
    )

    if matlab_registry._config is None:
        return {
            "ok": False,
            "error": "No MATLAB configuration loaded for this project.",
        }

    entities_file, _ = get_or_create_target_file()
    if is_toml_target(entities_file):
        err = write_variable(entities_file, name)
        if err:
            return err
        logger.info(
            "[variable_service] Declared MATLAB variable %r in the entities "
            "file; materializing its classdef",
            name,
        )

    # An explicit [matlab] variable_dir wins; otherwise the classdef goes
    # where scimatlab materializes stubs, which is the directory
    # +scidb/entities.m adds to the MATLAB path at run time. Falling back
    # rather than refusing is the point: a project can declare its
    # variables in the entities file and never configure a variable_dir.
    target_dir = matlab_registry._config.matlab_variable_dir
    if target_dir is None:
        from scimatlab.stubs import variable_stub_dir

        target_dir = variable_stub_dir(matlab_registry._config.project_root)
    if target_dir is None:
        return {
            "ok": False,
            "error": (
                "Nowhere to write the classdef: configure "
                "[tool.scistack.matlab] variable_dir, or an entities_file "
                "for its default location."
            ),
        }
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / f"{name}.m"

    if target_file.exists():
        return {"ok": False, "error": f"File already exists: {target_file}"}

    m_lines = [f"classdef {name} < scidb.BaseVariable"]
    if docstring:
        m_lines.append(f"    % {docstring}")
    m_lines.append("end")
    m_lines.append("")

    try:
        target_file.write_text("\n".join(m_lines), encoding="utf-8")
    except OSError as e:
        return {"ok": False, "error": f"Failed to write .m file: {e}"}

    try:
        from scimatlab.bridge import register_matlab_variable

        register_matlab_variable(name)
        matlab_registry.refresh_all()
    except Exception as e:
        return {"ok": False, "error": f"File written but registration failed: {e}"}

    return {"ok": True, "name": name}


def get_variable_records(variable_name: str, db) -> dict:
    """Return records and variant summary for a variable type.

    Delegates to the query logic in api/variables.py.
    """
    from scistack_gui.api.variables import get_variable_records as _get_var_records

    return _get_var_records(variable_name, db)


def get_variable_plot_data(variable_name: str, db) -> dict:
    """Raw points for the sidebar's default plot (to-do #4).

    Delegates to the query logic in api/variables.py.
    """
    from scistack_gui.api.variables import get_variable_plot_data as _get_plot_data

    return _get_plot_data(variable_name, db)
