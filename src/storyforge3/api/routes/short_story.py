from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from storyforge3.api.deps import get_short_story_service
from storyforge3.api.errors import book_not_found, internal_error, invalid_parameter
from storyforge3.api.response import ok
from storyforge3.models import AuditResult, ShortStoryConfig, ShortStoryMeta, ShortStoryPlan, ShortStoryResult
from storyforge3.services.short_story_service import ShortStoryService

router = APIRouter(prefix="/short-stories", tags=["short-stories"])


class CreateShortStoryRequest(BaseModel):
    title: str
    genre: str
    target_chars: int = 10_000
    premise: str = ""
    style: str = ""


class ExportRequest(BaseModel):
    fmt: str = "tomato_txt"


class ShortStoryMetaResponse(BaseModel):
    book_id: str
    title: str
    genre: str
    status: str
    target_chars: int
    premise: str
    style: str
    actual_chars: int
    created_at: str
    updated_at: str


class ShortStoryPlanResponse(BaseModel):
    book_id: str
    premise: str
    opening: str
    climax: str
    ending: str
    characters: str
    key_scenes: list[str]
    must_keep: list[str]
    must_avoid: list[str]


class ShortStoryTextResponse(BaseModel):
    text: str


class ShortStoryResultResponse(BaseModel):
    book_id: str
    status: str
    text: str
    error: str | None = None


class AuditResponse(BaseModel):
    chapter_no: int
    passed: bool
    blocking_issues: list[str]
    warnings: list[str]
    info: list[str]


class ExportResponse(BaseModel):
    path: str


def _meta_to_response(meta: ShortStoryMeta) -> ShortStoryMetaResponse:
    return ShortStoryMetaResponse(
        book_id=meta.book_id,
        title=meta.title,
        genre=meta.genre,
        status=meta.status.value,
        target_chars=meta.target_chars,
        premise=meta.premise,
        style=meta.style,
        actual_chars=meta.actual_chars,
        created_at=meta.created_at,
        updated_at=meta.updated_at,
    )


def _plan_to_response(plan: ShortStoryPlan) -> ShortStoryPlanResponse:
    return ShortStoryPlanResponse(
        book_id=plan.book_id,
        premise=plan.premise,
        opening=plan.opening,
        climax=plan.climax,
        ending=plan.ending,
        characters=plan.characters,
        key_scenes=list(plan.key_scenes),
        must_keep=list(plan.must_keep),
        must_avoid=list(plan.must_avoid),
    )


def _audit_to_response(audit: AuditResult) -> AuditResponse:
    return AuditResponse(
        chapter_no=audit.chapter_no,
        passed=audit.passed,
        blocking_issues=list(audit.blocking_issues),
        warnings=list(audit.warnings),
        info=list(audit.info),
    )


def _result_to_response(result: ShortStoryResult) -> ShortStoryResultResponse:
    return ShortStoryResultResponse(
        book_id=result.book_id,
        status=result.status.value,
        text=result.text,
        error=result.error,
    )


def _path_to_response(path: Path) -> ExportResponse:
    return ExportResponse(path=str(path))


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_short_story(
    req: CreateShortStoryRequest,
    response: Response,
    service: ShortStoryService = Depends(get_short_story_service),
):
    if req.target_chars <= 0:
        raise invalid_parameter("target_chars must be positive")
    meta = await service.create(
        ShortStoryConfig(
            title=req.title,
            genre=req.genre,
            target_chars=req.target_chars,
            premise=req.premise,
            style=req.style,
        )
    )
    response.status_code = status.HTTP_201_CREATED
    return ok(_meta_to_response(meta))


@router.get("")
async def list_short_stories(
    service: ShortStoryService = Depends(get_short_story_service),
):
    return ok([_meta_to_response(meta) for meta in service.list_stories()])


@router.get("/{book_id}")
async def get_short_story(
    book_id: str,
    service: ShortStoryService = Depends(get_short_story_service),
):
    result = service.get_status(book_id)
    if result is None:
        raise book_not_found(book_id)
    return ok(_result_to_response(result))


@router.post("/{book_id}/plan")
async def plan_short_story(
    book_id: str,
    service: ShortStoryService = Depends(get_short_story_service),
):
    try:
        plan = await service.plan(book_id)
    except FileNotFoundError as exc:
        raise book_not_found(book_id) from exc
    return ok(_plan_to_response(plan))


@router.post("/{book_id}/draft")
async def draft_short_story(
    book_id: str,
    service: ShortStoryService = Depends(get_short_story_service),
):
    try:
        text = await service.draft(book_id)
    except FileNotFoundError as exc:
        raise book_not_found(book_id) from exc
    return ok(ShortStoryTextResponse(text=text))


@router.post("/{book_id}/audit")
async def audit_short_story(
    book_id: str,
    service: ShortStoryService = Depends(get_short_story_service),
):
    try:
        audit = await service.audit(book_id)
    except FileNotFoundError as exc:
        raise book_not_found(book_id) from exc
    return ok(_audit_to_response(audit))


@router.post("/{book_id}/revise")
async def revise_short_story(
    book_id: str,
    service: ShortStoryService = Depends(get_short_story_service),
):
    try:
        result = await service.revise(book_id)
    except FileNotFoundError as exc:
        raise book_not_found(book_id) from exc
    return ok(_result_to_response(result))


@router.post("/{book_id}/export")
async def export_short_story(
    book_id: str,
    req: ExportRequest | None = None,
    service: ShortStoryService = Depends(get_short_story_service),
):
    try:
        path = await service.export(book_id, (req or ExportRequest()).fmt)
    except FileNotFoundError as exc:
        raise book_not_found(book_id) from exc
    except ValueError as exc:
        raise invalid_parameter(str(exc)) from exc
    return ok(_path_to_response(path))


@router.post("/{book_id}/run")
async def run_short_story_pipeline(
    book_id: str,
    service: ShortStoryService = Depends(get_short_story_service),
):
    try:
        result = await service.run_full_pipeline(book_id)
    except FileNotFoundError as exc:
        raise book_not_found(book_id) from exc
    except Exception as exc:
        raise internal_error(str(exc)) from exc
    return ok(_result_to_response(result))
