from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from storyforge3.api.deps import get_truth_extractor, get_truth_store
from storyforge3.api.errors import internal_error
from storyforge3.api.response import ok
from storyforge3.models import TruthData
from storyforge3.truth.extractor import TruthExtractionError, TruthExtractor
from storyforge3.truth.store import TruthStore

router = APIRouter(prefix="/books/{book_id}/truth", tags=["truth"])


class TruthDataResponse(BaseModel):
    chapter_no: int
    source: str
    fact_assertions: list[str]
    character_updates: list[dict]
    relationship_updates: list[dict]
    hook_updates: list[dict]
    irreversible_facts: list[str]
    notes: list[str]


class ExtractRequest(BaseModel):
    chapter_no: int
    text: str


@router.get("/latest")
async def get_latest_truth(
    book_id: str,
    store: TruthStore = Depends(get_truth_store),
):
    truth = store.load_latest(book_id)
    return ok(_truth_to_response(truth) if truth is not None else None)


@router.get("/history")
async def get_truth_history(
    book_id: str,
    store: TruthStore = Depends(get_truth_store),
):
    history = store.load_history(book_id)
    return ok([_truth_to_response(item) for item in history])


@router.get("/{chapter_no}")
async def get_truth_by_chapter(
    book_id: str,
    chapter_no: int,
    store: TruthStore = Depends(get_truth_store),
):
    truth = store.load(book_id, chapter_no)
    return ok(_truth_to_response(truth) if truth is not None else None)


@router.post("/extract")
async def extract_truth(
    book_id: str,
    req: ExtractRequest,
    extractor: TruthExtractor = Depends(get_truth_extractor),
    store: TruthStore = Depends(get_truth_store),
):
    previous_truth = store.load_latest(book_id)
    try:
        truth = await extractor.extract(req.chapter_no, req.text, previous_truth)
    except TruthExtractionError as exc:
        raise internal_error(str(exc)) from exc
    store.save(book_id, truth)
    return ok(_truth_to_response(truth))


def _truth_to_response(truth: TruthData) -> TruthDataResponse:
    return TruthDataResponse(
        chapter_no=truth.chapter_no,
        source=truth.source,
        fact_assertions=list(truth.fact_assertions),
        character_updates=list(truth.character_updates),
        relationship_updates=list(truth.relationship_updates),
        hook_updates=list(truth.hook_updates),
        irreversible_facts=list(truth.irreversible_facts),
        notes=list(truth.notes),
    )
