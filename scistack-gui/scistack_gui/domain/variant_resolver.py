"""
Pure variant resolution, deduplication, and pending-constant merging.

Builds the list of for_each targets from DB variants, manual edges, and
pending constant values. No I/O — works entirely on plain Python data.
"""

from __future__ import annotations

import ast
import logging
from itertools import product as _product

logger = logging.getLogger(__name__)


def build_inferred_variants(
    input_types: dict[str, list[str]],
    output_types: list[str],
    inferred_constants: dict[str, list],
) -> list[dict]:
    """Build synthetic variants from edge-inferred inputs/outputs/constants.

    Used when a function has no DB history yet (first run).

    Args:
        input_types: {param_name: [variable_type_names]}.
        output_types: List of output variable type names.
        inferred_constants: {const_name: [typed_values]} — cross-product is taken.

    Returns:
        List of variant dicts with input_types, output_type, constants.
    """
    logger.info(
        "[variant_resolver] build_inferred_variants: building variants from %d input(s), %d output(s), %d constant(s)",
        len(input_types),
        len(output_types),
        len(inferred_constants),
    )

    if inferred_constants:
        const_names_list = sorted(inferred_constants.keys())
        const_value_lists = [inferred_constants[c] for c in const_names_list]
        logger.debug(
            "[variant_resolver] computing cross-product of %d constant(s)",
            len(const_names_list),
        )
        variants = []
        for combo in _product(*const_value_lists):
            constants = dict(zip(const_names_list, combo, strict=False))
            for out in output_types:
                variants.append(
                    {
                        "input_types": input_types,
                        "output_type": out,
                        "constants": constants,
                    }
                )
        logger.info(
            "[variant_resolver] build_inferred_variants complete: built %d variant(s) from cross-product",
            len(variants),
        )
        return variants
    else:
        variants = [
            {"input_types": input_types, "output_type": out, "constants": {}}
            for out in output_types
        ]
        logger.info(
            "[variant_resolver] build_inferred_variants complete: built %d variant(s) (no constants)",
            len(variants),
        )
        return variants


def filter_variants(
    fn_variants: list[dict],
    selected_variants: list[dict],
) -> list[dict]:
    """Filter fn_variants to only those matching any of the selected variants.

    Falls back to all fn_variants if no match is found.
    """
    logger.info(
        "[variant_resolver] filter_variants: filtering %d variant(s) using %d selected variant(s)",
        len(fn_variants),
        len(selected_variants),
    )
    targets = [
        v
        for v in fn_variants
        if any(constants_match(v["constants"], sel) for sel in selected_variants)
    ]
    if not targets:
        logger.debug(
            "[variant_resolver] filter_variants: no match for selected=%r — returning all %d variants",
            selected_variants,
            len(fn_variants),
        )
    else:
        logger.info(
            "[variant_resolver] filter_variants complete: %d variant(s) matched",
            len(targets),
        )
    return targets if targets else fn_variants


def deduplicate_variants(targets: list[dict]) -> list[dict]:
    """Deduplicate variants by their constants dict.

    list_pipeline_variants may return duplicates across different output types
    for the same function.
    """
    logger.info(
        "[variant_resolver] deduplicate_variants: deduplicating %d variant(s)",
        len(targets),
    )
    seen: set[tuple] = set()
    unique: list[dict] = []
    for v in targets:
        key = tuple(sorted(v["constants"].items()))
        if key not in seen:
            seen.add(key)
            unique.append(v)
    duplicates_removed = len(targets) - len(unique)
    if duplicates_removed > 0:
        logger.debug("[variant_resolver] removed %d duplicate(s)", duplicates_removed)
    logger.info(
        "[variant_resolver] deduplicate_variants complete: %d unique variant(s)",
        len(unique),
    )
    return unique


def merge_pending_constants(
    fn_variants: list[dict],
    pending_constants: dict[str, set[str]],
) -> list[dict]:
    """Add synthetic targets for pending constant values not yet in the DB.

    For each pending value, cross-products with existing combinations of all
    other constants. The pending value itself is stored as a string, so we
    coerce it back to a Python literal where possible.

    Args:
        fn_variants: Current list of variant dicts (may be mutated list from
            deduplicate_variants).
        pending_constants: {constant_name: {pending_value_str, ...}}.

    Returns:
        Extended list of unique variant targets (appends to the input list).
    """
    logger.info(
        "[variant_resolver] merge_pending_constants: merging pending constants into %d variant(s)",
        len(fn_variants),
    )

    if not fn_variants or not pending_constants:
        logger.debug(
            "[variant_resolver] no variants or pending constants, skipping merge"
        )
        return fn_variants

    fn_const_names = {k for v in fn_variants for k in v["constants"]}
    pending_for_fn = {
        k: vals for k, vals in pending_constants.items() if k in fn_const_names
    }

    if not pending_for_fn:
        logger.debug(
            "[variant_resolver] no pending constants match function's constant parameters"
        )
        return fn_variants

    logger.info(
        "[variant_resolver] adding pending values for %d constant(s): %s",
        len(pending_for_fn),
        sorted(pending_for_fn),
    )

    existing_keys = {
        tuple(sorted((k, str(v)) for k, v in t["constants"].items()))
        for t in fn_variants
    }
    template = fn_variants[0]
    initial_variant_count = len(fn_variants)

    for const_name, pending_values in pending_for_fn.items():
        logger.debug(
            "[variant_resolver] processing %d pending value(s) for constant '%s'",
            len(pending_values),
            const_name,
        )
        # Collect unique combinations of other constants (typed).
        other_seen: set[tuple] = set()
        other_combos: list[dict] = []
        for v in fn_variants:
            other = {k: val for k, val in v["constants"].items() if k != const_name}
            okey = tuple(sorted((k, str(val)) for k, val in other.items()))
            if okey not in other_seen:
                other_seen.add(okey)
                other_combos.append(other)

        for pval_str in pending_values:
            pval = _coerce(pval_str)
            for other in other_combos:
                new_constants = dict(other)
                new_constants[const_name] = pval
                key = tuple(sorted((k, str(v)) for k, v in new_constants.items()))
                if key not in existing_keys:
                    existing_keys.add(key)
                    fn_variants.append(
                        {
                            "input_types": template["input_types"],
                            "constants": new_constants,
                            "output_type": template["output_type"],
                        }
                    )

    added_variant_count = len(fn_variants) - initial_variant_count
    logger.info(
        "[variant_resolver] merge_pending_constants complete: added %d variant(s), total %d",
        added_variant_count,
        len(fn_variants),
    )
    return fn_variants


def build_schema_kwargs(
    schema_level: list[str] | None,
    all_schema_keys: list[str],
    schema_filter: dict[str, list] | None,
    distinct_values: dict[str, list],
) -> dict[str, list]:
    """Build the schema kwargs dict for for_each.

    Args:
        schema_level: Which schema keys to iterate; None = all.
        all_schema_keys: All schema keys from the DB.
        schema_filter: {key: [selected values]}; None = all.
        distinct_values: {key: [all_values]} from db.distinct_schema_values.

    Returns:
        {schema_key: [values_to_iterate]}.
    """
    logger.info(
        "[variant_resolver] build_schema_kwargs: building schema kwargs for iteration"
    )
    iterate_keys = schema_level if schema_level is not None else list(all_schema_keys)
    logger.debug(
        "[variant_resolver] iterating over %d schema key(s): %s",
        len(iterate_keys),
        iterate_keys,
    )

    if schema_filter:
        logger.debug(
            "[variant_resolver] applying schema filter with %d key(s)",
            len(schema_filter),
        )
        schema_kwargs = {}
        for key in iterate_keys:
            if key in schema_filter and schema_filter[key]:
                schema_kwargs[key] = schema_filter[key]
                logger.debug(
                    "[variant_resolver] schema key '%s': using %d filtered value(s)",
                    key,
                    len(schema_filter[key]),
                )
            else:
                schema_kwargs[key] = distinct_values.get(key, [])
                logger.debug(
                    "[variant_resolver] schema key '%s': using %d distinct value(s)",
                    key,
                    len(distinct_values.get(key, [])),
                )
        logger.info(
            "[variant_resolver] build_schema_kwargs complete: %d schema key(s) configured",
            len(schema_kwargs),
        )
        return schema_kwargs
    else:
        logger.debug("[variant_resolver] no schema filter, using all distinct values")
        schema_kwargs = {key: distinct_values.get(key, []) for key in iterate_keys}
        logger.info(
            "[variant_resolver] build_schema_kwargs complete: %d schema key(s) configured",
            len(schema_kwargs),
        )
        return schema_kwargs


def constants_match(db_constants: dict, selected: dict) -> bool:
    """True if selected is a subset of db_constants (value equality as strings)."""
    return all(str(db_constants.get(k)) == str(v) for k, v in selected.items())


def compute_call_id(
    function_name: str,
    target: dict,
    distribute: bool = False,
    as_table=None,
) -> str | None:
    """Deterministic call_id for a target, matching scidb's real
    ForEachConfig.to_version_keys() shape exactly (see
    scidb.foreach_config), so a combo hidden before it's ever run lands on
    the same id as the real record it eventually produces if it is run.

    Returns None (fail-safe: "unknown, don't filter") for a target with an
    unresolved multi-type input (EachOf) — there's no single call site to
    hash yet. Hiding a specific combo is scoped to constant-value axes only
    (see plan-combo-hiding.md).
    """
    from scidb.foreach_config import call_id_from_version_keys

    inputs: dict = {}
    for param, type_val in target.get("input_types", {}).items():
        if isinstance(type_val, list):
            if len(type_val) != 1:
                return None
            inputs[param] = type_val[0]
        else:
            inputs[param] = type_val

    keys: dict = {
        "__fn": function_name,
        "__inputs": inputs,
        "__constants": dict(target.get("constants", {})),
    }
    if distribute:
        keys["__distribute"] = True
    if as_table:
        keys["__as_table"] = sorted(as_table) if isinstance(as_table, list) else True
    return call_id_from_version_keys(keys)


def hidden_call_ids_for_fn(hidden_node_ids: set[str], function_name: str) -> set[str]:
    """Hidden ``fn__{function_name}__{call_id}`` ids for one function, as
    bare call_ids (the id shape hiding a whole node already uses — see
    graph_builder.filter_hidden)."""
    from scistack_gui.domain.graph_builder import parse_fn_node_id

    out: set[str] = set()
    for nid in hidden_node_ids:
        parsed = parse_fn_node_id(nid)
        if parsed is not None and parsed[0] == function_name:
            out.add(parsed[1])
    return out


def resolve_target_call_id(
    function_name: str,
    target: dict,
    pending_constant_names: set[str],
    distribute: bool = False,
    as_table=None,
) -> str | None:
    """A target's EFFECTIVE call_id — reuses its real DB-history ``call_id``
    directly, except when ``apply_pending_overrides`` may have changed its
    identity (any of its constants share a name with a staged pending
    value), in which case it's never safe to trust a possibly-stale
    ``call_id`` field and it's recomputed fresh via ``compute_call_id``.
    """
    touched = bool(pending_constant_names & set(target.get("constants", {})))
    cid = target.get("call_id") if (not touched and target.get("call_id")) else None
    if cid is None:
        cid = compute_call_id(function_name, target, distribute=distribute, as_table=as_table)
    return cid


def filter_hidden_targets(
    targets: list[dict],
    function_name: str,
    hidden_call_ids: set[str],
    pending_constants: dict,
    distribute: bool = False,
    as_table=None,
) -> list[dict]:
    """Drop targets whose effective call_id (see ``resolve_target_call_id``)
    is hidden."""
    if not hidden_call_ids:
        return targets
    pending_names = set(pending_constants or {})
    kept = []
    for t in targets:
        cid = resolve_target_call_id(
            function_name, t, pending_names, distribute=distribute, as_table=as_table
        )
        if cid is not None and cid in hidden_call_ids:
            continue
        kept.append(t)
    return kept


def filter_disconnected_targets(
    targets: list[dict],
    function_name: str,
    hidden_edge_ids: set[str],
) -> list[dict]:
    """Drop targets whose WIRING (function name + variable input/output
    types — not constants, see graph_builder.wiring_id) has a user-hidden
    required inbound edge (graph_builder.hide_edge). Unlike
    ``filter_hidden_targets`` (one constant-value combo at a time), this
    drops every target sharing the disconnected wiring, since a missing
    required input makes the WHOLE wiring un-runnable, not just one
    variant of it. Each execution-service target IS its own call site, so
    this checks candidate inbound edge ids directly per target rather than
    going through graph_builder.hidden_wirings' multi-call-site grouping
    (that path is for the GUI graph endpoint, which has a full agg)."""
    if not hidden_edge_ids or not targets:
        return targets
    from scistack_gui.domain.graph_builder import inbound_edge_candidates, wiring_id

    kept = []
    for t in targets:
        input_types = t.get("input_types", {})
        wid = wiring_id(function_name, input_types, {t.get("output_type")})
        var_types: list[str] = []
        for tv in input_types.values():
            if isinstance(tv, (list, set, tuple)):
                var_types.extend(tv)
            else:
                var_types.append(tv)
        candidates = inbound_edge_candidates(
            function_name,
            wid,
            var_types=var_types,
            const_names=t.get("constants", {}).keys(),
        )
        if hidden_edge_ids.intersection(candidates):
            continue
        kept.append(t)
    return kept


def _coerce(s: str):
    """Coerce a string to a Python literal if possible."""
    try:
        return ast.literal_eval(s)
    except (ValueError, SyntaxError):
        return s
