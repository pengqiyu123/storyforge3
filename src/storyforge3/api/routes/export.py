from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel

from storyforge3.api.deps import get_export_service, get_paths
from storyforge3.api.errors import ApiError
from storyforge3.services.export_service import ExportService
from storyforge3.storage import StoragePaths

router = APIRouter(prefix="/books/{book_id}", tags=["export"])


class ExportBookRequest(BaseModel):
    fmt: str = "tomato_txt"
    approved_only: bool = True


@router.post("/export")
async def export_book(
    book_id: str,
    req: ExportBookRequest,
    service: ExportService = Depends(get_export_service),
):
    path = await service.export_book(book_id, req.fmt, approved_only=req.approved_only)
    return FileResponse(path, filename=path.name, media_type=_media_type(path))


@router.get("/exports/{filename}")
async def download_export(
    book_id: str,
    filename: str,
    paths: StoragePaths = Depends(get_paths),
):
    export_dir = (paths.book_dir(book_id) / "exports").resolve()
    path = (export_dir / filename).resolve()
    if not _is_within(path, export_dir) or not path.is_file():
        raise ApiError(status=404, code="EXPORT_NOT_FOUND", message=f"Export not found: {filename}")
    return FileResponse(path, filename=path.name, media_type=_media_type(path))


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _media_type(path: Path) -> str:
    if path.suffix.lower() == ".epub":
        return "application/epub+zip"
    if path.suffix.lower() == ".md":
        return "text/markdown; charset=utf-8"
    return "text/plain; charset=utf-8"
