"""
Pure graph-building logic for the pipeline DAG.

Builds React Flow nodes and edges from pre-fetched data. No I/O — works
entirely on plain Python data structures (dicts, lists, sets, strings).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


FnKey = tuple[str, str]
"""(fn_name, call_id) — uniquely identifies a for_each call site.

Two for_each() invocations of the same fn that differ in inputs, constants,
where, distribute, or as_table produce different call_ids and therefore
different FnKeys. Since 2026-07-18 the CANVAS no longer shows one node per
call site: call sites are grouped by WIRING (see ``wiring_id`` /
``group_call_sites_by_wiring``) and render as variant rows inside one
node — a new constant value forks a new call_id in scidb (by design) but
lands in the SAME canvas node. State computation stays per call site.
"""


@dataclass
class AggregatedData:
    """Aggregated pipeline data from DB variants.

    Function-keyed fields use ``FnKey = (fn_name, call_id)`` so the same
    function reused from multiple for_each call sites appears as multiple
    distinct entries (and therefore multiple distinct function nodes).

    ``const_fns`` keeps a per-FnKey set of which call sites use each
    constant — that determines which call-site node receives the
    constant→function edge.
    """

    all_var_types: set[str] = field(default_factory=set)
    fn_input_params: dict[FnKey, dict] = field(
        default_factory=lambda: defaultdict(dict)
    )
    fn_outputs: dict[FnKey, set] = field(default_factory=lambda: defaultdict(set))
    const_counts: dict[str, dict] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(int))
    )
    const_fns: dict[str, set] = field(default_factory=lambda: defaultdict(set))
    fn_constants: dict[FnKey, set] = field(default_factory=lambda: defaultdict(set))
    path_inputs: dict[str, dict] = field(default_factory=dict)
    fn_variants_map: dict[FnKey, list] = field(
        default_factory=lambda: defaultdict(list)
    )


# ---------------------------------------------------------------------------
# Function-node ID conventions
# ---------------------------------------------------------------------------
#
# DB-derived function nodes use composite IDs:
#     fn__{fn_name}__{call_id}
# where call_id is a 16-hex-char hash of the for_each call site's version
# keys minus __fn_hash (see scidb.foreach_config.call_id_from_version_keys).
#
# Manual function nodes (dragged in by the user) use a different suffix:
#     fn__{fn_name}__{6-char-random}
# These graduate to a canonical DB-derived id once a matching for_each call
# has been recorded.


def fn_node_id(fn_name: str, call_id: str) -> str:
    """Compose a DB-derived function-node ID from (fn_name, call_id)."""
    return f"fn__{fn_name}__{call_id}"


# ---------------------------------------------------------------------------
# Placement IDs — per-scope independent copies of a DB-derived canonical node
# ---------------------------------------------------------------------------
#
# A canonical id (var__{Type}, fn__{fn}__{wiring_id}, const__{name},
# pathInput__{name}) names a piece of real, shared DB data — but the SAME
# wiring can be independently PLACED (graduated) on more than one pipeline
# scope at once (e.g. a duplicated hypothesis re-running identical, unedited
# wiring). ``{canonical_id}::{pipeline_id}`` is the placement-qualified id
# for one such placement; ``::`` never appears in a pipeline_id (``main`` or
# ``pipe_{hex}``) or in a function/variable/constant label, so it's a safe,
# unambiguous separator.

PLACEMENT_SEP = "::"

# Every prefix a DB-derived (non-manual) canonical id can start with —
# shared by the layout.json migration and anything else that needs to
# distinguish "this id names real DB data" from a manual/opaque id.
_DB_DERIVED_PREFIXES = ("var__", "fn__", "const__", "pathInput__")

# Matches domain.scope_filter.ROOT / pipeline_store.ROOT_PIPELINE_ID — kept
# as a local literal since this module is pure (no DB/store imports).
_ROOT_PIPELINE_ID = "main"


def placement_id(canonical_id: str, pipeline_id: str) -> str:
    """The id for one scope's independent placement of a canonical node."""
    return f"{canonical_id}{PLACEMENT_SEP}{pipeline_id}"


def parse_placement_id(node_id: str) -> tuple[str, str] | None:
    """Split a placement-qualified id into (canonical_id, pipeline_id).

    Returns None for a bare id with no placement suffix.
    """
    if PLACEMENT_SEP not in node_id:
        return None
    bare, _, scope = node_id.rpartition(PLACEMENT_SEP)
    return (bare, scope) if bare else None


def strip_placement(node_id: str) -> str:
    """The bare canonical id, with any placement suffix removed (a no-op
    if there wasn't one). For every ad-hoc ``var__``/``const__``/
    ``pathInput__``/``fn__`` prefix-parser that only ever wants the bare
    id (never the scope), call this FIRST.
    """
    bare, _ = parse_placement_id(node_id) or (node_id, None)
    return bare


def parse_fn_node_id(node_id: str) -> tuple[str, str] | None:
    """Parse a composite fn node ID into (fn_name, call_id).

    Returns None for legacy/manual IDs that don't match the composite
    pattern (e.g. ``fn__bandpass`` or ``fn__bandpass__abc123`` where
    ``abc123`` is a random 6-char manual suffix rather than a 16-hex
    call_id). Strips a placement suffix (``::{pipeline_id}``) first, if
    present — callers only ever want the bare (fn_name, call_id), never
    the placement scope, so this is transparent to every consumer.
    """
    node_id, _scope = parse_placement_id(node_id) or (node_id, None)
    if not node_id.startswith("fn__"):
        return None
    body = node_id[len("fn__") :]
    # Split from the right: the last 16-hex segment is call_id, rest is fn_name.
    if "__" not in body:
        return None
    fn_name, _, suffix = body.rpartition("__")
    if not fn_name:
        return None
    if len(suffix) != 16 or not all(c in "0123456789abcdef" for c in suffix):
        return None
    return fn_name, suffix


@dataclass
class GraduationAction:
    """Side-effect to execute after merge_manual_nodes (pure return value)."""

    old_id: str
    new_id: str


# ---------------------------------------------------------------------------
# Wiring grouping (one canvas node per function + input/output shape)
# ---------------------------------------------------------------------------

_STATE_WORST_ORDER = {"red": 0, "pending": 1, "green": 2}


def wiring_id(fn_name: str, input_params: dict, out_types) -> str:
    """16-hex id for a function's WIRING: name + loadable-input shape +
    output types — the call_id recipe minus constants, so constant-value
    variants of the same call share one canvas node. Deterministic across
    graph builds (node ids key saved positions and scope membership)."""
    payload = json.dumps(
        {
            "fn": fn_name,
            "inputs": {
                k: (sorted(v) if isinstance(v, (list, set, tuple)) else v)
                for k, v in sorted(input_params.items())
            },
            "outputs": sorted(out_types),
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def group_call_sites_by_wiring(
    agg: AggregatedData,
    run_states: dict[str, str],
    pending_constants: dict[str, set] | None = None,
) -> tuple[AggregatedData, dict[str, str], dict[str, list[str]]]:
    """Re-key the aggregated call-site data to (fn_name, wiring_id) groups.

    User decision 2026-07-18: one canvas node per function + wiring;
    constant-value call sites become variant rows INSIDE the node (each row
    keeps its own per-call-site state chip — the no-blur guarantee moves
    from separate nodes to separate chips). scidb call identity is
    untouched; this is presentation-layer grouping only.

    Args:
        agg: call-site-keyed aggregate (NOT mutated).
        run_states: propagate_run_states output — per-call-site
            ``fn__{fn}__{call_id}`` keys plus ``var__*`` keys.
        pending_constants: staged values ({name: {value, ...}}); each gets a
            SYNTHESIZED ``staged`` variant row on every group that uses the
            constant, so the value is visible in the node it will land in.

    Returns:
        (grouped AggregatedData,
         node_states — run_states re-keyed to group node ids, group state =
         worst member state (red < pending < green), var__ entries kept,
         member_map — {group_node_id: [legacy member node ids]} for the
         one-time position/edge adoption).
    """
    pending_constants = pending_constants or {}
    grouped = AggregatedData()
    grouped.all_var_types = agg.all_var_types
    grouped.const_counts = agg.const_counts
    grouped.path_inputs = {}

    fkey_to_gkey: dict[FnKey, FnKey] = {}
    member_map: dict[str, list[str]] = {}
    group_member_states: dict[FnKey, list[str]] = defaultdict(list)

    for fkey in sorted(agg.fn_input_params.keys()):
        fn, cid = fkey
        wid = wiring_id(fn, agg.fn_input_params[fkey], agg.fn_outputs.get(fkey, set()))
        gkey = (fn, wid)
        fkey_to_gkey[fkey] = gkey

        grouped.fn_input_params[gkey].update(agg.fn_input_params[fkey])
        grouped.fn_outputs[gkey] |= set(agg.fn_outputs.get(fkey, set()))
        grouped.fn_constants[gkey] |= set(agg.fn_constants.get(fkey, set()))

        member_state = run_states.get(fn_node_id(fn, cid))
        if member_state:
            group_member_states[gkey].append(member_state)
        for row in agg.fn_variants_map.get(fkey, []):
            grouped.fn_variants_map[gkey].append(
                {
                    **row,
                    "call_id": cid,
                    **({"state": member_state} if member_state else {}),
                }
            )

        member_map.setdefault(fn_node_id(fn, wid), []).append(fn_node_id(fn, cid))

    # const/path-input edge targets follow their call sites into the groups.
    for const_name, fkeys in agg.const_fns.items():
        grouped.const_fns[const_name] = {fkey_to_gkey.get(f, f) for f in fkeys}
    for param_name, pi in agg.path_inputs.items():
        grouped.path_inputs[param_name] = {
            **pi,
            "functions": {fkey_to_gkey.get(f, f) for f in pi["functions"]},
        }

    # Staged pending values: a synthesized row per (constant, value) on
    # every group that uses the constant — no call site exists yet.
    for gkey in list(grouped.fn_constants.keys()):
        for const_name in sorted(grouped.fn_constants[gkey]):
            for pval in sorted(pending_constants.get(const_name, set())):
                grouped.fn_variants_map[gkey].append(
                    {
                        "constants": {const_name: pval},
                        "state": "pending",
                        "staged": True,
                    }
                )
                if "pending" not in group_member_states[gkey]:
                    group_member_states[gkey].append("pending")

    # Group node state = worst member state.
    node_states = {k: v for k, v in run_states.items() if not k.startswith("fn__")}
    for (fn, wid), states in group_member_states.items():
        if states:
            node_states[fn_node_id(fn, wid)] = min(
                states, key=lambda s: _STATE_WORST_ORDER.get(s, 0)
            )

    n_groups = len(grouped.fn_input_params)
    n_sites = len(agg.fn_input_params)
    if n_groups != n_sites:
        logger.info(
            "[graph_builder] wiring grouping: %d call site(s) -> %d node(s)",
            n_sites,
            n_groups,
        )
    return grouped, node_states, member_map


def legacy_position_adoptions(
    member_map: dict[str, list[str]],
    positions_by_scope: dict[str, dict],
) -> tuple[list[dict], list[str]]:
    """One-time migration plan (pure): pre-grouping documents saved
    positions under per-call-site node ids; the group node adopts the first
    member position found (keeping its SCOPE — position location IS scope
    membership) and every legacy key is dropped.

    Returns (adoptions [{new_id, scope, x, y}], drop_ids [legacy ids]).
    """
    adoptions: list[dict] = []
    drop_ids: list[str] = []
    for group_id, legacy_ids in member_map.items():
        placed = any(group_id in pos for pos in positions_by_scope.values())
        for legacy_id in legacy_ids:
            if legacy_id == group_id:
                continue
            for scope, positions in positions_by_scope.items():
                if legacy_id not in positions:
                    continue
                if not placed:
                    xy = positions[legacy_id]
                    adoptions.append(
                        {
                            "new_id": group_id,
                            "scope": scope,
                            "x": xy.get("x", 0),
                            "y": xy.get("y", 0),
                        }
                    )
                    placed = True
                if legacy_id not in drop_ids:
                    drop_ids.append(legacy_id)
    return adoptions, drop_ids


def legacy_edge_rewrites(
    member_map: dict[str, list[str]],
    manual_edges: list[dict],
) -> list[dict]:
    """Manual edges whose endpoints reference legacy per-call-site node ids,
    rewritten to the group node id (pure; caller persists via the edge
    upsert)."""
    legacy_to_group = {
        legacy_id: group_id
        for group_id, legacy_ids in member_map.items()
        for legacy_id in legacy_ids
        if legacy_id != group_id
    }
    rewrites = []
    for edge in manual_edges:
        new_source = legacy_to_group.get(edge["source"])
        new_target = legacy_to_group.get(edge["target"])
        if new_source or new_target:
            rewrites.append(
                {
                    **edge,
                    "source": new_source or edge["source"],
                    "target": new_target or edge["target"],
                }
            )
    return rewrites


def parse_path_input(value: str) -> dict | None:
    """If *value* (from __inputs) represents a PathInput, return parsed info.

    Handles two formats:
    - New: JSON with ``__type: "PathInput"`` (from PathInput.to_key())
    - Legacy: repr string like ``PathInput('{subject}/...', root_folder=...)``

    Returns ``{"template": ..., "root_folder": ...}`` or ``None``.
    """
    # New JSON format
    if value.startswith("{"):
        try:
            parsed = json.loads(value)
            if parsed.get("__type") == "PathInput":
                return {
                    "template": parsed["template"],
                    "root_folder": parsed.get("root_folder"),
                }
        except (json.JSONDecodeError, KeyError):
            pass

    # Legacy repr format: PathInput('...', root_folder=PosixPath('...'))
    if value.startswith("PathInput("):
        m = re.match(r"PathInput\('([^']*)'", value)
        if m:
            template = m.group(1)
            root_match = re.search(
                r"root_folder=(?:Posix|Windows|Pure\w*)?Path\('([^']*)'\)", value
            )
            root = root_match.group(1) if root_match else None
            return {"template": template, "root_folder": root}

    return None


def aggregate_variants(
    variants: list[dict],
    listed_var_names: set[str],
) -> AggregatedData:
    """Parse DB variants into aggregated data structures.

    Function-keyed fields use ``FnKey = (fn_name, call_id)`` so the same
    function reused from multiple for_each call sites becomes multiple
    entries.  call_id is taken from the variant dict (added by
    ``list_pipeline_variants``).

    Args:
        variants: From db.list_pipeline_variants().
        listed_var_names: Variable names from db.list_variables() to fill in
            types that exist but haven't been run through for_each.

    Returns:
        AggregatedData with all parsed fields.
    """
    logger.info(
        "[graph_builder] aggregate_variants: processing %d variant(s)", len(variants)
    )
    agg = AggregatedData()

    for v in variants:
        fn = v["function_name"]
        cid = v.get("call_id", "")
        if not cid:
            # Legacy variant without call_id — skip rather than collide
            # other call sites under an empty key.  Logged so we notice.
            logger.warning(
                "aggregate_variants: variant missing call_id, skipping: fn=%s out=%s",
                fn,
                v.get("output_type"),
            )
            continue
        fkey: FnKey = (fn, cid)
        out = v["output_type"]
        inputs = v["input_types"]
        constants = v["constants"]
        count = v["record_count"]

        agg.all_var_types.add(out)

        for param_name, type_val in inputs.items():
            pi = parse_path_input(type_val)
            if pi is not None:
                existing = agg.path_inputs.get(param_name)
                if existing is None:
                    agg.path_inputs[param_name] = {**pi, "functions": {fkey}}
                else:
                    existing["functions"].add(fkey)
            else:
                agg.all_var_types.add(type_val)
                agg.fn_input_params[fkey][param_name] = type_val

        agg.fn_outputs[fkey].add(out)

        # Ensure fkey is tracked even with only PathInput/constant inputs
        if fkey not in agg.fn_input_params:
            agg.fn_input_params[fkey] = {}

        for k, val in constants.items():
            agg.const_counts[k][str(val)] += count
            agg.const_fns[k].add(fkey)
            agg.fn_constants[fkey].add(k)

        # Per-call-site variant list (currently always one entry per FnKey
        # because list_pipeline_variants groups by version_keys, but kept
        # as a list to match the existing settings-panel contract).
        agg.fn_variants_map[fkey].append(
            {
                "constants": constants,
                "input_types": inputs,
                "output_type": out,
                "record_count": count,
            }
        )

    # Add variable types from the DB that weren't in any for_each run.
    agg.all_var_types |= listed_var_names
    logger.debug(
        "[graph_builder] added %d variable type(s) from list_variables",
        len(listed_var_names),
    )

    logger.info(
        "[graph_builder] aggregate_variants complete: %d variants → %d var types, %d call sites, %d constants, %d path inputs",
        len(variants),
        len(agg.all_var_types),
        len(agg.fn_outputs),
        len(agg.const_counts),
        len(agg.path_inputs),
    )
    return agg


def filter_hidden(agg: AggregatedData, hidden_ids: set[str]) -> AggregatedData:
    """Remove hidden nodes from the aggregated data (mutates in place).

    Args:
        agg: Aggregated data to filter.
        hidden_ids: Set of node IDs the user has explicitly deleted.

    Returns:
        The same AggregatedData, mutated.
    """
    logger.info(
        "[graph_builder] filter_hidden: filtering %d hidden node(s)", len(hidden_ids)
    )

    hidden_var_types = {
        nid.replace("var__", "", 1) for nid in hidden_ids if nid.startswith("var__")
    }
    # fn IDs in hidden_ids are composite ``fn__{fn_name}__{call_id}``.
    # Parse into FnKeys; ignore IDs that don't match (legacy/manual).
    hidden_fkeys: set[FnKey] = set()
    for nid in hidden_ids:
        parsed = parse_fn_node_id(nid)
        if parsed is not None:
            hidden_fkeys.add(parsed)
    hidden_const_names = {
        nid.replace("const__", "", 1) for nid in hidden_ids if nid.startswith("const__")
    }
    hidden_path_names = {
        nid.replace("pathInput__", "", 1)
        for nid in hidden_ids
        if nid.startswith("pathInput__")
    }

    agg.all_var_types -= hidden_var_types

    for fkey in list(agg.fn_outputs.keys()):
        agg.fn_outputs[fkey] -= hidden_var_types

    for fkey in list(agg.fn_input_params.keys()):
        agg.fn_input_params[fkey] = {
            p: t
            for p, t in agg.fn_input_params[fkey].items()
            if t not in hidden_var_types
        }

    for fkey in hidden_fkeys:
        agg.fn_input_params.pop(fkey, None)
        agg.fn_outputs.pop(fkey, None)
        agg.fn_constants.pop(fkey, None)

    for cname in hidden_const_names:
        agg.const_counts.pop(cname, None)
        agg.const_fns.pop(cname, None)

    for pname in hidden_path_names:
        agg.path_inputs.pop(pname, None)

    if hidden_ids:
        logger.info(
            "[graph_builder] filter_hidden complete: removed %d var, %d fn, %d const, %d pathInput",
            len(hidden_var_types),
            len(hidden_fkeys),
            len(hidden_const_names),
            len(hidden_path_names),
        )
        logger.debug(
            "[graph_builder] hidden nodes: var=%s fn=%s const=%s pathInput=%s",
            hidden_var_types,
            sorted(hidden_fkeys),
            hidden_const_names,
            hidden_path_names,
        )
    return agg


def _wiring_group_key(agg: "AggregatedData", fkey: FnKey) -> tuple[str, str]:
    """(fn_name, wiring_id) for the call site's canvas node — see wiring_id()."""
    fn, _cid = fkey
    return (
        fn,
        wiring_id(fn, agg.fn_input_params.get(fkey, {}), agg.fn_outputs.get(fkey, set())),
    )


def _fkey_has_constant_value(
    agg: "AggregatedData", fkey: FnKey, const_name: str, pval: str
) -> bool:
    return any(
        str(row.get("constants", {}).get(const_name)) == pval
        for row in agg.fn_variants_map.get(fkey, [])
    )


def auto_clean_pending_constants(
    pending_constants: dict[str, set[str]],
    agg: "AggregatedData",
) -> tuple[dict[str, set[str]], list[tuple[str, str]]]:
    """Remove pending values once every wiring that consumes them has run.

    A constant can feed multiple function nodes that share a function name
    but are wired to different inputs/outputs (e.g. compute_rolling_vo2 fed
    by RawVO2 in one node, RawHeartRate in another — each its own canvas
    node/wiring, see group_call_sites_by_wiring). A naive "is this value in
    the DB anywhere" check blurs across those wirings: as soon as ONE of
    them ran with the new value, the check saw the value in the DB and
    cleared the pending flag for ALL of them — silently un-marking the
    OTHER (never re-run) wiring as no-longer-pending, even though it's
    still showing its old, stale value. Removal must wait until every
    wiring group that references the constant has its own real call site
    recording that exact value.

    Returns:
        Tuple of (cleaned pending_constants, list of (name, value) to remove from DB).
    """
    removals: list[tuple[str, str]] = []
    for const_name in list(pending_constants.keys()):
        consuming_fkeys = agg.const_fns.get(const_name, set())
        required_groups = {_wiring_group_key(agg, fkey) for fkey in consuming_fkeys}
        still_pending: set[str] = set()
        for pval in pending_constants[const_name]:
            covered_groups = {
                _wiring_group_key(agg, fkey)
                for fkey in consuming_fkeys
                if _fkey_has_constant_value(agg, fkey, const_name, pval)
            }
            # required_groups being empty means no real call site references
            # this constant yet — never auto-clean on that vacuous truth.
            if required_groups and required_groups <= covered_groups:
                removals.append((const_name, pval))
            else:
                still_pending.add(pval)
        pending_constants[const_name] = still_pending
    if removals:
        logger.debug("auto_clean_pending_constants: removing %s", removals)
    return pending_constants, removals


def build_variable_nodes(
    all_var_types: set[str],
    record_counts: dict[str, int],
    run_states: dict[str, str],
) -> list[dict]:
    """Build React Flow variable nodes."""
    logger.info(
        "[graph_builder] build_variable_nodes: building %d variable node(s)",
        len(all_var_types),
    )
    nodes = []
    for vtype in sorted(all_var_types):
        data: dict = {
            "label": vtype,
            "total_records": record_counts.get(vtype, 0),
        }
        state = run_states.get(f"var__{vtype}", "green")
        data["run_state"] = state
        nodes.append(
            {
                "id": f"var__{vtype}",
                "type": "variableNode",
                "position": {"x": 0, "y": 0},
                "data": data,
            }
        )
    logger.debug("[graph_builder] built %d variable node(s)", len(nodes))
    return nodes


def build_constant_nodes(
    const_counts: dict[str, dict],
    pending_constants: dict[str, set[str]],
) -> list[dict]:
    """Build React Flow constant nodes."""
    logger.info(
        "[graph_builder] build_constant_nodes: building %d constant node(s)",
        len(const_counts),
    )
    nodes = []
    for const_name in sorted(const_counts.keys()):
        values = [
            {"value": val, "record_count": cnt}
            for val, cnt in sorted(const_counts[const_name].items())
        ]
        existing_values = {v["value"] for v in values}
        for pval in sorted(pending_constants.get(const_name, set())):
            if pval not in existing_values:
                values.append({"value": pval, "record_count": 0})
        nodes.append(
            {
                "id": f"const__{const_name}",
                "type": "constantNode",
                "position": {"x": 0, "y": 0},
                "data": {"label": const_name, "values": values},
            }
        )
    logger.debug("[graph_builder] built %d constant node(s)", len(nodes))
    return nodes


def overlay_saved_path_inputs(
    path_inputs: dict[str, dict],
    saved_path_inputs: list[dict],
) -> dict[str, dict]:
    """Overlay saved template/root_folder from layout.json onto path_inputs.

    Mutates path_inputs in place and returns it.
    """
    for saved_pi in saved_path_inputs:
        pname = saved_pi["name"]
        if pname in path_inputs:
            if saved_pi.get("template"):
                path_inputs[pname]["template"] = saved_pi["template"]
            if saved_pi.get("root_folder") is not None:
                path_inputs[pname]["root_folder"] = saved_pi["root_folder"]
        else:
            path_inputs[pname] = {
                "template": saved_pi.get("template", ""),
                "root_folder": saved_pi.get("root_folder"),
                "functions": set(),
            }
    return path_inputs


def build_path_input_nodes(path_inputs: dict[str, dict]) -> list[dict]:
    """Build React Flow path input nodes."""
    logger.info(
        "[graph_builder] build_path_input_nodes: building %d path input node(s)",
        len(path_inputs),
    )
    nodes = []
    for param_name in sorted(path_inputs.keys()):
        pi = path_inputs[param_name]
        nodes.append(
            {
                "id": f"pathInput__{param_name}",
                "type": "pathInputNode",
                "position": {"x": 0, "y": 0},
                "data": {
                    "label": param_name,
                    "template": pi["template"],
                    "root_folder": pi.get("root_folder"),
                },
            }
        )
    logger.debug("[graph_builder] built %d path input node(s)", len(nodes))
    return nodes


def build_function_nodes(
    fn_input_params: dict[FnKey, dict],
    fn_outputs: dict[FnKey, set],
    fn_constants: dict[FnKey, set],
    fn_variants_map: dict[FnKey, list],
    fn_params_map: dict[str, list[str]],
    run_states: dict[str, str],
    matlab_functions: set[str],
    saved_configs: dict[str, dict | None],
    matlab_output_order: dict[str, list[str]] | None = None,
    matlab_param_to_class: dict[str, dict[str, str]] | None = None,
) -> list[dict]:
    """Build React Flow function nodes — one per aggregate key.

    Keys arrive as ``(fn_name, wiring_id)`` when the caller grouped call
    sites via ``group_call_sites_by_wiring`` (the canvas default since
    2026-07-18); the builder is agnostic and works for raw
    ``(fn_name, call_id)`` keys too (unit tests, ungrouped callers).
    ``data.call_id`` is set to the key's suffix either way — the node id
    always ends with it.

    Args:
        fn_input_params: {(fn_name, call_id): {param: var_type}}.
        fn_outputs: {(fn_name, call_id): {output_types}}.
        fn_constants: {(fn_name, call_id): {constant_param_names}}.
        fn_variants_map: {(fn_name, call_id): [variant_dicts]} for settings panel.
        fn_params_map: {fn_name: [all_sig_params]} from registry.  Keyed by
            fn_name only because the function's signature does not vary
            across call sites.
        run_states: {node_id: state} keyed by composite ``fn__{fn}__{cid}`` IDs.
        matlab_functions: Set of MATLAB function names.
        saved_configs: {fn_name: config_dict or None} from manual nodes.  Same
            saved config applies to every call site of fn_name.
        matlab_output_order: {fn_name: [output_names in signature order]}.
        matlab_param_to_class: {fn_name: {param_name: class_name}} — explicit
            mapping from MATLAB signature param names to connected Variable class
            names. Used to decide which declared params got wired up so their
            handles are rendered (handle id `out__{param_name}`).
    """
    logger.info(
        "[graph_builder] build_function_nodes: building %d function node(s)",
        len(fn_input_params),
    )
    nodes = []
    # Sort by (fn_name, call_id) for stable output across runs.
    for fkey in sorted(fn_input_params.keys()):
        fn, cid = fkey
        input_params = dict(sorted(fn_input_params[fkey].items()))
        constant_params = sorted(fn_constants.get(fkey, set()))

        # Fill in any params the DB didn't capture.
        known = set(input_params) | set(constant_params)
        for name in fn_params_map.get(fn, []):
            if name not in known:
                input_params[name] = ""

        # MATLAB fns render handles in MATLAB-signature order using param names
        # (e.g. "time", "force_left"). Non-MATLAB fns use the class names directly.
        actual_outputs = fn_outputs.get(fkey, set())
        if fn in matlab_functions and matlab_output_order:
            declared = matlab_output_order.get(fn, [])
            p2c = (matlab_param_to_class or {}).get(fn, {})
            connected_classes = set(p2c.values()) | actual_outputs
            # Signature order, but only for params that actually map to a class
            # (either via an explicit edge or a DB variant).
            out_types = [
                p for p in declared if p in p2c or p2c.get(p) in connected_classes
            ]
            if not out_types:
                out_types = list(declared)
            # Any class in DB variants that is not covered by the declared
            # signature is a real anomaly — log it so we can see it.
            covered = {p2c.get(p) for p in out_types if p in p2c}
            orphan = actual_outputs - covered - {None}
            if orphan:
                logger.warning(
                    "[graph_builder] matlab fn=%s call_id=%s: DB variants %s "
                    "have no declared param mapping (matlab_param_to_class=%s)",
                    fn,
                    cid,
                    sorted(orphan),
                    p2c,
                )
            logger.debug(
                "[graph_builder] matlab fn=%s call_id=%s handles=%s param→class=%s",
                fn,
                cid,
                out_types,
                p2c,
            )
        else:
            out_types = sorted(actual_outputs)

        node_id = fn_node_id(fn, cid)
        fn_data: dict = {
            "label": fn,
            "call_id": cid,
            "variants": fn_variants_map.get(fkey, []),
            "input_params": input_params,
            "output_types": out_types,
            "constant_params": constant_params,
        }
        state = run_states.get(node_id)
        if state:
            fn_data["run_state"] = state
        if fn in matlab_functions:
            fn_data["language"] = "matlab"

        # Apply saved config (schemaFilter, runOptions) if present.  Saved
        # configs are keyed by fn_name and apply to all call sites of that fn.
        saved = saved_configs.get(fn)
        if saved:
            if "schemaFilter" in saved:
                fn_data["schemaFilter"] = saved["schemaFilter"]
            if "schemaLevel" in saved:
                fn_data["schemaLevel"] = saved["schemaLevel"]
            if "runOptions" in saved:
                fn_data["runOptions"] = saved["runOptions"]

        nodes.append(
            {
                "id": node_id,
                "type": "functionNode",
                "position": {"x": 0, "y": 0},
                "data": fn_data,
            }
        )
    logger.debug("[graph_builder] built %d function node(s)", len(nodes))
    return nodes


def build_edges(
    fn_input_params: dict[FnKey, dict],
    fn_outputs: dict[FnKey, set],
    const_fns: dict[str, set],
    path_inputs: dict[str, dict],
    manual_edges: list[dict],
    hidden_ids: set[str],
    matlab_param_to_class: dict[str, dict[str, str]] | None = None,
    hidden_edge_ids: set[str] | None = None,
) -> list[dict]:
    """Build React Flow edges (DB-derived + manual).

    Edges target/source the per-call-site node IDs (``fn__{fn}__{cid}``)
    so an input variable that feeds two different call sites of the same
    function produces two distinct edges.

    Args:
        fn_input_params: {(fn_name, call_id): {param: var_type}}.
        fn_outputs: {(fn_name, call_id): {output_types}}.
        const_fns: {const_name: {(fn_name, call_id), ...}}.
        path_inputs: {param_name: {"functions": set[FnKey], ...}}.
        manual_edges: List of manual edge dicts from pipeline_store.
        hidden_ids: Set of hidden node IDs.
        matlab_param_to_class: {fn_name: {param_name: class_name}} — for MATLAB
            fns, the explicit mapping from signature param name to connected
            Variable class. Drives sourceHandle=out__{param_name} for output
            edges instead of the class-name-based handle.
        hidden_edge_ids: Set of edge IDs the user has explicitly hidden (see
            pipeline_store.hide_edge) — excluded from the DB-derived edges
            they'd otherwise regenerate every rebuild. Never deletes data,
            only excludes rendering (and, for inbound edges, marks the
            target wiring "disconnected" — see hidden_wirings).
    """
    logger.info(
        "[graph_builder] build_edges: building edges from DB-derived data and manual edges"
    )
    edges = []
    seen_edges: set[tuple] = set()
    p2c_all = matlab_param_to_class or {}
    hidden_edge_ids = hidden_edge_ids or set()

    # Variable → function edges (one per call-site target).
    logger.debug("[graph_builder] building variable → function edges")
    hidden_var_to_fn = 0
    for fkey, params in fn_input_params.items():
        fn, cid = fkey
        target_id = fn_node_id(fn, cid)
        for param_name, in_type in params.items():
            key = (f"var__{in_type}", target_id)
            if key not in seen_edges:
                seen_edges.add(key)
                edge_id = f"e__{in_type}__{fn}__{cid}"
                if edge_id in hidden_edge_ids:
                    hidden_var_to_fn += 1
                    continue
                edges.append(
                    {
                        "id": edge_id,
                        "source": f"var__{in_type}",
                        "target": target_id,
                        "targetHandle": f"in__{param_name}",
                    }
                )
    var_to_fn_count = len(edges)
    logger.debug(
        "[graph_builder] built %d variable → function edge(s) (%d hidden)",
        var_to_fn_count,
        hidden_var_to_fn,
    )

    # Function → variable edges.  For MATLAB fns, use the param↔class mapping
    # (call-site-independent) so sourceHandle=out__{param_name}.
    logger.debug("[graph_builder] building function → variable edges")
    hidden_fn_to_var = 0
    for fkey, out_types in fn_outputs.items():
        fn, cid = fkey
        source_id = fn_node_id(fn, cid)
        class_to_param = {c: p for p, c in p2c_all.get(fn, {}).items()}
        for out_type in out_types:
            key = (source_id, f"var__{out_type}")
            if key in seen_edges:
                continue
            seen_edges.add(key)
            edge_id = f"e__{fn}__{cid}__{out_type}"
            if edge_id in hidden_edge_ids:
                hidden_fn_to_var += 1
                continue
            param = class_to_param.get(out_type)
            source_handle = f"out__{param}" if param else f"out__{out_type}"
            edges.append(
                {
                    "id": edge_id,
                    "source": source_id,
                    "target": f"var__{out_type}",
                    "sourceHandle": source_handle,
                }
            )
    fn_to_var_count = len(edges) - var_to_fn_count
    logger.debug(
        "[graph_builder] built %d function → variable edge(s) (%d hidden)",
        fn_to_var_count,
        hidden_fn_to_var,
    )

    # Constant → function edges (one per call site that uses the constant).
    logger.debug("[graph_builder] building constant → function edges")
    hidden_const_to_fn = 0
    for const_name, fkeys in const_fns.items():
        for fkey in fkeys:
            fn, cid = fkey
            target_id = fn_node_id(fn, cid)
            key = (f"const__{const_name}", target_id)
            if key not in seen_edges:
                seen_edges.add(key)
                edge_id = f"e__{const_name}__{fn}__{cid}"
                if edge_id in hidden_edge_ids:
                    hidden_const_to_fn += 1
                    continue
                edges.append(
                    {
                        "id": edge_id,
                        "source": f"const__{const_name}",
                        "target": target_id,
                        "targetHandle": f"const__{const_name}",
                    }
                )
    const_to_fn_count = len(edges) - var_to_fn_count - fn_to_var_count
    logger.debug(
        "[graph_builder] built %d constant → function edge(s) (%d hidden)",
        const_to_fn_count,
        hidden_const_to_fn,
    )

    # PathInput → function edges.
    logger.debug("[graph_builder] building pathInput → function edges")
    hidden_path_to_fn = 0
    for param_name, pi in path_inputs.items():
        for fkey in pi["functions"]:
            fn, cid = fkey
            target_id = fn_node_id(fn, cid)
            key = (f"pathInput__{param_name}", target_id)
            if key not in seen_edges:
                seen_edges.add(key)
                edge_id = f"e__{param_name}__{fn}__{cid}"
                if edge_id in hidden_edge_ids:
                    hidden_path_to_fn += 1
                    continue
                edges.append(
                    {
                        "id": edge_id,
                        "source": f"pathInput__{param_name}",
                        "target": target_id,
                        "targetHandle": f"in__{param_name}",
                    }
                )
    path_to_fn_count = (
        len(edges) - var_to_fn_count - fn_to_var_count - const_to_fn_count
    )
    logger.debug(
        "[graph_builder] built %d pathInput → function edge(s) (%d hidden)",
        path_to_fn_count,
        hidden_path_to_fn,
    )

    # Merge manually-created edges.
    logger.debug("[graph_builder] merging %d manual edge(s)", len(manual_edges))
    db_edge_count = len(edges)
    for me in manual_edges:
        if me["source"] in hidden_ids or me["target"] in hidden_ids:
            continue
        if me["id"] in hidden_edge_ids:
            continue
        if any(e["id"] == me["id"] for e in edges):
            continue
        edge: dict = {
            "id": me["id"],
            "source": me["source"],
            "target": me["target"],
            "data": {"manual": True},
        }
        if me.get("sourceHandle"):
            edge["sourceHandle"] = me["sourceHandle"]
        if me.get("targetHandle"):
            edge["targetHandle"] = me["targetHandle"]
        edges.append(edge)
    manual_edge_count = len(edges) - db_edge_count
    logger.debug("[graph_builder] added %d manual edge(s)", manual_edge_count)

    total_hidden = (
        hidden_var_to_fn + hidden_fn_to_var + hidden_const_to_fn + hidden_path_to_fn
    )
    logger.info(
        "[graph_builder] build_edges complete: %d total edges (%d DB-derived, "
        "%d manual, %d hidden)",
        len(edges),
        db_edge_count,
        manual_edge_count,
        total_hidden,
    )
    return edges


# ---------------------------------------------------------------------------
# Disconnected wirings — hiding an INBOUND edge (variable/constant/
# pathInput -> function) means that wiring is missing a required input
# entirely, not just decluttered from the canvas. Every call site sharing
# that wiring is affected (run_state forced red, execution blocked) — see
# domain.run_state.propagate_run_states(disconnected_fkeys=...) and
# domain.variant_resolver.filter_disconnected_targets. Hiding an OUTBOUND
# (function -> variable) edge is deliberately excluded here: it's cosmetic
# only, since the function's real output still exists in the DB either way.
# ---------------------------------------------------------------------------


def inbound_edge_candidates(
    fn: str, wid: str, var_types=(), const_names=(), path_names=()
) -> list[str]:
    """Candidate inbound edge ids (var/const/pathInput -> fn) for one
    wiring — the same id shape build_edges constructs, reusable anywhere a
    caller needs to check "is this call site's required input hidden?"
    without needing the edge to already exist (hidden_wirings,
    variant_resolver.filter_disconnected_targets)."""
    return (
        [f"e__{vt}__{fn}__{wid}" for vt in var_types]
        + [f"e__{cn}__{fn}__{wid}" for cn in const_names]
        + [f"e__{pn}__{fn}__{wid}" for pn in path_names]
    )


def hidden_wirings(
    fn_input_params: dict[FnKey, dict],
    fn_outputs: dict[FnKey, set],
    fn_constants: dict[FnKey, set],
    path_inputs: dict[str, dict],
    hidden_edge_ids: set[str],
) -> set[tuple[str, str]]:
    """(fn_name, wiring_id) pairs with at least one hidden inbound edge.

    Reconstructs each call site's candidate inbound edge ids the same way
    build_edges does (without needing edges to already exist) and checks
    them against ``hidden_edge_ids``. Works on the PRE-GROUPING agg (raw
    per-call-site FnKeys) — every call site sharing a wiring recomputes
    the same wiring_id, so the result is correct regardless of grouping.
    """
    if not hidden_edge_ids:
        return set()
    result: set[tuple[str, str]] = set()
    for fkey, params in fn_input_params.items():
        fn, _cid = fkey
        wid = wiring_id(fn, params, fn_outputs.get(fkey, set()))
        candidates = inbound_edge_candidates(
            fn, wid, var_types=params.values(), const_names=fn_constants.get(fkey, set())
        )
        if hidden_edge_ids.intersection(candidates):
            result.add((fn, wid))
    for param_name, pi in path_inputs.items():
        for fkey in pi["functions"]:
            fn, _cid = fkey
            wid = wiring_id(
                fn, fn_input_params.get(fkey, {}), fn_outputs.get(fkey, set())
            )
            if f"e__{param_name}__{fn}__{wid}" in hidden_edge_ids:
                result.add((fn, wid))
    if result:
        logger.info("[graph_builder] hidden_wirings: %s", sorted(result))
    return result


def wiring_disconnected_fkeys(
    fn_input_params: dict[FnKey, dict],
    fn_outputs: dict[FnKey, set],
    wirings: set[tuple[str, str]],
) -> set[FnKey]:
    """Map a (fn_name, wiring_id) set back to raw pre-grouping call-site
    FnKeys — for feeding domain.run_state.propagate_run_states, which
    still operates per real call site at the point it runs."""
    if not wirings:
        return set()
    result: set[FnKey] = set()
    for fkey, params in fn_input_params.items():
        fn, _cid = fkey
        wid = wiring_id(fn, params, fn_outputs.get(fkey, set()))
        if (fn, wid) in wirings:
            result.add(fkey)
    return result


def wirings_downstream_of(
    fn_input_params: dict[FnKey, dict],
    fn_outputs: dict[FnKey, set],
    seed_wirings: set[tuple[str, str]],
) -> set[tuple[str, str]]:
    """Every wiring that transitively consumes a seed wiring's output —
    used to report which OTHER functions become un-runnable as a
    consequence of a disconnected wiring (starved of an input) without
    being directly disconnected themselves. Returns only the downstream
    wirings, never the seeds (callers already have those)."""
    if not seed_wirings:
        return set()
    wiring_outputs: dict[tuple[str, str], set] = {}
    wiring_inputs: dict[tuple[str, str], set] = {}
    for fkey, params in fn_input_params.items():
        fn, _cid = fkey
        wid = wiring_id(fn, params, fn_outputs.get(fkey, set()))
        wiring_inputs.setdefault((fn, wid), set()).update(params.values())
        wiring_outputs.setdefault((fn, wid), set()).update(fn_outputs.get(fkey, set()))

    affected = set(seed_wirings)
    frontier = set(seed_wirings)
    while frontier:
        produced: set = set()
        for w in frontier:
            produced |= wiring_outputs.get(w, set())
        next_frontier = set()
        for w, inputs in wiring_inputs.items():
            if w in affected:
                continue
            if inputs & produced:
                affected.add(w)
                next_frontier.add(w)
        frontier = next_frontier
    return affected - seed_wirings


def candidate_edge_id(source_id: str, target_id: str) -> str | None:
    """The deterministic DB-derived edge id a (source, target) node-id pair
    WOULD have in build_edges' output, without needing the edge to exist.

    Used to detect "the user just dragged a connection that recreates a
    previously-hidden DB-derived edge" (see layout_service.put_edge) —
    reconnecting the exact same nodes should unhide the original edge
    rather than create a redundant manual one. Returns None for pairs that
    aren't a recognized DB-derived category (a genuinely new connection).
    Both ids may be placement-qualified; only the bare ids matter here.
    """
    src = strip_placement(source_id)
    tgt = strip_placement(target_id)
    src_prefixes = ("var__", "const__", "pathInput__")
    if src.startswith(src_prefixes):
        parsed = parse_fn_node_id(tgt)
        if parsed is None:
            return None
        fn, wid = parsed
        x = src.split("__", 1)[1]
        return f"e__{x}__{fn}__{wid}"
    if tgt.startswith("var__"):
        parsed = parse_fn_node_id(src)
        if parsed is None:
            return None
        fn, wid = parsed
        out_type = tgt[len("var__") :]
        return f"e__{fn}__{wid}__{out_type}"
    return None


# ---------------------------------------------------------------------------
# Cycle detection
# ---------------------------------------------------------------------------


def find_cycle(
    edges: list[dict], new_source: str, new_target: str
) -> list[str] | None:
    """Would adding an edge new_source -> new_target close a cycle?

    ``edges`` is the FULL current graph for one scope (DB-derived + manual,
    as returned by services.pipeline_service.get_pipeline_graph) — checking
    manual edges alone would miss a cycle closed through existing
    DB-derived data-lineage edges. A self-loop (new_source == new_target)
    is always a cycle.

    Returns the cycle path new_source -> new_target -> ... -> new_source if
    adding the edge would create one, else None.
    """
    if new_source == new_target:
        return [new_source, new_target]

    adjacency: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        adjacency[e["source"]].append(e["target"])

    # BFS forward from new_target: if new_source is reachable, the new edge
    # would close a loop back to itself.
    parent: dict[str, str] = {}
    frontier = deque([new_target])
    seen = {new_target}
    while frontier:
        current = frontier.popleft()
        if current == new_source:
            path = [current]
            while current != new_target:
                current = parent[current]
                path.append(current)
            path.reverse()
            return [new_source] + path
        for nxt in adjacency[current]:
            if nxt not in seen:
                seen.add(nxt)
                parent[nxt] = current
                frontier.append(nxt)
    return None


def _apply_saved_config(node_data: dict, config: dict | None) -> None:
    """Apply saved config (schemaFilter, runOptions) to a function node."""
    if not config:
        return
    if "schemaFilter" in config:
        node_data["schemaFilter"] = config["schemaFilter"]
    if "schemaLevel" in config:
        node_data["schemaLevel"] = config["schemaLevel"]
    if "runOptions" in config:
        node_data["runOptions"] = config["runOptions"]


def build_manual_node(
    node_id: str,
    meta: dict,
    pending_constants: dict[str, set[str]],
    manual_fn_state: str | None,
    resolved_input_params: dict[str, str] | None,
    resolved_output_types: list[str] | None,
    matlab_functions: set[str],
) -> dict:
    """Build a single manual node dict.

    Args:
        node_id: The manual node ID.
        meta: {"type": ..., "label": ..., "config": ...} from pipeline_store.
        pending_constants: {const_name: {pending_values}}.
        manual_fn_state: Pre-computed run state for function nodes (or None).
        resolved_input_params: Pre-resolved {param: var_type} for function nodes.
        resolved_output_types: Pre-resolved output types for function nodes.
        matlab_functions: Set of MATLAB function names.
    """
    fn_label = meta["label"]
    extra: dict = {}

    if meta["type"] == "variableNode":
        extra = {"total_records": 0, "run_state": "red"}
    elif meta["type"] == "constantNode":
        pending_vals = [
            {"value": pval, "record_count": 0}
            for pval in sorted(pending_constants.get(fn_label, set()))
        ]
        extra = {"values": pending_vals}
    elif meta["type"] == "pathInputNode":
        extra = {"template": "", "root_folder": None}
    elif meta["type"] == "functionNode":
        extra = {
            "input_params": resolved_input_params or {},
            "output_types": list(resolved_output_types or []),
            "constant_params": [],
            "run_state": manual_fn_state or "red",
        }
        if fn_label in matlab_functions:
            extra["language"] = "matlab"

    node_data: dict = {"label": fn_label, **extra}
    _apply_saved_config(
        node_data, meta.get("config") if meta["type"] == "functionNode" else None
    )

    return {
        "id": node_id,
        "type": meta["type"],
        "position": {"x": 0, "y": 0},
        "data": node_data,
    }


def merge_manual_nodes(
    existing_nodes: list[dict],
    manual_nodes: dict[str, dict],
    saved_positions: dict[str, dict],
) -> tuple[list[str], list[GraduationAction]]:
    """Determine which manual nodes to add and which to graduate.

    A manual function node graduates to its DB-derived counterpart only
    when there is exactly one DB node with the same (type, label).  If the
    same function name has multiple DB nodes (one per for_each call site),
    we cannot pick a canonical target unambiguously, so the manual node is
    kept as a separate node — the user can wire it up and run it to
    produce a real call site of its own.

    Graduation targets the manual node's OWN placement
    (``placement_id(canonical_id, meta["pipeline_id"])``), not the bare
    canonical id — this is what lets two manual nodes with the same label
    in DIFFERENT scopes (e.g. a duplicated pipeline re-running identical,
    unedited wiring) graduate independently instead of racing for one
    shared slot and stealing it from each other (the root cause fixed by
    this rework — see plan-placement-qualified-node-ids.md).

    Returns:
        Tuple of:
        - List of manual node IDs that should be added to the graph.
        - List of GraduationAction objects (side-effects for the service layer).
    """
    logger.info(
        "[graph_builder] merge_manual_nodes: processing %d manual node(s) against %d existing node(s)",
        len(manual_nodes),
        len(existing_nodes),
    )

    existing_ids = {n["id"] for n in existing_nodes}
    db_nodes_by_label: dict[tuple, list[str]] = {}
    for n in existing_nodes:
        key = (n["type"], n["data"]["label"])
        db_nodes_by_label.setdefault(key, []).append(n["id"])

    to_add: list[str] = []
    graduations: list[GraduationAction] = []

    for node_id, meta in manual_nodes.items():
        if node_id in existing_ids:
            continue
        key = (meta["type"], meta["label"])
        candidates = db_nodes_by_label.get(key, [])
        if len(candidates) == 1:
            canonical_id = candidates[0]
            target_id = placement_id(
                canonical_id, meta.get("pipeline_id") or _ROOT_PIPELINE_ID
            )
            if target_id not in saved_positions:
                graduations.append(
                    GraduationAction(old_id=node_id, new_id=target_id)
                )
                continue
        elif len(candidates) > 1:
            logger.debug(
                "merge_manual_nodes: not graduating %s — %d DB nodes share label %r "
                "(multiple call sites)",
                node_id,
                len(candidates),
                meta["label"],
            )
        to_add.append(node_id)

    logger.info(
        "[graph_builder] merge_manual_nodes complete: %d to add, %d to graduate",
        len(to_add),
        len(graduations),
    )
    if graduations:
        logger.debug(
            "[graph_builder] graduations: %s",
            [(g.old_id, g.new_id) for g in graduations],
        )
    return to_add, graduations
