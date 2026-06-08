from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from storyforge3.config import StoryForge3Config
from storyforge3.models import ChapterResult, ChapterStatus


@dataclass(frozen=True)
class DaemonConfig:
    book_id: str
    max_chapters_per_run: int = 5
    max_consecutive_failures: int = 3
    chapter_interval_seconds: float = 2.0
    start_from_chapter: int = 1
    target_chapters: int = 10


@dataclass(frozen=True)
class DaemonRunResult:
    book_id: str
    chapters_attempted: int
    chapters_succeeded: int
    chapters_failed: int
    consecutive_failures: int
    stopped_reason: str
    chapter_results: tuple[ChapterResult, ...]


class DaemonService:
    def __init__(self, config: StoryForge3Config, chapter_service: Any, export_service: Any) -> None:
        self.config = config
        self.chapter_service = chapter_service
        self.export_service = export_service

    async def run_batch(self, daemon_config: DaemonConfig) -> DaemonRunResult:
        results: list[ChapterResult] = []
        chapters_succeeded = 0
        chapters_failed = 0
        consecutive_failures = 0
        chapter_no = max(1, daemon_config.start_from_chapter)

        while len(results) < max(0, daemon_config.max_chapters_per_run) and chapter_no <= daemon_config.target_chapters:
            result = await self.chapter_service.run_full_pipeline(
                daemon_config.book_id,
                chapter_no,
                human_confirm=lambda _: True,
            )
            results.append(result)

            if self._is_success(result):
                chapters_succeeded += 1
                consecutive_failures = 0
                await self.export_service.export_chapter(daemon_config.book_id, chapter_no, "tomato_txt")
            else:
                chapters_failed += 1
                consecutive_failures += 1
                if consecutive_failures >= daemon_config.max_consecutive_failures:
                    return self._result(
                        daemon_config,
                        results,
                        chapters_succeeded,
                        chapters_failed,
                        consecutive_failures,
                        "consecutive_failures",
                    )

            if chapter_no >= daemon_config.target_chapters:
                return self._result(
                    daemon_config,
                    results,
                    chapters_succeeded,
                    chapters_failed,
                    consecutive_failures,
                    "target_reached",
                )

            chapter_no += 1
            if len(results) < daemon_config.max_chapters_per_run:
                await self._sleep(daemon_config.chapter_interval_seconds)

        stopped_reason = "target_reached" if chapter_no > daemon_config.target_chapters else "max_per_run"
        return self._result(
            daemon_config,
            results,
            chapters_succeeded,
            chapters_failed,
            consecutive_failures,
            stopped_reason,
        )

    @staticmethod
    def _is_success(result: ChapterResult) -> bool:
        return result.status == ChapterStatus.EXPORTED

    @staticmethod
    async def _sleep(seconds: float) -> None:
        if seconds > 0:
            await asyncio.sleep(seconds)

    @staticmethod
    def _result(
        daemon_config: DaemonConfig,
        results: list[ChapterResult],
        chapters_succeeded: int,
        chapters_failed: int,
        consecutive_failures: int,
        stopped_reason: str,
    ) -> DaemonRunResult:
        return DaemonRunResult(
            book_id=daemon_config.book_id,
            chapters_attempted=len(results),
            chapters_succeeded=chapters_succeeded,
            chapters_failed=chapters_failed,
            consecutive_failures=consecutive_failures,
            stopped_reason=stopped_reason,
            chapter_results=tuple(results),
        )
