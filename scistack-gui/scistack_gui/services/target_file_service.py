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

import keyword
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_IMPORT_SCIDB_RE = re.compile(r"^import scidb$", re.MULTILINE)


def validate_entity_name(name: str) -> "str | None":
    """Return an error string if *name* isn't a valid top-level identifier
    for a new PathInput/Sweep/Constant binding, else ``None``. Shared by
    every append-only entity-creation service that writes into the
    configured entities file."""
    name = name.strip()
    if not name or not name.isidentifier() or keyword.iskeyword(name):
        return f"'{name}' is not a valid name."
    if name.startswith("_"):
        return "Names must not start with an underscore."
    return None


def ensure_scidb_import(target_file: Path) -> None:
    """Idempotently make sure *target_file* has a bare ``import scidb`` line.

    Appended entity declarations use the qualified ``scidb.PathInput(...)``/
    ``scidb.Sweep(...)``/``scidb.constant(...)``/``scidb.BaseVariable`` form
    specifically so they never depend on what a pre-existing target file
    happens to already import -- a freshly auto-created file only ever gets
    a docstring header, and a bare-name append (``PathInput(...)`` with no
    import at all) would raise ``NameError`` the next time the file is
    scanned, silently (module-load failures during discovery are logged at
    DEBUG, not raised). Checked with a per-line regex rather than a
    substring check so an unrelated line like ``# see scidb docs`` can't
    produce a false positive.
    """
    text = target_file.read_text() if target_file.exists() else ""
    if _IMPORT_SCIDB_RE.search(text):
        return
    with open(target_file, "a") as f:
        f.write("\nimport scidb\n" if text else "import scidb\n")
    logger.debug("[target_file_service] Added 'import scidb' to %s", target_file)


def append_and_refresh(line: str, target_file: Path) -> "dict | None":
    """Ensure the required import is present, write *line* to *target_file*,
    and refresh the registry. Returns an error dict on failure, or ``None``
    on success. Shared by every append-only entity-creation service."""
    from scistack_gui import registry

    try:
        ensure_scidb_import(target_file)
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
