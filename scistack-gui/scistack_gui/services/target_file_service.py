"""
Where entity declarations get written, and the guards around writing them.

Two jobs:

1. **Append** (creation) -- the original role: shared "where do new
   PathInput/Sweep/Variable declarations get appended" lookup, used by
   ``services/path_input_service.py`` and ``api/variables.py``. Without the
   auto-create fallback here, every creation failed with a "--module not
   passed" error unless the user had hand-edited ``variable_file`` into
   scistack.toml themselves, with no GUI way to do so -- see
   ``.claude/pathinput-sweep-variable-creation-fixes.md``.

2. **Rewrite** (editing, Stage 5 of
   ``.claude/plan-gui-entity-editing-26-08-24.md``) --
   :func:`update_declaration` replaces an existing declaration's right-hand
   side in place. This module owns the *policy* around that: which file may
   be written, whether it has changed underneath us, atomic replacement,
   re-scan verification, and rollback. The *grammar* -- locating the span
   and rendering the replacement -- belongs to ``scidb.source_edit``
   (Python) and ``scistack_gui.matlab_parser`` (MATLAB).

Writes are confined to the configured entities file (``variable_file`` for
Python, ``[matlab] entities_file`` for MATLAB). A declaration living
anywhere else is read-only by design, and :func:`update_declaration`
refuses it with the exact source location so the UI can point at it. See
``docs/claude/entity-editability-model.md``.
"""

from __future__ import annotations

import hashlib
import keyword
import logging
import os
import re
import tempfile
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


# ---------------------------------------------------------------------------
# Rewriting an existing declaration
# ---------------------------------------------------------------------------

_SOURCE_KIND_REGISTRIES = {
    "parameter": "_parameter_sources",
    "path_input": "_path_input_sources",
}

_source_hashes: dict[str, str] = {}
"""Absolute file path -> sha256 of its contents when the registry last
scanned it. Populated by :func:`record_source_hash`; consumed by
:func:`update_declaration`'s stale-file guard, which refuses to write over
a file that has changed on disk since the values the GUI is showing were
read."""


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def record_source_hash(path: "Path | None") -> None:
    """Remember *path*'s current contents hash, as of a registry scan.

    Called after every scan of an entities file. A file we have no hash for
    is treated as "not verifiable" rather than "unchanged" -- see
    :func:`update_declaration`.
    """
    if path is None:
        return
    try:
        _source_hashes[str(path)] = _hash_text(path.read_text())
    except OSError as e:
        logger.debug("[target_file_service] Cannot hash %s: %s", path, e)


def declaration_source(kind: str, name: str) -> "str | None":
    """The source file the registry recorded for this entity, or ``None``."""
    from scistack_gui import registry

    attr = _SOURCE_KIND_REGISTRIES.get(kind)
    if attr is None:
        return None
    return getattr(registry, attr).get(name)


def _resolves_as_any_kind(name: str) -> bool:
    """Whether *name* is registered as ANY entity kind after a rewrite.

    Deliberately kind-agnostic: an edit may legitimately change an entity's
    kind. Adding a second value to a Constant rewrites it as a ``Sweep``
    (see ``docs/claude/entity-editability-model.md`` D4), so verifying
    against the kind it had *before* the edit would report success as a
    failure and roll a perfectly good write back.
    """
    return any(
        declaration_source(kind, name) is not None for kind in _SOURCE_KIND_REGISTRIES
    )


def _editable_targets() -> "tuple[Path | None, Path | None]":
    """``(python_entities_file, matlab_entities_file)`` -- the only two files
    the GUI may rewrite."""
    from scistack_gui import registry

    config = registry._config
    if config is None:
        return (registry._module_path, None)
    return (config.variable_file, config.matlab_entities_file)


def _location_of(kind: str, name: str, source: str) -> dict:
    """``{file, line}`` for a read-only declaration, so the UI can say
    exactly where to go instead of a generic "edit it in source" hint."""
    from scidb.source_edit import find_binding_span, line_number

    path = Path(source)
    payload = {"file": source, "line": None}
    try:
        text = path.read_text()
    except OSError:
        return payload

    if path.suffix == ".m":
        from scistack_gui.matlab_parser import find_entities_binding

        binding = find_entities_binding(path, name)
        if binding is not None:
            payload["line"] = line_number(text, binding.expr_span.start)
        return payload

    span = find_binding_span(text, name)
    if span is not None:
        payload["line"] = line_number(text, span.start)
    return payload


def update_declaration(
    kind: str, name: str, *, python_expr: str, matlab_expr: str
) -> dict:
    """Replace the right-hand side of an existing declaration in place.

    *python_expr* / *matlab_expr* are the rendered replacements; which one is
    used follows the owning file's language, so callers render both and stay
    language-agnostic.

    Returns ``{"ok": True, "name", "file", "old", "new"}`` on success, or
    ``{"ok": False, "error", ...}``. Failure modes, all non-destructive:

    - the entity is unknown, or lives outside the entities file
      (``"read_only"``, with ``{file, line}``);
    - the file changed on disk since the last scan (``"stale"``);
    - the declaration can no longer be located;
    - the write or the post-write verification failed, in which case the
      original bytes are restored.
    """
    from scidb.source_edit import find_binding_span, splice

    source = declaration_source(kind, name)
    if source is None:
        return {"ok": False, "error": f"No {kind} named '{name}' is registered."}

    path = Path(source)
    py_target, m_target = _editable_targets()
    is_matlab = path.suffix == ".m"
    target = m_target if is_matlab else py_target

    if target is None or Path(target) != path:
        location = _location_of(kind, name, source)
        where = location["file"]
        if location["line"] is not None:
            where = f"{where}:{location['line']}"
        logger.info(
            "[target_file_service] Refusing to edit %s '%s': declared in %s, "
            "outside the configured entities file (%s)",
            kind,
            name,
            source,
            target,
        )
        return {
            "ok": False,
            "error": (
                f"'{name}' is declared in {where} — edit it there and hit "
                f"Refresh Code. The GUI only writes to the entities file."
            ),
            "reason": "read_only",
            **location,
        }

    try:
        original = path.read_text()
    except OSError as e:
        return {"ok": False, "error": f"Cannot read {path}: {e}"}

    known_hash = _source_hashes.get(str(path))
    if known_hash is not None and known_hash != _hash_text(original):
        logger.info(
            "[target_file_service] Refusing to edit %s '%s': %s changed on disk "
            "since the last scan",
            kind,
            name,
            path,
        )
        return {
            "ok": False,
            "error": (
                f"{path.name} has changed on disk since it was last read. "
                f"Hit 🔄 Refresh Code, then try again."
            ),
            "reason": "stale",
        }

    if is_matlab:
        from scistack_gui.matlab_parser import find_entities_binding

        binding = find_entities_binding(path, name)
        span = binding.expr_span if binding is not None else None
        replacement = matlab_expr
    else:
        span = find_binding_span(original, name)
        replacement = python_expr

    if span is None:
        return {
            "ok": False,
            "error": (
                f"Could not locate the declaration of '{name}' in {path.name}. "
                f"It may be nested inside a function or written in a form the "
                f"editor cannot rewrite — edit it directly and hit Refresh Code."
            ),
            "reason": "unlocatable",
        }

    old_expr = span.extract(original)
    if kind == "path_input":
        _record_current_path_input_value(name)
    if old_expr == replacement:
        logger.debug(
            "[target_file_service] %s '%s' already reads %s; nothing to write",
            kind,
            name,
            replacement,
        )
        return {"ok": True, "name": name, "file": str(path), "old": old_expr,
                "new": replacement, "unchanged": True}

    updated = splice(original, span, replacement)

    logger.info(
        "[target_file_service] update_declaration: %s '%s' in %s: %s -> %s",
        kind,
        name,
        path,
        old_expr,
        replacement,
    )

    try:
        _atomic_write(path, updated)
    except OSError as e:
        return {"ok": False, "error": f"Failed to write {path}: {e}"}

    refresh_error = _refresh_registries()
    if refresh_error is None and not _resolves_as_any_kind(name):
        refresh_error = (
            f"'{name}' no longer resolves after the edit — the new value may "
            f"be invalid."
        )

    if refresh_error is not None:
        # Never leave a file the scanner can no longer read: put the original
        # bytes back and re-scan so the registry matches disk again.
        logger.warning(
            "[target_file_service] Rolling back edit to %s: %s", path, refresh_error
        )
        try:
            _atomic_write(path, original)
        except OSError as e:
            return {
                "ok": False,
                "error": (
                    f"{refresh_error} — AND restoring {path} failed: {e}. "
                    f"The file may be left in a bad state."
                ),
            }
        _refresh_registries()
        return {"ok": False, "error": refresh_error, "reason": "verify_failed"}

    record_source_hash(path)
    return {
        "ok": True,
        "name": name,
        "file": str(path),
        "old": old_expr,
        "new": replacement,
    }


def _record_current_path_input_value(name: str) -> None:
    """Remember the template *name* currently holds, immediately before a
    write-back overwrites it (D7).

    This is the ONLY moment history is recorded. Run history attributes a
    PathInput to a canvas node by content-matching its template, so
    overwriting a template would otherwise detach every run recorded against
    the old one. Editing a template *directly in source* still detaches it —
    that is unchanged, pre-existing behaviour for a deliberate hand-edit,
    and not something this table set out to fix.

    Best-effort: no open database (bootstrap, tests) means nothing to
    record, never a failed edit.
    """
    from scistack_gui import pipeline_store, registry

    try:
        from scistack_gui.db import get_db

        db = get_db()
    except Exception as e:
        logger.warning(
            "[target_file_service] No database while recording PathInput "
            "history for '%s' (%s) — a run recorded against its previous "
            "template will not resolve to this node",
            name,
            e,
        )
        return
    if db is None:
        logger.warning(
            "[target_file_service] No open database while recording PathInput "
            "history for '%s' — a run recorded against its previous template "
            "will not resolve to this node",
            name,
        )
        return

    pi = registry.get_path_inputs_registry().get(name)
    if pi is None:
        logger.warning(
            "[target_file_service] '%s' is not in the PathInput registry; "
            "cannot record the template being overwritten",
            name,
        )
        return

    # A PathInput with alternate templates is an EachOf of them; any arm can
    # be what a historical run matched on, so record each.
    arms = [pi] if getattr(pi, "path_template", None) is not None else (
        getattr(pi, "alternatives", None) or []
    )
    for arm in arms:
        template = getattr(arm, "path_template", None)
        if template is None:
            continue
        root = getattr(arm, "root_folder", None)
        try:
            pipeline_store.record_path_input_value(
                db, name, template, str(root) if root is not None else None
            )
        except Exception as e:  # never break an edit over this, but never hide it
            logger.warning(
                "[target_file_service] Could not record PathInput history for "
                "'%s' (template %r): %s",
                name,
                template,
                e,
            )
        else:
            logger.info(
                "[target_file_service] Recorded previous PathInput value: "
                "%s -> template=%r root_folder=%r",
                name,
                template,
                root,
            )


def _atomic_write(path: Path, text: str) -> None:
    """Replace *path*'s contents via a temp file in the same directory, so a
    crash mid-write can never leave a half-written entities file (which the
    scanner would then fail to parse, taking every entity in it down)."""
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    _invalidate_bytecode(path)


def _invalidate_bytecode(path: Path) -> None:
    """Drop any cached bytecode for *path*, so the re-scan actually re-reads
    it.

    ``registry`` loads entities files with ``spec_from_file_location`` +
    ``exec_module``, whose ``SourceFileLoader`` validates cached ``.pyc``
    against the source's **mtime (whole seconds) and size**. An entity edit
    routinely changes neither: ``constant(30)`` -> ``constant(45)`` and
    ``'a.csv'`` -> ``'b.csv'`` are byte-for-byte the same length, and the
    rewrite lands in the same second as the load that preceded it. Python
    then re-executes the STALE bytecode and the GUI keeps showing the old
    value even though the file on disk is correct — with nothing logged
    anywhere, because as far as every layer is concerned the write and the
    refresh both succeeded.
    """
    import importlib.util

    try:
        cached = importlib.util.cache_from_source(str(path))
    except (NotImplementedError, ValueError):
        return
    try:
        os.unlink(cached)
        logger.debug("[target_file_service] Dropped stale bytecode %s", cached)
    except FileNotFoundError:
        pass
    except OSError as e:
        logger.warning(
            "[target_file_service] Could not drop bytecode %s: %s — the next "
            "refresh may show a stale value",
            cached,
            e,
        )
    importlib.invalidate_caches()


def _refresh_registries() -> "str | None":
    """Re-scan after a write. Returns an error string, or ``None``."""
    from scistack_gui import registry

    try:
        if registry._config is not None:
            registry.refresh_all()
        else:
            registry.refresh_module()
    except Exception as e:
        return f"Definition was written but refresh failed: {e}"
    return None
