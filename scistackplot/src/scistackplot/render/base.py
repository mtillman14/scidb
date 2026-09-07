"""
Renderer protocol and the layout maths both renderers share.

A renderer translates a :class:`~scistackplot.resolved.ResolvedPlot` into a
backend figure. It performs **no** data reduction — every aggregation, ordering
and error band was decided in ``reduce.resolve``. Keeping renderers dumb is
what stops the interactive view and the exported figure from disagreeing.
"""

from __future__ import annotations

import math
from typing import Any, Protocol

import numpy as np
import pandas as pd

from ..resolved import ResolvedPlot


class Renderer(Protocol):
    """Anything that can draw a ResolvedPlot."""

    def render(self, resolved: ResolvedPlot) -> Any:  # pragma: no cover - protocol
        ...


def grid_shape(resolved: ResolvedPlot) -> tuple[int, int]:
    """Rows and columns of the subplot grid, as decided in ``reduce``."""
    return max(1, resolved.grid_rows), max(1, resolved.grid_cols)


def panel_position(resolved: ResolvedPlot, panel_index: int) -> tuple[int, int]:
    """Zero-based (row, column) of a panel. Layout is not the renderer's job."""
    panel = resolved.panels[panel_index]
    return panel.grid_row, panel.grid_col


def occupied_cells(resolved: ResolvedPlot) -> set[tuple[int, int]]:
    """Every grid cell that holds a panel — the basis for the axis rules."""
    return {(p.grid_row, p.grid_col) for p in resolved.panels}


def shows_x_labels(resolved: ResolvedPlot, row: int, col: int) -> bool:
    """
    Whether this cell carries the x tick labels AND the x axis title.

    ONE rule for both, deliberately: "nothing directly below" rather than
    "bottom row", because a wrapped grid's last row is usually partial and the
    panels above those empty cells are the bottom of their own column. The two
    used to drift — the title followed this rule while the tick labels were
    re-applied to every panel.
    """
    return (row + 1, col) not in occupied_cells(resolved)


def shows_y_labels(resolved: ResolvedPlot, row: int, col: int) -> bool:
    """Same idea on the other axis: nothing directly to the left."""
    return (row, col - 1) not in occupied_cells(resolved)


def is_categorical_x(resolved: ResolvedPlot) -> bool:
    """
    Whether the x axis is a set of discrete positions rather than a number line.

    A factor on x is categorical; a 1-D index or a second measure is numeric.
    """
    if resolved.x_order is None:
        return False
    return not all(_is_number(value) for value in resolved.x_order)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(
        value, bool
    )


def x_positions(
    values: pd.Series, resolved: ResolvedPlot
) -> tuple[np.ndarray, list[str] | None]:
    """
    Map x values to plotting positions.

    Returns ``(positions, tick_labels)``. ``tick_labels`` is None for a numeric
    axis; for a categorical axis it is the ordered level labels, and positions
    are their indices — which is what puts "01, 02, … 10" in the right order
    instead of pandas' lexicographic 1, 10, 2.
    """
    if not is_categorical_x(resolved):
        return pd.to_numeric(values, errors="coerce").to_numpy(dtype=float), None

    order = [str(v) for v in (resolved.x_order or [])]
    lookup = {label: position for position, label in enumerate(order)}
    positions = np.array(
        [lookup.get(str(v), np.nan) for v in values], dtype=float
    )
    return positions, order


def color_groups(
    frame: pd.DataFrame, resolved: ResolvedPlot
) -> list[tuple[Any, pd.DataFrame]]:
    """Split a panel frame into colour series, in declared level order."""
    color_column = resolved.encoding.color
    if not color_column or color_column not in frame.columns:
        return [(None, frame)]

    order = resolved.color_order or []
    groups: list[tuple[Any, pd.DataFrame]] = []
    seen = set()
    for level in order:
        subset = frame[frame[color_column].astype(str) == str(level)]
        if len(subset):
            groups.append((level, subset))
            seen.add(str(level))
    # Anything the declared order missed (shouldn't happen, but never drop data).
    for level in frame[color_column].dropna().unique():
        if str(level) not in seen:
            groups.append((level, frame[frame[color_column] == level]))
    return groups


#: A colour-blind-safe qualitative palette, used when the spec names none.
#: Okabe–Ito, which stays distinguishable in greyscale print.
DEFAULT_PALETTE = (
    "#0072B2",
    "#D55E00",
    "#009E73",
    "#CC79A7",
    "#E69F00",
    "#56B4E9",
    "#F0E442",
    "#000000",
)


def palette_color(index: int, palette: tuple[str, ...] = DEFAULT_PALETTE) -> str:
    return palette[index % len(palette)]
