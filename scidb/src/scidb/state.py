"""
Pipeline node staleness API.

Provides per-combo and per-node run state queries that use the full lineage
provenance graph rather than simple record-count approximations.

Staleness check priority (most to least authoritative):

1. **Lineage record exists** (scihist.for_each output):
   - Function staleness: stored ``function_hash`` vs current ``LineageFcn.hash``.
   - Input staleness: stored input ``record_id`` vs current latest record_id.
   - No timestamps used.

2. **No lineage, but ``__fn_hash`` in version_keys** (scidb.for_each output):
   - Function staleness: stored ``__fn_hash`` vs ``_compute_fn_hash(fn)``.
   - Input staleness: output record timestamp vs latest input record timestamp
     at the same schema_id.  Timestamps used only here, as the minimum
     unavoidable fallback when exact input record_ids are unavailable.

Typical usage::

    from scidb import check_node_state

    result = check_node_state(bandpass_filter, outputs=[FilteredSignal])
    print(result["state"])    # "green" | "grey" | "red"
    for combo in result["combos"]:
        print(combo["schema_combo"], combo["state"])
"""

import json
import logging
from typing import Literal

logger = logging.getLogger(__name__)

ComboState = Literal["up_to_date", "stale", "missing"]
NodeState = Literal["green", "grey", "red"]


def check_combo_state(
    fn,
    outputs: list[type],
    schema_combo: dict,
    branch_params: dict | None = None,
    db=None,
) -> ComboState:
    """Check the staleness of a single (function, schema_combo) pair.

    Args:
        fn: The pipeline function (plain callable or LineageFcn).
        outputs: List of output variable classes produced by fn.
        schema_combo: Dict of schema key → value identifying the specific
            data location, e.g. ``{"subject": 1, "session": "pre"}``.
        branch_params: Optional constants dict to disambiguate which variant
            to check when multiple variants exist for the same schema_combo,
            e.g. ``{"bandpass_filter.low_hz": 20}``.
        db: DatabaseManager instance.  Uses the global DB if omitted.

    Returns:
        ``"up_to_date"``  — output exists and full upstream provenance is unchanged.
        ``"stale"``       — output exists but upstream has changed (input record
                           updated or function code changed).
        ``"missing"``     — no output record exists for this combo.
    """
    from scilineage import LineageFcn
    from scidb.foreach_config import _compute_fn_hash

    if db is None:
        from scidb.database import get_database
        db = get_database()

    if not hasattr(fn, 'hash'):
        fn = LineageFcn(fn)

    combo_str = _combo_str(schema_combo, branch_params)

    # Step 1: all outputs must have a record for this combo.
    # Pass branch_params separately so namespaced keys (e.g. "fn.param") go
    # through the suffix-matching path rather than the version_keys filter,
    # which would fail because version_keys stores un-namespaced param names.
    output_record_id = None
    output_timestamp = None
    for OutputCls in outputs:
        rid = db.find_record_id(OutputCls, schema_combo, branch_params_filter=branch_params or None)
        if rid is None:
            logger.debug("missing: %s — no output record for %s", combo_str, OutputCls.__name__)
            return "missing"
        output_record_id = rid

    # Fetch the output record's timestamp (needed for fallback path).
    ts_rows = db._duck._fetchall(
        "SELECT timestamp FROM _record_metadata WHERE record_id = ? "
        "ORDER BY timestamp DESC LIMIT 1",
        [output_record_id],
    )
    output_timestamp = ts_rows[0][0] if ts_rows else None

    # --- Priority 1: bipartite-graph check (records produced by for_each) ---
    from . import provenance_query
    sig = provenance_query.stored_invocation_signature(db._duck, output_record_id)
    if sig is not None:
        return _check_via_graph(fn, db, output_record_id, sig, combo_str)

    # --- Priority 2: version_keys __fn_hash fallback (legacy / manual records) ---
    return _check_via_fn_hash(fn, db, output_record_id, output_timestamp,
                               schema_combo, combo_str)


def _check_via_graph(fn, db, output_record_id: str, sig: dict,
                     combo_str: str) -> ComboState:
    """Staleness check over the bipartite provenance graph.

    ``sig`` is the producing invocation's signature
    (``provenance_query.stored_invocation_signature``). A descendant is stale if
    its own function hash changed, or if ANY ancestor record_id in its
    provenance has been superseded — cascading data changes through arbitrarily
    deep chains and DAG shapes (fork/join).

    Scope (see docs/guide/node-states.md, "Propagation"):

    - ✅ Ancestor data re-saved (record_id superseded) → stale.
    - ✅ Python fn's own function hash mismatched → stale (Python ``LineageFcn``
      only; MATLAB proxies use a different hashing pipeline that can produce
      false mismatches — see ``.claude/defer-function-hash-staleness.md``).
    - ❌ Ancestor function code changed but not yet re-run → NOT detected here
      (only ``fn`` itself is passed in). The GUI DAG walk handles that, or the
      user re-runs the changed ancestor (creating a new record_id that cascades).
    """
    from scilineage import LineageFcn
    from scidb.foreach_config import _compute_fn_hash

    # Function's own code changed since the output was saved? (Python only.)
    # The graph stores ``function_hash`` = compute_function_hash(fn, 16) (the
    # ``__fn_hash`` the save path writes), so compare against the same recipe —
    # NOT LineageFcn.hash, which is a sha256 of a different string.
    stored_hash = sig.get("function_hash")
    current_hash = _compute_fn_hash(fn.fcn if hasattr(fn, "fcn") else fn)
    if stored_hash is not None and stored_hash != current_hash:
        if isinstance(fn, LineageFcn):
            logger.debug(
                "stale: %s — function hash changed: stored=%s current=%s",
                combo_str, stored_hash[:12], current_hash[:12],
            )
            return "stale"
        logger.debug(
            "function hash differs for %s (non-Python fn): stored=%s current=%s "
            "— not treated as stale", combo_str, stored_hash[:12], current_hash[:12],
        )

    # Deep walk: is ANY ancestor record_id superseded?
    if _has_superseded_ancestor(db, output_record_id, combo_str):
        return "stale"

    logger.debug("up_to_date: %s (graph, deep walk clean)", combo_str)
    return "up_to_date"


def _has_superseded_ancestor(db, record_id: str, combo_str: str,
                              visited: set | None = None,
                              max_depth: int = 50) -> bool:
    """BFS across the bipartite provenance graph from ``record_id`` backwards.

    Returns True as soon as an ancestor record is found whose latest
    variant-version differs from the record_id referenced as a variable input of
    its producing invocation — i.e., something upstream has been re-saved since
    the descendant was computed.

    ``visited`` guards against cycles; ``max_depth`` bounds cost on pathological
    graphs (matches ``get_upstream_provenance`` default × 2).
    """
    from . import provenance_query

    if visited is None:
        visited = set()

    queue: list[tuple[str, int]] = [(record_id, 0)]
    while queue:
        current_rid, depth = queue.pop(0)
        if current_rid in visited or depth > max_depth:
            continue
        visited.add(current_rid)

        inv = provenance_query.producing_invocation(db._duck, current_rid)
        if inv is None:
            continue  # raw/manual record — terminus, nothing to supersede
        var_inputs, _constants = provenance_query.invocation_inputs(db._duck, inv[0])

        for inp in var_inputs:
            used_rid = inp.get("record_id")
            if not used_rid:
                continue
            current_latest = db.get_latest_record_id_for_variant(used_rid)
            if current_latest != used_rid:
                logger.debug(
                    "stale: %s — upstream %s at depth %d superseded (was %s, now %s)",
                    combo_str, inp.get("variable_type", "unknown"), depth + 1,
                    used_rid, current_latest,
                )
                return True
            # Also catch direct .save() updates at the same (variable_name,
            # schema_id) that don't go through an invocation.
            latest_any = _get_latest_record_at_location(db, used_rid)
            if latest_any is not None and latest_any != used_rid:
                logger.debug(
                    "stale: %s — upstream %s at depth %d superseded by different "
                    "variant (was %s, now %s)",
                    combo_str, inp.get("variable_type", "unknown"), depth + 1,
                    used_rid, latest_any,
                )
                return True
            queue.append((used_rid, depth + 1))

    return False


def _check_via_fn_hash(fn, db, output_record_id: str, output_timestamp: str | None,
                        schema_combo: dict, combo_str: str) -> ComboState:
    """Staleness check using __fn_hash from version_keys + record_id/timestamp for inputs.

    Used when the output was saved via scidb.for_each (no lineage record).

    Input freshness priority:
    1. __upstream record_ids (preferred): exact record_id comparison per variant,
       avoids false "stale" when new records are added for a *different* constant
       variant of the same input type.
    2. Timestamp comparison (fallback): used only when __upstream is absent.
       This is less precise — it compares against the MAX timestamp across ALL
       records of the input type at the schema_id, regardless of variant.
    """
    from scidb.foreach_config import _compute_fn_hash

    # Read version_keys from the output record.
    vk_rows = db._duck._fetchall(
        "SELECT version_keys FROM _record_metadata WHERE record_id = ? LIMIT 1",
        [output_record_id],
    )
    if not vk_rows:
        logger.debug("stale: %s — could not read version_keys", combo_str)
        return "stale"

    vk = json.loads(vk_rows[0][0] or "{}") if vk_rows[0][0] else {}
    stored_fn_hash = vk.get("__fn_hash")

    # a. Function hash check.
    if stored_fn_hash is None:
        # Pre-Phase-0 record: no hash stored, cannot verify function identity.
        logger.warning(
            "up_to_date (unverified): %s — no __fn_hash in version_keys "
            "(record predates Phase 0; function staleness cannot be checked)",
            combo_str,
        )
    else:
        current_hash = _compute_fn_hash(fn.fcn if hasattr(fn, "fcn") else fn)
        if stored_fn_hash != current_hash:
            logger.debug("stale: %s — function hash changed (__fn_hash)", combo_str)
            return "stale"

    # b. Input freshness via __upstream record_ids (preferred path).
    # __upstream stores the exact record_ids of the inputs that were used.
    # get_latest_record_id_for_variant checks whether a newer record now exists
    # for the same (variable_name, schema_id, version_keys) — i.e., the same
    # variant.  This is variant-precise: records added for a different constant
    # variant of the same type do not trigger staleness here.
    upstream_raw = vk.get("__upstream")
    if upstream_raw:
        upstream: dict = json.loads(upstream_raw) if isinstance(upstream_raw, str) else (upstream_raw or {})
        for rid_col, used_rid in upstream.items():
            if not used_rid:
                continue
            current_rid = db.get_latest_record_id_for_variant(used_rid)
            if current_rid != used_rid:
                logger.debug(
                    "stale: %s — upstream %s updated (was %s, now %s)",
                    combo_str, rid_col, used_rid, current_rid,
                )
                return "stale"
        logger.debug("up_to_date: %s (__fn_hash + __upstream record_ids)", combo_str)
        return "up_to_date"

    # c. Fallback: timestamp comparison when __upstream is absent.
    # For each input variable type referenced in __inputs, find the latest
    # record at the same schema_id. If that record was saved after the output,
    # the output is stale.  Note: this is variant-unaware and may produce false
    # positives when multiple variants of the same input type exist.
    if output_timestamp is None:
        logger.debug("up_to_date (unverified): %s — no output timestamp available", combo_str)
        return "up_to_date"

    inputs_raw = vk.get("__inputs", "{}")
    input_types_map: dict = json.loads(inputs_raw) if isinstance(inputs_raw, str) else {}

    schema_id_rows = db._duck._fetchall(
        "SELECT schema_id FROM _record_metadata WHERE record_id = ? LIMIT 1",
        [output_record_id],
    )
    if not schema_id_rows:
        return "up_to_date"
    output_schema_id = schema_id_rows[0][0]

    for itype in input_types_map.values():
        latest_ts_rows = db._duck._fetchall(
            "SELECT MAX(timestamp) FROM _record_metadata "
            "WHERE variable_name = ? AND schema_id = ? AND excluded = FALSE",
            [itype, output_schema_id],
        )
        if not latest_ts_rows or latest_ts_rows[0][0] is None:
            continue
        latest_input_ts = latest_ts_rows[0][0]
        if latest_input_ts > output_timestamp:
            logger.debug(
                "stale: %s — upstream %s re-saved after output (timestamp fallback)",
                combo_str, itype,
            )
            return "stale"

    logger.debug("up_to_date: %s (__fn_hash + timestamp)", combo_str)
    return "up_to_date"


def check_multiple_nodes_state(
    nodes: list[dict],
    fn_registry: dict | None = None,
    db=None,
) -> dict[str, dict]:
    """Check run state for multiple function nodes in a single call.

    Optimizes database access by sharing the connection across all node checks.
    Useful for GUI graph building where many nodes need state computation.

    Args:
        nodes: List of dicts with keys:
            - ``fn`` or ``fn_name`` (callable or str): The function object or name
            - ``call_id`` (str): 16-hex-char call site identifier
            - ``outputs`` (list[type]): Output variable classes
            When ``fn`` is not provided, ``fn_name`` is looked up in ``fn_registry``.
        fn_registry: Optional dict mapping function names to function objects.
            Used when nodes specify ``fn_name`` instead of ``fn``.
        db: DatabaseManager instance. Uses the global DB if omitted.

    Returns:
        Dict mapping node_id (``fn__{fn_name}__{call_id}``) to state result:
        {
            "state": "green" | "grey" | "red",
            "counts": {"up_to_date": N, "stale": N, "missing": N},
        }

    Example:
        >>> nodes = [
        ...     {"fn": process_emg, "call_id": "abc123", "outputs": [FilteredEMG]},
        ...     {"fn": compute_stats, "call_id": "def456", "outputs": [Stats]},
        ... ]
        >>> states = check_multiple_nodes_state(nodes, db=db)
        >>> states["fn__process_emg__abc123"]["state"]
        'green'
    """
    if db is None:
        from scidb.database import get_database
        db = get_database()

    result: dict[str, dict] = {}

    for node in nodes:
        # Get function object
        fn = node.get("fn")
        if fn is None:
            fn_name = node.get("fn_name")
            if fn_name is None:
                logger.warning("check_multiple_nodes_state: node missing both 'fn' and 'fn_name', skipping")
                continue
            if fn_registry is None:
                logger.warning("check_multiple_nodes_state: fn_name=%r but no fn_registry provided, skipping",
                               fn_name)
                continue
            fn = fn_registry.get(fn_name)
            if fn is None:
                # Function not in registry — cannot run state check, mark as red
                fn_name_safe = fn_name
                call_id = node.get("call_id", "")
                node_id = f"fn__{fn_name_safe}__{call_id}"
                result[node_id] = {
                    "state": "red",
                    "counts": {"up_to_date": 0, "stale": 0, "missing": 0},
                }
                continue
        else:
            fn_name = getattr(fn, "__name__", None) or type(fn).__name__

        outputs = node.get("outputs", [])
        call_id = node.get("call_id")

        if not outputs:
            # No outputs specified — mark as red
            node_id = f"fn__{fn_name}__{call_id or ''}"
            result[node_id] = {
                "state": "red",
                "counts": {"up_to_date": 0, "stale": 0, "missing": 0},
            }
            continue

        # Call check_node_state for this node
        try:
            state_result = check_node_state(fn, outputs, db=db, call_id=call_id)
            node_id = f"fn__{fn_name}__{call_id or ''}"
            result[node_id] = {
                "state": state_result["state"],
                "counts": state_result.get("counts", {"up_to_date": 0, "stale": 0, "missing": 0}),
            }
        except Exception:
            logger.exception(
                "check_multiple_nodes_state: check_node_state failed for %s call_id=%s — marking as red",
                fn_name, call_id,
            )
            node_id = f"fn__{fn_name}__{call_id or ''}"
            result[node_id] = {
                "state": "red",
                "counts": {"up_to_date": 0, "stale": 0, "missing": 0},
            }

    logger.debug(
        "check_multiple_nodes_state: checked %d nodes, %d results",
        len(nodes), len(result),
    )

    return result


def check_node_state(
    fn,
    outputs: list[type],
    inputs: dict | None = None,
    db=None,
    call_id: str | None = None,
) -> dict:
    """Aggregate run state across all known combos for a pipeline function.

    Enumerates combos by comparing:
    - *actual* combos: output records in the DB whose version_keys.__fn matches fn.
    - *expected* combos: schema_ids present in the input variables for each variant.

    Combos in actual → checked via :func:`check_combo_state` (up_to_date or stale).
    Combos in expected but absent from actual → "missing".

    Args:
        fn: The pipeline function (plain callable or LineageFcn).
        outputs: List of output variable classes produced by fn.
        inputs: Optional dict mapping parameter names to input variable types
            (same format as ``for_each``'s ``inputs``).  Used as a fallback to
            determine expected combos when the function has never been run and
            no pipeline variants are registered in the DB.
        db: DatabaseManager instance.  Uses the global DB if omitted.
        call_id: Optional 16-hex-char identifier for a specific for_each call
            site (see :func:`scidb.foreach_config.call_id_from_version_keys`).
            When provided, both actual and expected combos are restricted to
            records produced by that call site.  Allows the same function to
            be reused across multiple call sites without their states
            blurring together.  When omitted, behaves as the union across
            all call sites.

    Returns:
        A dict with keys:

        ``"state"`` (:data:`NodeState`)
            Overall node state:

            - ``"green"``  — every expected combo is up_to_date.
            - ``"grey"``   — some combos up_to_date, some missing (partially run).
            - ``"red"``    — never run, or any combo is stale.

        ``"combos"`` (list of dict)
            Per-combo breakdown.  Each entry has:
            ``schema_combo`` (dict), ``branch_params`` (dict), ``state`` (ComboState).

        ``"counts"`` (dict)
            ``{"up_to_date": N, "stale": N, "missing": N}``.
    """
    if db is None:
        from scidb.database import get_database
        db = get_database()

    fn_name = getattr(fn, "__name__", None) or type(fn).__name__

    # Node completeness = invocation membership (§9c). Expected invocation_ids
    # come from the persisted snapshot (_for_each_expected) unioned with a live
    # prediction over current input data; "present" = those in _invocation.
    # "stale" collapses into "missing": a changed input or edited function shifts
    # the EXPECTED id, so the old one drops out of the expected set and the new
    # (absent) one shows as needs-run (see §9c / §10.4). The legacy ``call_id``
    # filter is gone — invocation_id is config-specific, so call sites never blur.
    from . import provenance_query
    from scidb.foreach_config import _compute_fn_hash

    fn_hash = _compute_fn_hash(fn.fcn if hasattr(fn, "fcn") else fn)
    expected = provenance_query.expected_invocations_for_function(
        db, fn_name, fn_hash, inputs_fallback=inputs,
    )
    present = provenance_query.present_invocation_schema_pairs(
        db._duck, {inv_id for inv_id, _sid in expected},
    )

    counts: dict[str, int] = {"up_to_date": 0, "stale": 0, "missing": 0}
    combo_results: list[dict] = []
    for inv_id, schema_id in expected:
        state: ComboState = "up_to_date" if (inv_id, schema_id) in present else "missing"
        counts[state] += 1
        combo_results.append({
            "schema_combo": _schema_id_to_combo(db, schema_id),
            "branch_params": {},
            "state": state,
        })

    # --- Aggregate to node state ---
    if not combo_results:
        # Function never run and no input data exists yet.
        overall: NodeState = "red"
    elif counts["missing"] > 0 and counts["up_to_date"] == 0:
        overall = "red"
    elif counts["missing"] > 0:
        overall = "grey"
    else:
        overall = "green"

    logger.debug(
        "node %s: %s (up_to_date=%d, missing=%d)",
        fn_name, overall, counts["up_to_date"], counts["missing"],
    )

    return {
        "state": overall,
        "combos": combo_results,
        "counts": counts,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _combo_str(schema_combo: dict, branch_params: dict | None = None) -> str:
    parts = [f"{k}={v}" for k, v in sorted(schema_combo.items())]
    if branch_params:
        parts += [f"{k}={v}" for k, v in sorted(branch_params.items())]
    return ", ".join(parts)


def _schema_id_to_combo(db, schema_id) -> dict:
    """Convert a schema_id to a dict of schema key → value."""
    schema_keys = db.dataset_schema_keys
    if not schema_keys:
        return {}

    col_select = ", ".join(f'"{k}"' for k in schema_keys)
    rows = db._duck._fetchall(
        f"SELECT {col_select} FROM _schema WHERE schema_id = ?",
        [int(schema_id)],
    )
    if not rows:
        return {}

    return {k: v for k, v in zip(schema_keys, rows[0]) if v is not None}


def _get_latest_record_at_location(db, record_id: str) -> str | None:
    """Get the latest record_id at the same (variable_name, schema_id),
    ignoring version_keys.

    Used by ``_has_superseded_ancestor`` to detect direct ``.save()``
    updates that don't carry ``__fn`` in version_keys — they would be
    in a different partition from pipeline-produced records and invisible
    to ``get_latest_record_id_for_variant``.
    """
    rows = db._duck._fetchall(
        "SELECT variable_name, schema_id FROM _record_metadata "
        "WHERE record_id = ? LIMIT 1",
        [record_id],
    )
    if not rows:
        return None
    vn, sid = rows[0]
    latest = db._duck._fetchall(
        "SELECT record_id FROM _record_metadata "
        "WHERE variable_name = ? AND schema_id = ? "
        "AND COALESCE(excluded, FALSE) = FALSE "
        "ORDER BY timestamp DESC LIMIT 1",
        [vn, int(sid)],
    )
    if not latest:
        return None
    return latest[0][0]
