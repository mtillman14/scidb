"""
Renderers.

Both take a fully reduced :class:`~scistackplot.resolved.ResolvedPlot` and only
translate it. matplotlib is the export and pipeline path (it returns the
``Figure`` a scidb ``plot_`` endpoint must return); plotly is the interactive
path (it returns a plotly.js figure dict for the webview).
"""

from .base import Renderer

__all__ = ["Renderer", "render_matplotlib", "render_plotly"]


def render_matplotlib(resolved):
    """Draw with matplotlib; returns a ``matplotlib.figure.Figure``."""
    from .mpl import render

    return render(resolved)


def render_plotly(resolved) -> dict:
    """Build a plotly.js figure dict (no plotly package required)."""
    from .plotly_ import render

    return render(resolved)
