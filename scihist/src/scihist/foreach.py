"""Deprecated shim — scihist.for_each / save moved into scidb.

The lineage-tracked batch execution that lived here is now part of
``scidb.for_each`` (which tracks lineage by default). This module remains so
existing ``from scihist.foreach import ...`` imports keep working; prefer
importing from ``scidb`` directly.

The one behavioral nuance preserved here is ``skip_computed=True`` as the
default (scidb.for_each defaults it to ``False``), matching the historical
scihist.for_each contract.
"""

from scidb.foreach import for_each as _scidb_for_each
from scidb.lineage_save import save  # noqa: F401 — re-exported for back-compat


def for_each(*args, skip_computed: bool = True, **kwargs):
    """Deprecated alias for ``scidb.for_each`` with ``skip_computed=True``.

    scidb.for_each tracks lineage by default; this wrapper only restores the
    historical scihist default of skipping already-computed combos.
    """
    return _scidb_for_each(*args, skip_computed=skip_computed, **kwargs)
