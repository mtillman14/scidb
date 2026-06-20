"""Deprecated shim — ``scihist.configure_database`` moved to scidb.

Prefer importing from ``scidb`` directly. This thin wrapper remains for
backward-compatible imports. (It previously also registered the database as
scilineage's cache backend; the rerun cache was removed, so it now simply
delegates to ``scidb.configure_database``.)
"""

from typing import Any


def configure_database(
    db_path: str,
    schema_keys: list[str] | None = None,
    **kwargs,
) -> Any:
    """Deprecated alias for ``scidb.configure_database``."""
    from scidb import configure_database as _scidb_configure

    return _scidb_configure(db_path, schema_keys)
