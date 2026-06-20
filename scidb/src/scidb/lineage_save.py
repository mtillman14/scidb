"""The public ``scidb.save()`` entry point.

``scidb.save(VariableClass, data, **metadata)`` saves raw data to the database.

It previously also handled ``scilineage.LineageFcnResult`` for the manual
compute-and-save pattern (``r = fn(x); save(Out, r)``). That path was removed
with the ``@lineage_fcn`` → ``@pipeline`` migration: provenance is now captured
by ``for_each`` directly into the bipartite graph, so there is no result wrapper
to unpack here.
"""

import logging

logger = logging.getLogger(__name__)


def save(variable_class, data, db=None, **metadata) -> str | None:
    """Save raw ``data`` as ``variable_class`` (thin wrapper over
    ``variable_class.save``, kept as the public ``scidb.save`` entry point)."""
    db_kwargs = {"db": db} if db is not None else {}
    rid = variable_class.save(data, **db_kwargs, **metadata)
    var_name = (
        variable_class.__name__ if isinstance(variable_class, type)
        else type(variable_class).__name__
    )
    logger.debug("save(): variable=%s, record_id=%s",
                 var_name, rid[:12] if rid else None)
    return rid
