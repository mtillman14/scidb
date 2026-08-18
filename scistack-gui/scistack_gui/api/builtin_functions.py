"""
POST /api/functions/builtin — manual built-in/library function references.

Thin FastAPI wrapper; the actual validation/registration logic lives in
``services/builtin_function_service.py`` so it can be shared with the
JSON-RPC handler used by the VS Code extension (``server.py``,
``create_builtin_function`` method).
"""

import logging

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


class CreateBuiltinFunctionRequest(BaseModel):
    language: str  # "python" | "matlab"
    reference: str  # e.g. "numpy.mean", "len", "mean"


@router.post("/functions/builtin")
def create_builtin_function(req: CreateBuiltinFunctionRequest) -> dict:
    from scistack_gui.services.builtin_function_service import (
        create_builtin_function as _create,
    )

    return _create(req.language, req.reference)
