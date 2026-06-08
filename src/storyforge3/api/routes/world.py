from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from storyforge3.api.deps import get_world_service
from storyforge3.api.errors import book_not_found
from storyforge3.api.response import ok
from storyforge3.models import WorldConfig
from storyforge3.services.world_service import WorldService

router = APIRouter(prefix="/books/{book_id}/world", tags=["world"])


class BuildWorldRequest(BaseModel):
    genre: str = "urban"
    seed_brief: str


class UpdateWorldRequest(BaseModel):
    setting: str
    power_system: str
    core_conflict: str
    rules: list[str] = Field(default_factory=list)


class WorldResponse(BaseModel):
    book_id: str
    setting: str
    power_system: str
    core_conflict: str
    rules: list[str]


def _world_to_response(world: WorldConfig) -> WorldResponse:
    return WorldResponse(
        book_id=world.book_id,
        setting=world.setting,
        power_system=world.power_system,
        core_conflict=world.core_conflict,
        rules=list(world.rules),
    )


@router.post("")
async def build_world(
    book_id: str,
    req: BuildWorldRequest,
    service: WorldService = Depends(get_world_service),
):
    world = await service.build(book_id, req.genre, req.seed_brief)
    return ok(_world_to_response(world))


@router.get("")
async def get_world(
    book_id: str,
    service: WorldService = Depends(get_world_service),
):
    world = await service.get(book_id)
    if world is None:
        raise book_not_found(book_id)
    return ok(_world_to_response(world))


@router.put("")
async def update_world(
    book_id: str,
    req: UpdateWorldRequest,
    service: WorldService = Depends(get_world_service),
):
    world = WorldConfig(
        book_id=book_id,
        setting=req.setting,
        power_system=req.power_system,
        core_conflict=req.core_conflict,
        rules=tuple(req.rules),
    )
    updated = await service.update(book_id, world)
    return ok(_world_to_response(updated))
