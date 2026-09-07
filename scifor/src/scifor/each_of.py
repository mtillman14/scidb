"""EachOf — express multiple alternatives for a for_each() parameter."""


class EachOf:
    """Wrapper expressing multiple alternatives for a for_each() parameter.

    Can wrap:
    - Data inputs (DataFrames, Fixed, Merge, ColumnSelection, PathInput): ``EachOf(df_a, df_b)``
    - Constants in inputs: ``EachOf(0.05, 0.01)``
    - where= filters: ``EachOf(Col("side") == "L", Col("side") == "R", None)``

    Each alternative expands into a separate, independent for_each() call. The
    total number of calls is the cartesian product of all ``EachOf`` axes in a
    single for_each() call; results are concatenated.

    With a single value, behaves identically to passing that value directly.

    **An EachOf may be constructed with no alternatives at all.** That is a
    placeholder, not a runnable axis -- it is what a ``scidb.Parameter``
    declared but not yet given a value looks like from here (a ``Parameter``
    IS an ``EachOf``). Refusing it belongs at EXPANSION, not construction, and
    :func:`require_alternatives` is where that happens: the cartesian product
    over a zero-length axis is empty, so ``for_each`` would iterate zero
    times, write no records, and return normally as though it had succeeded.
    Constructing an empty one is harmless; expanding one is the bug, and the
    error can name the input it came from.

    ``+scifor/EachOf.m`` mirrors this, and has to: a MATLAB superclass
    constructor call may not sit in a conditional branch, so
    ``+scidb/Parameter.m`` has exactly one ``obj@scifor.EachOf(args{:})`` call
    and ``args`` is empty for a value-less Parameter.
    """

    def __init__(self, *alternatives):
        self.alternatives = list(alternatives)

    def __repr__(self) -> str:
        items = ", ".join(getattr(a, "__name__", repr(a)) for a in self.alternatives)
        return f"EachOf({items})"


def require_alternatives(each_of, *, kind: str, param: "str | None" = None) -> None:
    """Raise ``ValueError`` if *each_of* has nothing to expand.

    Called by every ``for_each`` EachOf-expansion site -- ``scifor.for_each``,
    ``scidb.for_each`` and the two MATLAB mirrors -- as each axis is
    collected, before the cartesian product is built. One implementation
    rather than four copies of the same condition
    (``feedback_avoid_scifor_scidb_duplication``).

    The message uses ``type(each_of).__name__``, so a value-less
    ``scidb.Parameter`` reports itself as a Parameter without this layer
    having to know that class exists.
    """
    if each_of.alternatives:
        return
    target = f"input '{param}'" if kind == "input" else "where="
    raise ValueError(
        f"{type(each_of).__name__} bound to {target} has no alternatives, so "
        f"there is nothing to run. An empty axis would iterate zero times and "
        f"write no records while appearing to succeed -- give it at least one "
        f"value, or unbind it."
    )
