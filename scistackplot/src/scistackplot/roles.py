"""
Role assignment: defaults, completion, and validation.

Every factor carries exactly one :class:`~scistackplot.spec.Role`. Enforcing
that here — once, in the library — is what lets the GUI be a thin renderer of
whatever ``capability.available_plots`` returns instead of re-deriving the
invariant in TypeScript.
"""

from __future__ import annotations

import math

from .shape import Shape
from .spec import SINGLE_ASSIGNMENT_ROLES, PlotSpec, Role, VariantPolicy
from .table import LongTable


class RoleError(ValueError):
    """An invalid role assignment. Message names the one-line fix."""


def default_roles(table: LongTable, measure: str | None = None) -> dict[str, Role]:
    """
    A reasonable starting assignment for a freshly opened table.

    Mirrors the proof of concept's opening state (it preselected a factor for
    the x axis and left the rest available) but adds one thing it had no
    concept of: a variant factor defaults to COLOR so that two pipeline
    variants are visibly separated on first render rather than silently
    overplotted.
    """
    measure = measure or (table.measure_names[0] if table.measures else None)
    shape = table.shape_of(measure) if measure else Shape.UNKNOWN

    roles: dict[str, Role] = {}
    variants = [f for f in table.factors if f.is_variant and len(f.levels) > 1]
    fields = [f for f in table.factors if f.is_field]
    plain = [f for f in table.factors if not f.is_variant and not f.is_field]

    # A struct/dict variable's fields are parallel quantities (13 muscles, say),
    # not levels of one condition: one subplot each, never one overplotted axis.
    for factor in fields:
        roles[factor.name] = Role.FACET

    if variants:
        roles[variants[0].name] = Role.COLOR
        # FACET, not FREE, for the rest. A variant left FREE is pooled, which
        # `validate` refuses outright — so defaulting extras to FREE handed the
        # user an error instead of a plot the moment a table carried two variant
        # factors at once (e.g. a filter cutoff AND two versions of the
        # producing function's source). Faceting keeps them separated, which is
        # the same promise COLOR makes for the first one.
        for extra in variants[1:]:
            roles[extra.name] = Role.FACET

    # For 1-D measures the x axis is the within-observation index, so no factor
    # takes X; the leading factor becomes the colour channel instead.
    if shape is Shape.SERIES_1D:
        for factor in plain:
            if Role.COLOR not in roles.values():
                roles[factor.name] = Role.COLOR
            else:
                roles[factor.name] = Role.FREE
    else:
        for position, factor in enumerate(plain):
            if position == 0:
                roles[factor.name] = Role.X
            elif Role.COLOR not in roles.values():
                roles[factor.name] = Role.COLOR
            else:
                roles[factor.name] = Role.FREE

    return roles


def complete_roles(spec: PlotSpec, table: LongTable) -> dict[str, Role]:
    """
    Every factor in ``table`` mapped to a role.

    Factors the spec doesn't mention default to FREE — they stay in the frame
    as replicate rows, which is the conservative choice: it never silently
    drops or averages data the user didn't ask to drop or average.
    """
    roles = {name: role for name, role in spec.roles.items() if table.has_factor(name)}
    for factor in table.factors:
        roles.setdefault(factor.name, Role.FREE)
    return roles


def validate(spec: PlotSpec, table: LongTable) -> None:
    """Raise :class:`RoleError` if the spec cannot be resolved against the table."""
    # --- measures exist -------------------------------------------------
    if not spec.measures:
        raise RoleError("PlotSpec.measures is empty — name at least a y measure.")
    for measure in spec.measures:
        if measure not in table.measure_names:
            raise RoleError(
                f"Measure {measure!r} is not in the table. "
                f"Available measures: {table.measure_names}"
            )
    if len(spec.measures) > 2:
        raise RoleError(
            f"At most 2 measures are supported (y, and optionally x); "
            f"got {len(spec.measures)}: {spec.measures}"
        )

    # --- roles name real factors ----------------------------------------
    unknown = [name for name in spec.roles if not table.has_factor(name)]
    if unknown:
        raise RoleError(
            f"Roles assigned to unknown factor(s) {unknown}. "
            f"Table factors: {table.factor_names}"
        )

    # --- single-assignment channels -------------------------------------
    for role in SINGLE_ASSIGNMENT_ROLES:
        holders = spec.factors_with_role(role)
        if len(holders) > 1:
            raise RoleError(
                f"Role {role} accepts one factor but got {holders}. "
                f"Move all but one to 'facet' or 'free'."
            )

    shape = table.shape_of(spec.y_measure)

    # --- x-axis ownership ------------------------------------------------
    x_holder = spec.first_with_role(Role.X)
    if spec.x_measure is not None and x_holder is not None:
        raise RoleError(
            f"Measure {spec.x_measure!r} already supplies the x axis, so factor "
            f"{x_holder!r} cannot also hold role 'x'. Give it 'color', a facet "
            f"role, or 'free'."
        )
    if shape is Shape.SERIES_1D and x_holder is not None and spec.x_measure is None:
        raise RoleError(
            f"Measure {spec.y_measure!r} is 1-D, so the x axis is its "
            f"within-observation index ({spec.index_column or 'index'}); factor "
            f"{x_holder!r} cannot hold role 'x'. Give it 'color', a facet role, "
            f"or 'free'."
        )
    if shape is Shape.MATRIX_2D and x_holder is not None:
        raise RoleError(
            f"Measure {spec.y_measure!r} is 2-D (heatmap); its axes come from the "
            f"matrix itself, so factor {x_holder!r} cannot hold role 'x'."
        )

    # --- variants must not be pooled by accident -------------------------
    if spec.variant_policy is VariantPolicy.FACET:
        pooled = [
            f.name
            for f in table.variant_factors
            if len(f.levels) > 1
            and spec.roles.get(f.name, Role.FREE) in (Role.FREE, Role.AGGREGATE)
        ]
        if pooled:
            raise RoleError(
                f"Variant factor(s) {pooled} would be pooled: their levels are "
                f"different pipeline variants, not replicates, so averaging or "
                f"overplotting them silently mixes results. Assign them "
                f"'color'/'facet'/'iterate', pin one with "
                f"variant_policy='pin', or opt in with variant_policy='pool'."
            )
    if spec.variant_policy is VariantPolicy.PIN and not spec.pinned_variant:
        raise RoleError(
            "variant_policy='pin' requires PlotSpec.pinned_variant to name the "
            "variant to keep, e.g. {'bandpass.low_hz': 20}."
        )

    # --- 1-D needs an index ---------------------------------------------
    if shape is Shape.SERIES_1D and spec.index_column:
        if (
            spec.index_column not in table.frame.columns
            and spec.index_column != table.index_column
        ):
            raise RoleError(
                f"index_column {spec.index_column!r} is neither a column of the "
                f"table nor its declared index column ({table.index_column!r})."
            )


def default_spec(table: LongTable, measure: str | None = None) -> PlotSpec:
    """
    The spec a table opens on: default roles, the matching default kind, and a
    facet wrap wide enough for however many fields the measure has.

    Lives here rather than in the GUI so the panel and a library caller open on
    the same figure (CLAUDE.md NOTE 3).
    """
    from .capability import default_plot
    from .spec import FacetOptions, PlotKind, VariantPolicy

    measure = measure or (table.measure_names[0] if table.measures else None)
    if measure is None:
        raise RoleError("This table has no measures to plot.")

    roles = default_roles(table, measure)
    kind = default_plot(table.shape_of(measure), roles) or PlotKind.SCATTER

    # A 13-muscle struct wants a grid, not a 13-wide strip of subplots.
    facet_levels = max(
        (len(f.levels) for f in table.factors if roles.get(f.name) is Role.FACET),
        default=0,
    )
    wrap = min(4, math.ceil(math.sqrt(facet_levels))) if facet_levels > 3 else None

    # When the source can say which rows are current, open on those. A scidb
    # variable whose function was edited holds records from both the old and
    # the new code; showing all of them at once answers a question nobody
    # asked, and showing an arbitrary one is how the wrong data gets plotted.
    # This is a starting point, not a lock — clearing variant_policy brings
    # every version back, and the pinned factor stays in the table either way.
    policy = VariantPolicy.PIN if table.default_pin else VariantPolicy.FACET

    return PlotSpec(
        measures=[measure],
        roles=roles,
        kind=kind,
        facet=FacetOptions(wrap=wrap),
        variant_policy=policy,
        pinned_variant=dict(table.default_pin) if table.default_pin else None,
    )
