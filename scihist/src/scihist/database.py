"""Deprecated shim — scihist.configure_database / find_by_lineage moved to scidb.

``find_by_lineage`` is now ``scidb.find_by_lineage``. ``configure_database`` is
preserved here as a thin wrapper that calls ``scidb.configure_database`` and
then registers the database as scilineage's cache backend (the one behavior the
plain ``scidb.configure_database`` does not do), matching historical scihist.
Prefer importing from ``scidb`` directly.
"""

from typing import Any

from scidb import find_by_lineage  # noqa: F401 — re-exported for back-compat


def configure_database(
    db_path: str,
    schema_keys: list[str] | None = None,
    **kwargs,
) -> Any:
    """Deprecated alias for ``scidb.configure_database`` that also registers the
    database as scilineage's lineage cache backend.
    """
    from scidb import configure_database as _scidb_configure
    from scilineage import configure_backend

    db = _scidb_configure(db_path, schema_keys)
    configure_backend(db)
    return db
