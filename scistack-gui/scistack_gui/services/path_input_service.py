"""
PathInput/Sweep creation service — single source of truth for writing new
named ``scidb.PathInput``/``scidb.Sweep`` declarations to source.

Mirrors ``variable_service.create_variable``'s exact pattern: PathInput/
Sweep are source-scanned (see docs/claude/code-discovery-categories.md), so
"create from the GUI" means appending a real declaration to the configured
``variable_file`` and refreshing the registry — never writing to
layout.json. There is deliberately no "update" counterpart: editing an
existing PathInput/Sweep's value means editing the source file directly and
hitting Refresh Code, same as editing a function body today — no
source-rewrite machinery exists here (mirrors ``create_variable``, which is
also append-only).

This is also what ``portability_service.import_pipeline_document`` calls to
materialize a bundled PathInput/Sweep the importer doesn't already have
locally (see docs/claude/code-discovery-categories.md's portability
section) — one code path serves both callers.
"""

from __future__ import annotations

import keyword
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _validate_name(name: str) -> "str | None":
    """Return an error string if *name* isn't a valid top-level identifier
    for a new PathInput/Sweep binding, else ``None``."""
    name = name.strip()
    if not name or not name.isidentifier() or keyword.iskeyword(name):
        return f"'{name}' is not a valid name."
    if name.startswith("_"):
        return "Names must not start with an underscore."
    return None


def _append_and_refresh(line: str, target_file: Path) -> "dict | None":
    """Write *line* to *target_file* and refresh the registry. Returns an
    error dict on failure, or ``None`` on success."""
    from scistack_gui import registry

    try:
        with open(target_file, "a") as f:
            f.write(line)
    except OSError as e:
        return {"ok": False, "error": f"Failed to write to module file: {e}"}

    try:
        if registry._config is not None:
            registry.refresh_all()
        else:
            registry.refresh_module()
    except Exception as e:
        return {
            "ok": False,
            "error": f"Definition was written but refresh failed: {e}",
        }
    return None


def _path_input_call(template: str, root_folder: "str | None") -> str:
    args = [repr(template)]
    if root_folder:
        args.append(f"root_folder={root_folder!r}")
    return f"PathInput({', '.join(args)})"


def create_path_input(
    name: str,
    template: str,
    root_folder: "str | None" = None,
    alternate_templates: "list[dict] | None" = None,
) -> dict:
    """Append ``NAME = PathInput(...)`` (or, with ``alternate_templates``,
    ``NAME = EachOf(PathInput(...), PathInput(...), ...)``) to the
    configured ``variable_file`` and refresh the registry.

    ``alternate_templates`` is only ever populated by
    ``portability_service.import_pipeline_document`` materializing a
    bundled multi-template PathInput — the GUI's own create action never
    passes it (alternates are a source-code-only concept now, see
    docs/claude/code-discovery-categories.md).

    Returns ``{"ok": True, "name": name}`` on success, ``{"ok": False,
    "error": ...}`` on failure (invalid name, name collision, no configured
    target file, or a write/refresh failure).
    """
    from scistack_gui import registry

    err = _validate_name(name)
    if err:
        return {"ok": False, "error": err}
    if name in registry.get_path_inputs_registry():
        return {"ok": False, "error": f"A PathInput named '{name}' already exists."}

    from scistack_gui.services.target_file_service import get_or_create_target_file

    target_file, target_err = get_or_create_target_file()
    if target_file is None:
        return {"ok": False, "error": target_err}

    calls = [_path_input_call(template, root_folder)]
    calls.extend(
        _path_input_call(alt.get("template", ""), alt.get("root_folder"))
        for alt in (alternate_templates or [])
    )
    expr = calls[0] if len(calls) == 1 else f"EachOf({', '.join(calls)})"
    line = f"\n{name} = {expr}\n"

    logger.info(
        "[path_input_service] create_path_input: name=%r template=%r root_folder=%r "
        "%d alternate(s)",
        name,
        template,
        root_folder,
        len(calls) - 1,
    )
    err = _append_and_refresh(line, target_file)
    if err:
        return err
    return {"ok": True, "name": name}


def create_sweep(name: str, values: "list[float | int | str]") -> dict:
    """Append ``NAME = Sweep(...)`` to the configured ``variable_file`` and
    refresh the registry. If *values* is empty (the GUI's "New parameter
    sweep" form only collects a name today), scaffolds a single placeholder
    value instead of erroring -- same "create an editable stub, then
    hand-edit source and hit Refresh" pattern ``create_path_input`` already
    uses for an empty template.

    Returns ``{"ok": True, "name": name}`` on success, ``{"ok": False,
    "error": ...}`` on failure.
    """
    from scistack_gui import registry

    err = _validate_name(name)
    if err:
        return {"ok": False, "error": err}
    if name in registry.get_sweeps_registry():
        return {"ok": False, "error": f"A Sweep named '{name}' already exists."}
    if not values:
        values = [0]
        logger.info(
            "[path_input_service] create_sweep: no values given for %r, "
            "scaffolding a placeholder %r", name, values,
        )

    from scistack_gui.services.target_file_service import get_or_create_target_file

    target_file, target_err = get_or_create_target_file()
    if target_file is None:
        return {"ok": False, "error": target_err}

    args = ", ".join(repr(v) for v in values)
    line = f"\n{name} = Sweep({args})\n"

    logger.info(
        "[path_input_service] create_sweep: name=%r %d value(s)", name, len(values)
    )
    err = _append_and_refresh(line, target_file)
    if err:
        return err
    return {"ok": True, "name": name}
