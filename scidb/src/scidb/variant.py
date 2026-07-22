"""Variant branch_param pinning wrapper for variable type inputs in for_each (DB-backed)."""

from typing import Any


def branch_param(fn: str, **params: Any) -> dict:
    """Build a namespaced branch-param selector dict without a dotted-string kwarg.

    branch_params are namespaced per producing function (``f"{fn}.{param}"``). A bare
    name is resolved by suffix-match at load time, but collides when two pipeline
    steps share a param name (raising ``AmbiguousParamError``). The disambiguating
    namespaced form can't be written as a kwarg (a ``.`` is not a valid identifier),
    so this helper builds the dict for you — ``**``-unpack it into the load kwargs
    (non-schema kwargs become the branch-params filter)::

        Filtered.load(subject="S01", **branch_param("bandpass", low_hz=30))

    is equivalent to the awkward ``Filtered.load(subject="S01", **{"bandpass.low_hz": 30})``.
    """
    return {f"{fn}.{k}": v for k, v in params.items()}


class Variant:
    """
    Wrapper to pin an input to a specific branch_param variant.

    branch_param pinning is an **orthogonal, load-time filter**: it selects which
    branch_param variant of a variable to load, distinct from the other input
    wrappers' concerns:

    - ``ColumnSelection`` (``MyVar["col"]``) — which columns (after load)
    - ``Fixed(…, session="BL")`` — which schema metadata (per-combo, scifor loop)
    - ``Merge(…)`` — join several inputs (top level)
    - ``Variant(…, low_hz=20)`` — which branch_param variant (load time)

    Because branch_param pinning is threaded as a separate ``branch_params_filter``
    parameter through the loader (exactly like ``where=``), composition with the
    other wrappers is **order-agnostic**::

        Fixed(Variant(X, low_hz=20), session="BL") == Variant(Fixed(X, session="BL"), low_hz=20)

    ``Variant`` may also be a ``Merge`` constituent for **per-constituent** pinning::

        Merge(Variant(A, low_hz=20), B)

    branch_params are namespaced per producing function (e.g. ``bandpass.low_hz``);
    a bare name (``low_hz``) is matched by suffix at load time. When the bare name
    is ambiguous (two pipeline steps share a param name), disambiguate with the
    ``fn=`` keyword instead of a dotted-string kwarg::

        Variant(X, fn="detect_spikes", threshold=0.5)   # → "detect_spikes.threshold"

    This is exactly equivalent to ``Variant(X, **{"detect_spikes.threshold": 0.5})``
    but avoids the ``.``-in-a-kwarg wart.

    Pinning an input to one variant also fixes aggregation-mode variant smushing:
    variant expansion only sees matching records, so an aggregation no longer pools
    multiple distinct variants into one table.

    Example::

        # Run fn over only the low_hz=20 variant of FilteredEMG
        for_each(fn, {"x": Variant(FilteredEMG, low_hz=20)}, [Out], subject=[1, 2])

        # Run once per pinned variant, results concatenated
        EachOf(Variant(FilteredEMG, low_hz=20), Variant(FilteredEMG, low_hz=50))
    """

    def __init__(self, var_type: Any, *, fn: str | None = None, **branch_params: Any):
        """
        Args:
            var_type: The variable type to load (must have a ``.load()`` method),
                      or a ``ColumnSelection`` / ``Fixed`` wrapper, or a nested
                      ``Variant``.
            fn: Optional producing-function name used to disambiguate the
                      ``branch_params`` below. When given, each branch_param ``k`` is
                      namespaced to ``f"{fn}.{k}"`` (the namespaced form is then
                      matched exactly at load time, never via the ambiguous suffix
                      path). Use this instead of a dotted-string kwarg.
            **branch_params: branch_param key/value pairs to pin. Bare names are
                      suffix-matched against namespaced branch_params at load time
                      (unless ``fn=`` is given, which namespaces them).

        Raises:
            TypeError: If wrapping a ``Merge`` (pin per constituent instead) or an
                ``EachOf`` (EachOf must stay the outermost wrapper).
            ValueError: If no branch_params are given, or a nested ``Variant``
                supplies a conflicting value for the same key.
        """
        from .each_of import EachOf
        from .merge import Merge

        # ``fn=`` namespaces the supplied params under the producing function so the
        # exact-match load path resolves them without the dotted-string kwarg wart.
        if fn is not None:
            branch_params = {f"{fn}.{k}": v for k, v in branch_params.items()}

        if isinstance(var_type, Merge):
            raise TypeError(
                "Variant cannot wrap a Merge. branch_params are namespaced per "
                "producing function, so one branch_param cannot sensibly broadcast "
                "across Merge constituents. Pin per constituent instead: "
                "Merge(Variant(A, low_hz=20), B)."
            )
        if isinstance(var_type, EachOf):
            raise TypeError(
                "Variant cannot wrap an EachOf. EachOf must stay the outermost "
                "wrapper; nest Variant inside each alternative instead: "
                "EachOf(Variant(A, low_hz=20), Variant(A, low_hz=50))."
            )
        if not branch_params:
            raise ValueError(
                "Variant requires at least one branch_param to pin, e.g. "
                "Variant(FilteredEMG, low_hz=20)."
            )

        # Nested Variant: merge the dicts; raise on conflicting key values.
        if isinstance(var_type, Variant):
            merged = dict(var_type.branch_params)
            for k, v in branch_params.items():
                if k in merged and merged[k] != v:
                    raise ValueError(
                        f"Conflicting branch_param '{k}' in nested Variant: "
                        f"{merged[k]!r} vs {v!r}."
                    )
                merged[k] = v
            branch_params = merged
            var_type = var_type.var_type

        self.var_type = var_type
        self.branch_params = branch_params

    def to_key(self) -> str:
        """Return a canonical string for use as a version key."""
        if hasattr(self.var_type, "to_key"):
            inner_key = self.var_type.to_key()
        elif isinstance(self.var_type, type):
            inner_key = self.var_type.__name__
        else:
            inner_key = repr(self.var_type)
        sorted_kv = ", ".join(
            f"{k}={v!r}" for k, v in sorted(self.branch_params.items())
        )
        return f"Variant({inner_key}, {sorted_kv})"

    @property
    def __name__(self) -> str:
        """Display name for format_inputs and error messages."""
        from .foreach import _input_type_name

        inner_name = _input_type_name(self.var_type)
        kv = ", ".join(f"{k}={v}" for k, v in sorted(self.branch_params.items()))
        return f"Variant({inner_name}, {kv})"
