"""
Pure edge resolution logic for pipeline graphs.

Resolves input types, output types, and constant names from manual edges
and node metadata. No I/O — works entirely on plain Python data structures.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from scistack_gui.domain.graph_builder import (
    PARAM_ID_PREFIX,
    PATH_INPUT_ID_PREFIX,
    strip_placement,
)

logger = logging.getLogger(__name__)

# Binding kinds. A function parameter is fed by exactly one of these.
BINDING_VARIABLE = "variable"  # ref: [variable type names] (>1 ⇒ EachOf)
BINDING_PATHINPUT = "pathinput"  # ref: declared PathInput name
BINDING_PARAMETER = "parameter"  # ref: declared Parameter name


def variable_binding(type_names: list[str]) -> dict:
    return {"kind": BINDING_VARIABLE, "ref": type_names}


def pathinput_binding(declared_name: str) -> dict:
    return {"kind": BINDING_PATHINPUT, "ref": declared_name}


def parameter_binding(declared_name: str) -> dict:
    return {"kind": BINDING_PARAMETER, "ref": declared_name}


def bindings_of_kind(bindings: dict[str, dict], kind: str) -> dict:
    """``{param_name: ref}`` for one binding kind."""
    return {p: b["ref"] for p, b in (bindings or {}).items() if b["kind"] == kind}


def variable_types_view(bindings: dict[str, dict]) -> dict:
    """``{param_name: type}`` for variable bindings, in the shape the REST of
    the system uses: a bare string when one type is bound, a list only for a
    genuine multi-type (EachOf) input.

    That shape is load-bearing, not cosmetic. ``graph_builder.wiring_id``
    hashes the value as-is, so ``"RawEMG"`` and ``["RawEMG"]`` produce
    DIFFERENT wiring ids — and DB history (``list_pipeline_variants``) always
    spells it bare. A view that returned single-element lists would silently
    compute wiring ids that match nothing, breaking hidden-edge lookup.
    """
    out: dict = {}
    for param, ref in bindings_of_kind(bindings, BINDING_VARIABLE).items():
        if isinstance(ref, list) and len(ref) == 1:
            out[param] = ref[0]
        else:
            out[param] = ref
    return out


def loadable_bindings(bindings: dict[str, dict]) -> dict[str, dict]:
    """The bindings scidb serializes into ``__inputs`` — variables AND
    PathInputs, matching ``ForEachConfig._serialize_inputs``. Parameters are
    excluded: they expand into concrete values that travel in ``__constants``.
    """
    return {
        p: b
        for p, b in (bindings or {}).items()
        if b["kind"] in (BINDING_VARIABLE, BINDING_PATHINPUT)
    }


@dataclass
class ResolvedEdges:
    """Result of scanning edges for a function node.

    ``bindings`` is keyed by the FUNCTION PARAMETER the edge feeds, taken
    from the edge's ``targetHandle`` — never inferred from a node's name or
    from argument position. For PathInputs and Parameters the ``ref`` is the
    SOURCE-DECLARED name of the node feeding it, because the two can
    legitimately differ (a PathInput declared ``test_pi`` filling
    ``read_csv``'s ``filepath_or_buffer``). Callers that need the live object
    look it up in the registry by the declared name and bind it under the
    parameter name.

    **One dict, not three.** These used to be three parallel maps
    (``input_types`` / ``path_input_params`` / ``parameter_params``) and
    every consumer had to remember all of them. The ones that forgot were
    wrong: ``variant_resolver.compute_call_id`` hashed only ``input_types``,
    so its predicted call_id omitted the PathInput that scidb's
    ``ForEachConfig._serialize_inputs`` puts *into* ``__inputs`` — meaning a
    combo hidden before its first run landed on a different id than the
    record the run produced. ``wiring_id`` had the same blind spot, so two
    call sites fed by different PathInputs collapsed onto one canvas node.
    The three names survive below as read-only VIEWS over ``bindings`` for
    display and wire-format consumers; they are not separate state.
    """

    bindings: dict[str, dict]  # param_name → {"kind": ..., "ref": ...}
    output_types: list[str]  # ordered list of output variable labels

    @property
    def input_types(self) -> dict[str, list[str]]:
        """View: ``{param: [variable type names]}`` (display / wire format)."""
        return bindings_of_kind(self.bindings, BINDING_VARIABLE)

    @property
    def path_input_params(self) -> dict[str, str]:
        """View: ``{param: declared PathInput name}``."""
        return bindings_of_kind(self.bindings, BINDING_PATHINPUT)

    @property
    def parameter_params(self) -> dict[str, str]:
        """View: ``{param: declared Parameter name}``."""
        return bindings_of_kind(self.bindings, BINDING_PARAMETER)


def node_id_to_var_label(
    node_id: str,
    existing_node_labels: dict[str, str],
    manual_nodes: dict[str, dict],
) -> str | None:
    """Resolve a node ID to its variable label, or None if not a variable node.

    Args:
        node_id: The node ID to resolve (e.g. "var__RawEMG" or a manual node UUID).
        existing_node_labels: {node_id: label} for all DB-derived nodes already built.
        manual_nodes: {node_id: {"type": ..., "label": ...}} from pipeline_store.
    """
    # DB-derived nodes use the convention "var__TypeName", optionally
    # placement-qualified as "var__TypeName::{pipeline_id}" — strip that
    # suffix before parsing so a placed node still resolves correctly.
    bare_id = strip_placement(node_id)
    if bare_id.startswith("var__"):
        # Check existing DB nodes first.
        if node_id in existing_node_labels:
            return existing_node_labels[node_id]
        # Fall back to extracting from the (bare) ID itself.
        parts = bare_id.split("__")
        if len(parts) >= 2:
            return parts[1]
    # Check the manual_nodes dict.
    meta = manual_nodes.get(node_id)
    if meta and meta.get("type") == "variableNode":
        return meta.get("label")
    return None


def resolve_function_edges(
    fn_node_ids: set[str],
    manual_edges: list[dict],
    manual_nodes: dict[str, dict],
    existing_node_labels: dict[str, str],
) -> ResolvedEdges:
    """Resolve input/output/parameter connections for a function from edges.

    This is the single source of truth for edge inference, replacing the
    duplicated logic that was in api/pipeline.py, api/run.py, and server.py.

    **Every binding comes from an edge.** An incoming edge names the
    parameter it feeds in its ``targetHandle``; an edge that doesn't is
    dropped with a warning rather than guessed at. Two guesses used to live
    here and both produced silently-wrong wiring:

    * unhandled edges were matched to leftover signature params BY POSITION,
      so dropping a connection on a node with many params bound whichever
      param happened to be unfilled;
    * a Parameter edge with an unrecognized handle fell back to the source
      node's LABEL as the param name, which is only right when the declared
      name and the parameter name coincide.

    Args:
        fn_node_ids: Set of node IDs that represent this function
            (e.g. {"fn__my_func", "fn__my_func__abc123"}).
        manual_edges: List of edge dicts with id, source, target,
            sourceHandle, targetHandle.
        manual_nodes: {node_id: {"type": ..., "label": ...}} from pipeline_store.
        existing_node_labels: {node_id: label} for all DB-derived variable nodes.
    """
    bindings: dict[str, dict] = {}
    output_types: list[str] = []
    dropped = 0

    def _bind(param: str, binding: dict, edge: dict) -> None:
        """Bind one parameter, warning if that rebinds it to a different
        source. One handle takes one edge, so this means two edges are
        fighting over the same parameter — silently keeping the last one is
        how wiring bugs hide."""
        existing = bindings.get(param)
        if existing is not None and existing != binding:
            logger.warning(
                "[edge_resolver] parameter %r rebound by edge %s: %s %r "
                "replaces %s %r — the canvas has two edges on one handle",
                param,
                edge.get("id"),
                binding["kind"],
                binding["ref"],
                existing["kind"],
                existing["ref"],
            )
        bindings[param] = binding

    def _drop(edge: dict, why: str) -> None:
        nonlocal dropped
        dropped += 1
        logger.warning(
            "[edge_resolver] ignoring edge %s (%s -> %s, handle=%r): %s — "
            "reconnect it to the parameter's handle on the function node",
            edge.get("id"),
            edge.get("source"),
            edge.get("target"),
            edge.get("targetHandle"),
            why,
        )

    for edge in manual_edges:
        source = edge.get("source", "")
        target = edge.get("target", "")

        if source in fn_node_ids:
            # Edge from this function → a variable node (output).
            var_label = node_id_to_var_label(target, existing_node_labels, manual_nodes)
            if var_label and var_label not in output_types:
                output_types.append(var_label)

        elif target in fn_node_ids:
            # Edge into this function (variable input, PathInput, Parameter).
            th = edge.get("targetHandle") or ""
            bare_source = strip_placement(source)

            # PathInput → fn. The declared name and the parameter it fills
            # routinely differ, so ONLY the handle can say which param this
            # is; build_edges encodes both names in the DB-derived edge id
            # for the same reason (see graph_builder.candidate_edge_id).
            if bare_source.startswith(PATH_INPUT_ID_PREFIX):
                if th.startswith("in__"):
                    param = th[len("in__") :]
                    _bind(
                        param,
                        pathinput_binding(bare_source[len(PATH_INPUT_ID_PREFIX) :]),
                        edge,
                    )
                else:
                    _drop(edge, "PathInput edge carries no 'in__<param>' handle")
                continue

            # Parameter node (Constant and Sweep are one concept and one id
            # prefix since D6) — either DB-derived (param__ prefix) or a
            # still-manual node whose metadata says parameterNode.
            param_label = None
            if bare_source.startswith(PARAM_ID_PREFIX):
                src_meta = manual_nodes.get(source)
                param_label = (
                    src_meta["label"]
                    if src_meta
                    else bare_source[len(PARAM_ID_PREFIX) :]
                )
            else:
                src_meta = manual_nodes.get(source)
                if src_meta and src_meta.get("type") == "parameterNode":
                    param_label = src_meta["label"]

            if param_label is not None:
                if th.startswith(PARAM_ID_PREFIX):
                    # DB-derived Parameter edge: build_edges writes the
                    # constant's own name into BOTH the node id and the
                    # handle, so here the parameter name and the declared
                    # name are the same string by construction.
                    _bind(
                        th[len(PARAM_ID_PREFIX) :],
                        parameter_binding(param_label),
                        edge,
                    )
                elif th.startswith("in__"):
                    _bind(th[len("in__") :], parameter_binding(param_label), edge)
                else:
                    _drop(edge, "Parameter edge carries no parameter handle")
                continue

            # Variable → fn.
            var_label = node_id_to_var_label(source, existing_node_labels, manual_nodes)
            if var_label:
                if th.startswith("in__"):
                    param = th[len("in__") :]
                    # Several variable edges onto one handle is EachOf, not a
                    # conflict — accumulate instead of going through _bind.
                    existing = bindings.get(param)
                    if existing is not None and existing["kind"] == BINDING_VARIABLE:
                        if var_label not in existing["ref"]:
                            existing["ref"].append(var_label)
                    else:
                        _bind(param, variable_binding([var_label]), edge)
                else:
                    _drop(edge, "variable edge carries no 'in__<param>' handle")

    logger.debug(
        "resolve_function_edges: bindings=%s outputs=%s dropped=%d",
        bindings,
        output_types,
        dropped,
    )
    return ResolvedEdges(bindings=bindings, output_types=output_types)


def infer_manual_fn_output_types(
    fn_node_ids: set[str],
    manual_edges: list[dict],
    manual_nodes: dict[str, dict],
    existing_node_labels: dict[str, str],
) -> list[str]:
    """Infer output types from manual edges for a function (no positional matching needed).

    Used by the run path when DB variants exist but the user has rewired outputs.
    """
    output_types: list[str] = []
    for edge in manual_edges:
        if edge.get("source", "") in fn_node_ids:
            var_label = node_id_to_var_label(
                edge.get("target", ""), existing_node_labels, manual_nodes
            )
            if var_label and var_label not in output_types:
                output_types.append(var_label)
    return output_types


def infer_manual_fn_param_to_class(
    fn_node_ids: set[str],
    manual_edges: list[dict],
    manual_nodes: dict[str, dict],
    existing_node_labels: dict[str, str],
) -> dict[str, str]:
    """Extract {param_name: class_name} for a fn from its outgoing manual edges.

    Each manual edge from a function node carries the MATLAB signature param
    name in ``sourceHandle`` (``out__{param_name}``) and the downstream
    Variable class via the edge target. This gives an explicit mapping that
    does not rely on naming conventions — e.g. ``output1 → Result`` works.

    Edges without an ``out__`` prefix or without a resolvable target class
    are skipped. On duplicate param names the first wins.
    """
    mapping: dict[str, str] = {}
    for edge in manual_edges:
        if edge.get("source", "") not in fn_node_ids:
            continue
        sh = edge.get("sourceHandle") or ""
        if not sh.startswith("out__"):
            continue
        param = sh[len("out__") :]
        if not param or param in mapping:
            continue
        class_name = node_id_to_var_label(
            edge.get("target", ""), existing_node_labels, manual_nodes
        )
        if class_name:
            mapping[param] = class_name
    return mapping
