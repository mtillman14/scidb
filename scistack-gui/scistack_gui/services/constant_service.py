"""
Constant creation service — single source of truth for writing new named
``scidb.constant(...)`` declarations to source.

Mirrors ``path_input_service.create_path_input``'s exact pattern: a
Constant is source-scanned (see docs/claude/code-discovery-categories.md),
so "create from the GUI" means appending a real declaration to the
configured ``variable_file`` and refreshing the registry — never writing a
bare name to layout.json. There is deliberately no "update" counterpart:
editing an existing Constant's value means editing the source file
directly and hitting Refresh Code, same as PathInput/Sweep/Variable — no
source-rewrite machinery exists here.

The GUI's "New constant" form only collects a name (same as
``create_sweep``'s form), so *value* defaults to a scaffolded placeholder
rather than erroring — the user hand-edits the real value/description in
source afterward.
"""

from __future__ import annotations

import logging

from scistack_gui.services.target_file_service import (
    append_and_refresh,
    validate_entity_name,
)

logger = logging.getLogger(__name__)


def create_constant(
    name: str, value: "float | int | str | bool" = 0, description: str = ""
) -> dict:
    """Append ``NAME = scidb.constant(value, description=...)`` to the
    configured ``variable_file`` and refresh the registry.

    Returns ``{"ok": True, "name": name}`` on success, ``{"ok": False,
    "error": ...}`` on failure (invalid name, name collision, no configured
    target file, or a write/refresh failure).
    """
    from scistack_gui import registry

    err = validate_entity_name(name)
    if err:
        return {"ok": False, "error": err}
    if name in registry.get_constants_registry():
        return {"ok": False, "error": f"A Constant named '{name}' already exists."}

    from scistack_gui.services.target_file_service import get_or_create_target_file

    target_file, target_err = get_or_create_target_file()
    if target_file is None:
        return {"ok": False, "error": target_err}

    line = f"\n{name} = scidb.constant({value!r}, description={description!r})\n"

    logger.info(
        "[constant_service] create_constant: name=%r value=%r description=%r",
        name,
        value,
        description,
    )
    err = append_and_refresh(line, target_file)
    if err:
        return err
    return {"ok": True, "name": name}
