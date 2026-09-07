"""
The ``DataSource`` protocol — the one seam that makes this package both
standalone and scistack-compatible.

``scistackplot`` ships CSV and DataFrame implementations; ``scistackplotdb``
ships the scidb one. The GUI talks only to this protocol and never learns which
implementation it has, so the same application serves a lone CSV file and a
full scidb project. Everything above this line is pure long-table logic.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ..table import LongTable


@runtime_checkable
class DataSource(Protocol):
    """Supplies long-format tables and the metadata needed to build controls."""

    def describe(self) -> dict:
        """
        Factors, measures and shapes — everything the GUI needs to render its
        controls before any data is fetched.
        """
        ...

    def get_table(self, measures: list[str]) -> LongTable:
        """The long-format table for one or two measures."""
        ...

    def joinable_with(self, measure: str) -> list[str]:
        """
        Measures that can share a plot with ``measure``.

        Trivially "all the others" for a flat CSV. For scidb it is a real
        question — two variables can only share a plot if their schema levels
        can be joined — and answering it honestly keeps the GUI from offering
        combinations that cannot be built.
        """
        ...


class BaseSource:
    """Small shared implementation for sources backed by a single table."""

    name: str = "table"

    def _table(self) -> LongTable:  # pragma: no cover - overridden
        raise NotImplementedError

    def describe(self) -> dict:
        return self._table().describe()

    def get_table(self, measures: list[str]) -> LongTable:
        table = self._table()
        unknown = [m for m in measures if m not in table.measure_names]
        if unknown:
            raise KeyError(
                f"Unknown measure(s) {unknown}. Available: {table.measure_names}"
            )
        return table

    def joinable_with(self, measure: str) -> list[str]:
        return [m for m in self._table().measure_names if m != measure]

    def default_measure(self) -> str | None:
        measures = self._table().measure_names
        return measures[0] if measures else None

    def metadata(self) -> dict[str, Any]:
        return {"source": type(self).__name__, "name": self.name}
