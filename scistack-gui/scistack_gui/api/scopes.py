"""
Nested-pipeline scope endpoints (plan-gui-nested-pipelines.md Part A).

GET    /api/pipelines                     — list VISIBLE scopes + use edges
POST   /api/pipelines                     — create a scope
PUT    /api/pipelines/{pid}               — rename (root included)
DELETE /api/pipelines/{pid}               — hide (guards apply; never
                                             deletes data — see
                                             pipeline_store.hide_pipeline)
POST   /api/pipelines/{pid}/unhide        — restore a hidden scope
GET    /api/pipelines/hidden              — hidden scopes (restore panel)
GET    /api/pipelines/{pid}/interface     — the scope's ports
POST   /api/pipelines/{pid}/extract       — turn selected nodes into a new
                                             submodule pipeline (a move,
                                             not a copy)
POST   /api/pipelines/{pid}/duplicate     — fork pid's own nodes into a
                                             new independent pipeline
                                             (submodule placements keep
                                             pointing at the same child)
POST   /api/hypotheses/{pid}/duplicate    — same, and tags the copy as
                                             its own hypothesis (new tab)
POST   /api/pipelines/{pid}/uses          — place a pipeline node on pid
PUT    /api/pipeline-uses/{use_id}/binding
DELETE /api/pipeline-uses/{use_id}

GET    /api/hypotheses                    — hypothesis-tagged pipelines (tabs)
POST   /api/hypotheses                    — create a pipeline + tag it
PUT    /api/hypotheses/{pid}              — edit metadata (research
                                             question, statement, evidence)
DELETE /api/hypotheses/{pid}              — hide (delegates to
                                             hide_pipeline's guards)

Store-level ValueErrors (cycles, last-visible-pipeline guard, duplicate
names, unknown ids, binding-key whitelist) map to HTTP 400 with the store's
message.
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


class HypothesisCreate(BaseModel):
    name: str


class HypothesisUpdate(BaseModel):
    research_question: str | None = None
    hypothesis_statement: str | None = None
    evidence_for: list | None = None
    evidence_against: list | None = None


class ExtractToSubmodule(BaseModel):
    node_ids: list[str]
    name: str


class DuplicatePipeline(BaseModel):
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
    """Hides the pipeline (never deletes data) — see scope_service.hide_pipeline."""
    return _guard(scope_service.hide_pipeline, pipeline_id)


@router.post("/pipelines/{pipeline_id}/unhide")
def post_unhide_pipeline(pipeline_id: str) -> dict:
    return _guard(scope_service.unhide_pipeline, pipeline_id)


@router.get("/pipelines/hidden")
def get_hidden_pipelines() -> dict:
    return scope_service.list_hidden_pipelines()


@router.get("/hypotheses")
def get_hypotheses() -> dict:
    return scope_service.list_hypotheses()


@router.post("/hypotheses")
def post_hypothesis(body: HypothesisCreate) -> dict:
    return _guard(scope_service.create_hypothesis, body.name)


@router.put("/hypotheses/{pipeline_id}")
def put_hypothesis(pipeline_id: str, body: HypothesisUpdate) -> dict:
    return _guard(
        scope_service.update_hypothesis,
        pipeline_id,
        body.research_question,
        body.hypothesis_statement,
        body.evidence_for,
        body.evidence_against,
    )


@router.delete("/hypotheses/{pipeline_id}")
def delete_hypothesis(pipeline_id: str) -> dict:
    """Hides the hypothesis (never deletes data) — see scope_service.hide_hypothesis."""
    return _guard(scope_service.hide_hypothesis, pipeline_id)


@router.post("/pipelines/{pipeline_id}/extract")
def post_extract_to_submodule(pipeline_id: str, body: ExtractToSubmodule) -> dict:
    return _guard(
        scope_service.extract_to_submodule, pipeline_id, body.node_ids, body.name
    )


@router.post("/pipelines/{pipeline_id}/duplicate")
def post_duplicate_pipeline(pipeline_id: str, body: DuplicatePipeline) -> dict:
    return _guard(scope_service.duplicate_pipeline, pipeline_id, body.name)


@router.post("/hypotheses/{pipeline_id}/duplicate")
def post_duplicate_hypothesis(pipeline_id: str, body: DuplicatePipeline) -> dict:
    return _guard(scope_service.duplicate_hypothesis, pipeline_id, body.name)


@router.get("/pipelines/{pipeline_id}/interface")
def get_pipeline_interface(pipeline_id: str) -> dict:
    return scope_service.pipeline_interface(pipeline_id)


@router.get("/pipelines/{pipeline_id}/plan")
def get_pipeline_plan(pipeline_id: str, target: str = "") -> list[dict]:
    """The plan-preview dialog's data (R2): compile the document scope to a
    backend pipeline and dry-run plan it — nothing executes."""
    from scistack_gui.db import get_db
    from scistack_gui.services.execution_service import plan_pipeline

    return _guard(plan_pipeline, get_db(), pipeline_id, target)


class PipelineRunRequest(BaseModel):
    mode: str = "all"  # all | until | endpoints
    target: str = ""  # step/fn name (mode="until")
    finalized: bool | None = None  # endpoint draft/record flag
    skip_computed: bool = True
    run_id: str | None = None


@router.post("/pipelines/{pipeline_id}/run")
def post_pipeline_run(pipeline_id: str, body: PipelineRunRequest) -> dict:
    """Execute the scope through the backend verbs in a background run
    thread (same relay/cancel machinery as per-node runs)."""
    from scistack_gui.api.run import start_pipeline_run

    return _guard(
        start_pipeline_run,
        pipeline_id,
        body.mode,
        body.target,
        body.finalized,
        body.skip_computed,
        body.run_id,
    )


@router.post("/pipelines/{pipeline_id}/uses")
def post_pipeline_use(pipeline_id: str, body: UseCreate) -> dict:
    return _guard(
        scope_service.add_pipeline_use,
        pipeline_id,
        body.child_pipeline_id,
        body.binding,
        body.x,
        body.y,
    )


@router.put("/pipeline-uses/{use_id}/binding")
def put_use_binding(use_id: str, body: BindingUpdate) -> dict:
    return _guard(scope_service.update_use_binding, use_id, body.binding)


@router.delete("/pipeline-uses/{use_id}")
def delete_pipeline_use(use_id: str) -> dict:
    return _guard(scope_service.remove_pipeline_use, use_id)
