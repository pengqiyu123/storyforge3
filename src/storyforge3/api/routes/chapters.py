from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from storyforge3.api.deps import get_chapter_service
from storyforge3.api.errors import chapter_not_found, internal_error, invalid_parameter, state_error
from storyforge3.api.response import ok
from storyforge3.api.sse import PipelineEvent, sse_manager
from storyforge3.audit.llm_auditor import LLMAuditIssue, LLMAuditResult
from storyforge3.models import AuditResult, ChapterIntent, ChapterResult
from storyforge3.services.chapter_service import ChapterService
from storyforge3.services.length_normalizer import LengthNormalizationResult
from storyforge3.state.machine import InvalidTransitionError
from storyforge3.truth.extractor import TruthExtractionError

router = APIRouter(prefix="/books/{book_id}/chapters", tags=["chapters"])


class DraftRequest(BaseModel):
    goal: str | None = None
    must_keep: list[str] = Field(default_factory=list)
    must_avoid: list[str] = Field(default_factory=list)


class LlmAuditRequest(BaseModel):
    text: str


class NormalizeRequest(BaseModel):
    text: str
    target_chars: int = 2500
    soft_ratio: float = 0.15


class ReviseRequest(BaseModel):
    mode: str = "auto"


class ExportRequest(BaseModel):
    fmt: str = "tomato_txt"


class ChapterTextResponse(BaseModel):
    text: str


class ExportResponse(BaseModel):
    path: str


class ChapterIntentResponse(BaseModel):
    chapter_no: int
    goal: str
    outline_node: str
    arc_context: str
    must_keep: list[str]
    must_avoid: list[str]
    style_emphasis: list[str]


class ChapterStatusResponse(BaseModel):
    book_id: str
    chapter_no: int
    status: str
    title: str
    error: str | None


class AuditResponse(BaseModel):
    chapter_no: int
    passed: bool
    blocking_issues: list[str]
    warnings: list[str]
    info: list[str]


class LlmAuditIssueResponse(BaseModel):
    severity: str
    dimension: str
    description: str
    suggestion: str


class LlmAuditResponse(BaseModel):
    passed: bool
    issues: list[LlmAuditIssueResponse]


class NormalizeResponse(BaseModel):
    text: str
    action: str
    original_chars: int
    final_chars: int


def _intent_to_response(intent: ChapterIntent) -> ChapterIntentResponse:
    return ChapterIntentResponse(
        chapter_no=intent.chapter_no,
        goal=intent.goal,
        outline_node=intent.outline_node,
        arc_context=intent.arc_context,
        must_keep=list(intent.must_keep),
        must_avoid=list(intent.must_avoid),
        style_emphasis=list(intent.style_emphasis),
    )


def _request_to_intent(chapter_no: int, req: DraftRequest) -> ChapterIntent | None:
    if req.goal is None and not req.must_keep and not req.must_avoid:
        return None
    return ChapterIntent(
        chapter_no=chapter_no,
        goal=req.goal or "推进主线",
        must_keep=tuple(req.must_keep),
        must_avoid=tuple(req.must_avoid),
    )


def _audit_to_response(audit: AuditResult) -> AuditResponse:
    return AuditResponse(
        chapter_no=audit.chapter_no,
        passed=audit.passed,
        blocking_issues=list(audit.blocking_issues),
        warnings=list(audit.warnings),
        info=list(audit.info),
    )


def _llm_issue_to_response(issue: LLMAuditIssue) -> LlmAuditIssueResponse:
    return LlmAuditIssueResponse(
        severity=issue.severity,
        dimension=issue.dimension,
        description=issue.description,
        suggestion=issue.suggestion,
    )


def _llm_audit_to_response(result: LLMAuditResult) -> LlmAuditResponse:
    return LlmAuditResponse(
        passed=result.passed,
        issues=[_llm_issue_to_response(issue) for issue in result.issues],
    )


def _normalize_to_response(result: LengthNormalizationResult) -> NormalizeResponse:
    return NormalizeResponse(
        text=result.text,
        action=result.action,
        original_chars=result.original_chars,
        final_chars=result.final_chars,
    )


def _result_to_response(result: ChapterResult) -> ChapterStatusResponse:
    return ChapterStatusResponse(
        book_id=result.book_id,
        chapter_no=result.chapter_no,
        status=result.status.value if hasattr(result.status, "value") else str(result.status),
        title=result.title,
        error=result.error,
    )


def _path_to_response(path: Path) -> ExportResponse:
    return ExportResponse(path=str(path))


@router.post("/{chapter_no}/plan")
async def plan_chapter(
    book_id: str,
    chapter_no: int,
    service: ChapterService = Depends(get_chapter_service),
):
    intent = await service.plan(book_id, chapter_no)
    return ok(_intent_to_response(intent))


@router.post("/{chapter_no}/draft")
async def draft_chapter(
    book_id: str,
    chapter_no: int,
    req: DraftRequest | None = None,
    service: ChapterService = Depends(get_chapter_service),
):
    await _publish_start(book_id, chapter_no, "draft", f"开始第 {chapter_no} 章草稿")
    try:
        text = await service.draft(book_id, chapter_no, _request_to_intent(chapter_no, req or DraftRequest()))
        await _publish_complete(book_id, chapter_no, "draft", {"chars": len(text)})
        return ok(ChapterTextResponse(text=text))
    except Exception as exc:
        await _publish_error(book_id, chapter_no, str(exc), "draft")
        raise internal_error(str(exc)) from exc


@router.post("/{chapter_no}/audit")
async def audit_chapter(
    book_id: str,
    chapter_no: int,
    service: ChapterService = Depends(get_chapter_service),
):
    try:
        audit = await service.audit(book_id, chapter_no)
    except FileNotFoundError as exc:
        raise chapter_not_found(book_id, chapter_no) from exc
    return ok(_audit_to_response(audit))


@router.post("/{chapter_no}/llm-audit")
async def llm_audit_chapter(
    book_id: str,
    chapter_no: int,
    req: LlmAuditRequest,
    service: ChapterService = Depends(get_chapter_service),
):
    result = await service.run_llm_audit(book_id, chapter_no, req.text)
    return ok(_llm_audit_to_response(result))


@router.post("/{chapter_no}/normalize")
async def normalize_chapter(
    book_id: str,
    chapter_no: int,
    req: NormalizeRequest,
    service: ChapterService = Depends(get_chapter_service),
):
    del book_id, chapter_no
    if req.target_chars <= 0:
        raise invalid_parameter("target_chars must be positive")
    result = await service.normalize_length(
        req.text,
        target_chars=req.target_chars,
        soft_ratio=req.soft_ratio,
    )
    return ok(_normalize_to_response(result))


@router.post("/{chapter_no}/revise")
async def revise_chapter(
    book_id: str,
    chapter_no: int,
    req: ReviseRequest | None = None,
    service: ChapterService = Depends(get_chapter_service),
):
    try:
        result = await service.revise(book_id, chapter_no, (req or ReviseRequest()).mode)
    except ValueError as exc:
        raise invalid_parameter(str(exc)) from exc
    return ok(_result_to_response(result))


@router.post("/{chapter_no}/approve")
async def approve_chapter(
    book_id: str,
    chapter_no: int,
    service: ChapterService = Depends(get_chapter_service),
):
    result = await service.approve(book_id, chapter_no)
    return ok(_result_to_response(result))


@router.post("/{chapter_no}/export")
async def export_chapter(
    book_id: str,
    chapter_no: int,
    req: ExportRequest | None = None,
    service: ChapterService = Depends(get_chapter_service),
):
    path = await service.export(book_id, chapter_no, (req or ExportRequest()).fmt)
    return ok(_path_to_response(path))


@router.post("/{chapter_no}/run")
async def run_full_pipeline(
    book_id: str,
    chapter_no: int,
    service: ChapterService = Depends(get_chapter_service),
):
    await _publish_start(book_id, chapter_no, "full_pipeline", f"开始第 {chapter_no} 章完整管线")
    try:
        result = await service.run_full_pipeline(book_id, chapter_no, human_confirm=lambda _: True)
        await _publish_complete(
            book_id,
            chapter_no,
            "full_pipeline",
            {"status": result.status.value if hasattr(result.status, "value") else str(result.status), "error": result.error},
        )
        return ok(_result_to_response(result))
    except InvalidTransitionError as exc:
        await _publish_error(book_id, chapter_no, str(exc), "full_pipeline")
        raise state_error(str(exc)) from exc
    except TruthExtractionError as exc:
        await _publish_error(book_id, chapter_no, str(exc), "full_pipeline")
        raise internal_error(str(exc)) from exc
    except Exception as exc:
        await _publish_error(book_id, chapter_no, str(exc), "full_pipeline")
        raise internal_error(str(exc)) from exc


@router.get("/{chapter_no}/status")
async def get_chapter_status(
    book_id: str,
    chapter_no: int,
    service: ChapterService = Depends(get_chapter_service),
):
    result = await service.get_status(book_id, chapter_no)
    if result is None:
        raise chapter_not_found(book_id, chapter_no)
    return ok(_result_to_response(result))


async def _publish_start(book_id: str, chapter_no: int, stage: str, message: str) -> None:
    await sse_manager.publish(
        PipelineEvent(
            type="pipeline:start",
            book_id=book_id,
            chapter_no=chapter_no,
            stage=stage,
            message=message,
        )
    )


async def _publish_complete(book_id: str, chapter_no: int, stage: str, detail: dict | None = None) -> None:
    await sse_manager.publish(
        PipelineEvent(
            type="pipeline:complete",
            book_id=book_id,
            chapter_no=chapter_no,
            stage=stage,
            detail=detail,
        )
    )


async def _publish_error(book_id: str, chapter_no: int, message: str, stage: str | None = None) -> None:
    await sse_manager.publish(
        PipelineEvent(
            type="pipeline:error",
            book_id=book_id,
            chapter_no=chapter_no,
            stage=stage,
            message=message,
        )
    )
