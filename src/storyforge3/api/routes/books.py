from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter, Depends

from storyforge3.api.deps import get_book_service, get_chapter_reconciler
from storyforge3.api.errors import book_not_found, invalid_parameter
from storyforge3.api.response import ok
from storyforge3.models import BookConfig, BookMeta
from storyforge3.services.book_service import BookService
from storyforge3.services.chapter_reconciler import BookReconciliation, ChapterConsistency, ChapterReconciler

router = APIRouter(prefix="/books", tags=["books"])


class CreateBookRequest(BaseModel):
    title: str
    genre: str
    platform: str = "tomato"
    target_chapters: int = 100
    chapter_word_count: int = 2500
    language: str = "zh"
    fanfic_mode: str = ""


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
    fanfic_mode: str = ""


class ChapterConsistencyResponse(BaseModel):
    chapter_no: int
    has_text: bool
    has_plan: bool
    has_truth: bool
    has_export: bool
    has_state: bool
    has_run: bool
    state_status: str | None
    status: str
    validity: str
    inconsistent_reasons: list[str]


class BookReconciliationResponse(BaseModel):
    book_id: str
    chapters: list[ChapterConsistencyResponse]
    inconsistent_count: int
    max_chapter: int
    valid_chapter_count: int
    highest_contiguous_chapter: int
    next_writable_chapter_no: int
    has_blocking_inconsistency: bool


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
        fanfic_mode=meta.fanfic_mode,
    )


def _consistency_to_response(item: ChapterConsistency) -> ChapterConsistencyResponse:
    return ChapterConsistencyResponse(
        chapter_no=item.chapter_no,
        has_text=item.has_text,
        has_plan=item.has_plan,
        has_truth=item.has_truth,
        has_export=item.has_export,
        has_state=item.has_state,
        has_run=item.has_run,
        state_status=item.state_status,
        status=item.status,
        validity=item.validity,
        inconsistent_reasons=list(item.inconsistent_reasons),
    )


def _reconciliation_to_response(result: BookReconciliation) -> BookReconciliationResponse:
    return BookReconciliationResponse(
        book_id=result.book_id,
        chapters=[_consistency_to_response(item) for item in result.chapters],
        inconsistent_count=result.inconsistent_count,
        max_chapter=result.max_chapter,
        valid_chapter_count=result.valid_chapter_count,
        highest_contiguous_chapter=result.highest_contiguous_chapter,
        next_writable_chapter_no=result.next_writable_chapter_no,
        has_blocking_inconsistency=result.has_blocking_inconsistency,
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
        fanfic_mode=req.fanfic_mode,
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


@router.get("/{book_id}/reconcile")
async def reconcile_book(
    book_id: str,
    reconciler: ChapterReconciler = Depends(get_chapter_reconciler),
):
    return ok(_reconciliation_to_response(reconciler.reconcile(book_id)))


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
