"""
Which plot kinds are available, and which one to pick by default.

This is the single rule behind two of the requirements that look separate:
"different data types get different default plots", and "iterating over a
higher schema level unlocks more summative plot types". Both fall out of one
observation — a distribution needs replicates, and replicates exist only when
some factor is left FREE (not mapped to a channel, not collapsed).

The GUI must render only what ``available_plots`` returns. Plot policy lives
here, not in TypeScript (CLAUDE.md NOTE 3).
"""

from __future__ import annotations

from .shape import Shape
from .spec import PlotKind, PlotSpec, Role
from .table import LongTable

#: Kinds that summarize several rows per x position into one mark.
DISTRIBUTION_KINDS = (PlotKind.BOX, PlotKind.VIOLIN, PlotKind.BAR, PlotKind.BAND)


def has_replicates(roles: dict[str, Role]) -> bool:
    """
    True when some factor's levels survive as multiple rows per plotted cell.

    AGGREGATE deliberately does not count: it collapses its factor to a mean
    *before* plotting, so it removes replicates rather than providing them.
    Its purpose is noise reduction ("average over trials"), after which a
    remaining FREE factor (e.g. subject) is what supplies the distribution.
    """
    return any(role is Role.FREE for role in roles.values())


def available_plots(
    shape: Shape,
    roles: dict[str, Role],
    *,
    n_measures: int = 1,
) -> list[PlotKind]:
    """Plot kinds that can be rendered for this shape and role assignment."""
    if shape is Shape.MATRIX_2D:
        return [PlotKind.HEATMAP]

    if n_measures >= 2:
        # x comes from a second measure: a relational scatter, optionally with
        # a connecting line when the x measure is ordered.
        return [PlotKind.SCATTER, PlotKind.LINE]

    replicates = has_replicates(roles)

    if shape is Shape.SERIES_1D:
        kinds = [PlotKind.LINE]
        if replicates:
            kinds.append(PlotKind.BAND)
        return kinds

    if shape is Shape.SCALAR:
        kinds = [PlotKind.SCATTER, PlotKind.STRIP]
        if replicates:
            kinds.extend([PlotKind.BOX, PlotKind.VIOLIN, PlotKind.BAR])
        return kinds

    return []


def default_plot(
    shape: Shape,
    roles: dict[str, Role],
    *,
    n_measures: int = 1,
) -> PlotKind | None:
    """
    The kind to select when a table is first opened.

    scalar → scatter, or box once there are replicates to distribute;
    1-D → one line per observation, or a mean line with a shaded error region
    once there are replicates; 2-D → heatmap.
    """
    kinds = available_plots(shape, roles, n_measures=n_measures)
    if not kinds:
        return None

    replicates = has_replicates(roles)
    if n_measures >= 2:
        return PlotKind.SCATTER
    if shape is Shape.SERIES_1D:
        return PlotKind.BAND if replicates else PlotKind.LINE
    if shape is Shape.SCALAR:
        return PlotKind.BOX if replicates else PlotKind.SCATTER
    return kinds[0]


def why_unavailable(kind: PlotKind, shape: Shape, roles: dict[str, Role]) -> str | None:
    """
    Explain a kind's absence, for GUI tooltips on disabled options.

    Returns None when the kind IS available.
    """
    if kind in available_plots(shape, roles):
        return None
    if shape is Shape.MATRIX_2D:
        return "2-D measures render as a heatmap."
    if kind in DISTRIBUTION_KINDS and not has_replicates(roles):
        return (
            "Needs replicates: leave at least one factor 'free' (unassigned) so "
            "each x position has several values to summarize."
        )
    if kind is PlotKind.BAND and shape is not Shape.SERIES_1D:
        return "Error bands apply to 1-D measures."
    if kind is PlotKind.LINE and shape is Shape.SCALAR:
        return "Lines need a 1-D measure or a second measure for the x axis."
    return f"Not available for a {shape} measure."


def capabilities(spec: PlotSpec, table: LongTable) -> dict:
    """
    The full JSON-serializable capability report for the GUI.

    One call gives the panel everything it needs to render its controls:
    which kinds are selectable, why the others are not, and what the default
    would be for the current role assignment.
    """
    from .roles import complete_roles

    roles = complete_roles(spec, table)
    shape = table.shape_of(spec.y_measure)
    n_measures = len(spec.measures)
    allowed = available_plots(shape, roles, n_measures=n_measures)

    return {
        "shape": str(shape),
        "has_replicates": has_replicates(roles),
        "default": str(default_plot(shape, roles, n_measures=n_measures) or ""),
        "available": [str(k) for k in allowed],
        "kinds": [
            {
                "kind": str(kind),
                "available": kind in allowed,
                "reason": why_unavailable(kind, shape, roles),
            }
            for kind in PlotKind
        ],
        "roles": {name: str(role) for name, role in roles.items()},
    }
