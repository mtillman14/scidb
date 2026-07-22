"""
Variable-related API endpoints.

GET  /api/variables/{variable_name}/records — records + variant summary
POST /api/variables/create                 — define a new BaseVariable subclass
"""

import json
import keyword
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from scidb.database import DatabaseManager

from scidb import BaseVariable
from scistack_gui import registry
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


# ---- Create new variable type -------------------------------------------------


class CreateVariableRequest(BaseModel):
    name: str
    docstring: str | None = None


@router.post("/variables/create")
async def create_variable(req: CreateVariableRequest) -> dict:
    """
    Define a new BaseVariable subclass by appending it to the user's module file,
    then refresh the registry so it's immediately available.
    """
    name = req.name.strip()
    logger.info("create_variable request: name=%r docstring=%r", name, req.docstring)

    # --- Validation ---
    if not name.isidentifier() or keyword.iskeyword(name):
        return {"ok": False, "error": f"'{name}' is not a valid Python class name."}

    if name.startswith("_"):
        return {
            "ok": False,
            "error": "Variable names must not start with an underscore.",
        }

    if not name[0].isupper():
        return {
            "ok": False,
            "error": "Variable names should start with an uppercase letter.",
        }

    if name in BaseVariable._all_subclasses:
        return {"ok": False, "error": f"A variable named '{name}' already exists."}

    # --- Determine target file (Python or MATLAB) ---
    target_file = None
    if registry._config is not None and registry._config.variable_file is not None:
        target_file = registry._config.variable_file
    elif registry._module_path is not None:
        target_file = registry._module_path

    if target_file is None:
        # No Python target — fall back to MATLAB if configured.
        from scistack_gui import matlab_registry

        if (
            matlab_registry.has_matlab_config()
            and matlab_registry._config is not None
            and matlab_registry._config.matlab_variable_dir is not None
        ):
            from scistack_gui.services.variable_service import _create_matlab_variable

            result = _create_matlab_variable(name, req.docstring)
            if result.get("ok"):
                await ws.broadcast({"type": "dag_updated"})
            return result
        return {
            "ok": False,
            "error": "No module file was loaded at startup (--module not passed). "
            "Cannot append a new class.",
        }

    # --- Build the class definition ---
    lines = ["\n"]
    if req.docstring:
        escaped = req.docstring.replace('"""', '\\"\\"\\"')
        lines.append(f'class {name}(BaseVariable):\n    """{escaped}"""\n    pass\n')
    else:
        lines.append(f"class {name}(BaseVariable):\n    pass\n")

    # --- Append to the module file ---
    try:
        with open(target_file, "a") as f:
            f.writelines(lines)
        logger.info("Appended class %s to %s", name, target_file)
    except OSError as e:
        return {"ok": False, "error": f"Failed to write to module file: {e}"}

    # --- Refresh so the new class is registered ---
    try:
        if registry._config is not None:
            registry.refresh_all()
        else:
            registry.refresh_module()
    except Exception as e:
        logger.exception("Refresh failed after appending class %s", name)
        return {"ok": False, "error": f"Class was written but refresh failed: {e}"}

    await ws.broadcast({"type": "dag_updated"})
    return {"ok": True, "name": name}
