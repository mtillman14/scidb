"""Column selection wrapper for DataFrame inputs in for_each."""

from typing import Any


class ColumnSelection:
    """
    Wraps a DataFrame with column selection for use in for_each() inputs.

    After filtering the DataFrame for the current combo, extracts only the
    specified columns. Single column -> returns numpy array of values.
    Multiple columns -> returns a sub-DataFrame.

    Example:
        for_each(
            fn,
            inputs={"speed": ColumnSelection(data_df, ["speed"])},
            subject=[1, 2, 3],
        )

    When ``iterate=True`` the selection means "run fn once per column" rather
    than "pass these columns as one argument." The per-combo loop feeds each
    column (as a single-column array) to fn in turn and reassembles the
    per-column results into one wide row. All iterate selections in a single
    for_each() call must share the same column set (zipped by name).
    """

    def __init__(self, data: Any, columns: list[str], iterate: bool = False):
        """
        Args:
            data: A pandas DataFrame.
            columns: List of column names to extract after filtering.
            iterate: If True, iterate over the columns (one fn call each) and
                reassemble; if False (default), pass the column(s) as a single
                argument.
        """
        self.data = data
        self.columns = columns
        self.iterate = iterate

    @property
    def __name__(self) -> str:
        """Return a display name for format_inputs and error messages."""
        data_name = _display_name(self.data)
        suffix = ", iterate" if self.iterate else ""
        if len(self.columns) == 1 and not self.iterate:
            return f'{data_name}["{self.columns[0]}"]'
        cols = ", ".join(f'"{c}"' for c in self.columns)
        return f'{data_name}[{cols}{suffix}]'

    def __hash__(self):
        return hash((id(self.data), tuple(self.columns), self.iterate))


def _display_name(obj: Any) -> str:
    """Get a display name for an object."""
    try:
        import pandas as pd
        if isinstance(obj, pd.DataFrame):
            return f"DataFrame{list(obj.columns)}"
    except ImportError:
        pass
    return getattr(obj, '__name__', type(obj).__name__)
