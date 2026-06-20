"""The ``@pipeline`` marker — the lightweight replacement for ``@lineage_fcn``.

A pipeline function is just a **plain Python function** tagged so that:

- :mod:`scidb.discover` can find it (GUI pipeline-node discovery), and
- :func:`scidb.for_each` can read its per-function options (``unpack_output``,
  ``generates_file``).

Unlike the old ``@lineage_fcn``, ``@pipeline`` does **not** wrap the function or
change its return value — calling a ``@pipeline`` function returns its raw result.
Provenance is captured by ``for_each`` from the inputs it loads (the bipartite
graph), not from a wrapper object. There is no ``LineageFcnResult``.

Usage::

    @pipeline
    def bandpass(signal, low_hz):
        return ...

    @pipeline(unpack_output=True)
    def load_csv(filepath):
        return time, force_left, force_right

    @pipeline(generates_file="{subject}/out.csv")
    def export(data):
        ...
"""

from __future__ import annotations

from typing import Any, Callable

# Attribute names stamped onto a tagged function.
PIPELINE_FLAG = "__scidb_pipeline__"
UNPACK_OUTPUT_ATTR = "__scidb_unpack_output__"
GENERATES_FILE_ATTR = "__scidb_generates_file__"


def pipeline(
    fn: Callable | None = None,
    *,
    unpack_output: bool = False,
    generates_file: Any | None = None,
):
    """Mark a plain function as a pipeline step.

    Works bare (``@pipeline``) or called (``@pipeline(unpack_output=True)``).
    Returns the function unchanged except for marker attributes, so it stays an
    ordinary callable.
    """

    def deco(f: Callable) -> Callable:
        setattr(f, PIPELINE_FLAG, True)
        setattr(f, UNPACK_OUTPUT_ATTR, bool(unpack_output))
        if generates_file is not None:
            setattr(f, GENERATES_FILE_ATTR, generates_file)
        return f

    return deco(fn) if callable(fn) else deco


def is_pipeline_function(obj: Any) -> bool:
    """True if ``obj`` is a callable tagged by :func:`pipeline`."""
    return callable(obj) and bool(getattr(obj, PIPELINE_FLAG, False))
