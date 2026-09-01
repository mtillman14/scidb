"""Materializing MATLAB ``classdef`` files for TOML-declared variables.

A Variable is a *type*, and MATLAB requires one public classdef per file
named after the file -- so unlike a Parameter or a PathInput, a variable
declared in the entities file cannot simply be handed over the bridge as a
value. It needs a real file on the MATLAB path before ``RawEMG()`` resolves.

This lives in ``scimatlab`` because "make a declared entity referenceable
from MATLAB" is a MATLAB-wrapper concern (CLAUDE.md NOTE 3). It used to
live in ``scistack_gui.matlab_registry``, which meant a hand-written MATLAB
script got no such guarantee and a project that never configured
``[matlab] variable_dir`` got no classdef at all -- the run failed mid-way
with ``Unrecognized function or variable 'RawEMG'`` and nothing anywhere
had said why (see ``.claude/plan-matlab-variable-classdef-materialization.md``).

**Which names need writing is not decided here.** ``+scidb/entities.m``
asks MATLAB itself (``exist(name, 'class')``) and passes only the names
that failed. MATLAB's path is the only authority on whether a class
resolves; deciding from Python by looking for a file in the stub directory
would write a second ``RawEMG.m`` shadowing a hand-written classdef that
lives elsewhere on the path. The GUI applies the same rule with the
registry's parsed classdefs (``matlab_registry.materialize_variable_stubs``).

Only ever creates. A stub whose TOML declaration later disappears is left
alone -- deleting generated-but-referenced files is how a pipeline stops
running mid-session, and the project's ethos is to hide, never delete.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_STUB_DIRNAME = "scistack_variables"
"""Where stubs go when ``[matlab] variable_dir`` is not configured: a
directory beside the entities file, named so it reads as generated output
rather than a place to hand-author code."""


def variable_stub_dir(project_start: "Path | str | None" = None) -> "Path | None":
    """The directory MATLAB classdef stubs are written to, or ``None``.

    Resolution order:

    1. ``[tool.scistack.matlab] variable_dir``, relative to the config file's
       directory -- an explicitly configured home always wins.
    2. ``<entities_file.parent>/scistack_variables``.

    ``None`` when the project declares no entities file at all: there is
    then nothing to materialize *from*, and inventing a directory would
    create one in a project that never asked for it.

    The default deliberately does **not** become
    ``SciStackConfig.matlab_variable_dir``: that field feeds
    ``SciStackConfig.has_matlab``, so defaulting it would make every
    Python-only project with an entities file load the MATLAB registry.
    """
    from scidb.entities import entities_path
    from scifor.discovery import find_project_config, read_scistack_section

    start = Path(project_start) if project_start is not None else Path.cwd()

    config = find_project_config(start)
    if config is not None:
        section = read_scistack_section(config) or {}
        matlab_section = section.get("matlab")
        if not isinstance(matlab_section, dict):
            matlab_section = {}
        raw = matlab_section.get("variable_dir")
        if isinstance(raw, str) and raw:
            return Path(os.path.normpath(os.path.abspath(str(config.parent / raw))))

    entities = entities_path(start)
    if entities is None:
        return None
    return entities.parent / DEFAULT_STUB_DIRNAME


def classdef_text(name: str) -> str:
    """The stub source. One place, so the GUI's copy and MATLAB's
    self-healing copy can never drift into writing different files."""
    return (
        f"classdef {name} < scidb.BaseVariable\n"
        f"    % Declared in the SciStack entities file; this stub exists\n"
        f"    % because MATLAB requires one classdef file per type.\n"
        f"end\n"
    )


def write_variable_classdefs(
    names, target_dir: "Path | str | None" = None, project_start=None
) -> dict:
    """Write a classdef stub for each name in *names* that has no file yet.

    *target_dir* defaults to :func:`variable_stub_dir` for *project_start*.
    The directory is created only when there is something to write, so a
    project with no missing classdefs never grows an empty folder.

    Returns ``{"dir", "created", "skipped", "errors"}`` -- plain strings and
    lists, because MATLAB reads this over the bridge. ``dir`` is ``""`` when
    no directory could be resolved.
    """
    from scidb.log import Log

    wanted = [str(n) for n in names if str(n)]
    if not wanted:
        return {"dir": "", "created": [], "skipped": [], "errors": []}

    resolved = (
        Path(target_dir) if target_dir is not None else variable_stub_dir(project_start)
    )
    if resolved is None:
        message = (
            "no entities file and no [matlab] variable_dir for this project, so "
            f"there is nowhere to write classdefs for: {', '.join(sorted(wanted))}"
        )
        Log.warn("[stubs] %s", message, layer="matlab")
        return {"dir": "", "created": [], "skipped": [], "errors": [message]}

    created: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []
    for name in wanted:
        target = resolved / f"{name}.m"
        if target.exists():
            Log.debug(
                "[stubs] classdef for '%s' already exists at %s",
                name,
                target,
                layer="matlab",
            )
            skipped.append(name)
            continue
        try:
            resolved.mkdir(parents=True, exist_ok=True)
            target.write_text(classdef_text(name), encoding="utf-8")
        except OSError as e:
            message = f"could not write classdef for '{name}' at {target}: {e}"
            Log.warn("[stubs] %s", message, layer="matlab")
            errors.append(message)
            continue
        Log.info(
            "[stubs] Materialized classdef for declared variable '%s' at %s",
            name,
            target,
            layer="matlab",
        )
        created.append(name)

    return {
        "dir": str(resolved),
        "created": created,
        "skipped": skipped,
        "errors": errors,
    }
