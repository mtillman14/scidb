"""ColName wrapper — resolves to the single non-schema data column name of a DataFrame."""

from typing import Any


class ColName:
    """
    Marker that resolves to a data column name string at for_each time.

    Two forms:

    1. ``ColName(df)`` — *static*. Resolves once, up front, to the single
       non-schema data column name of ``df``. Use when a function needs to know
       the name of the one data column in a DataFrame but should stay
       framework-agnostic. Raises ValueError if ``df`` has 0 or 2+ non-schema
       data columns.

    2. ``ColName()`` — *deferred*. Resolves per-column inside a ``for_columns``
       iteration to the name of the column currently being fed to the function.
       Requires at least one iterate input (``for_columns`` /
       ``ColumnSelection(..., iterate=True)``); using it without one is an error.

    Example (static):
        set_schema(["subject", "session"])
        result = for_each(
            analyze,
            inputs={"table": raw_df, "col_name": ColName(raw_df)},
            subject=[1, 2],
            session=["pre", "post"],
        )

        # The function is pure — no framework imports:
        def analyze(table, col_name):
            return table[col_name].mean()

    Example (deferred, current for_columns column):
        for_each(
            analyze,
            inputs={"df": means_df.for_columns(), "col_name": ColName()},
            subject=[],
        )
    """

    def __init__(self, data: Any = None):
        """
        Args:
            data: A pandas DataFrame whose single data column name will be
                resolved (static form). Omit it for the deferred form, which
                resolves to the current ``for_columns`` column.
        """
        self.data = data

    @property
    def is_deferred(self) -> bool:
        """True for the no-arg form (resolves to the current for_columns column)."""
        return self.data is None
