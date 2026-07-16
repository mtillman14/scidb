"""The ``@scistack`` marker — the lightweight replacement for ``@lineage_fcn``.

A ``@scistack``-tagged function is just a **plain Python function** tagged so
that:

- :mod:`scidb.discover` can find it (GUI pipeline-node discovery), and
- :func:`scidb.for_each` can read its per-function option
  (``generates_file``).

Unlike the old ``@lineage_fcn``, ``@scistack`` does **not** wrap the function
or change its return value — calling a ``@scistack`` function returns its raw
result. Provenance is captured by ``for_each`` from the inputs it loads (the
bipartite graph), not from a wrapper object. There is no ``LineageFcnResult``.

Usage::

    @scistack
    def bandpass(signal, low_hz):
        return ...

    @scistack(generates_file="{subject}/out.csv")
    def export(data):
        ...
"""

from __future__ import annotations

from typing import Any, Callable

# Attribute names stamped onto a tagged function.
SCISTACK_FLAG = "__scistack__"
GENERATES_FILE_ATTR = "__scistack_generates_file__"


def scistack(
    fn: Callable | None = None,
    *,
    generates_file: Any | None = None,
):
    """Mark a plain function so scistack pays attention to it.

    Works bare (``@scistack``) or called
    (``@scistack(generates_file="{subject}/out.csv")``). Returns the
    function unchanged except for marker attributes, so it stays an
    ordinary callable.
    """

    def deco(f: Callable) -> Callable:
        setattr(f, SCISTACK_FLAG, True)
        if generates_file is not None:
            setattr(f, GENERATES_FILE_ATTR, generates_file)
        return f

    return deco(fn) if callable(fn) else deco


def is_scistack_function(obj: Any) -> bool:
    """True if ``obj`` is a callable tagged by :func:`scistack`."""
    return callable(obj) and bool(getattr(obj, SCISTACK_FLAG, False))
