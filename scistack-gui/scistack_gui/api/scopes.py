"""
Nested-pipeline scope endpoints (plan-gui-nested-pipelines.md Part A).

GET    /api/pipelines                     — list scopes + use edges
POST   /api/pipelines                     — create a scope
PUT    /api/pipelines/{pid}               — rename
DELETE /api/pipelines/{pid}               — delete (guards apply)
GET    /api/pipelines/{pid}/interface     — the scope's ports
POST   /api/pipelines/{pid}/uses          — place a pipeline node on pid
PUT    /api/pipeline-uses/{use_id}/binding
DELETE /api/pipeline-uses/{use_id}

Store-level ValueErrors (cycles, root guards, duplicate names, unknown
ids, binding-key whitelist) map to HTTP 400 with the store's message.
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from scistack_gui.services import scope_service

logger = logging.getLogger(__name__)

router = APIRouter()


class PipelineCreate(BaseModel):
    name: str


class PipelineRename(BaseModel):
    name: str


class UseCreate(BaseModel):
    child_pipeline_id: str
    binding: dict | None = None
    x: float = 0.0
    y: float = 0.0


class BindingUpdate(BaseModel):
    binding: dict


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/pipelines")
def get_pipelines() -> dict:
    return scope_service.list_pipelines()


@router.post("/pipelines")
def post_pipeline(body: PipelineCreate) -> dict:
    return _guard(scope_service.create_pipeline, body.name)


@router.put("/pipelines/{pipeline_id}")
def put_pipeline(pipeline_id: str, body: PipelineRename) -> dict:
    return _guard(scope_service.rename_pipeline, pipeline_id, body.name)


@router.delete("/pipelines/{pipeline_id}")
def delete_pipeline(pipeline_id: str) -> dict:
    return _guard(scope_service.delete_pipeline, pipeline_id)


@router.get("/pipelines/{pipeline_id}/interface")
def get_pipeline_interface(pipeline_id: str) -> dict:
    return scope_service.pipeline_interface(pipeline_id)


@router.post("/pipelines/{pipeline_id}/uses")
def post_pipeline_use(pipeline_id: str, body: UseCreate) -> dict:
    return _guard(
        scope_service.add_pipeline_use,
        pipeline_id, body.child_pipeline_id, body.binding, body.x, body.y,
    )


@router.put("/pipeline-uses/{use_id}/binding")
def put_use_binding(use_id: str, body: BindingUpdate) -> dict:
    return _guard(scope_service.update_use_binding, use_id, body.binding)


@router.delete("/pipeline-uses/{use_id}")
def delete_pipeline_use(use_id: str) -> dict:
    return _guard(scope_service.remove_pipeline_use, use_id)
