from __future__ import annotations

import hashlib
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from storyforge3.api.deps import get_chapter_service
from storyforge3.api.errors import chapter_empty, chapter_not_found, content_conflict, internal_error, invalid_parameter, state_error
from storyforge3.api.response import ok
from storyforge3.api.sse import PipelineEvent, make_progress_event, sse_manager
from storyforge3.audit.chinese_text import count_chinese_chars
from storyforge3.audit.llm_auditor import LLMAuditIssue, LLMAuditResult
from storyforge3.export.formatter import PlatformFormatter
from storyforge3.export.markdown import format_markdown_chapter
from storyforge3.export.qidian import format_qidian_chapter
from storyforge3.models import AuditResult, ChapterIntent, ChapterResult, RevisionDiff, RuleResult
from storyforge3.services.chapter_service import ChapterService
from storyforge3.services.length_normalizer import LengthNormalizationResult
from storyforge3.state.machine import InvalidTransitionError
from storyforge3.truth.extractor import TruthExtractionError

router = APIRouter(prefix="/books/{book_id}/chapters", tags=["chapters"])
_EXPORT_PREVIEW_FORMATTER = PlatformFormatter()
_SUPPORTED_EXPORT_PREVIEW_FORMATS = {"tomato_txt", "markdown", "qidian_txt"}
_EXPORT_PREVIEW_PLACEHOLDER_TITLE = "__preview__"


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


class UpdateTextRequest(BaseModel):
    text: str = Field(..., min_length=1, description="章节正文")
    expected_hash: str | None = Field(default=None, description="乐观锁：当前正文的 SHA-256 前 8 位")


class ExportRequest(BaseModel):
    fmt: str = "tomato_txt"


class ChapterTextResponse(BaseModel):
    text: str


class ExportResponse(BaseModel):
    path: str


class ExportPreviewResponse(BaseModel):
    chapter_no: int
    format: str
    preview_text: str
    char_count: int
    format_errors: list[str] = Field(default_factory=list)


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
    text: str
    content_hash: str | None
    actual_chars: int
    revision_diff: "RevisionDiffResponse | None" = None
    error: str | None


class AuditResponse(BaseModel):
    chapter_no: int
    passed: bool
    blocking_issues: list[str]
    warnings: list[str]
    info: list[str]
    rule_results: list["RuleResultResponse"] = Field(default_factory=list)


class RuleResultResponse(BaseModel):
    rule_id: str
    passed: bool
    severity: str
    category: str
    message: str
    detail: dict = Field(default_factory=dict)


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


class RevisionDiffBlockResponse(BaseModel):
    kind: str
    before_text: str = ""
    after_text: str = ""


class RevisionDiffSummaryResponse(BaseModel):
    changed_blocks: int
    added_blocks: int
    removed_blocks: int
    before_chars: int
    after_chars: int


class RevisionDiffResponse(BaseModel):
    unit: str
    summary: RevisionDiffSummaryResponse
    blocks: list[RevisionDiffBlockResponse] = Field(default_factory=list)


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
        rule_results=[_rule_result_to_response(result) for result in audit.rule_results],
    )


def _rule_result_to_response(result: RuleResult) -> RuleResultResponse:
    severity = result.severity.name if hasattr(result.severity, "name") else str(result.severity).upper()
    category = result.category.name if hasattr(result.category, "name") else str(result.category).upper()
    return RuleResultResponse(
        rule_id=result.rule_id,
        passed=result.passed,
        severity=severity,
        category=category,
        message=result.message,
        detail=dict(result.detail),
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
        text=result.text,
        content_hash=_content_fingerprint(result.text) if result.text else None,
        actual_chars=count_chinese_chars(result.text),
        revision_diff=_diff_to_response(result.revision_diff) if result.revision_diff else None,
        error=result.error,
    )


def _diff_to_response(diff: RevisionDiff) -> RevisionDiffResponse:
    return RevisionDiffResponse(
        unit=diff.unit,
        summary=RevisionDiffSummaryResponse(**asdict(diff.summary)),
        blocks=[RevisionDiffBlockResponse(**asdict(block)) for block in diff.blocks],
    )


def _path_to_response(path: Path) -> ExportResponse:
    return ExportResponse(path=str(path))


def _preview_to_response(result: ChapterResult, fmt: str) -> ExportPreviewResponse:
    preview_text: str
    format_errors: list[str] = []
    if fmt == "tomato_txt":
        preview_text, format_errors = _format_tomato_preview(result)
    elif fmt == "markdown":
        preview_text = format_markdown_chapter(result.chapter_no, result.text)
    elif fmt == "qidian_txt":
        preview_text = format_qidian_chapter(result.chapter_no, result.text)
    else:
        raise invalid_parameter(f"unsupported export preview format: {fmt}")
    return ExportPreviewResponse(
        chapter_no=result.chapter_no,
        format=fmt,
        preview_text=preview_text,
        char_count=count_chinese_chars(preview_text),
        format_errors=format_errors,
    )


def _format_tomato_preview(result: ChapterResult) -> tuple[str, list[str]]:
    title = _normalize_preview_title(result.chapter_no, result.title)
    if title is not None:
        preview_text = _EXPORT_PREVIEW_FORMATTER.format_chapter(title, result.chapter_no, result.text)
        return preview_text, _EXPORT_PREVIEW_FORMATTER.check_format(title, result.chapter_no, preview_text)

    formatted = _EXPORT_PREVIEW_FORMATTER.format_chapter(
        _EXPORT_PREVIEW_PLACEHOLDER_TITLE,
        result.chapter_no,
        result.text,
    )
    parts = formatted.split("\n\n")
    preview_text = "\n\n".join([f"第{result.chapter_no}章", *parts[1:]]) if len(parts) > 1 else f"第{result.chapter_no}章"
    return preview_text, _check_tomato_preview_without_title(result.chapter_no, preview_text)


def _normalize_preview_title(chapter_no: int, title: str) -> str | None:
    normalized = title.strip()
    if not normalized:
        return None
    prefix = f"第{chapter_no}章"
    if normalized == prefix:
        return None
    if normalized.startswith(prefix):
        remainder = normalized[len(prefix) :].strip()
        return remainder or None
    return normalized


def _check_tomato_preview_without_title(chapter_no: int, formatted_text: str) -> list[str]:
    errors: list[str] = []
    lines = formatted_text.splitlines()
    if not lines or lines[0] != f"第{chapter_no}章":
        errors.append("chapter_header_format")
    if any(pattern in formatted_text for pattern in ("#", "**", "---", "[](", "](")):
        errors.append("markdown_artifacts")
    count = count_chinese_chars(formatted_text)
    if count < 1000 or count > 4000:
        errors.append("word_count_out_of_range")
    paragraphs = [line for line in lines[1:] if line.strip()]
    if len(paragraphs) < 3:
        errors.append("paragraph_count")
    return errors


@router.post("/{chapter_no}/plan")
async def plan_chapter(
    book_id: str,
    chapter_no: int,
    service: ChapterService = Depends(get_chapter_service),
):
    intent = await service.plan(book_id, chapter_no)
    return ok(_intent_to_response(intent))


@router.get("/{chapter_no}/plan")
async def get_chapter_plan(
    book_id: str,
    chapter_no: int,
    service: ChapterService = Depends(get_chapter_service),
):
    intent = await service.get_plan(book_id, chapter_no)
    if intent is None:
        raise chapter_not_found(book_id, chapter_no)
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
        text = await service.draft(
            book_id,
            chapter_no,
            _request_to_intent(chapter_no, req or DraftRequest()),
            on_chunk_progress=lambda completed, total: sse_manager.publish(
                make_progress_event(book_id, chapter_no, completed, total)
            ),
        )
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
    await _publish_start(book_id, chapter_no, "revise", f"开始第 {chapter_no} 章修订")
    try:
        result = await service.revise(book_id, chapter_no, (req or ReviseRequest()).mode)
    except ValueError as exc:
        await _publish_error(book_id, chapter_no, str(exc), "revise")
        raise invalid_parameter(str(exc)) from exc
    except Exception as exc:
        await _publish_error(book_id, chapter_no, str(exc), "revise")
        raise internal_error(str(exc)) from exc
    await _publish_complete(
        book_id,
        chapter_no,
        "revise",
        {"status": result.status.value if hasattr(result.status, "value") else str(result.status)},
    )
    return ok(_result_to_response(result))


@router.put("/{chapter_no}/text")
async def update_chapter_text(
    book_id: str,
    chapter_no: int,
    req: UpdateTextRequest,
    service: ChapterService = Depends(get_chapter_service),
):
    try:
        result = await service.update_text(book_id, chapter_no, req.text, expected_hash=req.expected_hash)
    except FileNotFoundError as exc:
        raise chapter_not_found(book_id, chapter_no) from exc
    except ValueError as exc:
        message = str(exc)
        if message == "空章节请先使用 draft 管线生成正文":
            raise chapter_empty(message) from exc
        if message == "章节内容已被修改，请刷新后重试":
            raise content_conflict(message) from exc
        raise invalid_parameter(message) from exc
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


@router.get("/{chapter_no}/export-preview")
async def export_chapter_preview(
    book_id: str,
    chapter_no: int,
    fmt: str = "tomato_txt",
    service: ChapterService = Depends(get_chapter_service),
):
    normalized_fmt = fmt.strip().lower()
    if normalized_fmt not in _SUPPORTED_EXPORT_PREVIEW_FORMATS:
        raise invalid_parameter(f"unsupported export preview format: {fmt}")
    result = await service.get_status(book_id, chapter_no)
    if result is None:
        raise chapter_not_found(book_id, chapter_no)
    return ok(_preview_to_response(result, normalized_fmt))


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


def _content_fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
