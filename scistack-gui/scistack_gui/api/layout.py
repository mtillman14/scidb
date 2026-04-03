"""
GET  /api/layout          — return saved node positions
PUT  /api/layout/{node_id} — persist a single node's position
"""

from fastapi import APIRouter
from pydantic import BaseModel
from scistack_gui import layout as layout_store

router = APIRouter()


class Position(BaseModel):
    x: float
    y: float


@router.get("/layout")
def get_layout() -> dict[str, dict]:
    return layout_store.read_layout()


@router.put("/layout/{node_id}")
def put_layout(node_id: str, pos: Position):
    layout_store.write_node_position(node_id, pos.x, pos.y)
    return {"ok": True}
