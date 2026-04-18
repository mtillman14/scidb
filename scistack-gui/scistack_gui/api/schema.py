"""
GET /schema

Returns the experiment schema: the keys and their distinct values.
Used by the frontend to populate the global schema filter bar.
"""

from fastapi import APIRouter, Depends
from scidb.database import DatabaseManager
from scistack_gui.db import get_db

router = APIRouter()


@router.get("/info")
def get_info():
    """Returns metadata about the open database (used by the frontend header)."""
    from scistack_gui.services.pipeline_service import get_info as _get_info
    return _get_info()


@router.get("/schema")
def get_schema(db: DatabaseManager = Depends(get_db)):
    """Returns schema keys and all distinct values for each key."""
    from scistack_gui.services.pipeline_service import get_schema as _get_schema
    return _get_schema(db)


@router.get("/variables")
def list_variables():
    """Returns all registered variable type names."""
    from scistack_gui.services.pipeline_service import get_variables_list
    return get_variables_list()
