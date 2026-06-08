from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter, Depends

from storyforge3.api.deps import get_book_service
from storyforge3.api.errors import book_not_found, invalid_parameter
from storyforge3.api.response import ok
from storyforge3.models import BookConfig, BookMeta
from storyforge3.services.book_service import BookService

router = APIRouter(prefix="/books", tags=["books"])


class CreateBookRequest(BaseModel):
    title: str
    genre: str
    platform: str = "tomato"
    target_chapters: int = 100
    chapter_word_count: int = 2500
    language: str = "zh"


class UpdateStatusRequest(BaseModel):
    status: str


class BookResponse(BaseModel):
    book_id: str
    title: str
    genre: str
    platform: str
    status: str
    target_chapters: int
    chapter_word_count: int
    language: str
    current_chapter: int
    created_at: str
    updated_at: str


def _meta_to_response(meta: BookMeta) -> BookResponse:
    return BookResponse(
        book_id=meta.book_id,
        title=meta.title,
        genre=meta.genre,
        platform=meta.platform,
        status=meta.status.value if hasattr(meta.status, "value") else str(meta.status),
        target_chapters=meta.target_chapters,
        chapter_word_count=meta.chapter_word_count,
        language=meta.language,
        current_chapter=meta.current_chapter,
        created_at=meta.created_at,
        updated_at=meta.updated_at,
    )


@router.post("")
async def create_book(
    req: CreateBookRequest,
    service: BookService = Depends(get_book_service),
):
    config = BookConfig(
        title=req.title,
        genre=req.genre,
        platform=req.platform,
        target_chapters=req.target_chapters,
        chapter_word_count=req.chapter_word_count,
        language=req.language,
    )
    meta = await service.create(config)
    return ok(_meta_to_response(meta))


@router.get("")
async def list_books(service: BookService = Depends(get_book_service)):
    books = await service.list_books()
    return ok([_meta_to_response(book) for book in books])


@router.get("/{book_id}")
async def get_book(
    book_id: str,
    service: BookService = Depends(get_book_service),
):
    meta = await service.get(book_id)
    if meta is None:
        raise book_not_found(book_id)
    return ok(_meta_to_response(meta))


@router.patch("/{book_id}/status")
async def update_book_status(
    book_id: str,
    req: UpdateStatusRequest,
    service: BookService = Depends(get_book_service),
):
    meta = await service.get(book_id)
    if meta is None:
        raise book_not_found(book_id)
    try:
        updated = await service.update_status(book_id, req.status)
    except ValueError as exc:
        raise invalid_parameter(f"Invalid book status: {req.status}") from exc
    return ok(_meta_to_response(updated))
