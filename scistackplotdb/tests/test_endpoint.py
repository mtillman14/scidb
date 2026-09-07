"""Endpoint generation: spec -> plot_ function + for_each call."""

from __future__ import annotations

import pytest
from scistackplot import PlotKind, PlotSpec, Role

from scistackplotdb import ScidbSource, default_path_template, generate_endpoint

pytest.importorskip("seaborn")


@pytest.fixture
def table(seeded):
    return ScidbSource(seeded).get_table(["StepLength"])


@pytest.fixture
def iterating_spec():
    return PlotSpec(
        measures=["StepLength"],
        roles={"subject": Role.ITERATE, "session": Role.X, "trial": Role.FREE},
        kind=PlotKind.BOX,
    )


def test_iterate_roles_become_foreach_keywords(table, iterating_spec):
    code = generate_endpoint(iterating_spec, table, input_variable="StepLength")

    assert code.iterate_keys == ["subject"]
    assert "subject=[]," in code.foreach_source
    # Non-iterated keys stay as DataFrame columns (decision D2) — they must NOT
    # appear as iteration keywords.
    assert "session=[]" not in code.foreach_source
    assert "trial=[]" not in code.foreach_source


def test_plot_input_is_passed_as_a_table(table, iterating_spec):
    """plot_ does not default as_table on (only stat_ does), so say it."""
    code = generate_endpoint(iterating_spec, table, input_variable="StepLength")
    assert "as_table=['df']" in code.foreach_source


def test_generated_call_is_finalized_by_default(table, iterating_spec):
    code = generate_endpoint(iterating_spec, table, input_variable="StepLength")
    assert "finalized=True" in code.foreach_source


def test_draft_mode_is_available(table, iterating_spec):
    code = generate_endpoint(
        iterating_spec, table, input_variable="StepLength", finalized=False
    )
    assert "finalized=False" in code.foreach_source


def test_path_template_names_every_iterate_key():
    """Omitting one would make two figures write the same file."""
    template = default_path_template("plot_steplength", ["subject", "session"])
    assert "{subject}" in template
    assert "{session}" in template


def test_output_variable_defaults_from_the_input(table, iterating_spec):
    code = generate_endpoint(iterating_spec, table, input_variable="StepLength")
    assert code.output_variable == "StepLengthFigure"
    assert "outputs=[StepLengthFigure]" in code.foreach_source


def test_generated_source_compiles(table, iterating_spec):
    code = generate_endpoint(iterating_spec, table, input_variable="StepLength")
    compile(code.source, "<generated>", "exec")


def test_second_measure_is_passed_as_a_second_input(seeded):
    source = ScidbSource(seeded)
    table = source.get_table(["StepLength", "Mass"])
    spec = PlotSpec(
        measures=["StepLength", "Mass"],
        roles={"subject": Role.COLOR, "session": Role.FREE, "trial": Role.FREE},
        kind=PlotKind.SCATTER,
    )

    code = generate_endpoint(
        spec, table, input_variable="StepLength", x_variable="Mass"
    )
    assert '"df_x": Mass,' in code.foreach_source
    assert "as_table=['df', 'df_x']" in code.foreach_source
