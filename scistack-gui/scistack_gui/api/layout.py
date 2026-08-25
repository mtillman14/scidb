"""
GET  /api/layout          — return saved node positions
PUT  /api/layout/{node_id} — persist a single node's position (and optionally
                             register it as a manually-placed node)
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from scidb.database import DatabaseManager

from scistack_gui.db import get_db

logger = logging.getLogger(__name__)


class ParameterCreate(BaseModel):
    name: str
    # One list whatever the count. Numbers stay int-or-float rather than
    # being coerced to float: the hidden-value store keys on the RENDERED
    # string, so silently turning 20 into 20.0 makes an unchecked '20' stop
    # matching (see domain.variant_resolver.is_hidden_value, which tolerates
    # both spellings precisely because this field preserves the difference).
    values: list[float | int | str | bool] = []


class ParameterUpdate(BaseModel):
    values: list[float | int | str | bool] = []
    description: str = ""


class PathInputCreate(BaseModel):
    name: str
    template: str = ""
    root_folder: str | None = None


class PathInputUpdate(BaseModel):
    template: str
    root_folder: str | None = None
    alternate_templates: list[dict] | None = None


class EdgeCreate(BaseModel):
    source: str
    target: str
    source_handle: str | None = None
    target_handle: str | None = None


class EdgeDelete(BaseModel):
    # Optional: the frontend already has the removed edge's endpoints in
    # local React Flow state — passed through so a hidden DB-derived edge
    # can be labeled in the restore panel. Absent for edges deleted some
    # other way (defaults keep the DELETE body optional).
    source: str = ""
    target: str = ""
    source_handle: str | None = None
    target_handle: str | None = None


router = APIRouter()


class PositionUpdate(BaseModel):
    x: float
    y: float
    # Present only when the node was just dragged from the sidebar palette.
    node_type: str | None = None
    label: str | None = None
    # Scope the node lives on (nested pipelines); default = root canvas.
    pipeline_id: str = "main"


class NodeConfigUpdate(BaseModel):
    config: dict


class NoteUpdate(BaseModel):
    text: str


@router.get("/layout")
def get_layout(pipeline_id: str = "main") -> dict:
    from scistack_gui.services.layout_service import get_layout as _get

    return _get(pipeline_id)


@router.put("/layout/{node_id}")
def put_layout(node_id: str, body: PositionUpdate):
    from scistack_gui.services.layout_service import put_layout as _put

    return _put(node_id, body.x, body.y, body.node_type, body.label, body.pipeline_id)


@router.delete("/layout/{node_id}")
def delete_layout(node_id: str):
    from scistack_gui.services.layout_service import delete_layout as _del

    return _del(node_id)


@router.get("/notes")
def get_notes() -> dict[str, str]:
    from scistack_gui.services.layout_service import get_notes as _get

    return _get()


@router.put("/notes/{key:path}")
def put_note(key: str, body: NoteUpdate):
    from scistack_gui.services.layout_service import set_note as _set

    return _set(key, body.text)


@router.get("/parameters")
def get_parameters() -> list[dict]:
    from scistack_gui.services.layout_service import get_parameters as _get

    return _get()


@router.post("/parameters")
def post_parameter(body: ParameterCreate):
    """Create a Parameter. ``values`` is the final, already-computed flat
    list -- range generation (start/end/step) is a frontend concern. Empty
    scaffolds a placeholder, matching the 'New parameter' form, which only
    collects a name."""
    from scistack_gui.services.layout_service import create_parameter

    return create_parameter(body.name, body.values)


@router.put("/parameters/{name}")
def put_parameter(name: str, body: ParameterUpdate):
    """Rewrite an existing Parameter's declaration in source.

    One route whatever the value count -- adding a value is adding an
    argument, not a change of kind (D6).

    Returns ``{"ok": False, "reason": "read_only", "file", "line"}`` when the
    Parameter is declared outside the configured entities file, so the
    frontend can render "declared in foo.py:42" rather than a generic hint.
    An empty ``values`` is rejected: emptying a Parameter would silently drop
    every variant it produces.
    """
    from scistack_gui.services.layout_service import update_parameter

    return update_parameter(name, body.values, body.description)


@router.delete("/parameters/{name}")
def delete_parameter(name: str, pipeline_id: str = "main"):
    """Hides the node only — the source declaration is untouched."""
    from scistack_gui.services.layout_service import delete_parameter as _del

    return _del(name, pipeline_id)


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
def put_path_input(name: str, body: PathInputUpdate):
    """Rewrite an existing PathInput's declaration in source.

    ``alternate_templates`` re-renders it as ``EachOf(PathInput(...), ...)``
    under the same name — that is what "multiple templates" is, not a
    separate concept.
    """
    from scistack_gui.services.layout_service import update_path_input

    return update_path_input(
        name, body.template, body.root_folder, body.alternate_templates
    )


@router.delete("/path-inputs/{name}")
def delete_path_input(name: str, pipeline_id: str = "main"):
    """Hides the node only — the source declaration is untouched (never
    delete, mark hidden). To CHANGE a template, use ``PUT`` above."""
    from scistack_gui.services.layout_service import delete_path_input as _del

    return _del(name, pipeline_id)


@router.post("/path-inputs/{node_id}/deep-copy")
def post_deep_copy_path_input(node_id: str):
    """Opt-in fork: give this ONE PathInput node placement an independent
    named definition, leaving every other placement of the original name
    untouched (see layout_service.deep_copy_path_input)."""
    from scistack_gui.services.layout_service import deep_copy_path_input

    try:
        return deep_copy_path_input(node_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/edges/{edge_id}")
def put_edge(
    edge_id: str, body: EdgeCreate, db: DatabaseManager = Depends(get_db)
):
    from scistack_gui.services.layout_service import put_edge as _put

    try:
        return _put(
            db,
            edge_id,
            body.source,
            body.target,
            body.source_handle,
            body.target_handle,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/layout/{node_id}/config")
def put_node_config(
    node_id: str, body: NodeConfigUpdate, db: DatabaseManager = Depends(get_db)
):
    from scistack_gui.services.layout_service import put_node_config as _put

    return _put(db, node_id, body.config)


@router.delete("/edges/{edge_id}")
def delete_edge(
    edge_id: str, body: EdgeDelete = EdgeDelete(), db: DatabaseManager = Depends(get_db)
):
    from scistack_gui.services.layout_service import delete_edge as _del

    return _del(
        db, edge_id, body.source, body.target, body.source_handle, body.target_handle
    )


class UnhideEdgeRequest(BaseModel):
    pipeline_id: str = "main"


@router.post("/edges/{edge_id}/unhide")
def unhide_edge(
    edge_id: str,
    body: UnhideEdgeRequest = UnhideEdgeRequest(),
    db: DatabaseManager = Depends(get_db),
):
    from scistack_gui.services.layout_service import unhide_edge as _unhide

    return _unhide(db, edge_id, body.pipeline_id)


@router.get("/edges/hidden")
def get_hidden_edges(pipeline_id: str | None = None, db: DatabaseManager = Depends(get_db)):
    from scistack_gui.services.layout_service import get_hidden_edges as _get

    return _get(db, pipeline_id)
