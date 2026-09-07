"""
``resolve(spec, table)`` — turn a spec plus data into renderer-ready panels.

Everything semantic happens here: filtering, variant handling, exploding 1-D
measures, collapsing AGGREGATE factors, fanning out ITERATE factors into
separate figures, faceting, and summarizing replicates into a statistic with an
error band. Renderers below this line only translate.

Two reductions are easy to confuse, so they are named apart deliberately:

* **AGGREGATE (a role)** collapses a factor — "average over trials" — and
  removes it from the data before anything is drawn.
* **Summarizing (a plot kind)** turns whatever replicate rows remain at each x
  position into a centre and an error band. This is what BAR and BAND do.

You can have either, both, or neither.
"""

from __future__ import annotations

from typing import Any, Iterable

import numpy as np
import pandas as pd
from scistacklog import Log

from .resolved import COLOR, SERIES, X, Y, Y_HIGH, Y_LOW, Z
from .resolved import Encoding, Labels, Panel, ResolvedPlot
from .roles import complete_roles, validate
from .shape import Shape
from .spec import ErrorBand, Matcher, PlotKind, PlotSpec, Role, Statistic, VariantPolicy
from .table import LongTable, natural_sort_key

LAYER = "scistackplot"

#: Default index column name created when a 1-D measure is exploded.
DEFAULT_INDEX_COLUMN = "index"

#: Rows per figure above which the GUI path downsamples before serializing.
#: 1-D data over hundreds of trials is megabytes, and it crosses the webview
#: boundary on every interaction. Export never downsamples (max_points=None).
MAX_TRANSPORT_POINTS = 20_000


def resolve(
    spec: PlotSpec,
    table: LongTable,
    *,
    max_points: int | None = None,
) -> list[ResolvedPlot]:
    """
    Reduce ``spec`` against ``table``.

    Returns one :class:`ResolvedPlot` per combination of the spec's ITERATE
    factors — the interactive equivalent of the pipeline's ``for_each`` fan-out
    over iterated schema keys. The two must always produce the same figure set;
    ``tests/test_fanout_parity.py`` asserts it.
    """
    with Log.timer("resolve", layer=LAYER, extra=str(spec.kind)):
        validate(spec, table)
        roles = complete_roles(spec, table)

        frame = table.frame
        frame = _apply_filters(frame, spec)
        frame, roles = _apply_variant_policy(frame, spec, table, roles)

        y_measure = spec.y_measure
        shape = table.shape_of(y_measure)
        index_column = spec.index_column or table.index_column or DEFAULT_INDEX_COLUMN

        if shape is Shape.SERIES_1D and not table.measure(y_measure).exploded:
            frame, index_column = _explode_1d(frame, y_measure, index_column)
        elif shape is not Shape.SERIES_1D:
            index_column = None

        frame = _collapse_aggregates(frame, spec, roles, index_column)

        Log.debug(
            "resolve: measure=%s shape=%s kind=%s rows=%d roles=%s",
            y_measure,
            shape,
            spec.kind,
            len(frame),
            {k: str(v) for k, v in roles.items()},
            layer=LAYER,
        )

        # A factor can be absent from the frame if it was aggregated away or
        # filtered to nothing; grouping by it would raise rather than degrade.
        iterate = [
            name
            for name, role in roles.items()
            if role is Role.ITERATE and name in frame.columns
        ]
        figures: list[ResolvedPlot] = []

        if iterate:
            for key_values, group in _ordered_groups(frame, iterate, table):
                figures.append(
                    _build_figure(
                        group,
                        spec,
                        table,
                        roles,
                        shape,
                        index_column,
                        figure_key=dict(zip(iterate, key_values, strict=True)),
                        max_points=max_points,
                    )
                )
        else:
            figures.append(
                _build_figure(
                    frame,
                    spec,
                    table,
                    roles,
                    shape,
                    index_column,
                    figure_key={},
                    max_points=max_points,
                )
            )

        Log.info(
            "resolved %s of %r: %d figure(s), %d panel(s), %d row(s)",
            spec.kind,
            y_measure,
            len(figures),
            sum(len(f.panels) for f in figures),
            sum(f.row_count for f in figures),
            layer=LAYER,
        )
        return figures


# ---------------------------------------------------------------------------
# Stage helpers
# ---------------------------------------------------------------------------


def _apply_filters(frame: pd.DataFrame, spec: PlotSpec) -> pd.DataFrame:
    if not spec.filters:
        return frame
    mask = pd.Series(True, index=frame.index)
    for flt in spec.filters:
        if flt.column not in frame.columns:
            Log.warn(
                "filter on unknown column %r ignored", flt.column, layer=LAYER
            )
            continue
        column = frame[flt.column]
        if flt.include is not None:
            mask &= column.isin(list(flt.include))
        if flt.exclude is not None:
            mask &= ~column.isin(list(flt.exclude))
        if flt.minimum is not None:
            mask &= pd.to_numeric(column, errors="coerce") >= flt.minimum
        if flt.maximum is not None:
            mask &= pd.to_numeric(column, errors="coerce") <= flt.maximum
    filtered = frame[mask]
    Log.debug(
        "filters kept %d of %d row(s)", len(filtered), len(frame), layer=LAYER
    )
    return filtered


def _apply_variant_policy(
    frame: pd.DataFrame,
    spec: PlotSpec,
    table: LongTable,
    roles: dict[str, Role],
) -> tuple[pd.DataFrame, dict[str, Role]]:
    """
    Honor ``variant_policy``.

    FACET is the default and needs nothing here (``roles.validate`` has already
    refused to let a multi-level variant factor sit in FREE/AGGREGATE). PIN
    filters to one variant. POOL is the deliberate opt-in to averaging across
    pipeline variants, and always says so in the log — a pooled figure looks
    exactly like an unpooled one.
    """
    variant_names = [f.name for f in table.variant_factors]
    if not variant_names:
        return frame, roles

    if spec.variant_policy is VariantPolicy.PIN:
        mask = pd.Series(True, index=frame.index)
        for key, value in (spec.pinned_variant or {}).items():
            if key in frame.columns:
                mask &= frame[key].astype(str) == str(value)
        pinned = frame[mask]
        Log.info(
            "variant pin %s kept %d of %d row(s)",
            spec.pinned_variant,
            len(pinned),
            len(frame),
            layer=LAYER,
        )
        return pinned, roles

    if spec.variant_policy is VariantPolicy.POOL:
        unassigned = [
            name
            for name in variant_names
            if roles.get(name, Role.FREE) in (Role.FREE, Role.AGGREGATE)
        ]
        if unassigned:
            Log.warn(
                "variant_policy='pool': averaging across variant factor(s) %s — "
                "results from different pipeline variants are being combined",
                unassigned,
                layer=LAYER,
            )
            roles = dict(roles)
            for name in unassigned:
                roles[name] = Role.AGGREGATE
        return frame, roles

    return frame, roles


def _explode_1d(
    frame: pd.DataFrame, measure: str, index_column: str
) -> tuple[pd.DataFrame, str]:
    """
    Turn one array per row into one row per sample, adding an index column.

    The index is positional (0..n-1 within each original row). A source that
    knows a real axis — time in seconds, percent of gait cycle — supplies it as
    an ordinary column and sets ``LongTable.index_column``, in which case the
    measure arrives already exploded and this never runs.
    """
    if index_column in frame.columns:
        # Caller supplied a real axis but left the arrays nested: unusual, but
        # exploding would misalign it, so refuse loudly rather than corrupt.
        raise ValueError(
            f"Cannot explode 1-D measure {measure!r}: column {index_column!r} "
            f"already exists. Set LongTable.index_column and pre-explode, or "
            f"choose a different PlotSpec.index_column."
        )

    working = frame.copy()
    working[index_column] = working[measure].map(
        lambda v: list(range(len(v))) if _is_sequence(v) else []
    )
    exploded = working.explode([measure, index_column], ignore_index=True)
    exploded = exploded.dropna(subset=[measure])
    exploded[measure] = pd.to_numeric(exploded[measure], errors="coerce")
    exploded[index_column] = pd.to_numeric(exploded[index_column], errors="coerce")

    Log.debug(
        "exploded 1-D measure %r: %d row(s) -> %d sample(s)",
        measure,
        len(frame),
        len(exploded),
        layer=LAYER,
    )
    return exploded, index_column


def _is_sequence(value: Any) -> bool:
    return isinstance(value, (list, tuple, np.ndarray))


def _collapse_aggregates(
    frame: pd.DataFrame,
    spec: PlotSpec,
    roles: dict[str, Role],
    index_column: str | None,
) -> pd.DataFrame:
    """Average the measures over every AGGREGATE factor's levels."""
    aggregated = [name for name, role in roles.items() if role is Role.AGGREGATE]
    if not aggregated:
        return frame

    keep = [
        name
        for name, role in roles.items()
        if role is not Role.AGGREGATE and name in frame.columns
    ]
    if index_column and index_column in frame.columns:
        keep.append(index_column)

    measures = [m for m in spec.measures if m in frame.columns]
    if not keep:
        # Everything collapses to a single value.
        collapsed = frame[measures].mean().to_frame().T
    else:
        collapsed = (
            frame.groupby(keep, dropna=False, sort=False)[measures]
            .mean()
            .reset_index()
        )

    Log.debug(
        "aggregate over %s: %d -> %d row(s)",
        aggregated,
        len(frame),
        len(collapsed),
        layer=LAYER,
    )
    return collapsed


# ---------------------------------------------------------------------------
# Figure construction
# ---------------------------------------------------------------------------


def _build_figure(
    frame: pd.DataFrame,
    spec: PlotSpec,
    table: LongTable,
    roles: dict[str, Role],
    shape: Shape,
    index_column: str | None,
    *,
    figure_key: dict[str, Any],
    max_points: int | None,
) -> ResolvedPlot:
    color = _role_holder(roles, Role.COLOR)
    x_factor = _role_holder(roles, Role.X)
    # Several factors may be faceted at once; their combined levels are the
    # panels, and FacetOptions decides how those panels are arranged.
    facet_names = [
        name
        for name, role in roles.items()
        if role is Role.FACET and name in frame.columns
    ]

    original_rows = len(frame)
    if max_points is not None and original_rows > max_points:
        frame = _downsample(frame, max_points, index_column)

    panels: list[Panel] = []

    if facet_names:
        groups = _ordered_groups(frame, facet_names, table)
    else:
        groups = [((), frame)]

    for key_values, group in groups:
        key = dict(zip(facet_names, key_values, strict=True))
        panel_frame = _panel_frame(
            group, spec, table, shape, x_factor, color, index_column
        )
        panels.append(Panel(frame=panel_frame, key=key))

    n_rows, n_cols, row_labels, col_labels = _assign_grid(panels, spec.facet)

    encoding = _encoding_for(spec.kind, color, shape)
    labels = _labels_for(spec, table, x_factor, color, index_column, figure_key)

    y_limits = None
    if spec.facet.share_y and len(panels) > 1:
        y_limits = _shared_limits(panels, encoding)

    return ResolvedPlot(
        kind=spec.kind,
        panels=panels,
        encoding=encoding,
        labels=labels,
        spec=spec,
        figure_key=figure_key,
        x_order=_level_order(table, x_factor, panels, X) if x_factor else None,
        color_order=_level_order(table, color, panels, COLOR) if color else None,
        grid_rows=n_rows,
        grid_cols=n_cols,
        row_labels=row_labels,
        col_labels=col_labels,
        y_limits=y_limits,
        downsampled_from=original_rows if max_points and original_rows > max_points else None,
    )


def _panel_frame(
    group: pd.DataFrame,
    spec: PlotSpec,
    table: LongTable,
    shape: Shape,
    x_factor: str | None,
    color: str | None,
    index_column: str | None,
) -> pd.DataFrame:
    """Build the canonical ``__x``/``__y``/… frame the renderers consume."""
    y_measure = spec.y_measure

    if shape is Shape.MATRIX_2D:
        return _matrix_frame(group, y_measure)

    out = pd.DataFrame(index=group.index)

    # --- x --------------------------------------------------------------
    if spec.x_measure is not None:
        out[X] = pd.to_numeric(group[spec.x_measure], errors="coerce")
    elif shape is Shape.SERIES_1D and index_column and index_column in group.columns:
        out[X] = pd.to_numeric(group[index_column], errors="coerce")
    elif x_factor:
        out[X] = group[x_factor].values
    else:
        # No x at all: a single categorical position, matching the proof of
        # concept's "Observation" fallback when no tick factor was chosen.
        out[X] = ""

    out[Y] = pd.to_numeric(group[y_measure], errors="coerce")

    if color:
        out[COLOR] = group[color].values

    # --- one polyline per replicate combination --------------------------
    if spec.kind is PlotKind.LINE:
        series_cols = [
            name
            for name in table.factor_names
            if name in group.columns and name != x_factor
        ]
        if series_cols:
            out[SERIES] = (
                group[series_cols]
                .astype(str)
                .agg(" | ".join, axis=1)
                .values
            )
        else:
            out[SERIES] = ""

    out = out.dropna(subset=[Y])

    # --- summarize replicates into centre + error ------------------------
    if spec.kind in (PlotKind.BAR, PlotKind.BAND):
        out = _summarize(out, spec, color)

    if spec.kind is PlotKind.LINE or spec.kind is PlotKind.BAND:
        out = out.sort_values(X, kind="stable")

    return out.reset_index(drop=True)


def _matrix_frame(group: pd.DataFrame, measure: str) -> pd.DataFrame:
    """One row holding the (possibly averaged) matrix for a heatmap panel."""
    matrices = [np.asarray(v, dtype=float) for v in group[measure] if _is_sequence(v)]
    if not matrices:
        return pd.DataFrame({Z: []})
    shapes = {m.shape for m in matrices}
    if len(shapes) > 1:
        Log.warn(
            "heatmap: %d matrices with differing shapes %s — using the first",
            len(matrices),
            sorted(shapes),
            layer=LAYER,
        )
        stacked = matrices[0]
    elif len(matrices) > 1:
        Log.debug("heatmap: averaging %d matrices", len(matrices), layer=LAYER)
        stacked = np.mean(np.stack(matrices), axis=0)
    else:
        stacked = matrices[0]
    return pd.DataFrame({Z: [stacked]})


def _summarize(frame: pd.DataFrame, spec: PlotSpec, color: str | None) -> pd.DataFrame:
    """Collapse replicate rows at each x (and colour) into centre + error."""
    group_cols = [X] + ([COLOR] if color else [])
    grouped = frame.groupby(group_cols, dropna=False, sort=False)[Y]

    statistic = spec.aggregate.statistic
    centre = grouped.median() if statistic is Statistic.MEDIAN else grouped.mean()

    error = spec.aggregate.error
    if error is ErrorBand.IQR:
        low = grouped.quantile(0.25)
        high = grouped.quantile(0.75)
    elif error is ErrorBand.NONE:
        low = centre
        high = centre
    else:
        sd = grouped.std(ddof=1).fillna(0.0)
        count = grouped.count()
        if error is ErrorBand.SD:
            spread = sd
        elif error is ErrorBand.SEM:
            spread = sd / np.sqrt(count.where(count > 0, 1))
        else:  # CI95
            spread = 1.96 * sd / np.sqrt(count.where(count > 0, 1))
        low = centre - spread
        high = centre + spread

    out = pd.concat(
        {Y: centre, Y_LOW: low, Y_HIGH: high}, axis=1
    ).reset_index()
    return out


def _downsample(
    frame: pd.DataFrame, max_points: int, index_column: str | None
) -> pd.DataFrame:
    """
    Reduce row count for transport.

    Striding (rather than random sampling) preserves the visual shape of 1-D
    traces, which is the case that actually gets big. The caller records the
    original size on the ResolvedPlot so the GUI can say so.
    """
    stride = max(1, len(frame) // max_points)
    reduced = frame.iloc[::stride]
    Log.warn(
        "downsampled %d row(s) to %d for transport (stride=%d)",
        len(frame),
        len(reduced),
        stride,
        layer=LAYER,
    )
    return reduced


# ---------------------------------------------------------------------------
# Ordering, encoding, labels
# ---------------------------------------------------------------------------


def _role_holder(roles: dict[str, Role], role: Role) -> str | None:
    for name, assigned in roles.items():
        if assigned is role:
            return name
    return None


def _ordered_groups(
    frame: pd.DataFrame, columns: list[str], table: LongTable
) -> list[tuple[tuple, pd.DataFrame]]:
    """
    Group by ``columns`` in the factors' declared level order.

    Declared order matters: zero-padded schema keys ("01", "02", … "10") sort
    lexicographically into 1, 10, 2 under pandas' default, which is a visible
    bug on an axis and in a facet strip. ``LongTable`` carries the real order.
    """
    present = [c for c in columns if c in frame.columns]
    if not present:
        return [((), frame)]

    groups = {key: group for key, group in frame.groupby(present, dropna=False, sort=False)}
    ordered_keys = sorted(
        groups.keys(),
        key=lambda key: tuple(
            _level_rank(table, column, value)
            for column, value in zip(present, _as_tuple(key), strict=True)
        ),
    )
    return [(_as_tuple(key), groups[key]) for key in ordered_keys]


def _as_tuple(key: Any) -> tuple:
    return key if isinstance(key, tuple) else (key,)


def _level_rank(table: LongTable, column: str, value: Any) -> tuple:
    """Position of ``value`` in the factor's declared levels, else natural sort."""
    try:
        levels = table.factor(column).levels
    except KeyError:
        return (1,) + natural_sort_key(value)
    for position, level in enumerate(levels):
        if level == value or str(level) == str(value):
            return (0, position)
    return (1,) + natural_sort_key(value)


def _level_order(
    table: LongTable, column: str | None, panels: list[Panel], frame_column: str
) -> list[Any] | None:
    if not column:
        return None
    present: list[Any] = []
    for panel in panels:
        if frame_column in panel.frame.columns:
            present.extend(panel.frame[frame_column].dropna().unique().tolist())
    unique = list(dict.fromkeys(present))
    return sorted(unique, key=lambda v: _level_rank(table, column, v))


def _assign_grid(panels, facet) -> tuple[int, int, list[str], list[str]]:
    """
    Place every panel in the grid, and report its shape.

    Two modes. With no rules the panels simply flow in resolution order,
    wrapping at ``facet.wrap``. With ``rows``/``cols`` matchers, each panel is
    placed by testing its label against the rules — which is what makes a
    layout describable ("left column = names starting with L") and therefore
    reusable across variables, rather than a hand-arrangement of one figure.

    A panel matching no rule goes to a trailing "other" row/column instead of
    being dropped: silently losing a muscle because a pattern had a typo is the
    worst possible failure here.
    """
    if not panels:
        return 1, 1, [], []

    if not facet.has_rules:
        return _flow_grid(panels, facet.wrap)

    row_labels = _rule_labels(facet.rows)
    col_labels = _rule_labels(facet.cols)
    row_overflow = False
    col_overflow = False

    # Panels that share a cell (two rules matching the same label, or several
    # panels in one rule with no rule on the other axis) stack along the free
    # axis, so nothing is hidden underneath anything else.
    used: dict[tuple[int, int], int] = {}
    for panel in panels:
        label = panel.title
        row = _match_index(facet.rows, label)
        col = _match_index(facet.cols, label)
        if facet.rows and row is None:
            row, row_overflow = len(facet.rows), True
        if facet.cols and col is None:
            col, col_overflow = len(facet.cols), True

        if row is None:  # columns ruled, rows free: stack downwards
            row = used.get((None, col), 0)  # type: ignore[arg-type]
            used[(None, col)] = row + 1  # type: ignore[index]
        elif col is None:  # rows ruled, columns free: flow rightwards
            col = used.get((row, None), 0)  # type: ignore[arg-type]
            used[(row, None)] = col + 1  # type: ignore[index]

        panel.grid_row, panel.grid_col = row, col

    if row_overflow:
        row_labels = row_labels + ["other"]
        Log.warn(
            "facet layout: some panels matched no row rule — see the 'other' row",
            layer=LAYER,
        )
    if col_overflow:
        col_labels = col_labels + ["other"]
        Log.warn(
            "facet layout: some panels matched no column rule — see the "
            "'other' column",
            layer=LAYER,
        )

    n_rows = max((p.grid_row for p in panels), default=0) + 1
    n_cols = max((p.grid_col for p in panels), default=0) + 1
    Log.debug(
        "facet grid %dx%d from %d row rule(s), %d column rule(s)",
        n_rows,
        n_cols,
        len(facet.rows),
        len(facet.cols),
        layer=LAYER,
    )
    return n_rows, n_cols, row_labels, col_labels


def _flow_grid(panels, wrap: int | None) -> tuple[int, int, list[str], list[str]]:
    """Panels in resolution order, wrapped to ``wrap`` columns."""
    count = len(panels)
    n_cols = min(count, wrap) if wrap and wrap > 0 else count
    n_cols = max(1, n_cols)
    for index, panel in enumerate(panels):
        panel.grid_row, panel.grid_col = divmod(index, n_cols)
    n_rows = max((p.grid_row for p in panels), default=0) + 1
    return n_rows, n_cols, [], []


def _match_index(rules: list[Matcher], label: str) -> int | None:
    """First rule that matches, or None. First match wins — order is the tie-break."""
    for index, rule in enumerate(rules):
        if rule.matches(label):
            return index
    return None


def _rule_labels(rules: list[Matcher]) -> list[str]:
    return [rule.display for rule in rules]


def _encoding_for(kind: PlotKind, color: str | None, shape: Shape) -> Encoding:
    if shape is Shape.MATRIX_2D:
        return Encoding(x=None, y=None, z=Z)
    return Encoding(
        x=X,
        y=Y,
        color=COLOR if color else None,
        y_low=Y_LOW if kind in (PlotKind.BAR, PlotKind.BAND) else None,
        y_high=Y_HIGH if kind in (PlotKind.BAR, PlotKind.BAND) else None,
        series=SERIES if kind is PlotKind.LINE else None,
    )


def _labels_for(
    spec: PlotSpec,
    table: LongTable,
    x_factor: str | None,
    color: str | None,
    index_column: str | None,
    figure_key: dict[str, Any],
) -> Labels:
    style = spec.style
    if style.x_label:
        x_label = style.x_label
    elif spec.x_measure:
        x_label = table.measure(spec.x_measure).display
    elif x_factor:
        x_label = table.factor(x_factor).display
    elif index_column:
        x_label = index_column
    else:
        x_label = ""

    y_label = style.y_label or table.measure(spec.y_measure).display

    title = style.title
    if title is None and figure_key:
        title = ", ".join(f"{k}={v}" for k, v in figure_key.items())

    return Labels(
        x=x_label,
        y=y_label,
        color=table.factor(color).display if color else None,
        title=title,
    )


def _shared_limits(panels: list[Panel], encoding: Encoding) -> tuple[float, float] | None:
    lows: list[float] = []
    highs: list[float] = []
    for panel in panels:
        frame = panel.frame
        columns = [c for c in (encoding.y, encoding.y_low, encoding.y_high) if c and c in frame.columns]
        for column in columns:
            values = pd.to_numeric(frame[column], errors="coerce").dropna()
            if len(values):
                lows.append(float(values.min()))
                highs.append(float(values.max()))
    if not lows:
        return None
    low, high = min(lows), max(highs)
    if low == high:
        pad = abs(low) * 0.05 or 1.0
        return (low - pad, high + pad)
    pad = (high - low) * 0.05
    return (low - pad, high + pad)


def unique_values(frame: pd.DataFrame, column: str) -> list[Any]:
    """Distinct values of a column, natural-sorted. Used by sources for levels."""
    if column not in frame.columns:
        return []
    return sorted(frame[column].dropna().unique().tolist(), key=natural_sort_key)


def iter_columns(names: Iterable[str]) -> list[str]:
    return [n for n in names if n]
