from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from storyforge3.api.deps import get_volume_service
from storyforge3.api.errors import book_not_found
from storyforge3.api.response import ok
from storyforge3.models import VolumeOutline
from storyforge3.services.volume_service import VolumeService

router = APIRouter(prefix="/books/{book_id}/volumes", tags=["volumes"])


class PlanVolumesRequest(BaseModel):
    volume_count: int
    total_chapters: int = 10


class UpdateVolumeRequest(BaseModel):
    title: str
    chapter_count: int
    synopsis: str
    key_scenes: list[str] = Field(default_factory=list)
    rhythm_curve: list[str] = Field(default_factory=list)


class VolumeResponse(BaseModel):
    book_id: str
    volume_no: int
    title: str
    chapter_count: int
    synopsis: str
    key_scenes: list[str]
    rhythm_curve: list[str]


def _volume_to_response(volume: VolumeOutline) -> VolumeResponse:
    return VolumeResponse(
        book_id=volume.book_id,
        volume_no=volume.volume_no,
        title=volume.title,
        chapter_count=volume.chapter_count,
        synopsis=volume.synopsis,
        key_scenes=list(volume.key_scenes),
        rhythm_curve=list(volume.rhythm_curve),
    )


@router.post("")
async def plan_volumes(
    book_id: str,
    req: PlanVolumesRequest,
    service: VolumeService = Depends(get_volume_service),
):
    volumes = await service.plan(book_id, req.volume_count, req.total_chapters)
    return ok([_volume_to_response(volume) for volume in volumes])


@router.get("")
async def list_volumes(
    book_id: str,
    service: VolumeService = Depends(get_volume_service),
):
    volumes = await service.list_volumes(book_id)
    return ok([_volume_to_response(volume) for volume in volumes])


@router.get("/{volume_no}")
async def get_volume(
    book_id: str,
    volume_no: int,
    service: VolumeService = Depends(get_volume_service),
):
    volume = await service.get(book_id, volume_no)
    if volume is None:
        raise book_not_found(book_id)
    return ok(_volume_to_response(volume))


@router.put("/{volume_no}")
async def update_volume(
    book_id: str,
    volume_no: int,
    req: UpdateVolumeRequest,
    service: VolumeService = Depends(get_volume_service),
):
    outline = VolumeOutline(
        book_id=book_id,
        volume_no=volume_no,
        title=req.title,
        chapter_count=req.chapter_count,
        synopsis=req.synopsis,
        key_scenes=tuple(req.key_scenes),
        rhythm_curve=tuple(req.rhythm_curve),
    )
    updated = await service.update(book_id, volume_no, outline)
    return ok(_volume_to_response(updated))
