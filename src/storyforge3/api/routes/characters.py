from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from storyforge3.api.deps import get_character_service
from storyforge3.api.errors import book_not_found
from storyforge3.api.response import ok
from storyforge3.models import Character, Relationship
from storyforge3.services.character_service import CharacterService

router = APIRouter(prefix="/books/{book_id}/characters", tags=["characters"])


class CreateCharacterRequest(BaseModel):
    spec: str


class BatchCreateCharactersRequest(BaseModel):
    specs: list[str]


class UpdateCharacterRequest(BaseModel):
    updates: dict[str, Any] = Field(default_factory=dict)


class CharacterResponse(BaseModel):
    book_id: str
    name: str
    role: str
    profile: str
    personality: str
    abilities: list[str]
    arc_direction: str


class RelationshipResponse(BaseModel):
    character_a: str
    character_b: str
    relation_type: str
    description: str


def _character_to_response(character: Character) -> CharacterResponse:
    return CharacterResponse(
        book_id=character.book_id,
        name=character.name,
        role=character.role.value if hasattr(character.role, "value") else str(character.role),
        profile=character.profile,
        personality=character.personality,
        abilities=list(character.abilities),
        arc_direction=character.arc_direction,
    )


def _relationship_to_response(relationship: Relationship) -> RelationshipResponse:
    return RelationshipResponse(
        character_a=relationship.character_a,
        character_b=relationship.character_b,
        relation_type=relationship.relation_type,
        description=relationship.description,
    )


@router.post("")
async def create_character(
    book_id: str,
    req: CreateCharacterRequest,
    service: CharacterService = Depends(get_character_service),
):
    character = await service.create(book_id, req.spec)
    return ok(_character_to_response(character))


@router.post("/batch")
async def create_characters_batch(
    book_id: str,
    req: BatchCreateCharactersRequest,
    service: CharacterService = Depends(get_character_service),
):
    characters = await service.create_batch(book_id, tuple(req.specs))
    return ok([_character_to_response(character) for character in characters])


@router.get("")
async def list_characters(
    book_id: str,
    service: CharacterService = Depends(get_character_service),
):
    characters = await service.list_characters(book_id)
    return ok([_character_to_response(character) for character in characters])


@router.get("/relationships")
async def get_relationships(
    book_id: str,
    service: CharacterService = Depends(get_character_service),
):
    relationships = await service.get_relationships(book_id)
    return ok([_relationship_to_response(relationship) for relationship in relationships])


@router.patch("/{name}")
async def update_character(
    book_id: str,
    name: str,
    req: UpdateCharacterRequest,
    service: CharacterService = Depends(get_character_service),
):
    try:
        character = await service.update(book_id, name, req.updates)
    except FileNotFoundError as exc:
        raise book_not_found(book_id) from exc
    return ok(_character_to_response(character))
