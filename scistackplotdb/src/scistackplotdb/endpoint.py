"""
Turning a ``PlotSpec`` into a pipeline endpoint.

The GUI's "Add to pipeline" produces two things: a ``plot_`` function (generated
by ``scistackplot.codegen`` — literal seaborn, no runtime dependency on this
package) and the ``for_each`` call that runs it. This module owns the second
half, and with it the one translation that has to be exactly right:

    Role.ITERATE  ->  a for_each iteration keyword

Interactively, ITERATE fans out through a pandas ``groupby`` inside
``resolve()``. In the pipeline it fans out through ``for_each`` + ``PathOutput``.
If those two ever disagree, the exported pipeline is not what the user
previewed — the worst failure mode this layer has, and what
``tests/test_fanout_parity.py`` exists to prevent.

Everything else the endpoint needs already exists in scidb: ``finalized``,
artifact stamping, ``skip_computed`` and ``scidb report`` are untouched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from scistacklog import Log
from scistackplot import LongTable, PlotSpec, default_function_name
from scistackplot import generate_plot_function

LAYER = "scistackplotdb"


@dataclass
class EndpointCode:
    """Generated source for one plotting endpoint."""

    function_name: str
    function_source: str
    foreach_source: str
    iterate_keys: list[str] = field(default_factory=list)
    path_template: str = ""
    output_variable: str = ""

    @property
    def source(self) -> str:
        """Function and call together, ready to append to a pipeline module."""
        return f"{self.function_source}\n\n{self.foreach_source}"


def generate_endpoint(
    spec: PlotSpec,
    table: LongTable,
    *,
    input_variable: str,
    function_name: str | None = None,
    output_variable: str | None = None,
    path_template: str | None = None,
    finalized: bool = True,
    x_variable: str | None = None,
) -> EndpointCode:
    """
    Generate the ``plot_`` function and its ``for_each`` call.

    ``input_variable`` is the scidb variable type supplying the data;
    ``x_variable`` is the optional second measure for an x–y scatter.
    """
    name = function_name or default_function_name(spec)
    iterate_keys = list(spec.iterate_factors)
    output = output_variable or default_output_variable(input_variable)
    template = path_template or default_path_template(name, iterate_keys)

    function_source = generate_plot_function(spec, table, function_name=name)
    foreach_source = _foreach_call(
        function_name=name,
        input_variable=input_variable,
        x_variable=x_variable,
        output_variable=output,
        path_template=template,
        iterate_keys=iterate_keys,
        finalized=finalized,
    )

    Log.info(
        "generated endpoint %s: input=%s output=%s iterate=%s finalized=%s",
        name,
        input_variable,
        output,
        iterate_keys or "none",
        finalized,
        layer=LAYER,
    )
    return EndpointCode(
        function_name=name,
        function_source=function_source,
        foreach_source=foreach_source,
        iterate_keys=iterate_keys,
        path_template=template,
        output_variable=output,
    )


def default_output_variable(input_variable: str) -> str:
    """``StepLength`` -> ``StepLengthFigure``."""
    return f"{input_variable}Figure"


def default_path_template(function_name: str, iterate_keys: list[str]) -> str:
    """
    Build a PathOutput template that cannot collide.

    Every ITERATE key goes into the filename. Omitting one would make two
    figures write the same file; for schema keys scidb treats that as
    pre-existing overwrite behavior (no error), and for variants its collision
    guard raises before anything renders. Including them all avoids both.
    """
    slug = re.sub(r"^plot_", "", function_name)
    parts = "".join(f"_{{{key}}}" for key in iterate_keys)
    return f"plots/{slug}{parts}.png"


def _foreach_call(
    *,
    function_name: str,
    input_variable: str,
    x_variable: str | None,
    output_variable: str,
    path_template: str,
    iterate_keys: list[str],
    finalized: bool,
) -> str:
    inputs = [f'        "df": {input_variable},']
    table_inputs = ["df"]
    if x_variable:
        inputs.append(f'        "df_x": {x_variable},')
        table_inputs.append("df_x")
    inputs.append(f'        "filename": PathOutput("{path_template}"),')

    lines = [
        "for_each(",
        f"    {function_name},",
        "    inputs={",
        *inputs,
        "    },",
        f"    outputs=[{output_variable}],",
        # A plot_ function receives the long-format table (schema keys as
        # columns) — as_table defaults ON only for stat_, so say it explicitly.
        f"    as_table={table_inputs!r},",
        f"    finalized={finalized},",
    ]
    for key in iterate_keys:
        # [] means "every value present" — the same all-values resolution
        # scifor applies to an empty iteration list.
        lines.append(f"    {key}=[],")
    lines.append(")")
    return "\n".join(lines)


def required_declarations(code: EndpointCode) -> list[str]:
    """
    Variable types the generated call needs that may not exist yet.

    The GUI declares these through the normal entity-declaration path before
    writing the code, so a generated endpoint never references an undeclared
    type.
    """
    return [code.output_variable]
