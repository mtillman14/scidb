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
from scidb import BaseVariable
from scidb.database import DatabaseManager
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

    # Dynamically build the SELECT clause for schema key columns.
    schema_select = ", ".join(f's."{k}"' for k in schema_keys)
    if schema_select:
        schema_select += ", "

    query = f"""
        WITH latest AS (
            SELECT record_id, schema_id, branch_params
            FROM _record_metadata
            WHERE variable_name = $1
              AND excluded = FALSE
            QUALIFY ROW_NUMBER() OVER (PARTITION BY record_id ORDER BY timestamp DESC) = 1
        )
        SELECT {schema_select}l.branch_params
        FROM latest l
        LEFT JOIN _schema s ON l.schema_id = s.schema_id
        ORDER BY {", ".join(f's."{k}"' for k in schema_keys) or "l.branch_params"}
    """

    try:
        rows = db._duck._fetchall(query, [variable_name])
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    col_names = schema_keys + ["branch_params"]

    records = []
    for row in rows:
        row_dict = dict(zip(col_names, row))
        raw_bp = row_dict.get("branch_params") or "{}"
        bp = json.loads(raw_bp) if isinstance(raw_bp, str) else (raw_bp or {})
        records.append({
            **{k: str(row_dict[k]) if row_dict[k] is not None else None for k in schema_keys},
            "branch_params": bp,
            "variant_label": _format_variant_label(bp),
        })

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
        return {"ok": False, "error": "Variable names must not start with an underscore."}

    if not name[0].isupper():
        return {"ok": False, "error": "Variable names should start with an uppercase letter."}

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
        if matlab_registry.has_matlab_config() and matlab_registry._config is not None and matlab_registry._config.matlab_variable_dir is not None:
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
