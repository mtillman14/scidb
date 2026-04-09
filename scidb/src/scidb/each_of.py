"""EachOf — express multiple alternatives for a for_each() parameter."""


class EachOf:
    """Wrapper expressing multiple alternatives for a for_each() parameter.

    Can wrap:
    - Variable types in inputs: ``EachOf(StepLength, StepTime)``
    - Constants in inputs: ``EachOf(0.05, 0.01)``
    - where= filters: ``EachOf(Side == "L", Side == "R", None)``

    Each alternative becomes a separate variant. The total number of variants
    is the cartesian product of all ``EachOf`` axes in a single ``for_each()``
    call.

    With a single value, behaves identically to passing that value directly.
    """

    def __init__(self, *alternatives):
        if not alternatives:
            raise ValueError("EachOf requires at least one alternative")
        self.alternatives = list(alternatives)

    def __repr__(self) -> str:
        items = ", ".join(
            getattr(a, "__name__", repr(a)) for a in self.alternatives
        )
        return f"EachOf({items})"
