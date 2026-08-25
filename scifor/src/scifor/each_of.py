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
    """

    def __init__(self, *alternatives):
        if not alternatives:
            raise ValueError("EachOf requires at least one alternative")
        self.alternatives = list(alternatives)

    def __repr__(self) -> str:
        items = ", ".join(getattr(a, "__name__", repr(a)) for a in self.alternatives)
        return f"EachOf({items})"
