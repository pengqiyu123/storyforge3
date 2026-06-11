from __future__ import annotations

import shutil
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from storyforge3.api.deps import get_workspace_service
from storyforge3.api.errors import invalid_parameter, state_error
from storyforge3.api.response import ok
from storyforge3.models import RestoreResult, WorkspaceValidation
from storyforge3.services.workspace_service import WorkspaceService

router = APIRouter(prefix="/workspace", tags=["workspace"])


class WorkspaceValidationResponse(BaseModel):
    valid: bool
    books_dir: str
    book_count: int
    issues: list[str]


class RestoreResultResponse(BaseModel):
    success: bool
    book_count: int
    backup_path: str
    message: str


@router.get("/validate")
async def validate_workspace(
    service: WorkspaceService = Depends(get_workspace_service),
):
    result = service.validate()
    return ok(_validation_response(result))


@router.post("/backup")
async def backup_workspace(
    service: WorkspaceService = Depends(get_workspace_service),
):
    try:
        result = service.backup()
    except ValueError as exc:
        raise state_error(str(exc)) from exc
    return FileResponse(result.path, filename=Path(result.path).name, media_type="application/zip")


@router.post("/restore")
async def restore_workspace(
    file: UploadFile = File(...),
    service: WorkspaceService = Depends(get_workspace_service),
):
    filename = Path(file.filename or "workspace-backup.zip").name
    suffix = Path(filename).suffix or ".zip"
    with NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp_path = Path(tmp.name)
        shutil.copyfileobj(file.file, tmp)
    try:
        result = service.restore(tmp_path)
    except ValueError as exc:
        raise invalid_parameter(str(exc)) from exc
    finally:
        tmp_path.unlink(missing_ok=True)
        await file.close()
    return ok(_restore_response(result))


def _validation_response(result: WorkspaceValidation) -> WorkspaceValidationResponse:
    return WorkspaceValidationResponse(
        valid=result.valid,
        books_dir=result.books_dir,
        book_count=result.book_count,
        issues=list(result.issues),
    )


def _restore_response(result: RestoreResult) -> RestoreResultResponse:
    return RestoreResultResponse(
        success=result.success,
        book_count=result.book_count,
        backup_path=result.backup_path,
        message=result.message,
    )
