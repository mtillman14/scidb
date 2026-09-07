"""
Plotly renderer — the interactive path.

Emits a plain ``{"data": [...], "layout": {...}}`` dict rather than a
``plotly.graph_objects.Figure``. That is deliberate: the consumer is plotly.js
running inside a VS Code webview, which wants JSON. Building it directly means
the interactive path needs no plotly Python package at all, keeps the payload
inspectable in tests, and avoids shipping a second figure object across the
JSON-RPC boundary only to serialize it anyway.

``plotly`` remains an optional extra for users who want a Figure in a notebook
(:func:`to_figure`).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scistacklog import Log

from ..resolved import ResolvedPlot
from ..spec import PlotKind
from .base import (
    color_groups,
    grid_shape,
    palette_color,
    panel_position,
    shows_x_labels,
    shows_y_labels,
)

LAYER = "scistackplot"


def render(resolved: ResolvedPlot) -> dict:
    """Build a plotly.js figure dict."""
    with Log.timer("render_plotly", layer=LAYER, extra=str(resolved.kind)):
        n_rows, n_cols = grid_shape(resolved)
        traces: list[dict] = []
        layout: dict[str, Any] = {
            "showlegend": bool(resolved.encoding.color),
            "legend": {"title": {"text": resolved.labels.color or ""}},
            "margin": {"l": 60, "r": 20, "t": 40, "b": 50},
            "hovermode": "closest",
            "annotations": [],
            # The grid shape travels with the figure so the panel can size it:
            # 4 rows of subplots need more height than 1, and only the renderer
            # knows how the panels were laid out.
            "meta": {"rows": n_rows, "cols": n_cols},
        }
        if resolved.labels.title:
            layout["title"] = {"text": resolved.labels.title}

        positions = [
            panel_position(resolved, index) for index in range(len(resolved.panels))
        ]
        seen_legend: set[str] = set()

        for index, panel in enumerate(resolved.panels):
            row, col = positions[index]
            slot = row * n_cols + col + 1
            x_axis = "x" if slot == 1 else f"x{slot}"
            y_axis = "y" if slot == 1 else f"y{slot}"

            traces.extend(
                _panel_traces(panel.frame, resolved, x_axis, y_axis, seen_legend)
            )
            _add_axes(
                layout,
                resolved,
                slot,
                row,
                col,
                n_rows,
                n_cols,
                bottom=shows_x_labels(resolved, row, col),
                leftmost=shows_y_labels(resolved, row, col),
            )
            if panel.key:
                layout["annotations"].append(
                    _panel_title(panel.title, row, col, n_rows, n_cols)
                )

        return {"data": traces, "layout": layout}


def to_figure(resolved: ResolvedPlot):
    """Wrap :func:`render` in a ``plotly.graph_objects.Figure`` (optional extra)."""
    try:
        import plotly.graph_objects as go
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ImportError(
            "to_figure() needs plotly (pip install scistackplot[interactive]). "
            "render() returns a plain figure dict with no such requirement."
        ) from exc
    return go.Figure(render(resolved))


# ---------------------------------------------------------------------------


def _panel_traces(
    frame: pd.DataFrame,
    resolved: ResolvedPlot,
    x_axis: str,
    y_axis: str,
    seen_legend: set[str],
) -> list[dict]:
    if frame.empty:
        return []

    encoding = resolved.encoding
    kind = resolved.kind
    traces: list[dict] = []

    if kind is PlotKind.HEATMAP:
        matrix = np.asarray(frame[encoding.z].iloc[0], dtype=float)
        return [
            {
                "type": "heatmap",
                "z": matrix.tolist(),
                "xaxis": x_axis.replace("x", "x"),
                "yaxis": y_axis,
                "colorscale": "Viridis",
            }
        ]

    for index, (level, subset) in enumerate(color_groups(frame, resolved)):
        color = palette_color(index)
        label = str(level) if level is not None else resolved.labels.y
        show_legend = level is not None and label not in seen_legend
        if show_legend:
            seen_legend.add(label)

        base = {
            "name": label,
            "legendgroup": label,
            "showlegend": show_legend,
            "xaxis": x_axis,
            "yaxis": y_axis,
        }
        x_values = _values(subset[encoding.x])

        if kind in (PlotKind.SCATTER, PlotKind.STRIP):
            traces.append(
                {
                    **base,
                    "type": "scatter",
                    "mode": "markers",
                    "x": x_values,
                    "y": _values(subset[encoding.y]),
                    "marker": {"color": color, "size": 8, "opacity": resolved.spec.style.alpha},
                }
            )
        elif kind is PlotKind.LINE:
            traces.extend(_line_traces(subset, resolved, base, color))
        elif kind is PlotKind.BAND:
            traces.extend(_band_traces(subset, resolved, base, color))
        elif kind is PlotKind.BAR:
            error = None
            if encoding.has_error:
                centre = np.asarray(_values(subset[encoding.y]), dtype=float)
                error = {
                    "type": "data",
                    "symmetric": False,
                    "array": (
                        np.asarray(_values(subset[encoding.y_high]), dtype=float) - centre
                    ).tolist(),
                    "arrayminus": (
                        centre - np.asarray(_values(subset[encoding.y_low]), dtype=float)
                    ).tolist(),
                }
            traces.append(
                {
                    **base,
                    "type": "bar",
                    "x": x_values,
                    "y": _values(subset[encoding.y]),
                    "marker": {"color": color},
                    **({"error_y": error} if error else {}),
                }
            )
        elif kind in (PlotKind.BOX, PlotKind.VIOLIN):
            traces.append(
                {
                    **base,
                    "type": "box" if kind is PlotKind.BOX else "violin",
                    "x": x_values,
                    "y": _values(subset[encoding.y]),
                    "marker": {"color": color},
                    "line": {"color": color},
                    "boxpoints": "outliers" if kind is PlotKind.BOX else None,
                }
            )

    return traces


def _line_traces(subset, resolved, base, color) -> list[dict]:
    """One trace per polyline; only the first carries the legend entry."""
    encoding = resolved.encoding
    series_column = encoding.series
    if series_column and series_column in subset.columns:
        groups = list(subset.groupby(series_column, sort=False))
    else:
        groups = [(None, subset)]

    traces = []
    for position, (series_id, rows) in enumerate(groups):
        traces.append(
            {
                **base,
                "showlegend": base["showlegend"] and position == 0,
                "type": "scatter",
                "mode": "lines",
                "x": _values(rows[encoding.x]),
                "y": _values(rows[encoding.y]),
                "line": {"color": color, "width": 1.5},
                "opacity": resolved.spec.style.alpha,
                "hovertext": str(series_id) if series_id is not None else None,
            }
        )
    return traces


def _band_traces(subset, resolved, base, color) -> list[dict]:
    encoding = resolved.encoding
    x_values = _values(subset[encoding.x])
    traces = []
    if encoding.has_error:
        traces.append(
            {
                **base,
                "showlegend": False,
                "type": "scatter",
                "mode": "lines",
                "x": x_values + x_values[::-1],
                "y": _values(subset[encoding.y_high]) + _values(subset[encoding.y_low])[::-1],
                "fill": "toself",
                "fillcolor": _rgba(color, 0.22),
                "line": {"width": 0},
                "hoverinfo": "skip",
            }
        )
    traces.append(
        {
            **base,
            "type": "scatter",
            "mode": "lines",
            "x": x_values,
            "y": _values(subset[encoding.y]),
            "line": {"color": color, "width": 2},
        }
    )
    return traces


def _add_axes(
    layout,
    resolved,
    slot,
    row,
    col,
    n_rows,
    n_cols,
    *,
    bottom: bool = True,
    leftmost: bool = True,
) -> None:
    x_key = "xaxis" if slot == 1 else f"xaxis{slot}"
    y_key = "yaxis" if slot == 1 else f"yaxis{slot}"
    x_anchor = "y" if slot == 1 else f"y{slot}"
    y_anchor = "x" if slot == 1 else f"x{slot}"

    x0, y0, cell_width, cell_height = _cell(row, col, n_rows, n_cols)

    layout[x_key] = {
        "domain": [x0, x0 + cell_width],
        "anchor": x_anchor,
        # Tick labels and the axis title share ONE rule (base.shows_x_labels).
        "showticklabels": bottom,
        "title": {"text": resolved.labels.x if bottom else ""},
        "type": "log" if resolved.spec.style.log_x else "-",
    }
    layout[y_key] = {
        "domain": [y0, y0 + cell_height],
        "anchor": y_anchor,
        "showticklabels": leftmost,
        "title": {"text": resolved.labels.y if leftmost else ""},
        "type": "log" if resolved.spec.style.log_y else "-",
    }
    # Link the axes when the spec asks for shared scales, so panning/zooming one
    # subplot moves them all — and so hiding tick labels stays truthful.
    if slot != 1:
        if resolved.spec.facet.share_x:
            layout[x_key]["matches"] = "x"
        if resolved.spec.facet.share_y:
            layout[y_key]["matches"] = "y"
    if resolved.y_limits and resolved.kind is not PlotKind.HEATMAP:
        layout[y_key]["range"] = list(resolved.y_limits)


def _panel_title(text, row, col, n_rows, n_cols) -> dict:
    x0, y0, cell_width, cell_height = _cell(row, col, n_rows, n_cols)
    return {
        "text": text,
        "showarrow": False,
        "xref": "paper",
        "yref": "paper",
        "x": x0 + cell_width / 2,
        "y": min(1.0, y0 + cell_height + Y_GAP * 0.25),
        "xanchor": "center",
        "yanchor": "bottom",
        "font": {"size": 11},
    }


#: Space between subplot cells, as a fraction of the figure. The vertical gap is
#: much larger than the horizontal one because a row costs more: tick labels
#: hang below a cell and the next row's title sits above it, and at 0.06 they
#: collided.
X_GAP = 0.05
Y_GAP = 0.14


def _cell(row, col, n_rows, n_cols) -> tuple[float, float, float, float]:
    """(x0, y0, width, height) of one grid cell, in paper coordinates."""
    y_gap = Y_GAP if n_rows > 1 else 0.0
    x_gap = X_GAP if n_cols > 1 else 0.0
    cell_width = (1.0 - x_gap * (n_cols - 1)) / n_cols
    cell_height = (1.0 - y_gap * (n_rows - 1)) / n_rows
    # Plotly's y domain runs bottom-up; our rows run top-down.
    return (
        col * (cell_width + x_gap),
        (n_rows - row - 1) * (cell_height + y_gap),
        cell_width,
        cell_height,
    )


def _values(series: pd.Series) -> list:
    """Series -> a JSON-safe list (numpy scalars are not JSON serializable)."""
    return [None if pd.isna(v) else (v.item() if hasattr(v, "item") else v) for v in series]


def _rgba(hex_color: str, alpha: float) -> str:
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"
