"""Renderer tests — both backends draw the same ResolvedPlot without reducing it."""

from __future__ import annotations

import json

import pytest

from scistackplot import (
    PlotKind,
    PlotSpec,
    Role,
    render_matplotlib,
    render_plotly,
    resolve,
)

matplotlib = pytest.importorskip("matplotlib")


@pytest.fixture
def box_spec():
    return PlotSpec(
        measures=["StepLength"],
        roles={"subject": Role.X, "session": Role.COLOR, "trial": Role.FREE},
        kind=PlotKind.BOX,
    )


@pytest.fixture
def band_spec():
    return PlotSpec(
        measures=["Signal"],
        roles={"session": Role.COLOR, "subject": Role.FREE, "trial": Role.FREE},
        kind=PlotKind.BAND,
    )


# --- matplotlib ------------------------------------------------------------


def test_matplotlib_returns_a_figure(scalar_table, box_spec):
    from matplotlib.figure import Figure

    figure = render_matplotlib(resolve(box_spec, scalar_table)[0])
    assert isinstance(figure, Figure)
    matplotlib.pyplot.close(figure)


@pytest.mark.parametrize(
    "kind",
    [PlotKind.SCATTER, PlotKind.STRIP, PlotKind.BOX, PlotKind.VIOLIN, PlotKind.BAR],
)
def test_every_scalar_kind_renders(scalar_table, kind):
    spec = PlotSpec(
        measures=["StepLength"],
        roles={"subject": Role.X, "session": Role.COLOR, "trial": Role.FREE},
        kind=kind,
    )
    figure = render_matplotlib(resolve(spec, scalar_table)[0])
    assert figure.axes
    matplotlib.pyplot.close(figure)


@pytest.mark.parametrize("kind", [PlotKind.LINE, PlotKind.BAND])
def test_every_series_kind_renders(series_table, kind):
    spec = PlotSpec(
        measures=["Signal"],
        roles={"session": Role.COLOR, "subject": Role.FREE, "trial": Role.FREE},
        kind=kind,
    )
    figure = render_matplotlib(resolve(spec, series_table)[0])
    assert figure.axes
    matplotlib.pyplot.close(figure)


def test_facets_become_subplots(scalar_table):
    spec = PlotSpec(
        measures=["StepLength"],
        roles={
            "subject": Role.X,
            "session": Role.FACET,
            "trial": Role.FREE,
        },
        kind=PlotKind.BOX,
    )
    figure = render_matplotlib(resolve(spec, scalar_table)[0])
    visible = [ax for ax in figure.axes if ax.get_visible()]
    assert len(visible) == 2
    matplotlib.pyplot.close(figure)


def test_categorical_axis_ticks_are_in_declared_order(wide_subject_table):
    spec = PlotSpec(
        measures=["Mass"], roles={"subject": Role.X}, kind=PlotKind.SCATTER
    )
    figure = render_matplotlib(resolve(spec, wide_subject_table)[0])
    labels = [t.get_text() for t in figure.axes[0].get_xticklabels()]

    assert labels[:3] == ["01", "02", "03"]
    matplotlib.pyplot.close(figure)


def test_heatmap_renders_a_2d_measure():
    import numpy as np
    import pandas as pd

    from scistackplot import LongTable

    frame = pd.DataFrame(
        {"subject": ["01", "02"], "Map": [np.zeros((4, 5)), np.ones((4, 5))]}
    )
    table = LongTable.from_frame(frame, factors=["subject"], measures=["Map"])
    spec = PlotSpec(measures=["Map"], roles={"subject": Role.FREE}, kind=PlotKind.HEATMAP)

    figure = render_matplotlib(resolve(spec, table)[0])
    assert figure.axes
    matplotlib.pyplot.close(figure)


# --- plotly ----------------------------------------------------------------


def test_plotly_output_is_json_serializable(scalar_table, box_spec):
    payload = render_plotly(resolve(box_spec, scalar_table)[0])
    json.dumps(payload)  # the webview boundary requires this

    assert payload["data"]
    assert "layout" in payload


def test_plotly_makes_one_trace_per_colour_level(scalar_table, box_spec):
    payload = render_plotly(resolve(box_spec, scalar_table)[0])
    assert len(payload["data"]) == 2
    assert {trace["name"] for trace in payload["data"]} == {"pre", "post"}


def test_plotly_band_emits_fill_and_line(series_table, band_spec):
    payload = render_plotly(resolve(band_spec, series_table)[0])
    fills = [t for t in payload["data"] if t.get("fill") == "toself"]
    lines = [t for t in payload["data"] if t.get("mode") == "lines" and "fill" not in t]

    assert len(fills) == 2  # one per session
    assert len(lines) == 2


def test_plotly_facets_get_their_own_axes(scalar_table):
    spec = PlotSpec(
        measures=["StepLength"],
        roles={"subject": Role.X, "session": Role.FACET, "trial": Role.FREE},
        kind=PlotKind.BOX,
    )
    payload = render_plotly(resolve(spec, scalar_table)[0])
    assert "xaxis" in payload["layout"]
    assert "xaxis2" in payload["layout"]


def test_plotly_legend_entry_appears_once_per_level(series_table):
    """A 24-trial line plot must not produce a 24-entry legend."""
    spec = PlotSpec(
        measures=["Signal"],
        roles={"session": Role.COLOR, "subject": Role.FREE, "trial": Role.FREE},
        kind=PlotKind.LINE,
    )
    payload = render_plotly(resolve(spec, series_table)[0])
    shown = [t for t in payload["data"] if t.get("showlegend")]
    assert len(shown) == 2


# --- facet grid layout -----------------------------------------------------


@pytest.fixture
def wrapped_grid(struct_table):
    """A facet grid whose last row is partial — 3 fields wrapped 2 wide."""
    from scistackplot import FacetOptions

    return PlotSpec(
        measures=["RawEMG"],
        roles={"ColName": Role.FACET, "subject": Role.COLOR, "trial": Role.FREE},
        kind=PlotKind.BAND,
        facet=FacetOptions(wrap=2),
    )


def test_panel_titles_show_the_value_not_the_key(struct_table, wrapped_grid):
    resolved = resolve(wrapped_grid, struct_table)[0]
    assert {p.title for p in resolved.panels} == {"RHAM", "RTA", "LMG"}
    assert all("ColName=" not in p.title for p in resolved.panels)


def test_plotly_ships_its_grid_shape(struct_table, wrapped_grid):
    payload = render_plotly(resolve(wrapped_grid, struct_table)[0])
    # 3 panels wrapped 2 wide -> 2 rows, 2 columns.
    assert payload["layout"]["meta"] == {"rows": 2, "cols": 2}


def test_plotly_ticklabels_only_where_nothing_is_below(struct_table, wrapped_grid):
    """
    The partial-last-row case: with 3 panels in a 2x2 grid, the panel at
    (row 0, col 1) has an EMPTY cell below it, so it keeps its tick labels
    even though it is not on the bottom row.
    """
    payload = render_plotly(resolve(wrapped_grid, struct_table)[0])
    layout = payload["layout"]

    # slots: 1=(0,0) 2=(0,1) 3=(1,0)
    assert layout["xaxis"]["showticklabels"] is False   # (0,0) has (1,0) below
    assert layout["xaxis2"]["showticklabels"] is True   # (0,1) has nothing below
    assert layout["xaxis3"]["showticklabels"] is True   # bottom row


def test_plotly_links_shared_axes(struct_table, wrapped_grid):
    payload = render_plotly(resolve(wrapped_grid, struct_table)[0])
    assert payload["layout"]["xaxis2"]["matches"] == "x"
    assert payload["layout"]["yaxis2"]["matches"] == "y"


def test_plotly_rows_do_not_overlap(struct_table, wrapped_grid):
    """Each row's cell must clear the one below with room for tick labels."""
    layout = render_plotly(resolve(wrapped_grid, struct_table)[0])["layout"]
    top_row = layout["yaxis"]["domain"]
    bottom_row = layout["yaxis3"]["domain"]

    assert bottom_row[1] < top_row[0]
    assert top_row[0] - bottom_row[1] >= 0.1


def test_matplotlib_keeps_ticklabels_above_an_empty_cell(struct_table, wrapped_grid):
    """
    3 panels in a 2x2 grid: the one at (0, 1) has an EMPTY cell below it, so it
    is the bottom of its own column and must keep BOTH its x label and its tick
    labels — sharex would otherwise strip them from the whole top row.
    """
    resolved = resolve(wrapped_grid, struct_table)[0]
    figure = render_matplotlib(resolved)

    labelled = [
        ax for ax in figure.axes if ax.get_visible() and ax.get_xlabel()
    ]
    # (0, 1) and (1, 0) are both bottom-of-column; (0, 0) is not.
    assert len(labelled) == 2
    for ax in labelled:
        assert any(t.get_visible() for t in ax.get_xticklabels())
    matplotlib.pyplot.close(figure)


# --- rule-defined facet layout ---------------------------------------------


def _layout_spec(rows=(), cols=()):
    from scistackplot import FacetOptions
    from scistackplot.spec import MatchOp, Matcher

    return PlotSpec(
        measures=["RawEMG"],
        roles={"ColName": Role.FACET, "subject": Role.COLOR, "trial": Role.FREE},
        kind=PlotKind.BAND,
        facet=FacetOptions(
            rows=[Matcher(op=MatchOp(op), value=v) for op, v in rows],
            cols=[Matcher(op=MatchOp(op), value=v) for op, v in cols],
        ),
    )


def test_row_rules_place_panels_by_name(struct_table):
    """Left/right muscles as two rows — the EMG arrangement."""
    spec = _layout_spec(rows=[("starts_with", "R"), ("starts_with", "L")])
    resolved = resolve(spec, struct_table)[0]

    by_title = {p.title: p for p in resolved.panels}
    assert by_title["RHAM"].grid_row == 0
    assert by_title["RTA"].grid_row == 0
    assert by_title["LMG"].grid_row == 1
    assert resolved.grid_rows == 2
    # Two R muscles flow across that row.
    assert {by_title["RHAM"].grid_col, by_title["RTA"].grid_col} == {0, 1}


def test_column_rules_place_panels_by_name(struct_table):
    spec = _layout_spec(cols=[("ends_with", "HAM"), ("ends_with", "TA")])
    resolved = resolve(spec, struct_table)[0]

    by_title = {p.title: p for p in resolved.panels}
    assert by_title["RHAM"].grid_col == 0
    assert by_title["RTA"].grid_col == 1
    # LMG matches neither: it lands in the trailing "other" column, not nowhere.
    assert by_title["LMG"].grid_col == 2
    assert resolved.col_labels[-1] == "other"


def test_rules_on_both_axes_make_a_true_grid(struct_table):
    spec = _layout_spec(
        rows=[("starts_with", "R"), ("starts_with", "L")],
        cols=[("ends_with", "HAM"), ("ends_with", "TA"), ("ends_with", "MG")],
    )
    resolved = resolve(spec, struct_table)[0]
    by_title = {p.title: p for p in resolved.panels}

    assert (by_title["RHAM"].grid_row, by_title["RHAM"].grid_col) == (0, 0)
    assert (by_title["RTA"].grid_row, by_title["RTA"].grid_col) == (0, 1)
    assert (by_title["LMG"].grid_row, by_title["LMG"].grid_col) == (1, 2)
    assert (resolved.grid_rows, resolved.grid_cols) == (2, 3)


def test_regex_rules_are_supported(struct_table):
    spec = _layout_spec(rows=[("regex", "^R"), ("regex", "^L")])
    resolved = resolve(spec, struct_table)[0]
    by_title = {p.title: p for p in resolved.panels}
    assert by_title["LMG"].grid_row == 1


def test_an_invalid_regex_does_not_break_the_figure(struct_table):
    """The user is still typing; a half-written pattern must not raise."""
    spec = _layout_spec(rows=[("regex", "[unclosed")])
    resolved = resolve(spec, struct_table)[0]
    assert len(resolved.panels) == 3


def test_rule_layout_survives_a_spec_round_trip(struct_table):
    spec = _layout_spec(rows=[("starts_with", "R")], cols=[("ends_with", "MG")])
    restored = PlotSpec.from_json(spec.to_json())
    assert restored.facet.rows[0].value == "R"
    assert restored.facet.cols[0].op.value == "ends_with"


# --- one rule for tick labels and axis titles ------------------------------


def test_x_ticklabels_and_title_follow_the_same_rule(struct_table, wrapped_grid):
    """Item 1: they used to drift — the title obeyed the rule, ticks did not."""
    layout = render_plotly(resolve(wrapped_grid, struct_table)[0])["layout"]
    for slot in ("", "2", "3"):
        axis = layout[f"xaxis{slot}"]
        assert axis["showticklabels"] is bool(axis["title"]["text"])


def test_matplotlib_ticklabels_and_title_follow_the_same_rule(
    struct_table, wrapped_grid
):
    figure = render_matplotlib(resolve(wrapped_grid, struct_table)[0])
    for ax in figure.axes:
        if not ax.get_visible():
            continue
        ticks_shown = any(t.get_visible() for t in ax.get_xticklabels())
        assert ticks_shown is bool(ax.get_xlabel())
    matplotlib.pyplot.close(figure)
