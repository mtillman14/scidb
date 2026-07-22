"""Column selection wrapper for variable types in for_each (DB-backed)."""

from typing import Any


class ColumnSelection:
    """
    Wraps a variable class with column selection for use in for_each() inputs.

    Created automatically by BaseVariable.__class_getitem__ when using bracket
    syntax:

        MyVar["col_name"]           # single column -> numpy array
        MyVar[["col_a", "col_b"]]   # multiple columns -> DataFrame subset

    After loading, only the specified columns are extracted from the loaded
    DataFrame. Single column selection returns a numpy array; multiple columns
    return a DataFrame subset.

    When ``iterate=True`` (constructed via ``MyVar.for_columns(...)``) the
    selection means "run fn once per column and reassemble the per-column
    results into a single wide output variable" rather than "pass the columns
    as one argument." An **empty** ``columns`` (``[]``, the default) means "all
    data columns", resolved at for_each time. ``None`` is accepted as an alias
    for the empty/all sentinel for backward compatibility.

    For standalone DataFrame usage, see scifor.ColumnSelection.
    """

    def __init__(
        self, var_type: type, columns: "list[str] | None" = None, iterate: bool = False
    ):
        """
        Args:
            var_type: The variable class to load.
            columns: List of column names to extract after loading. An empty
                list ``[]`` (the default) means "all data columns", resolved at
                for_each time (only meaningful with ``iterate=True``). ``None``
                is accepted as an alias for ``[]``.
            iterate: If True, iterate over the columns (one fn call each) and
                reassemble into one wide output; if False (default), pass the
                column(s) as a single argument.
        """
        if columns is None:
            columns = []
        self.var_type = var_type
        # Normalize the all-columns sentinel to an empty list (copying any
        # provided list so a shared default object is never mutated).
        self.columns = list(columns) if columns else []
        self.iterate = iterate

    @property
    def __name__(self) -> str:
        """Return a display name for format_inputs and error messages."""
        var_name = getattr(self.var_type, "__name__", type(self.var_type).__name__)
        suffix = ", iterate" if self.iterate else ""
        if not self.columns:
            return f"{var_name}[<all columns>{suffix}]"
        if len(self.columns) == 1 and not self.iterate:
            return f'{var_name}["{self.columns[0]}"]'
        cols = ", ".join(f'"{c}"' for c in self.columns)
        return f"{var_name}[{cols}{suffix}]"

    def load(self, **metadata) -> Any:
        """Load from the underlying var_type, then apply column selection."""
        return self.var_type.load(**metadata)

    def to_csv(self, filename: str, *args, **kwargs) -> None:
        """Export the selected column(s) to a CSV file in flat table format.

        Writes one row per schema_id with the selected columns as value
        columns. The underlying variable must be a single-row table per
        schema_id. ``filename`` must end with ``.csv``. ``kwargs`` mirror
        ``load()`` (``where=``, ``version=``, ``db=``, metadata).

        Example:
            GaitData["Speed"].to_csv("speed.csv", subject=1)
            GaitData[["Speed", "Cadence"]].to_csv("gait.csv", subject=1)
        """
        from scidb.csv_export import export_csv

        export_csv(self, filename, *args, **kwargs)

    # --- Comparison operators that produce ColumnFilter objects ---

    def __eq__(self, other):
        try:
            from scidb.filters import ColumnFilter

            return ColumnFilter(self.var_type, self.columns[0], "==", other)
        except ImportError:
            raise NotImplementedError(
                "Comparison operators on ColumnSelection require scidb."
            )

    def __ne__(self, other):
        try:
            from scidb.filters import ColumnFilter

            return ColumnFilter(self.var_type, self.columns[0], "!=", other)
        except ImportError:
            raise NotImplementedError(
                "Comparison operators on ColumnSelection require scidb."
            )

    def __lt__(self, other):
        try:
            from scidb.filters import ColumnFilter

            return ColumnFilter(self.var_type, self.columns[0], "<", other)
        except ImportError:
            raise NotImplementedError(
                "Comparison operators on ColumnSelection require scidb."
            )

    def __le__(self, other):
        try:
            from scidb.filters import ColumnFilter

            return ColumnFilter(self.var_type, self.columns[0], "<=", other)
        except ImportError:
            raise NotImplementedError(
                "Comparison operators on ColumnSelection require scidb."
            )

    def __gt__(self, other):
        try:
            from scidb.filters import ColumnFilter

            return ColumnFilter(self.var_type, self.columns[0], ">", other)
        except ImportError:
            raise NotImplementedError(
                "Comparison operators on ColumnSelection require scidb."
            )

    def __ge__(self, other):
        try:
            from scidb.filters import ColumnFilter

            return ColumnFilter(self.var_type, self.columns[0], ">=", other)
        except ImportError:
            raise NotImplementedError(
                "Comparison operators on ColumnSelection require scidb."
            )

    def isin(self, values):
        """Create an InFilter for set membership testing."""
        try:
            from scidb.filters import InFilter

            return InFilter(self.var_type, self.columns[0], list(values))
        except ImportError:
            raise NotImplementedError("isin() on ColumnSelection requires scidb.")

    def to_key(self) -> str:
        """Return a canonical string for use as a version key.

        Includes ``iterate`` and the resolved column list so that changing the
        iterated column set (including the empty ``[]`` -> all-columns
        resolution done before this is called) invalidates cached results.
        """
        name = getattr(self.var_type, "__name__", repr(self.var_type))
        return f"{name}[{self.columns!r}, iterate={self.iterate}]"

    def __hash__(self):
        return hash((self.var_type, tuple(self.columns), self.iterate))
