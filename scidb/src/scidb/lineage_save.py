"""Lineage-aware save paths for LineageFcnResult outputs.

Persists a ``scilineage.LineageFcnResult`` (and the side-effect ``generates_file``
variant) into the scidb database with full provenance: the output value plus the
bipartite provenance graph (records ↔ invocations) written via
``provenance_save.record_run_from_lineage``.

This logic previously lived in ``scihist.foreach`` and was imported *up* into
``scidb.foreach`` (an inverted layer dependency). It operates entirely on scidb
internals (``_save_record_metadata``, ``DatabaseManager.save``) plus scilineage
primitives, so it belongs in scidb. ``scihist`` now re-exports these for
backward compatibility.
"""

import json
import logging
import time
from datetime import datetime
from typing import Any

from .log import Log as _Log

logger = logging.getLogger(__name__)


def _save_lineage_fcn_result(
    output_obj: Any,
    data: "LineageFcnResult",
    metadata: dict,
    db: Any | None,
    input_rids: dict | None = None,
) -> str | None:
    """Save a LineageFcnResult with full lineage tracking."""
    from scilineage import LineageFcnResult, extract_lineage, get_raw_value
    from .database import get_database, get_user_id

    output_name = output_obj.__name__ if isinstance(output_obj, type) else type(output_obj).__name__
    fn_name = data.invoked.fcn.fn.__name__ if hasattr(data.invoked.fcn, 'fn') else "unknown"
    logger.debug("_save_lineage_fcn_result entry: output=%s, fn=%s, generates_file=%s, metadata=%s",
                 output_name, fn_name, data.invoked.fcn.generates_file, metadata)
    t0 = time.time()

    try:
        active_db = db
        if active_db is None:
            active_db = get_database()

        # Lineage-only save for side-effect functions (generates_file=True)
        if data.invoked.fcn.generates_file:
            lineage_record = extract_lineage(data)
            lineage_dict = _lineage_to_dict(lineage_record)
            pipeline_lineage_hash = data.invoked.compute_lineage_hash()
            generated_id = f"generated:{pipeline_lineage_hash[:32]}"
            user_id = get_user_id()
            nested_metadata = active_db._split_metadata(metadata)

            schema_keys = nested_metadata.get("schema", {})
            version_keys = nested_metadata.get("version", {})
            version_keys["__fn"] = lineage_dict.get("function_name", fn_name)
            version_keys["__fn_hash"] = lineage_dict.get("function_hash", "")
            schema_level = active_db._infer_schema_level(schema_keys)
            schema_id = (
                active_db._duck._get_or_create_schema_id(schema_level, schema_keys)
                if schema_level is not None and schema_keys
                else 0
            )
            active_db._save_record_metadata(
                record_id=generated_id,
                timestamp=datetime.now().isoformat(),
                variable_name=output_name,
                schema_id=schema_id,
                version_keys=version_keys or None,
                content_hash=None,
                lineage_hash=pipeline_lineage_hash,
                schema_version=getattr(output_obj, 'schema_version', 1),
                user_id=user_id,
            )
            _record_generates_file_graph(
                active_db, generated_id, output_name, output_obj, data,
                lineage_dict, user_id, pipeline_lineage_hash,
            )
            elapsed = time.time() - t0
            logger.debug("_save_lineage_fcn_result exit: output=%s, record_id=%s (generates_file), elapsed=%.3fs",
                         output_name, generated_id[:12], elapsed)
            if _Log:
                stored_fn_hash = lineage_dict.get("function_hash") or ""
                _Log.info(f"[save-lineage] {output_name}: record_id={generated_id[:12]} function_hash={stored_fn_hash[:12] or 'None'} (generates_file)")
                _Log.debug(f"[save-lineage] {output_name}: pipeline_lineage_hash={pipeline_lineage_hash[:12]}")
            return generated_id

        lineage_record = extract_lineage(data)
        lineage_dict = _lineage_to_dict(lineage_record)
        lineage_hash = data.hash
        pipeline_lineage_hash = data.invoked.compute_lineage_hash()
        raw_data = get_raw_value(data)

        variable_class = output_obj if isinstance(output_obj, type) else type(output_obj)
        instance = variable_class(raw_data)
        fn_metadata = dict(metadata)
        fn_metadata["__fn"] = lineage_dict.get("function_name", fn_name)
        fn_metadata["__fn_hash"] = lineage_dict.get("function_hash", "")
        rid = active_db.save(
            instance,
            fn_metadata,
            lineage=lineage_dict,
            lineage_hash=lineage_hash,
            pipeline_lineage_hash=pipeline_lineage_hash,
            output_num=int(getattr(data, "output_num", 0) or 0),
            graph_function_hash=_graph_fn_hash(data),
        )
        elapsed = time.time() - t0
        logger.debug("_save_lineage_fcn_result exit: output=%s, record_id=%s, elapsed=%.3fs",
                     output_name, rid[:12] if rid else None, elapsed)
        if _Log and rid:
            stored_fn_hash = lineage_dict.get("function_hash") or ""
            _Log.info(f"[save-lineage] {output_name}: record_id={rid[:12]} function_hash={stored_fn_hash[:12] or 'None'}")
            _Log.debug(f"[save-lineage] {output_name}: lineage_hash={lineage_hash[:12] if lineage_hash else 'None'}, pipeline_lineage_hash={pipeline_lineage_hash[:12]}")
        return rid
    except Exception:
        elapsed = time.time() - t0
        logger.exception("_save_lineage_fcn_result FAILED: output=%s, fn=%s, elapsed=%.3fs",
                         output_name, fn_name, elapsed)
        raise


def save_lineage_result(
    output_obj: Any,
    lineage_result: "LineageFcnResult",
    metadata: dict,
    db: Any | None,
) -> str | None:
    """Save a LineageFcnResult with lineage tracking.

    This function is called by scidb.for_each when it detects a LineageFcnResult.
    It receives pre-built metadata from scidb (including version_keys and branch_params)
    and adds lineage-specific information.

    Args:
        output_obj: The output variable class
        lineage_result: The LineageFcnResult containing data and lineage info
        metadata: Pre-built metadata from scidb (includes __fn, __fn_hash,
                  __inputs, __constants, __branch_params, __upstream)
        db: Database instance (optional)

    Returns:
        record_id of the saved output
    """
    from scilineage import extract_lineage, get_raw_value
    from .database import get_database

    output_name = output_obj.__name__ if hasattr(output_obj, '__name__') else str(output_obj)
    logger.info("[scidb] save_lineage_result callback: saving %s with lineage", output_name)
    if _Log:
        _Log.info(f"[scidb] save_lineage_result: saving {output_name} with lineage")

    output_name = output_obj.__name__ if isinstance(output_obj, type) else type(output_obj).__name__
    fn_name = lineage_result.invoked.fcn.fn.__name__ if hasattr(lineage_result.invoked.fcn, 'fn') else "unknown"
    logger.debug("save_lineage_result entry: output=%s, fn=%s, generates_file=%s",
                 output_name, fn_name, lineage_result.invoked.fcn.generates_file)

    active_db = db if db is not None else get_database()

    # Extract input_rids from __upstream in metadata (legacy, no longer used)
    # BaseVariable reconstruction in scidb wrapper now handles variable tracking.
    input_rids = {}
    if "__upstream" in metadata:
        try:
            # Handle both dict (new format) and JSON string (old format) for backward compatibility
            upstream_val = metadata["__upstream"]
            if isinstance(upstream_val, dict):
                input_rids = upstream_val
            else:
                input_rids = json.loads(upstream_val)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Failed to parse __upstream for rid tracking")

    # Merge in Fixed input record_ids from scihist (for staleness tracking)
    if "__lineage_fixed_rids" in metadata:
        fixed_rids = metadata.get("__lineage_fixed_rids", {})
        if fixed_rids:
            input_rids.update(fixed_rids)
            logger.debug("Merged %d fixed_rids into input_rids", len(fixed_rids))

    # Extract lineage
    lineage_record = extract_lineage(lineage_result)
    lineage_dict = _lineage_to_dict(lineage_record)

    # Handle generates_file case (lineage-only save)
    if lineage_result.invoked.fcn.generates_file:
        from .database import get_user_id
        pipeline_lineage_hash = lineage_result.invoked.compute_lineage_hash()
        generated_id = f"generated:{pipeline_lineage_hash[:32]}"
        user_id = get_user_id()
        nested_metadata = active_db._split_metadata(metadata)

        schema_keys = nested_metadata.get("schema", {})
        version_keys = nested_metadata.get("version", {})
        # version_keys already contains __fn, __fn_hash from scidb
        schema_level = active_db._infer_schema_level(schema_keys)
        schema_id = (
            active_db._duck._get_or_create_schema_id(schema_level, schema_keys)
            if schema_level is not None and schema_keys
            else 0
        )
        active_db._save_record_metadata(
            record_id=generated_id,
            timestamp=datetime.now().isoformat(),
            variable_name=output_name,
            schema_id=schema_id,
            version_keys=version_keys or None,
            content_hash=None,
            lineage_hash=pipeline_lineage_hash,
            schema_version=getattr(output_obj, 'schema_version', 1),
            user_id=user_id,
        )
        _record_generates_file_graph(
            active_db, generated_id, output_name, output_obj, lineage_result,
            lineage_dict, user_id, pipeline_lineage_hash,
        )
        logger.info("[scidb] save_lineage_result: saved generates_file output, record_id=%s", generated_id[:12])
        if _Log:
            _Log.info(f"[scidb] save_lineage_result complete (generates_file): record_id={generated_id[:12]}")
        return generated_id

    # Normal case: save data + lineage
    logger.debug("[scidb] save_lineage_result: normal save path (data + lineage)")
    lineage_hash = lineage_result.hash
    pipeline_lineage_hash = lineage_result.invoked.compute_lineage_hash()
    raw_data = get_raw_value(lineage_result)

    variable_class = output_obj if isinstance(output_obj, type) else type(output_obj)
    instance = variable_class(raw_data)

    # Use pre-built metadata from scidb (already contains version_keys and branch_params)
    rid = active_db.save(
        instance,
        metadata,
        lineage=lineage_dict,
        lineage_hash=lineage_hash,
        pipeline_lineage_hash=pipeline_lineage_hash,
        output_num=int(getattr(lineage_result, "output_num", 0) or 0),
        graph_function_hash=_graph_fn_hash(lineage_result),
    )

    logger.info("[scidb] save_lineage_result: saved %s, record_id=%s", output_name, rid[:12] if rid else None)
    if _Log:
        _Log.info(f"[scidb] save_lineage_result complete: {output_name} record_id={rid[:12] if rid else None}")
    return rid


def save(variable_class, data, db=None, **metadata) -> str | None:
    """Save data to the database with lineage tracking.

    This is the lineage-aware save that handles LineageFcnResult:
    - If ``data`` is a LineageFcnResult, extracts lineage and saves with full
      provenance tracking.
    - Otherwise, delegates to ``variable_class.save(data, **metadata)``.

    Args:
        variable_class: The BaseVariable subclass to save as.
        data: The data to save. Can be a LineageFcnResult or raw data.
        db: Optional database instance.
        **metadata: Addressing metadata (e.g., subject=1, trial=1).

    Returns:
        str: The record_id of the saved data.
    """
    from scilineage import LineageFcnResult

    var_name = variable_class.__name__ if isinstance(variable_class, type) else type(variable_class).__name__
    is_lineage = isinstance(data, LineageFcnResult)
    logger.debug("save() entry: variable=%s, is_lineage_result=%s, metadata_keys=%s",
                 var_name, is_lineage, list(metadata.keys()))

    if is_lineage:
        rid = _save_lineage_fcn_result(variable_class, data, metadata, db)
        logger.debug("save() exit: variable=%s, record_id=%s (lineage path)",
                     var_name, rid[:12] if rid else None)
        return rid
    else:
        db_kwargs = {"db": db} if db is not None else {}
        rid = variable_class.save(data, **db_kwargs, **metadata)
        logger.debug("save() exit: variable=%s, record_id=%s (plain path)",
                     var_name, rid[:12] if rid else None)
        return rid


def _record_generates_file_graph(
    active_db, generated_id, output_name, output_obj, lineage_result,
    lineage_dict, user_id, pipeline_hash=None,
) -> None:
    """Write the bipartite graph for a ``generates_file`` (side-effect) save.

    These records are persisted via ``_save_record_metadata`` directly (no
    ``db.save``), so the graph is recorded here instead. Needed so
    ``skip_computed``, node-state, and ``find_by_lineage`` see an invocation for
    generated outputs. Additive/defensive: never fail the save on a graph error.
    """
    try:
        from .provenance_save import record_run_from_lineage
        record_run_from_lineage(
            active_db,
            generated_id,
            output_name,
            getattr(output_obj, "schema_version", 1),
            int(getattr(lineage_result, "output_num", 0) or 0),
            lineage_dict,
            where_clause=None,
            user_id=user_id,
            function_hash=_graph_fn_hash(lineage_result),
            pipeline_hash=pipeline_hash,
        )
    except Exception:
        logger.debug("generates_file graph write failed", exc_info=True)


def _graph_fn_hash(lineage_result: Any) -> str | None:
    """16-char ``compute_function_hash`` of a LineageFcnResult's function.

    The bipartite graph stores ``compute_function_hash(fn, 16)`` (the same
    ``__fn_hash`` for_each writes), so the staleness/skip read side can use one
    hashing recipe across both save paths. ``LineageRecord.function_hash`` is
    instead ``LineageFcn.hash`` (a different scheme), so we derive the 16-char
    form here from the wrapped function. Returns None if unavailable (the graph
    then falls back to the lineage dict's value).
    """
    try:
        from scilineage.hashing import compute_function_hash
        fcn = lineage_result.invoked.fcn
        return compute_function_hash(fcn, truncate=16)
    except Exception:
        logger.debug("_graph_fn_hash: could not compute function hash", exc_info=True)
        return None


def _lineage_to_dict(lineage_record) -> dict:
    """Convert a scilineage.LineageRecord to the dict format scidb expects."""
    return {
        "function_name": lineage_record.function_name,
        "function_hash": lineage_record.function_hash,
        "inputs": lineage_record.inputs,
        "constants": lineage_record.constants,
    }
