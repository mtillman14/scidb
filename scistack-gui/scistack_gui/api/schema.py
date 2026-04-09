"""
GET /schema

Returns the experiment schema: the keys and their distinct values.
Used by the frontend to populate the global schema filter bar.
"""

from fastapi import APIRouter, Depends
from scidb.database import DatabaseManager
from scistack_gui.db import get_db, get_db_path

router = APIRouter()


@router.get("/info")
def get_info():
    """Returns metadata about the open database (used by the frontend header)."""
    return {"db_name": get_db_path().name}


@router.get("/schema")
def get_schema(db: DatabaseManager = Depends(get_db)):
    """
    Returns schema keys and all distinct values for each key.

    Example response:
        {
            "keys": ["subject", "session"],
            "values": {
                "subject": [1, 2, 3],
                "session": ["pre", "post"]
            }
        }
    """
    keys = db.dataset_schema_keys
    values = {key: db.distinct_schema_values(key) for key in keys}
    return {"keys": keys, "values": values}


@router.get("/variables")
def list_variables():
    """Returns all registered variable type names.

    Uses the in-memory registry (BaseVariable._all_subclasses) so that
    variable types are available for filter setup even before any data
    has been saved.

    Example response:
        [{"variable_name": "RawSignal"}, {"variable_name": "Side"}]
    """
    from scidb import BaseVariable
    return [{"variable_name": name} for name in sorted(BaseVariable._all_subclasses.keys())]
