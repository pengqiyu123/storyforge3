from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from storyforge3.api.deps import get_config
from storyforge3.api.errors import not_found
from storyforge3.api.response import ok
from storyforge3.config import StoryForge3Config
from storyforge3.snapshot import SnapshotManager

router = APIRouter(prefix="/books/{book_id}/snapshots", tags=["snapshots"])


class SnapshotMetaResponse(BaseModel):
    book_id: str
    chapter_no: int
    timestamp: str
    file_count: int
    path: str


class RestoreResultResponse(BaseModel):
    restored_files: list[str]
    count: int


def _get_manager(config: StoryForge3Config = Depends(get_config)) -> SnapshotManager:
    return SnapshotManager(config.books_dir, max_count=config.snapshot_max_count)


@router.get("")
async def list_snapshots(
    book_id: str,
    manager: SnapshotManager = Depends(_get_manager),
):
    snapshots = manager.list_snapshots(book_id)
    return ok([SnapshotMetaResponse(**item) for item in snapshots])


@router.post("/{snapshot_path:path}/restore")
async def restore_snapshot(
    book_id: str,
    snapshot_path: str,
    manager: SnapshotManager = Depends(_get_manager),
):
    try:
        result = manager.restore_snapshot(book_id, snapshot_path)
    except FileNotFoundError as exc:
        raise not_found(str(exc)) from exc
    return ok(RestoreResultResponse(**result))
