"""
The parity test.

``Role.ITERATE`` fans out twice by two different mechanisms: interactively
through a pandas ``groupby`` inside ``resolve()``, and in the pipeline through
``for_each`` + ``PathOutput``. They must produce the same set of figures. If
they ever disagree, the exported pipeline is not what the user previewed —
the worst failure mode this layer has.

This test runs BOTH paths against the same database and compares the figure
sets, rather than asserting on the generated source text (which would pass
happily while the semantics drifted).
"""

from __future__ import annotations

import pytest
from scistackplot import PlotKind, PlotSpec, Role, resolve

from scistackplotdb import ScidbSource, generate_endpoint

pytest.importorskip("seaborn")


def _run_generated(code, tmp_path):
    from scidb import PathOutput, for_each

    from conftest import StepLength, StepLengthFigure

    namespace = {
        "for_each": for_each,
        "PathOutput": PathOutput,
        "StepLength": StepLength,
        "StepLengthFigure": StepLengthFigure,
    }
    exec(compile(code.source, "<generated>", "exec"), namespace)  # noqa: S102
    return sorted(tmp_path.glob("fig_*.png"))


def test_interactive_fanout_matches_pipeline_fanout(seeded, tmp_path):
    source = ScidbSource(seeded)
    table = source.get_table(["StepLength"])
    spec = PlotSpec(
        measures=["StepLength"],
        roles={"subject": Role.ITERATE, "session": Role.X, "trial": Role.FREE},
        kind=PlotKind.BOX,
    )

    interactive = resolve(spec, table)
    code = generate_endpoint(
        spec,
        table,
        input_variable="StepLength",
        path_template=str(tmp_path / "fig_{subject}.png"),
    )
    files = _run_generated(code, tmp_path)

    assert len(files) == len(interactive) == 3
    assert {path.stem.removeprefix("fig_") for path in files} == {
        figure.figure_key["subject"] for figure in interactive
    }


def test_two_iterate_keys_fan_out_the_same_both_ways(seeded, tmp_path):
    source = ScidbSource(seeded)
    table = source.get_table(["StepLength"])
    spec = PlotSpec(
        measures=["StepLength"],
        roles={
            "subject": Role.ITERATE,
            "session": Role.ITERATE,
            "trial": Role.X,
        },
        kind=PlotKind.SCATTER,
    )

    interactive = resolve(spec, table)
    code = generate_endpoint(
        spec,
        table,
        input_variable="StepLength",
        path_template=str(tmp_path / "fig_{subject}_{session}.png"),
    )
    files = _run_generated(code, tmp_path)

    assert len(interactive) == 6  # 3 subjects x 2 sessions
    assert len(files) == len(interactive)


def test_no_iterate_produces_exactly_one_figure_both_ways(seeded, tmp_path):
    source = ScidbSource(seeded)
    table = source.get_table(["StepLength"])
    spec = PlotSpec(
        measures=["StepLength"],
        roles={"session": Role.X, "subject": Role.COLOR, "trial": Role.FREE},
        kind=PlotKind.BOX,
    )

    interactive = resolve(spec, table)
    code = generate_endpoint(
        spec,
        table,
        input_variable="StepLength",
        path_template=str(tmp_path / "fig_all.png"),
    )
    files = _run_generated(code, tmp_path)

    assert len(interactive) == 1
    assert len(files) == 1
