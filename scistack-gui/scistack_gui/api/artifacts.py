"""
Endpoint-presentation routes (plan-endpoint-presentation.md).

GET  /api/endpoints/{fn_name}/artifacts — finalized figures/stats manifest
GET  /api/artifacts/file?path=          — serve one artifact (project-dir
                                          guarded; 403 outside, 404 missing)
POST /api/report                        — write the endpoint report,
                                          return its index.html path
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from scidb.database import DatabaseManager

from scistack_gui.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/endpoints/{fn_name}/artifacts")
def get_endpoint_artifacts(fn_name: str,
                           db: DatabaseManager = Depends(get_db)) -> dict:
    from scistack_gui.services.endpoint_service import endpoint_artifacts
    return endpoint_artifacts(db, fn_name)


@router.get("/artifacts/file")
def get_artifact_file(path: str, db: DatabaseManager = Depends(get_db)):
    from scistack_gui.services.endpoint_service import artifact_file_path
    try:
        resolved = artifact_file_path(db, path)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return FileResponse(resolved)


@router.post("/report")
def post_report(db: DatabaseManager = Depends(get_db)) -> dict:
    from scistack_gui.services.endpoint_service import write_report
    try:
        return write_report(db)
    except Exception as exc:
        logger.exception("[api/artifacts] report generation failed")
        raise HTTPException(status_code=500, detail=str(exc))
