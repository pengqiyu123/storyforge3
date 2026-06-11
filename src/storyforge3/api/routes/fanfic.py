from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from storyforge3.api.deps import get_fanfic_service
from storyforge3.api.errors import book_not_found
from storyforge3.api.response import ok
from storyforge3.models import FanficCanon, FanficMode
from storyforge3.services.fanfic_service import FanficService

router = APIRouter(prefix="/books/{book_id}/fanfic", tags=["fanfic"])


class CanonImportRequest(BaseModel):
    source_text: str
    source_name: str
    mode: FanficMode


class CanonResponse(BaseModel):
    book_id: str
    source_name: str
    mode: str
    world_rules: str
    character_profiles: str
    key_events: str
    power_system: str
    writing_style: str
    full_document: str
    generated_at: str


def _canon_to_response(canon: FanficCanon) -> CanonResponse:
    return CanonResponse(
        book_id=canon.book_id,
        source_name=canon.source_name,
        mode=canon.mode.value,
        world_rules=canon.world_rules,
        character_profiles=canon.character_profiles,
        key_events=canon.key_events,
        power_system=canon.power_system,
        writing_style=canon.writing_style,
        full_document=canon.full_document,
        generated_at=canon.generated_at,
    )


@router.post("/import")
async def import_canon(
    book_id: str,
    req: CanonImportRequest,
    service: FanficService = Depends(get_fanfic_service),
):
    canon = await service.import_canon(book_id, req.source_text, req.source_name, req.mode)
    return ok(_canon_to_response(canon))


@router.get("/canon")
async def get_canon(
    book_id: str,
    service: FanficService = Depends(get_fanfic_service),
):
    canon = service.get_canon(book_id)
    if canon is None:
        raise book_not_found(book_id)
    return ok(_canon_to_response(canon))


@router.post("/refresh")
async def refresh_canon(
    book_id: str,
    req: CanonImportRequest,
    service: FanficService = Depends(get_fanfic_service),
):
    try:
        canon = await service.refresh_canon(book_id, req.source_text)
    except FileNotFoundError as exc:
        raise book_not_found(book_id) from exc
    return ok(_canon_to_response(canon))
