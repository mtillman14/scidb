"""
Constant — a lightweight wrapper for pipeline configuration values.

Scientific pipelines accumulate magic numbers: sampling rates, bandpass limits,
epoch durations, regularization weights, etc. Wrapping them in ``constant(...)``
gives each value a description and a source location so the GUI sidebar can
surface them, while still letting the value behave transparently like its
underlying type.

Example:
    from scidb import constant

    SAMPLING_RATE_HZ = constant(
        1000,
        description="Default sampling rate for all recordings",
    )

    DEFAULT_BANDPASS = constant(
        (1.0, 40.0),
        description="Standard LFP bandpass (Hz)",
    )

    # Transparent use:
    duration = 5 * SAMPLING_RATE_HZ          # 5000
    low = DEFAULT_BANDPASS[0]                 # 1.0

    # Discovery-side detection:
    isinstance(SAMPLING_RATE_HZ, Constant)    # True
    SAMPLING_RATE_HZ.description              # "Default sampling rate ..."
    SAMPLING_RATE_HZ.source_file              # "/path/to/module.py"
"""

from __future__ import annotations

import inspect
from typing import Any


class Constant:
    """
    Transparent wrapper around a pipeline configuration value.

    ``Constant`` instances forward arithmetic, comparison, container, and
    attribute access to the underlying value so they can be used in place of
    the raw value at call sites. The wrapper additionally carries a human
    description and the source file/line where it was constructed, which the
    scidb discovery scanner uses to populate the GUI sidebar.

    Prefer the :func:`constant` factory over instantiating this class directly
    — the factory captures the caller's source location automatically.
    """

    __slots__ = ("_value", "description", "source_file", "source_line")

    def __init__(
        self,
        value: Any,
        description: str = "",
        source_file: str = "",
        source_line: int = 0,
    ) -> None:
        # Bypass __setattr__ on __slots__ via object.__setattr__ to make the
        # wrapper feel as immutable as possible from the outside.
        object.__setattr__(self, "_value", value)
        object.__setattr__(self, "description", description)
        object.__setattr__(self, "source_file", source_file)
        object.__setattr__(self, "source_line", source_line)

    # ------------------------------------------------------------------
    # Introspection / debugging
    # ------------------------------------------------------------------
    @property
    def value(self) -> Any:
        """Return the wrapped underlying value."""
        return self._value

    def __repr__(self) -> str:
        return (
            f"Constant({self._value!r}, description={self.description!r})"
        )

    # ------------------------------------------------------------------
    # Attribute passthrough
    # ------------------------------------------------------------------
    def __getattr__(self, name: str) -> Any:
        # __getattr__ is only called when normal lookup fails, so our own
        # slots (description, source_file, ...) take precedence.
        return getattr(self._value, name)

    # ------------------------------------------------------------------
    # Conversions
    # ------------------------------------------------------------------
    def __bool__(self) -> bool:
        return bool(self._value)

    def __int__(self) -> int:
        return int(self._value)

    def __float__(self) -> float:
        return float(self._value)

    def __complex__(self) -> complex:
        return complex(self._value)

    def __str__(self) -> str:
        return str(self._value)

    def __format__(self, format_spec: str) -> str:
        return format(self._value, format_spec)

    def __bytes__(self) -> bytes:
        return bytes(self._value)

    def __index__(self) -> int:
        # Needed for things like ``range(SAMPLING_RATE_HZ)`` and slicing.
        return self._value.__index__()

    def __hash__(self) -> int:
        return hash(self._value)

    # ------------------------------------------------------------------
    # Comparison
    # ------------------------------------------------------------------
    @staticmethod
    def _unwrap(other: Any) -> Any:
        return other._value if isinstance(other, Constant) else other

    def __eq__(self, other: Any) -> bool:
        return self._value == self._unwrap(other)

    def __ne__(self, other: Any) -> bool:
        return self._value != self._unwrap(other)

    def __lt__(self, other: Any) -> bool:
        return self._value < self._unwrap(other)

    def __le__(self, other: Any) -> bool:
        return self._value <= self._unwrap(other)

    def __gt__(self, other: Any) -> bool:
        return self._value > self._unwrap(other)

    def __ge__(self, other: Any) -> bool:
        return self._value >= self._unwrap(other)

    # ------------------------------------------------------------------
    # Arithmetic (left-hand)
    # ------------------------------------------------------------------
    def __add__(self, other: Any) -> Any:
        return self._value + self._unwrap(other)

    def __sub__(self, other: Any) -> Any:
        return self._value - self._unwrap(other)

    def __mul__(self, other: Any) -> Any:
        return self._value * self._unwrap(other)

    def __truediv__(self, other: Any) -> Any:
        return self._value / self._unwrap(other)

    def __floordiv__(self, other: Any) -> Any:
        return self._value // self._unwrap(other)

    def __mod__(self, other: Any) -> Any:
        return self._value % self._unwrap(other)

    def __pow__(self, other: Any, mod: Any = None) -> Any:
        if mod is None:
            return self._value ** self._unwrap(other)
        return pow(self._value, self._unwrap(other), mod)

    def __matmul__(self, other: Any) -> Any:
        return self._value @ self._unwrap(other)

    def __lshift__(self, other: Any) -> Any:
        return self._value << self._unwrap(other)

    def __rshift__(self, other: Any) -> Any:
        return self._value >> self._unwrap(other)

    def __and__(self, other: Any) -> Any:
        return self._value & self._unwrap(other)

    def __xor__(self, other: Any) -> Any:
        return self._value ^ self._unwrap(other)

    def __or__(self, other: Any) -> Any:
        return self._value | self._unwrap(other)

    # ------------------------------------------------------------------
    # Arithmetic (right-hand)
    # ------------------------------------------------------------------
    def __radd__(self, other: Any) -> Any:
        return self._unwrap(other) + self._value

    def __rsub__(self, other: Any) -> Any:
        return self._unwrap(other) - self._value

    def __rmul__(self, other: Any) -> Any:
        return self._unwrap(other) * self._value

    def __rtruediv__(self, other: Any) -> Any:
        return self._unwrap(other) / self._value

    def __rfloordiv__(self, other: Any) -> Any:
        return self._unwrap(other) // self._value

    def __rmod__(self, other: Any) -> Any:
        return self._unwrap(other) % self._value

    def __rpow__(self, other: Any) -> Any:
        return self._unwrap(other) ** self._value

    def __rmatmul__(self, other: Any) -> Any:
        return self._unwrap(other) @ self._value

    def __rlshift__(self, other: Any) -> Any:
        return self._unwrap(other) << self._value

    def __rrshift__(self, other: Any) -> Any:
        return self._unwrap(other) >> self._value

    def __rand__(self, other: Any) -> Any:
        return self._unwrap(other) & self._value

    def __rxor__(self, other: Any) -> Any:
        return self._unwrap(other) ^ self._value

    def __ror__(self, other: Any) -> Any:
        return self._unwrap(other) | self._value

    # ------------------------------------------------------------------
    # Unary
    # ------------------------------------------------------------------
    def __neg__(self) -> Any:
        return -self._value

    def __pos__(self) -> Any:
        return +self._value

    def __abs__(self) -> Any:
        return abs(self._value)

    def __invert__(self) -> Any:
        return ~self._value

    def __round__(self, ndigits: int | None = None) -> Any:
        if ndigits is None:
            return round(self._value)
        return round(self._value, ndigits)

    # ------------------------------------------------------------------
    # Container / iteration
    # ------------------------------------------------------------------
    def __len__(self) -> int:
        return len(self._value)

    def __iter__(self):
        return iter(self._value)

    def __contains__(self, item: Any) -> bool:
        return self._unwrap(item) in self._value

    def __getitem__(self, key: Any) -> Any:
        return self._value[self._unwrap(key)]

    def __reversed__(self):
        return reversed(self._value)


def constant(value: Any, description: str = "") -> Constant:
    """
    Wrap ``value`` in a :class:`Constant`, capturing the caller's source
    location so the GUI sidebar can link back to the definition.

    Args:
        value: The underlying value (scalar, tuple, list, dict, etc.).
        description: Human-readable description of what the constant is for.

    Returns:
        A :class:`Constant` instance that behaves transparently as ``value``
        for arithmetic, comparison, container, and attribute access.
    """
    # inspect.stack()[0] is this frame; [1] is the caller.
    caller = inspect.stack()[1]
    try:
        source_file = caller.filename
        source_line = caller.lineno
    finally:
        # Break the frame reference cycle that ``inspect.stack`` creates.
        del caller
    return Constant(
        value,
        description=description,
        source_file=source_file,
        source_line=source_line,
    )
