"""
Shared "where do new PathInput/Sweep/Variable declarations get appended"
lookup, used by both ``services/path_input_service.py`` and
``api/variables.py``.

Without the auto-create fallback here, every PathInput/Sweep/Variable
"create" from the GUI failed with a "--module not passed" error unless the
user had hand-edited ``variable_file`` into scistack.toml themselves, with
no GUI way to do so -- see
``.claude/pathinput-sweep-variable-creation-fixes.md``.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def get_or_create_target_file() -> "tuple[Path | None, str | None]":
    """Return ``(target_file, error)`` -- exactly one is non-``None``.

    Resolution order:
      1. Legacy single-file mode (``--module``) or an already-configured
         project-mode ``variable_file`` -- both already worked before this
         module existed.
      2. Project-mode config with no ``variable_file`` set: auto-create a
         default file for loose-script projects and persist it into
         scistack.toml. Packaged (``pyproject.toml``) projects get a clear
         hand-edit error instead -- the Paths popup never auto-writes to
         pyproject.toml (see ``config._reject_packaged_project``).
      3. No config and no module loaded at all: the original error.
    """
    from scistack_gui import registry

    if registry._config is not None and registry._config.variable_file is not None:
        return registry._config.variable_file, None
    if registry._module_path is not None:
        return registry._module_path, None

    if registry._config is not None:
        from scistack_gui import config as config_mod
        from scistack_gui.db import get_db_path
        from scistack_gui.services.registry_reload_service import (
            reload_registries_from_disk,
        )

        db_path = get_db_path()
        logger.info(
            "[target_file_service] No variable_file configured; attempting "
            "auto-create for project at %s",
            db_path,
        )
        try:
            config_mod.set_variable_file(db_path, None)
        except ValueError as e:
            logger.info("[target_file_service] Auto-create refused: %s", e)
            return None, (
                "No variable_file configured for this packaged project. Add "
                'variable_file = "path/to/file.py" under [tool.scistack] in '
                "pyproject.toml, then hit Refresh."
            )

        new_config = reload_registries_from_disk(db_path)
        logger.info(
            "[target_file_service] Auto-created variable_file=%s",
            new_config.variable_file,
        )
        return new_config.variable_file, None

    return None, "No module file was loaded at startup (--module not passed)."
