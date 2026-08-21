"""
Variable-related API endpoints.

GET  /api/variables/{variable_name}/records — records + variant summary
POST /api/variables/create                 — define a new BaseVariable subclass
"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from scidb.database import DatabaseManager

from scistack_gui.api import ws
from scistack_gui.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


def _format_variant_label(branch_params: dict) -> str:
    """
    Produce a concise human-readable label from branch_params.

    branch_params keys are namespaced as "fn_name.param" (for constants) or bare
    names (for dynamic discriminators). Strip the function prefix when all keys
    share the same function, so the display stays compact.
    """
    if not branch_params:
        return "(raw)"

    # Collect key=value pairs, stripping common fn prefix for readability.
    parts = []
    for k, v in sorted(branch_params.items()):
        short_k = k.split(".")[-1] if "." in k else k
        parts.append(f"{short_k}={v}")
    return ", ".join(parts)


@router.get("/variables/{variable_name}/records")
def get_variable_records(variable_name: str, db: DatabaseManager = Depends(get_db)):
    """
    Return all records for a variable type with schema key values and variant info.

    Response shape:
      {
        "schema_keys": ["subject", "session"],
        "records": [
          {"subject": "1", "session": "pre", "branch_params": {...}, "variant_label": "..."},
          ...
        ],
        "variants": [
          {"label": "...", "branch_params": {...}, "record_count": 4},
          ...
        ]
      }
    """
    schema_keys: list[str] = db._duck.dataset_schema

    # The pre-bipartite _record_metadata table (with its embedded
    # branch_params column) is gone: record identity lives on the _record
    # entity and branch_params are DERIVED from the provenance graph.
    # Query the variable's data table joined to _record/_schema, then batch
    # the branch-params walk (never per-record — the N+1 trap).

    # Validate the name against the _variables registry table — unknown
    # variables return the empty shape (and the {name}_data interpolation
    # below only ever receives a known-registered name).
    known = {
        row[0] for row in db._duck._fetchall("SELECT variable_name FROM _variables")
    }
    if variable_name not in known:
        logger.info("get_variable_records: unknown variable %r", variable_name)
        return {"schema_keys": schema_keys, "records": [], "variants": []}

    schema_select = ", ".join(f's."{k}"' for k in schema_keys)
    if schema_select:
        schema_select = ", " + schema_select
    query = f"""
        SELECT DISTINCT t.record_id{schema_select}
        FROM "{variable_name}_data" t
        JOIN _record r ON t.record_id = r.record_id
        LEFT JOIN _schema s ON r.schema_id = s.schema_id
        WHERE r.excluded IS DISTINCT FROM TRUE
        ORDER BY {", ".join(f's."{k}"' for k in schema_keys) or "t.record_id"}
    """
    try:
        rows = db._duck._fetchall(query)
    except Exception as exc:
        logger.warning("get_variable_records(%s) query failed: %s", variable_name, exc)
        raise HTTPException(status_code=404, detail=str(exc))

    record_ids = [row[0] for row in rows]
    from scidb.provenance_query import branch_params_batch

    bp_by_record = branch_params_batch(db._duck, record_ids)

    records = []
    for row in rows:
        record_id = row[0]
        schema_vals = dict(zip(schema_keys, row[1:], strict=False))
        bp = bp_by_record.get(record_id, {})
        records.append(
            {
                **{
                    k: str(schema_vals[k]) if schema_vals[k] is not None else None
                    for k in schema_keys
                },
                "branch_params": bp,
                "variant_label": _format_variant_label(bp),
            }
        )

    # Build variant summary: group by branch_params JSON (canonical sort).
    variant_map: dict[str, dict] = {}
    for rec in records:
        key = json.dumps(rec["branch_params"], sort_keys=True)
        if key not in variant_map:
            variant_map[key] = {
                "label": rec["variant_label"],
                "branch_params": rec["branch_params"],
                "record_count": 0,
            }
        variant_map[key]["record_count"] += 1

    variants = list(variant_map.values())

    return {
        "schema_keys": schema_keys,
        "records": records,
        "variants": variants,
    }


# ---- Default plotting by schema level (to-do #4) ------------------------------


def _numeric_plot_kind(sample: object) -> "str | None":
    """Classify a variable's data column for the default-plot mechanism
    from one SAMPLE VALUE already fetched via the duckdb Python client
    (not by parsing a SQL type-name string) — see
    plan-default-plotting-by-schema-level.md for why: the duckdb client's
    own Python type for a row value (float/int for a scalar column, list
    for a LIST column) is the ground truth actually observed, with no
    dependency on knowing DuckDB's information_schema type-string spelling
    for list/array columns across versions.

    Returns "scalar", "1d", or None (not eligible). A column is uniformly
    typed by DuckDB, so sampling any one row's value classifies the whole
    column.
    """
    if isinstance(sample, bool):  # bool is an int subclass — exclude explicitly
        return None
    if isinstance(sample, (int, float)):
        return "scalar"
    if isinstance(sample, list) and sample and all(
        isinstance(v, (int, float)) and not isinstance(v, bool) for v in sample
    ):
        return "1d"
    return None


@router.get("/variables/{variable_name}/plot-data")
def get_variable_plot_data(variable_name: str, db: DatabaseManager = Depends(get_db)):
    """
    Raw points for the sidebar's default plot (to-do #4) — every record's
    schema key values + its scalar/1D-numeric value, unaggregated. The
    frontend groups/averages by whichever schema keys the user leaves
    checked; shipping raw points keeps that instant (no round trip per
    schema-level toggle).

    Response shape:
      {
        "eligible": bool,
        "reason": str | None,             # why not, when eligible=False
        "kind": "scalar" | "1d" | None,
        "schema_keys": ["subject", "session"],
        "points": [
          {"subject": "1", "session": "pre", "value": 0.42},
          ...
        ]
      }
    """
    schema_keys: list[str] = db._duck.dataset_schema
    empty = {"eligible": False, "reason": None, "kind": None,
             "schema_keys": schema_keys, "points": []}

    known = {
        row[0] for row in db._duck._fetchall("SELECT variable_name FROM _variables")
    }
    if variable_name not in known:
        logger.info("get_variable_plot_data: unknown variable %r", variable_name)
        return {**empty, "reason": "unknown variable"}

    data_table = f"{variable_name}_data"
    cols = db._duck._fetchall(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = ? AND column_name != 'record_id' "
        "ORDER BY ordinal_position",
        [data_table],
    )
    if len(cols) != 1:
        return {**empty, "reason": "not a scalar/1D variable (multi-column data)"}
    value_col = cols[0][0]

    schema_select = ", ".join(f's."{k}"' for k in schema_keys)
    if schema_select:
        schema_select = ", " + schema_select
    query = f"""
        SELECT t.record_id, t."{value_col}"{schema_select}
        FROM "{data_table}" t
        JOIN _record r ON t.record_id = r.record_id
        LEFT JOIN _schema s ON r.schema_id = s.schema_id
        WHERE r.excluded IS DISTINCT FROM TRUE
    """
    try:
        rows = db._duck._fetchall(query)
    except Exception as exc:
        logger.warning("get_variable_plot_data(%s) query failed: %s", variable_name, exc)
        raise HTTPException(status_code=404, detail=str(exc))

    if not rows:
        return {**empty, "reason": "no records yet"}

    kind = _numeric_plot_kind(rows[0][1])
    if kind is None:
        return {**empty, "reason": f"not scalar/1D numeric (got {type(rows[0][1]).__name__})"}

    points = []
    for row in rows:
        value = row[1]
        schema_vals = dict(zip(schema_keys, row[2:], strict=False))
        points.append({
            **{
                k: (str(v) if v is not None else None)
                for k, v in schema_vals.items()
            },
            "value": value,
        })

    logger.info(
        "get_variable_plot_data(%s): kind=%s, %d point(s)",
        variable_name, kind, len(points),
    )
    return {
        "eligible": True,
        "reason": None,
        "kind": kind,
        "schema_keys": schema_keys,
        "points": points,
    }


# ---- Create new variable type -------------------------------------------------


class CreateVariableRequest(BaseModel):
    name: str
    docstring: str | None = None


@router.post("/variables/create")
async def create_variable(req: CreateVariableRequest) -> dict:
    """
    Define a new BaseVariable subclass by appending it to the user's module file,
    then refresh the registry so it's immediately available.

    Delegates to ``services.variable_service.create_variable`` -- the single
    source of truth also used by the JSON-RPC (VS Code extension) path in
    server.py -- so validation/target-file/MATLAB-fallback behavior can't
    drift between the two transports.
    """
    from scistack_gui.services.variable_service import create_variable as _create

    name = req.name.strip()
    logger.info("create_variable request: name=%r docstring=%r", name, req.docstring)

    result = _create(name, req.docstring)
    if result.get("ok"):
        await ws.broadcast({"type": "dag_updated"})
    return result
