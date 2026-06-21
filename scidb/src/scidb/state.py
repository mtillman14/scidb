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
    print(result["state"])    # "green" | "red"
    for combo in result["combos"]:
        print(combo["schema_combo"], combo["state"])
"""

import json
import logging
from typing import Literal

logger = logging.getLogger(__name__)

ComboState = Literal["up_to_date", "stale", "missing"]
# Node state is BINARY: a node is either fully computed-and-current ("green") or
# needs attention ("red"). "grey"/partial was removed — "needs attention" is one
# state regardless of whether the node never ran, ran partially, has a re-saved
# input, or had its function edited.
NodeState = Literal["green", "red"]


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
    if db is None:
        from scidb.database import get_database
        db = get_database()

    combo_str = _combo_str(schema_combo, branch_params)

    # Step 1: all outputs must have a record for this combo.
    # Pass branch_params separately so namespaced keys (e.g. "fn.param") go
    # through the suffix-matching path rather than the version_keys filter,
    # which would fail because version_keys stores un-namespaced param names.
    output_record_id = None
    for OutputCls in outputs:
        rid = db.find_record_id(OutputCls, schema_combo, branch_params_filter=branch_params or None)
        if rid is None:
            logger.debug("missing: %s — no output record for %s", combo_str, OutputCls.__name__)
            return "missing"
        output_record_id = rid

    # Staleness over the bipartite provenance graph (records produced by
    # for_each). A record with no producing invocation is raw/manual — there is
    # no function or input to be stale against, so it is up_to_date.
    from . import provenance_query
    sig = provenance_query.stored_invocation_signature(db._duck, output_record_id)
    if sig is None:
        logger.debug("up_to_date: %s — raw record (no producing invocation)", combo_str)
        return "up_to_date"
    return _check_via_graph(fn, db, output_record_id, sig, combo_str)


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
    from scidb.foreach_config import _compute_fn_hash

    # Function's own code changed since the output was saved? (Python only.)
    # The graph stores ``function_hash`` = compute_function_hash(fn, 16) (the
    # ``__fn_hash`` the save path writes), so compare against the same recipe.
    # Trust the hash only for plain Python functions: a MATLAB handle brings its
    # own ``.hash`` from a different hashing pipeline, so a mismatch there is not
    # reliable evidence of a code change (see .claude/defer-function-hash-staleness.md).
    trusts_hash = not hasattr(fn, "hash")
    stored_hash = sig.get("function_hash")
    current_hash = _compute_fn_hash(fn.fcn if hasattr(fn, "fcn") else fn)
    if stored_hash is not None and stored_hash != current_hash:
        if trusts_hash:
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
            "state": "green" | "red",
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
            Overall node state (binary):

            - ``"green"`` — the node has expected work and every expected combo
              is present (fully computed and current).
            - ``"red"``   — anything else: never run, partially run, an input was
              re-saved but not re-run, or the function was edited. Any missing
              expected invocation makes the whole node red.

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
    # are derived LIVE from current input data over each variant config the
    # function has run with (plus the declared-inputs fallback); "present" =
    # those in _invocation. There is no persisted snapshot — `_for_each_expected`
    # was removed because the predicted-vs-realized id pair was a drift hazard.
    # Consequence: a zero-input function (PathInput-only loader) has no live
    # source for its expected set, so a partially-run loader still reads green
    # (the un-run combos leave no trace); it is red only when never run.
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

    # --- Aggregate to node state (binary: green | red) ---
    # green iff the node has expected work AND all of it is present; red otherwise
    # (never run / no input data, partially run, input re-saved but not re-run, or
    # edited function — all leave >=1 expected invocation missing).
    if combo_results and counts["missing"] == 0:
        overall: NodeState = "green"
    else:
        overall = "red"

    logger.debug(
        "node %s: %s (up_to_date=%d, missing=%d)",
        fn_name, overall, counts["up_to_date"], counts["missing"],
    )

    return {
        "state": overall,
        "combos": combo_results,
        "counts": counts,
    }


def check_pathinput_node_state(
    fn,
    outputs: list[type],
    inputs: dict,
    db=None,
    **iteration: list,
) -> dict:
    """Outdated check for a PathInput / constant-only function (no variable inputs).

    A loader whose only inputs are a ``PathInput`` (+ optional constants) has no
    DB-variable input to predict an expected set from, so the generic
    :func:`check_node_state` can only report green-when-run / red-when-never-run
    (a partially-run loader reads green — un-run combos leave no trace). This check
    closes that gap by reconstructing the combos a run *would* produce **now** and
    diffing them against what the loader has actually produced.

    The should-run set is exactly the combos a run would *produce output for* now —
    the **intersection** of the files on disk and the declared grid::

        should = PathInput.discover()  ∩  Cartesian product of `iteration`
               − schema-excluded combos

    i.e. discovered combos restricted to the grid (empty/unspecified grid keys are
    wildcards, so pure-discovery mode keeps every discovered combo). A grid combo
    with no file produces nothing, and a file outside the grid is not iterated — so
    neither is in ``should`` (and neither makes the node red). When there is no
    PathInput at all (pure constants over a grid), ``should`` is just the grid.

    Realized = the schema locations this function has produced output at under the
    **current constants** (graph ground truth, content-addressed match — no
    invocation_id recompute). The node is **red** iff any should-combo is not
    realized (a new in-grid file appeared and hasn't been run); **green** otherwise.
    Adding unwanted new data to the exclusion list drops it from ``should`` and
    flips the node back to green, as if it did not exist.

    Args:
        fn: the pipeline function (plain callable).
        outputs: output variable classes (accepted for signature parity; unused —
            realized locations are read per producing function).
        inputs: the ``for_each`` ``inputs`` dict (PathInput + any constants).
        db: DatabaseManager (global DB if omitted).
        **iteration: the iteration grid (e.g. ``subject=["1", "2"]``) — the same
            metadata_iterables passed to ``for_each``. Empty/omitted keys fall back
            to filesystem discovery, exactly like ``for_each``.

    Returns the same dict shape as :func:`check_node_state`: ``{state, combos, counts}``.
    """
    import itertools

    if db is None:
        from scidb.database import get_database
        db = get_database()
    from scidb.database import _schema_str
    from scidb.exclusions import filter_excluded_combos
    from .foreach import _find_pathinput
    from .provenance import compute_constant_record_id
    from . import provenance_query

    fn_name = getattr(fn, "__name__", None) or type(fn).__name__
    schema_keys = list(db.dataset_schema_keys)

    def _norm(combo: dict) -> dict:
        return {k: _schema_str(v) for k, v in combo.items() if v is not None}

    # --- should-run set: PathInput.discover() ∩ iteration grid, dedup, then exclude.
    # This is exactly what for_each would *produce output for* now: a discovered
    # file only counts if its combo is within the declared grid, and a grid combo
    # only counts if a file exists for it. Unspecified/empty grid keys are
    # wildcards, so pure-discovery mode (no grid) keeps every discovered combo. ---
    should: list[dict] = []
    seen: set = set()

    def _add(combo: dict) -> None:
        c = _norm(combo)
        key = tuple(sorted(c.items()))
        if c and key not in seen:
            seen.add(key)
            should.append(c)

    grid_keys = [k for k, v in iteration.items() if v]
    grid_sets = {k: {_schema_str(x) for x in iteration[k]} for k in grid_keys}

    pi = _find_pathinput(inputs)
    if pi is not None:
        # Discovered combos that satisfy the grid (the intersection).
        for combo in pi.discover():
            c = _norm(combo)
            if all(c.get(k) in grid_sets[k] for k in grid_keys):
                _add(c)
    elif grid_keys:
        # No PathInput (pure constant inputs over a grid): there is no filesystem
        # to intersect with, so the declared grid itself is the should-run set.
        for prod in itertools.product(*[iteration[k] for k in grid_keys]):
            _add(dict(zip(grid_keys, prod)))

    should = filter_excluded_combos(should, schema_keys, db)

    # --- realized locations produced under the current constants (graph truth) ---
    cfg = provenance_query.config_from_inputs(inputs)
    const_rids = {p: compute_constant_record_id(v) for p, v in cfg["constants"].items()}
    realized_sids = provenance_query.realized_inputless_schema_ids(
        db._duck, fn_name, const_rids,
    )
    realized = [_norm(_schema_id_to_combo(db, sid)) for sid in realized_sids]

    def _is_realized(c: dict) -> bool:
        # a should-combo is covered if some realized location agrees on all its keys
        return any(all(r.get(k) == v for k, v in c.items()) for r in realized)

    counts: dict[str, int] = {"up_to_date": 0, "stale": 0, "missing": 0}
    combo_results: list[dict] = []
    for c in should:
        st: ComboState = "up_to_date" if _is_realized(c) else "missing"
        counts[st] += 1
        combo_results.append({"schema_combo": c, "branch_params": {}, "state": st})

    overall: NodeState = "green" if (combo_results and counts["missing"] == 0) else "red"
    logger.debug(
        "pathinput node %s: %s (should=%d, up_to_date=%d, missing=%d)",
        fn_name, overall, len(should), counts["up_to_date"], counts["missing"],
    )
    return {"state": overall, "combos": combo_results, "counts": counts}


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
        "SELECT type, schema_id FROM _record "
        "WHERE record_id = ? LIMIT 1",
        [record_id],
    )
    if not rows:
        return None
    vn, sid = rows[0]
    # Recency from the save-event log; type/schema/excluded from the _record entity.
    latest = db._duck._fetchall(
        "SELECT rm.record_id FROM _record_save rm "
        "JOIN _record r ON r.record_id = rm.record_id "
        "WHERE r.type = ? AND r.schema_id = ? "
        "AND COALESCE(r.excluded, FALSE) = FALSE "
        "ORDER BY rm.timestamp DESC LIMIT 1",
        [vn, int(sid)],
    )
    if not latest:
        return None
    return latest[0][0]
