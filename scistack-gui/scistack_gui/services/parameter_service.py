"""
Parameter creation and editing — the single source of truth for writing
named ``scidb.Parameter(...)`` declarations to source.

A Parameter is a named thing with one or more values, replacing the former
Constant (one) / Sweep (many) split — see
docs/claude/entity-editability-model.md (D6). One service, because there is
one concept: adding a value is adding an argument, never a change of kind.

A Parameter is source-scanned (see
docs/claude/code-discovery-categories.md), so "create from the GUI" means
appending a real declaration to the configured ``variable_file`` and
refreshing the registry — never writing a bare name to layout.json.

The declaration text is rendered by ``scidb.source_edit.render_parameter``
(Python) / ``matlab_parser.render_matlab_parameter`` (MATLAB), which own the
declaration grammar. :func:`update_parameter` rewrites an existing
declaration in place through ``target_file_service.update_declaration``,
which owns the write policy (entities-file confinement, stale-file guard,
atomic write, rollback).
"""

from __future__ import annotations

import logging

from scistack_gui.services.target_file_service import (
    append_and_refresh,
    validate_entity_name,
)

logger = logging.getLogger(__name__)


def create_parameter(
    name: str, values: "list | None" = None, description: str = ""
) -> dict:
    """Append ``NAME = scidb.Parameter(...)`` to the configured
    ``variable_file`` and refresh the registry.

    An empty *values* scaffolds a single placeholder rather than erroring —
    the GUI's "New parameter" form only collects a name, so the user fills
    in the real value(s) afterwards, in the panel or in source. Contrast
    :func:`update_parameter`, where empty is rejected: emptying an
    *existing* Parameter would silently drop every variant it produces.

    Returns ``{"ok": True, "name": name}`` on success, ``{"ok": False,
    "error": ...}`` on failure (invalid name, name collision, no configured
    target file, or a write/refresh failure).
    """
    from scistack_gui import registry

    err = validate_entity_name(name)
    if err:
        return {"ok": False, "error": err}
    if name in registry.get_parameters_registry():
        return {"ok": False, "error": f"A Parameter named '{name}' already exists."}

    values = list(values or [])
    if not values:
        values = [0]
        logger.info(
            "[parameter_service] create_parameter: no values given for %r, "
            "scaffolding a placeholder %r",
            name,
            values,
        )

    from scistack_gui.services.target_file_service import (
        get_or_create_target_file,
        is_toml_target,
        write_entity,
    )

    target_file, target_err = get_or_create_target_file()
    if target_file is None:
        return {"ok": False, "error": target_err}

    logger.info(
        "[parameter_service] create_parameter: name=%r %d value(s) description=%r "
        "target=%s",
        name,
        len(values),
        description,
        target_file,
    )

    if is_toml_target(target_file):
        from scidb.entities import render_parameter_value

        if description:
            # The TOML format has no home for it (plan D4). Say so rather
            # than dropping it silently -- a description that vanishes with
            # no trace is worse than one that never appeared.
            logger.warning(
                "[parameter_service] Dropping description %r for %r: the TOML "
                "entities file has no description field; declare the Parameter "
                "in Python if you need one",
                description,
                name,
            )
        err = write_entity(
            target_file,
            section="parameters",
            name=name,
            rendered=render_parameter_value(values),
        )
    else:
        from scidb.source_edit import render_parameter

        line = f"\n{name} = {render_parameter(values, description)}\n"
        err = append_and_refresh(line, target_file)

    if err:
        return err
    return {"ok": True, "name": name}


def update_parameter(name: str, values: list, description: str = "") -> dict:
    """Rewrite an existing Parameter's declaration in place, in whichever
    language declared it.

    Adding a value is just a longer *values* list — there is no separate
    "convert" operation, because there is no second kind to convert to
    (D6). An empty *values* is rejected.
    """
    if not values:
        return {
            "ok": False,
            "error": (
                f"A Parameter needs at least one value; '{name}' was left "
                f"unchanged."
            ),
        }

    from scidb.entities import render_parameter_value
    from scidb.source_edit import render_parameter

    from scistack_gui.matlab_parser import render_matlab_parameter
    from scistack_gui.services.target_file_service import update_declaration

    return update_declaration(
        "parameter",
        name,
        python_expr=render_parameter(values, description),
        matlab_expr=render_matlab_parameter(values, description),
        toml_expr=render_parameter_value(values),
    )
