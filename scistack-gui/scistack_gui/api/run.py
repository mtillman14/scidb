"""
POST /api/run

Triggers a for_each call in a background thread and streams stdout
back to the frontend via WebSocket.

Payload:
  {
    "function_name": "compute_rolling_vo2",
    "variants": [
      {"window_seconds": 30, "sample_interval": 5},
      {"window_seconds": 60, "sample_interval": 5}
    ]
  }

Each entry in `variants` is a constants dict. We run one for_each call
per variant. If `variants` is empty we run all known variants from the DB.
"""

import ctypes
import logging
import sys
import time
import uuid
import threading
from io import StringIO
from contextlib import redirect_stdout

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from scihist import for_each
from scidb.database import DatabaseManager

from scistack_gui.db import get_db
from scistack_gui import registry
from scistack_gui.api.ws import push_message

# This logger is configured in server.py (FastAPI) / __main__.py (JSON-RPC)
# to write to stderr with the "[scistack] …" prefix. The extension forwards
# stderr to the SciStack Output channel, so .info() calls here show up in
# VS Code's UI in addition to being captured by scidb.log.Log for the on-disk
# scidb.log file.
logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Per-run cancellation registry
# ---------------------------------------------------------------------------
#
# Each entry: {
#   "event": threading.Event,        # set by cancel_run / force_cancel_run
#   "thread": threading.Thread,      # the worker thread running _run_in_thread
#   "cancelled": bool,               # True after cooperative cancel requested
#   "force_cancelled": bool,         # True after force cancel requested
# }
#
# The registry is module-level (process-wide); lookups by run_id are O(1).
# Mutated only from the FastAPI/JSON-RPC handler thread and the worker
# thread's entry/exit, so a plain dict is sufficient.
_active_runs: dict[str, dict] = {}
_active_runs_lock = threading.Lock()


class WhereFilterSpec(BaseModel):
    variable: str              # variable type name, e.g. "Side"
    op: str                    # "==", "!=", "<", "<=", ">", ">=", "IN"
    value: str                 # always string, coerced on backend


class RunRequest(BaseModel):
    function_name: str
    variants: list[dict] = []   # list of constants dicts; empty = run all known
    run_id: str | None = None   # frontend-generated ID; we generate one if absent
    schema_filter: dict[str, list] | None = None   # {key: [selected values]}; None = all
    schema_level: list[str] | None = None          # which schema keys to iterate; None = all
    run_options: dict | None = None   # {dry_run, save, distribute}; all optional
    where_filters: list[WhereFilterSpec] | None = None  # data filters for where= param


def _run_in_thread(run_id: str, function_name: str, variants: list[dict], db: DatabaseManager,
                    schema_filter: dict[str, list] | None = None,
                    schema_level: list[str] | None = None,
                    run_options: dict | None = None,
                    where_filters: list[WhereFilterSpec] | None = None):
    """
    Executed in a background thread. Runs for_each for each variant,
    captures stdout line-by-line, and pushes it to the WebSocket queue.
    """
    logger.info(
        "[run_thread] Thread started for run_id=%s, function=%s, variants=%d, "
        "schema_level=%s, schema_filter=%s, where_filters=%s, run_options=%s",
        run_id, function_name, len(variants or []),
        schema_level, _summarize_schema_filter(schema_filter),
        len(where_filters) if where_filters else 0,
        run_options,
    )

    def emit(text: str):
        logger.debug("[run_thread] Emitting output for run_id=%s: %s", run_id, text.rstrip())
        push_message({"type": "run_output", "run_id": run_id, "text": text})

    class _RunLogRelay(logging.Handler):
        """Relays scifor/scidb INFO+ log records to the frontend run console.

        The pipeline narrative (banner, progress, run summary, failures) is
        log records since the logging redesign — stdout only carries dry-run
        output — so the frontend gets it from a scoped handler instead.
        Attached to the "scifor"/"scidb" loggers only (never "scistack_gui",
        whose records include emit()'s own debug line — a feedback loop).
        """

        _RELAY_LOGGERS = ("scifor", "scidb")

        def __init__(self):
            super().__init__(level=logging.INFO)
            self.setFormatter(logging.Formatter("%(message)s"))

        def emit(self, record):
            try:
                emit(self.format(record) + "\n")
            except Exception:
                pass

        def __enter__(self):
            for name in self._RELAY_LOGGERS:
                logging.getLogger(name).addHandler(self)
            return self

        def __exit__(self, *exc):
            for name in self._RELAY_LOGGERS:
                logging.getLogger(name).removeHandler(self)
            return False

    # Register this run so cancel_run/force_cancel_run can find it.
    logger.info("[run_thread] Registering run in active runs registry (run_id=%s)", run_id)
    cancel_event = threading.Event()
    with _active_runs_lock:
        _active_runs[run_id] = {
            "event": cancel_event,
            "thread": threading.current_thread(),
            "cancelled": False,
            "force_cancelled": False,
        }
    logger.debug("[run_thread] Run registered successfully (run_id=%s)", run_id)

    def _is_cancelled() -> bool:
        return cancel_event.is_set()

    # The DatabaseManager is stored in thread-local storage by configure_database().
    # Background threads don't inherit that local, so we re-register it here.
    logger.info("[run_thread] Setting current database for thread (run_id=%s)", run_id)
    db.set_current_db()

    logger.info("[run_thread] Looking up function '%s' in registry (run_id=%s)", function_name, run_id)
    try:
        fn = registry.get_function(function_name)
        logger.debug("[run_thread] Function found: %s (run_id=%s)", fn, run_id)
    except KeyError as e:
        logger.warning("[run_thread] Function not found: %s (run_id=%s)", e, run_id)
        push_message({"type": "run_done", "run_id": run_id, "success": False,
                      "error": str(e), "cancelled": False})
        with _active_runs_lock:
            _active_runs.pop(run_id, None)
        logger.info("[run_thread] Thread exiting due to function not found (run_id=%s)", run_id)
        return

    # Derive the for_each targets for this function node — DB history with
    # manual-wiring overrides, or the manual-edge fallback. Shared with the
    # pipeline compiler (execution_service) so per-node and pipeline runs
    # derive identically.
    logger.info("[run_thread] Deriving targets for '%s' (run_id=%s)",
                function_name, run_id)
    from scistack_gui.services.execution_service import derive_fn_targets
    fn_variants = derive_fn_targets(db, function_name)
    logger.debug("[run_thread] Derived %d target(s) for '%s' (run_id=%s)",
                 len(fn_variants), function_name, run_id)
    if not fn_variants:
        push_message({"type": "run_done", "run_id": run_id, "success": False,
                      "error": f"No pipeline history or output connections found for '{function_name}'. "
                               "Connect it to an output variable node first."})
        with _active_runs_lock:
            _active_runs.pop(run_id, None)
        logger.info("[run_thread] Thread exiting due to no targets (run_id=%s)", run_id)
        return

    # --- Variant resolution via domain layer ---
    logger.info("[run_thread] Resolving variants to execute (run_id=%s)", run_id)
    from scistack_gui.domain.variant_resolver import (
        filter_variants, deduplicate_variants,
    )

    # Determine which variants to run.
    if variants:
        logger.debug("[run_thread] Filtering %d DB variants to requested %d variants (run_id=%s)",
                    len(fn_variants), len(variants), run_id)
        targets = filter_variants(fn_variants, variants)
    else:
        logger.debug("[run_thread] Using all %d DB variants (run_id=%s)", len(fn_variants), run_id)
        targets = fn_variants

    # Staged pending constants override DB values on the derived targets —
    # shared helper with the pipeline compiler so eager and pull runs
    # materialize staged values identically. Deduplicate AFTER overriding:
    # targets differing only in the overridden constant collapse together.
    from scistack_gui import pipeline_store as _ps
    from scistack_gui.services.execution_service import apply_pending_overrides
    pending_consts = _ps.get_pending_constants(db)
    if pending_consts:
        logger.info("[run_thread] Pending constants will override DB values: %s (run_id=%s)",
                    list(pending_consts.keys()), run_id)
    unique_targets = deduplicate_variants(
        apply_pending_overrides(targets, pending_consts))
    logger.debug("[run_thread] After override + deduplication: %d unique targets (run_id=%s)",
                len(unique_targets), run_id)

    # Extract run options (dry_run, save, distribute, as_table).
    logger.info("[run_thread] Extracting run options (run_id=%s)", run_id)
    opts = run_options or {}
    opt_dry_run = opts.get("dry_run", False)
    opt_save = opts.get("save", True)
    opt_distribute = opts.get("distribute", False)
    opt_as_table = opts.get("as_table", False)
    logger.debug("[run_thread] Run options: dry_run=%s, save=%s, distribute=%s, as_table=%s (run_id=%s)",
                opt_dry_run, opt_save, opt_distribute, opt_as_table, run_id)

    # Schema iteration is handled by for_each via schema_filter/schema_level —
    # but for_each ONLY auto-iterates when one of them is set. With both None
    # it pools every schema row into a single call, which is never what a
    # canvas Run means for per-combo functions (the seed scripts pass
    # explicit iterables). Default to iterating ALL schema keys — EXCEPT
    # when the user explicitly chose as_table, which means "pool the rows".
    if schema_level is None and schema_filter is None and not opt_as_table:
        schema_level = list(db.dataset_schema_keys)
        logger.info("[run_thread] No schema iteration requested — defaulting "
                    "to all schema keys: %s (run_id=%s)", schema_level, run_id)
    if schema_level:
        logger.debug("[run_thread] Schema level: %s (run_id=%s)", schema_level, run_id)
    if schema_filter:
        logger.debug("[run_thread] Schema filter: %s (run_id=%s)",
                     {k: f"{len(v)} values" for k, v in schema_filter.items()}, run_id)

    success = True
    run_started_at = time.time()
    # Accumulated across targets from scifor's authoritative "summary"
    # progress events: for_each never raises on iteration failures
    # (continue-and-report), so success must be decided from these counts —
    # NOT from "the for_each call returned". skip_computed skips are
    # removed before the loop and never inflate 'failed'.
    combo_totals = {"completed": 0, "failed": 0}
    # Build where= argument from where_filters.
    logger.info("[run_thread] Building where filters (run_id=%s)", run_id)
    where_arg = _build_where(where_filters)
    if where_arg:
        logger.debug("[run_thread] Where filters built: %s (run_id=%s)", where_arg, run_id)

    logger.info(
        "[run_thread] Starting execution of %d target(s) for '%s' "
        "(dry_run=%s, save=%s, distribute=%s, as_table=%s, schema_level=%s, schema_filter=%s) (run_id=%s)",
        len(unique_targets), function_name,
        opt_dry_run, opt_save, opt_distribute, opt_as_table,
        schema_level, _summarize_schema_filter(schema_filter), run_id,
    )

    cancelled = False
    try:
        for idx, v in enumerate(unique_targets, 1):
            # Cooperative cancel: stop before launching the next variant.
            if _is_cancelled():
                logger.info("[run_thread] Cancel detected between variants — stopping (run_id=%s, target=%d/%d)",
                            run_id, idx, len(unique_targets))
                cancelled = True
                emit("⛔ Cancelled\n")
                break
            # Build inputs dict: variable class inputs + scalar constants
            logger.info("[run_thread] Processing target %d/%d (run_id=%s)",
                       idx, len(unique_targets), run_id)
            try:
                logger.debug("[run_thread] Building inputs for target %d (run_id=%s)", idx, run_id)
                inputs = {}
                for param, type_names in v["input_types"].items():
                    # type_names may be a list (new) or a string (from DB history).
                    if isinstance(type_names, list):
                        if len(type_names) > 1:
                            from scidb import EachOf
                            inputs[param] = EachOf(*(registry.get_variable_class(t) for t in type_names))
                            logger.debug("[run_thread] Input '%s' is EachOf with %d types (run_id=%s)",
                                       param, len(type_names), run_id)
                        else:
                            inputs[param] = registry.get_variable_class(type_names[0])
                            logger.debug("[run_thread] Input '%s' is single type: %s (run_id=%s)",
                                       param, type_names[0], run_id)
                    else:
                        inputs[param] = registry.get_variable_class(type_names)
                        logger.debug("[run_thread] Input '%s' is type: %s (run_id=%s)",
                                   param, type_names, run_id)
                # Constants arrive already pending-overridden (see
                # apply_pending_overrides above the loop).
                inputs.update(v["constants"])
                logger.debug("[run_thread] Added constants to inputs: %s (run_id=%s)",
                           v["constants"], run_id)

                OutputCls = registry.get_variable_class(v["output_type"])
                logger.debug("[run_thread] Output class: %s (run_id=%s)", v["output_type"], run_id)
            except KeyError as e:
                logger.error("[run_thread] Failed to resolve input/output types for target %d: %s (run_id=%s)",
                           idx, e, run_id)
                emit(f"Error: {e}\n")
                success = False
                continue

            # Target constants are final (pending overrides already applied).
            label = f"{function_name}({', '.join(f'{k}={val}' for k, val in v['constants'].items())})" \
                    if v["constants"] else function_name
            logger.info(
                "[run_thread] Target %d/%d -> %s, inputs=%s, output=%s (run_id=%s)",
                idx, len(unique_targets), label,
                {k: (type_names if isinstance(type_names, list) else [type_names])
                 for k, type_names in v["input_types"].items()},
                v["output_type"], run_id,
            )
            emit(f"▶ Running {label}\n")

            # Emit structured run_start message for the frontend.
            logger.debug("[run_thread] Emitting run_start message for target %d (run_id=%s)", idx, run_id)
            started_at = time.time()
            push_message({
                "type": "run_start",
                "run_id": run_id,
                "function_name": function_name,
                "constants": v["constants"],
                "input_types": {k: str(vt) for k, vt in v["input_types"].items()},
                "output_type": v["output_type"],
                "started_at": started_at,
            })

            # Progress callback: relay structured progress to the frontend.
            def _progress_fn(info: dict):
                # The end-of-run summary carries this target's final counts.
                if info.get("event") == "summary":
                    combo_totals["completed"] += info.get("completed", 0)
                    combo_totals["failed"] += info.get(
                        "failed", info.get("skipped", 0))
                # Convert metadata values to strings for JSON serialization.
                meta = {str(k): str(val) for k, val in info.get("metadata", {}).items()}
                logger.debug("[run_thread] Progress update: event=%s, current=%d, total=%d (run_id=%s)",
                           info["event"], info["current"], info["total"], run_id)
                push_message({
                    "type": "run_progress",
                    "run_id": run_id,
                    "event": info["event"],
                    "current": info["current"],
                    "total": info["total"],
                    "completed": info["completed"],
                    "skipped": info["skipped"],
                    "metadata": meta,
                    "error": info.get("error"),
                })

            # Relay the run narrative (log records) plus any stdout (dry-run
            # output) to the frontend console.
            logger.info("[run_thread] Executing for_each for target %d (run_id=%s)",
                       idx, run_id)
            buf = StringIO()
            target_snapshot = dict(combo_totals)
            try:
                with _RunLogRelay(), redirect_stdout(buf):
                    for_each(fn, inputs=inputs, outputs=[OutputCls],
                             dry_run=opt_dry_run, save=opt_save,
                             distribute=opt_distribute,
                             as_table=opt_as_table,
                             where=where_arg,
                             skip_computed=False,
                             _progress_fn=_progress_fn,
                             _cancel_check=_is_cancelled,
                             schema_filter=schema_filter,
                             schema_level=schema_level)
                output = buf.getvalue()
                if output:
                    logger.debug("[run_thread] Captured %d bytes of stdout (run_id=%s)",
                               len(output), run_id)
                    emit(output)
                target_ms = int((time.time() - started_at) * 1000)
                target_failed = combo_totals["failed"] - target_snapshot["failed"]
                target_completed = (combo_totals["completed"]
                                    - target_snapshot["completed"])
                if target_failed:
                    logger.warning(
                        "[run_thread] Target %d/%d (%s) finished in %d ms with "
                        "%d failed combo(s) (completed=%d) (run_id=%s)",
                        idx, len(unique_targets), label, target_ms,
                        target_failed, target_completed, run_id)
                    emit(f"⚠ {label}: {target_failed} combo(s) failed "
                         f"({target_completed} completed) — see log above\n")
                else:
                    logger.info("[run_thread] Target %d/%d (%s) completed successfully in %d ms (run_id=%s)",
                                idx, len(unique_targets), label, target_ms, run_id)
            except KeyboardInterrupt:
                # Force-cancel injected an interrupt into this thread (or the
                # user pressed Ctrl-C in CLI mode).  Treat as cancel and stop.
                logger.warning(
                    "[run_thread] Target %d/%d (%s) interrupted by KeyboardInterrupt (force-cancel) (run_id=%s)",
                    idx, len(unique_targets), label, run_id,
                )
                output = buf.getvalue()
                if output:
                    logger.debug("[run_thread] Emitting %d bytes of partial stdout (run_id=%s)",
                               len(output), run_id)
                    emit(output)
                cancelled = True
                emit("⛔ Force-cancelled\n")
                break
            except Exception as exc:
                logger.exception("[run_thread] Target %d/%d (%s) failed with exception (run_id=%s)",
                                idx, len(unique_targets), label, run_id)
                emit(f"Error: {exc}\n")
                success = False
    except KeyboardInterrupt:
        # Defence in depth: if KeyboardInterrupt slips past the per-target
        # handler (e.g. fired between targets), still cancel cleanly.
        logger.warning("[run_thread] Interrupted by KeyboardInterrupt at top level (run_id=%s)",
                       run_id)
        cancelled = True
        emit("⛔ Force-cancelled\n")
    finally:
        logger.info("[run_thread] Cleanup and completion (run_id=%s)", run_id)
        duration_ms = int((time.time() - run_started_at) * 1000)
        # Honest verdict: iteration failures never raise out of for_each,
        # so a run with any failed combos is NOT a success.
        if combo_totals["failed"] > 0:
            success = False
        # Read the final cancel flags from the registry before popping it.
        logger.debug("[run_thread] Removing run from active registry (run_id=%s)", run_id)
        with _active_runs_lock:
            entry = _active_runs.pop(run_id, None)
        was_force = bool(entry and entry.get("force_cancelled"))
        if cancel_event.is_set():
            cancelled = True
        logger.info(
            "[run_thread] Thread finished (success=%s, cancelled=%s, force=%s, "
            "completed_combos=%d, failed_combos=%d) in %d ms (run_id=%s)",
            success, cancelled, was_force, combo_totals["completed"],
            combo_totals["failed"], duration_ms, run_id,
        )
        logger.debug("[run_thread] Emitting run_done message (run_id=%s)", run_id)
        push_message({"type": "run_done", "run_id": run_id, "success": success,
                      "duration_ms": duration_ms,
                      "cancelled": cancelled, "force_cancelled": was_force,
                      "completed_combos": combo_totals["completed"],
                      "failed_combos": combo_totals["failed"]})
        logger.debug("[run_thread] Emitting dag_updated message (run_id=%s)", run_id)
        push_message({"type": "dag_updated"})


def _build_where(where_filters: list[WhereFilterSpec] | None):
    """Convert frontend WhereFilterSpec list into scidb filter objects.

    Returns None (no filter), a single Filter, or EachOf(filter1, filter2, ...).
    """
    if not where_filters:
        return None

    import ast
    from scidb.filters import VariableFilter

    def _coerce(s: str):
        try:
            return ast.literal_eval(s)
        except (ValueError, SyntaxError):
            return s

    scidb_filters = []
    for f in where_filters:
        var_cls = registry.get_variable_class(f.variable)
        val = _coerce(f.value)
        scidb_filters.append(VariableFilter(var_cls, f.op, val))

    if len(scidb_filters) == 1:
        return scidb_filters[0]

    from scidb import EachOf
    return EachOf(*scidb_filters)


def _summarize_schema_filter(schema_filter: dict[str, list] | None) -> str:
    """Compact one-line summary of a schema_filter for logging."""
    if not schema_filter:
        return "none"
    return ", ".join(f"{k}={len(v)}v" for k, v in schema_filter.items())


@router.post("/run")
def start_run(req: RunRequest, db: DatabaseManager = Depends(get_db)):
    logger.info("[api/run] POST /api/run - Validating request")
    logger.debug("[api/run] Request: function_name=%s, variants=%d, run_id=%s, schema_filter=%s, "
                "schema_level=%s, run_options=%s, where_filters=%d",
                req.function_name, len(req.variants), req.run_id,
                _summarize_schema_filter(req.schema_filter), req.schema_level,
                req.run_options, len(req.where_filters) if req.where_filters else 0)

    run_id = req.run_id or str(uuid.uuid4())[:8]
    logger.info("[api/run] Generated run_id: %s", run_id)

    logger.info("[api/run] Spawning background thread for run_id=%s", run_id)
    thread = threading.Thread(
        target=_run_in_thread,
        args=(run_id, req.function_name, req.variants, db,
              req.schema_filter, req.schema_level, req.run_options,
              req.where_filters),
        daemon=True,
    )
    thread.start()
    logger.info("[api/run] Background thread started for run_id=%s", run_id)
    return {"run_id": run_id}


def _run_pipeline_in_thread(run_id: str, pipeline_id: str, mode: str,
                            target: str, finalized, skip_computed: bool,
                            db: DatabaseManager):
    """Background execution of a document pipeline through the backend
    verbs (G2). Reuses the per-node run's registry (force-cancel works —
    KeyboardInterrupt between/inside steps; cooperative cancel is a no-op
    for pipeline runs in v1: Pipeline._run has no between-step hook yet)
    and its message contract (run_output / run_done / dag_updated).
    """
    from scistack_gui.services.execution_service import run_pipeline

    def emit(text: str):
        push_message({"type": "run_output", "run_id": run_id, "text": text})

    class _RunLogRelay(logging.Handler):
        _RELAY_LOGGERS = ("scifor", "scidb")

        def __init__(self):
            super().__init__(level=logging.INFO)
            self.setFormatter(logging.Formatter("%(message)s"))

        def emit(self, record):
            try:
                emit(self.format(record) + "\n")
            except Exception:
                pass

        def __enter__(self):
            for name in self._RELAY_LOGGERS:
                logging.getLogger(name).addHandler(self)
            return self

        def __exit__(self, *exc):
            for name in self._RELAY_LOGGERS:
                logging.getLogger(name).removeHandler(self)
            return False

    cancel_event = threading.Event()
    with _active_runs_lock:
        _active_runs[run_id] = {
            "event": cancel_event,
            "thread": threading.current_thread(),
            "cancelled": False,
            "force_cancelled": False,
        }
    db.set_current_db()
    logger.info("[pipeline_run] run_id=%s scope=%s mode=%s target=%r",
                run_id, pipeline_id, mode, target)
    emit(f"▶ Running pipeline scope {pipeline_id} (mode={mode}"
         + (f", target={target}" if target else "") + ")\n")

    success, cancelled = True, False
    run_started_at = time.time()
    buf = StringIO()
    report: list = []
    try:
        with _RunLogRelay(), redirect_stdout(buf):
            result = run_pipeline(db, pipeline_id, mode=mode, target=target,
                                  finalized=finalized,
                                  skip_computed=skip_computed)
        report = (result or {}).get("report") or []
        # Draft outputs of a show run exist ONLY in this return value (no
        # records are written) — push them to the preview panel before
        # run_done. Payloads may be non-JSON scalars; stringify defensively.
        if mode == "show":
            rendered = (result or {}).get("rendered") or []
            safe = [r if isinstance(r, (str, int, float, bool, dict, list))
                    else str(r) for r in rendered]
            push_message({"type": "show_rendered", "run_id": run_id,
                          "step": target, "rendered": safe})
    except KeyboardInterrupt:
        cancelled = True
        emit("⛔ Force-cancelled\n")
    except Exception as exc:
        logger.exception("[pipeline_run] failed (run_id=%s)", run_id)
        emit(f"Error: {exc}\n")
        success = False
    finally:
        output = buf.getvalue()
        if output:
            emit(output)
        # Honest verdict: step for_each calls never raise on iteration
        # failures (continue-and-report), so success comes from the
        # pipeline's per-step run report.
        completed_combos = sum(e.get("completed", 0) for e in report)
        failed_combos = sum(e.get("failed", 0) for e in report)
        for e in report:
            if e.get("failed"):
                emit(f"⚠ {e.get('label', e.get('step'))}: "
                     f"{e['failed']} combo(s) failed "
                     f"({e.get('completed', 0)} completed)\n")
        if failed_combos > 0:
            success = False
            emit(f"✗ Pipeline run finished with {failed_combos} failed "
                 f"combo(s) across {sum(1 for e in report if e.get('failed'))}"
                 f" step(s) — see log above\n")
        duration_ms = int((time.time() - run_started_at) * 1000)
        with _active_runs_lock:
            entry = _active_runs.pop(run_id, None)
        was_force = bool(entry and entry.get("force_cancelled"))
        if cancel_event.is_set():
            cancelled = True
        logger.info("[pipeline_run] finished (run_id=%s success=%s "
                    "cancelled=%s completed_combos=%d failed_combos=%d) "
                    "in %d ms", run_id, success, cancelled,
                    completed_combos, failed_combos, duration_ms)
        push_message({"type": "run_done", "run_id": run_id,
                      "success": success, "duration_ms": duration_ms,
                      "cancelled": cancelled, "force_cancelled": was_force,
                      "completed_combos": completed_combos,
                      "failed_combos": failed_combos})
        push_message({"type": "dag_updated"})


def start_pipeline_run(pipeline_id: str, mode: str = "all", target: str = "",
                       finalized=None, skip_computed: bool = True,
                       run_id: "str | None" = None) -> dict:
    """Spawn a background pipeline run (called from api/scopes and the
    JSON-RPC handler). Validates the mode/target shape up front so bad
    requests fail synchronously."""
    from scistack_gui.db import get_db

    if mode not in ("all", "until", "endpoints", "show"):
        raise ValueError(f"unknown run mode {mode!r}")
    if mode in ("until", "show") and not target:
        raise ValueError(f"mode={mode!r} requires a target step name")
    rid = run_id or str(uuid.uuid4())[:8]
    thread = threading.Thread(
        target=_run_pipeline_in_thread,
        args=(rid, pipeline_id, mode, target, finalized, skip_computed,
              get_db()),
        daemon=True,
    )
    thread.start()
    logger.info("[api/run] pipeline run thread started (run_id=%s)", rid)
    return {"run_id": rid}


# ---------------------------------------------------------------------------
# Cancel APIs (called from server.py JSON-RPC handlers)
# ---------------------------------------------------------------------------

def cancel_run(run_id: str) -> dict:
    """Cooperatively cancel a running for_each.

    Sets the cancel event so the worker thread breaks between combos.
    Safe: completed combos are saved, in-flight combo finishes normally.

    Returns:
        ``{"ok": True, "cancelled": True}`` on success,
        ``{"ok": False, "error": "unknown run_id"}`` if the run isn't active.
    """
    logger.info("[cancel_run] Attempting cooperative cancel for run_id=%s", run_id)
    with _active_runs_lock:
        entry = _active_runs.get(run_id)
        if entry is None:
            logger.warning("[cancel_run] Unknown run_id=%s (not in active runs)", run_id)
            return {"ok": False, "error": f"unknown run_id: {run_id}"}
        logger.debug("[cancel_run] Setting cancelled flag and event for run_id=%s", run_id)
        entry["cancelled"] = True
        entry["event"].set()
    logger.info("[cancel_run] Cooperative cancel requested for run_id=%s", run_id)
    return {"ok": True, "cancelled": True, "force": False}


def force_cancel_run(run_id: str) -> dict:
    """Force-cancel a running for_each by injecting KeyboardInterrupt.

    Sets the cooperative cancel event AND calls
    ``ctypes.pythonapi.PyThreadState_SetAsyncExc`` to raise
    ``KeyboardInterrupt`` in the worker thread. Best-effort:

    - Won't interrupt code blocked in C extensions, native syscalls,
      or threading primitives that don't poll for interrupts.
    - When that fails, the user must restart the Python subprocess via
      the existing ``scistack.restartPython`` command.

    Returns:
        ``{"ok": True, "cancelled": True, "force": True, "best_effort": True}``
        on success,
        ``{"ok": False, "error": "..."}`` if the run isn't active or the
        ctypes injection failed unexpectedly.
    """
    logger.info("[force_cancel_run] Attempting force cancel for run_id=%s", run_id)
    with _active_runs_lock:
        entry = _active_runs.get(run_id)
        if entry is None:
            logger.warning("[force_cancel_run] Unknown run_id=%s (not in active runs)", run_id)
            return {"ok": False, "error": f"unknown run_id: {run_id}"}
        logger.debug("[force_cancel_run] Setting cancelled and force_cancelled flags for run_id=%s", run_id)
        entry["cancelled"] = True
        entry["force_cancelled"] = True
        entry["event"].set()
        thread = entry["thread"]

    tid = thread.ident
    if tid is None:
        logger.warning(
            "[force_cancel_run] Could not resolve thread id for run_id=%s (thread not started?)",
            run_id,
        )
        return {
            "ok": True,
            "cancelled": True,
            "force": True,
            "best_effort": True,
            "injected": False,
            "warning": "thread id not available",
        }

    logger.info("[force_cancel_run] Injecting KeyboardInterrupt into thread tid=%s (run_id=%s)", tid, run_id)
    # PyThreadState_SetAsyncExc takes (long thread_id, PyObject* exc) and
    # returns the number of threads modified. Returns:
    #   0  → invalid thread id (worker likely already exited)
    #   1  → success
    #  >1  → catastrophic; immediately undo by passing NULL
    n = ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_long(tid),
        ctypes.py_object(KeyboardInterrupt),
    )
    if n == 0:
        logger.warning(
            "[force_cancel_run] Injection failed - thread tid=%s no longer exists (run_id=%s)",
            tid, run_id,
        )
        return {
            "ok": True,
            "cancelled": True,
            "force": True,
            "best_effort": True,
            "injected": False,
            "warning": "thread no longer running",
        }
    if n > 1:
        # Undo the over-broad injection per Python docs.
        logger.error(
            "[force_cancel_run] Injection affected %d threads - rolling back (run_id=%s)",
            n, run_id,
        )
        ctypes.pythonapi.PyThreadState_SetAsyncExc(
            ctypes.c_long(tid), ctypes.c_long(0))
        return {
            "ok": False,
            "error": f"PyThreadState_SetAsyncExc affected {n} threads (rolled back)",
        }

    logger.info(
        "[force_cancel_run] Successfully injected KeyboardInterrupt into tid=%s (run_id=%s)",
        tid, run_id,
    )
    return {
        "ok": True,
        "cancelled": True,
        "force": True,
        "best_effort": True,
        "injected": True,
    }
