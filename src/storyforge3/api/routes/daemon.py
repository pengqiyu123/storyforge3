from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel

from storyforge3.api.deps import get_daemon_service
from storyforge3.api.response import ok
from storyforge3.api.sse import PipelineEvent, sse_manager
from storyforge3.services.daemon_service import DaemonConfig, DaemonRunResult, DaemonService

router = APIRouter(tags=["daemon"])


class DaemonStartRequest(BaseModel):
    max_chapters_per_run: int = 5
    max_consecutive_failures: int = 3
    chapter_interval_seconds: float = 2.0
    start_from_chapter: int = 1
    target_chapters: int = 10


class DaemonResultResponse(BaseModel):
    book_id: str
    chapters_attempted: int
    chapters_succeeded: int
    chapters_failed: int
    consecutive_failures: int
    stopped_reason: str


@router.post("/books/{book_id}/daemon/start")
async def start_daemon(
    book_id: str,
    req: DaemonStartRequest,
    background_tasks: BackgroundTasks,
    service: DaemonService = Depends(get_daemon_service),
):
    daemon_config = DaemonConfig(
        book_id=book_id,
        max_chapters_per_run=req.max_chapters_per_run,
        max_consecutive_failures=req.max_consecutive_failures,
        chapter_interval_seconds=req.chapter_interval_seconds,
        start_from_chapter=req.start_from_chapter,
        target_chapters=req.target_chapters,
    )

    async def _run() -> None:
        await _publish_daemon_start(daemon_config)
        try:
            result = await service.run_batch(daemon_config)
        except Exception as exc:
            await _publish_daemon_error(daemon_config, str(exc))
            return
        await _publish_daemon_complete(daemon_config, result)

    background_tasks.add_task(_run)
    return ok({"status": "started", "book_id": book_id})


async def _publish_daemon_start(config: DaemonConfig) -> None:
    await sse_manager.publish(
        PipelineEvent(
            type="pipeline:start",
            book_id=config.book_id,
            chapter_no=config.start_from_chapter,
            stage="daemon",
            message="批量写作已启动",
            detail=asdict(config),
        )
    )


async def _publish_daemon_complete(config: DaemonConfig, result: DaemonRunResult) -> None:
    response = DaemonResultResponse(
        book_id=result.book_id,
        chapters_attempted=result.chapters_attempted,
        chapters_succeeded=result.chapters_succeeded,
        chapters_failed=result.chapters_failed,
        consecutive_failures=result.consecutive_failures,
        stopped_reason=result.stopped_reason,
    )
    await sse_manager.publish(
        PipelineEvent(
            type="pipeline:complete",
            book_id=config.book_id,
            chapter_no=config.start_from_chapter,
            stage="daemon",
            detail=response.model_dump(),
        )
    )


async def _publish_daemon_error(config: DaemonConfig, message: str) -> None:
    await sse_manager.publish(
        PipelineEvent(
            type="pipeline:error",
            book_id=config.book_id,
            chapter_no=config.start_from_chapter,
            stage="daemon",
            message=message,
        )
    )
