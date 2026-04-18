"""
GET  /api/layout          — return saved node positions
PUT  /api/layout/{node_id} — persist a single node's position (and optionally
                             register it as a manually-placed node)
"""

import logging
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from scidb.database import DatabaseManager
from scistack_gui.db import get_db

logger = logging.getLogger(__name__)

class ConstantCreate(BaseModel):
    name: str


class PathInputCreate(BaseModel):
    name: str
    template: str = ""
    root_folder: str | None = None


class EdgeCreate(BaseModel):
    source: str
    target: str
    source_handle: str | None = None
    target_handle: str | None = None

router = APIRouter()


class PositionUpdate(BaseModel):
    x: float
    y: float
    # Present only when the node was just dragged from the sidebar palette.
    node_type: str | None = None
    label: str | None = None


class NodeConfigUpdate(BaseModel):
    config: dict


@router.get("/layout")
def get_layout() -> dict:
    from scistack_gui.services.layout_service import get_layout as _get
    return _get()


@router.put("/layout/{node_id}")
def put_layout(node_id: str, body: PositionUpdate):
    from scistack_gui.services.layout_service import put_layout as _put
    return _put(node_id, body.x, body.y, body.node_type, body.label)


@router.delete("/layout/{node_id}")
def delete_layout(node_id: str):
    from scistack_gui.services.layout_service import delete_layout as _del
    return _del(node_id)


@router.get("/constants")
def get_constants() -> list[str]:
    from scistack_gui.services.layout_service import get_constants as _get
    return _get()


@router.post("/constants")
def post_constant(body: ConstantCreate):
    from scistack_gui.services.layout_service import create_constant
    return create_constant(body.name)


@router.delete("/constants/{name}")
def delete_constant(name: str):
    from scistack_gui.services.layout_service import delete_constant as _del
    return _del(name)


@router.get("/path-inputs")
def get_path_inputs() -> list[dict]:
    from scistack_gui.services.layout_service import get_path_inputs as _get
    result = _get()
    logger.info("GET /path-inputs → %s", result)
    return result


@router.post("/path-inputs")
def post_path_input(body: PathInputCreate):
    from scistack_gui.services.layout_service import create_path_input
    return create_path_input(body.name, body.template, body.root_folder)


@router.put("/path-inputs/{name}")
def put_path_input(name: str, body: PathInputCreate):
    from scistack_gui.services.layout_service import update_path_input
    return update_path_input(name, body.template, body.root_folder)


@router.delete("/path-inputs/{name}")
def delete_path_input(name: str):
    from scistack_gui.services.layout_service import delete_path_input as _del
    return _del(name)


@router.put("/edges/{edge_id}")
def put_edge(edge_id: str, body: EdgeCreate):
    from scistack_gui.services.layout_service import put_edge as _put
    return _put(edge_id, body.source, body.target,
                body.source_handle, body.target_handle)


@router.put("/layout/{node_id}/config")
def put_node_config(node_id: str, body: NodeConfigUpdate,
                    db: DatabaseManager = Depends(get_db)):
    from scistack_gui.services.layout_service import put_node_config as _put
    return _put(db, node_id, body.config)


@router.delete("/edges/{edge_id}")
def delete_edge(edge_id: str):
    from scistack_gui.services.layout_service import delete_edge as _del
    return _del(edge_id)
