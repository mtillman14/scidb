"""ColName wrapper — resolves to the single data column name of a Variable type."""

from typing import Any


class ColName:
    """
    Marker that resolves to the single data column name of a DB-backed variable.

    Use this when a function needs to know the name of the data column
    but the function itself should stay framework-agnostic.

    Two forms:

    1. ``ColName(MyVar)`` — *static*. At for_each time it is replaced by the
       string name of the single data column for that variable type. Raises
       ValueError if the variable has 0 or 2+ data columns.

    2. ``ColName()`` — *deferred*. Resolves per-column inside a ``for_columns``
       iteration to the name of the column currently being fed to the function.
       Requires at least one iterate input (``MyVar.for_columns()``); using it
       without one is an error.

    Example (static):
        for_each(
            analyze,
            inputs={"table": MyVar, "col_name": ColName(MyVar)},
            outputs=[Result],
            subject=[1, 2, 3],
        )

        # The function is pure — no framework imports:
        def analyze(table, col_name):
            return table[col_name].mean()

    Example (deferred, current for_columns column):
        for_each(
            analyze,
            inputs={"df": MyVar.for_columns(), "col_name": ColName()},
            outputs=[Result],
            subject=[],
        )
    """

    def __init__(self, var_type: Any = None):
        """
        Args:
            var_type: The variable type (class) whose data column name will be
                resolved (static form). Omit it for the deferred form, which
                resolves to the current ``for_columns`` column.
        """
        self.var_type = var_type

    @property
    def is_deferred(self) -> bool:
        """True for the no-arg form (resolves to the current for_columns column)."""
        return self.var_type is None
