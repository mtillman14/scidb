"""
GET /api/registry

Returns all pipeline functions and variable types known to the server,
sourced from the user module loaded at startup.
"""

import logging

from fastapi import APIRouter
from scistack_gui.api import ws

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/registry")
def get_registry() -> dict:
    from scistack_gui.services.pipeline_service import get_registry as _get
    return _get()


@router.post("/refresh")
async def refresh_registry() -> dict:
    from scistack_gui.services.pipeline_service import refresh_module
    result = refresh_module()
    if result.get("ok"):
        await ws.broadcast({"type": "dag_updated"})
    return result
