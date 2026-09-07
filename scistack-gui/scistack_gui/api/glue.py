"""
Glue-node endpoints — list, create, read, save, remove, and the live column
list the code panel shows beside the editor.

A glue node has **no run endpoint**, by design (D5). It is transient by
construction, so a standalone run would produce nothing and a state badge
would describe nothing; it executes only as part of a consuming function's
run. See ``docs/claude/free-code-glue-nodes.md`` §5, and ``api/run.py``'s
refusal of a glue node id.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from scistack_gui.api import ws

logger = logging.getLogger(__name__)

router = APIRouter()


class CreateGlueRequest(BaseModel):
    name: str
    param: str = "value"
    language: str = "python"


class SaveGlueRequest(BaseModel):
    name: str
    source: str


@router.get("/glue")
def list_glue() -> dict:
    from scistack_gui.services import glue_service

    return {"nodes": glue_service.list_glue_nodes()}


@router.get("/glue/{name}")
def get_glue(name: str) -> dict:
    from scistack_gui.services import glue_service

    return glue_service.read_glue_source(name)


@router.get("/glue/{name}/columns")
def get_glue_columns(name: str, variable_type: str = "") -> dict:
    """The columns a glue on ``variable_type`` actually receives.

    Read live on every panel open rather than scaffolded into the file as a
    comment: a comment goes stale the moment the node is rewired.
    """
    from scistack_gui.services import glue_service

    if not variable_type:
        return {
            "ok": False,
            "error": (
                "This glue node is not wired to a variable yet, so there are "
                "no columns to show."
            ),
        }
    return glue_service.input_columns(variable_type)


@router.post("/glue")
async def create_glue(req: CreateGlueRequest) -> dict:
    from scistack_gui.services import glue_service

    result = glue_service.create_glue_node(
        req.name, param=req.param, language=req.language
    )
    if result.get("ok"):
        await ws.broadcast({"type": "dag_updated"})
    return result


@router.put("/glue")
async def save_glue(req: SaveGlueRequest) -> dict:
    """Write the edited body, then refresh the registry.

    The refresh is the whole point of the round-trip: the new body has a new
    hash, so the consuming function's glue chain hash changes, so its next
    run recomputes instead of skipping. Saving without refreshing would look
    identical in the panel and silently keep running the old body.
    """
    from scistack_gui.services import glue_service

    result = glue_service.update_glue_source(req.name, req.source)
    if result.get("ok"):
        await ws.broadcast({"type": "dag_updated"})
    return result


@router.delete("/glue/{name}")
async def delete_glue(name: str) -> dict:
    """Remove the node from the canvas. The source file is never unlinked."""
    from scistack_gui.services import glue_service

    result = glue_service.delete_glue_node(name)
    if result.get("ok"):
        await ws.broadcast({"type": "dag_updated"})
    return result
