from __future__ import annotations

import asyncio
from pathlib import Path

from storyforge3.config import StoryForge3Config
from storyforge3.models import ChapterResult, ChapterStatus
from storyforge3.services.daemon_service import DaemonConfig, DaemonService


def run(coro):
    return asyncio.run(coro)


class MockChapterService:
    def __init__(self, statuses: list[ChapterStatus]) -> None:
        self.statuses = statuses
        self.calls: list[int] = []

    async def run_full_pipeline(self, book_id: str, chapter_no: int, *, human_confirm):
        self.calls.append(chapter_no)
        index = len(self.calls) - 1
        status = self.statuses[index] if index < len(self.statuses) else ChapterStatus.EXPORTED
        return ChapterResult(book_id, chapter_no, status, f"第{chapter_no}章", f"正文{chapter_no}")


class MockExportService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, str]] = []

    async def export_chapter(self, book_id: str, chapter_no: int, fmt: str = "tomato_txt") -> Path:
        self.calls.append((book_id, chapter_no, fmt))
        return Path(f"{book_id}-{chapter_no}.{fmt}")


def test_daemon_generates_until_target_reached(config: StoryForge3Config) -> None:
    chapter_service = MockChapterService([ChapterStatus.EXPORTED, ChapterStatus.EXPORTED, ChapterStatus.EXPORTED])
    export_service = MockExportService()
    service = DaemonService(config, chapter_service, export_service)

    result = run(
        service.run_batch(
            DaemonConfig(
                book_id="lurenjia",
                start_from_chapter=1,
                target_chapters=3,
                max_chapters_per_run=5,
                chapter_interval_seconds=0,
            )
        )
    )

    assert result.stopped_reason == "target_reached"
    assert result.chapters_attempted == 3
    assert result.chapters_succeeded == 3
    assert result.chapters_failed == 0
    assert result.consecutive_failures == 0
    assert chapter_service.calls == [1, 2, 3]
    assert export_service.calls == [("lurenjia", 1, "tomato_txt"), ("lurenjia", 2, "tomato_txt"), ("lurenjia", 3, "tomato_txt")]


def test_daemon_resets_consecutive_failures_after_success(config: StoryForge3Config) -> None:
    chapter_service = MockChapterService([ChapterStatus.NEEDS_REVIEW, ChapterStatus.NEEDS_REVIEW, ChapterStatus.EXPORTED])
    service = DaemonService(config, chapter_service, MockExportService())

    result = run(
        service.run_batch(
            DaemonConfig(
                book_id="lurenjia",
                start_from_chapter=1,
                target_chapters=3,
                max_consecutive_failures=3,
                max_chapters_per_run=5,
                chapter_interval_seconds=0,
            )
        )
    )

    assert result.stopped_reason == "target_reached"
    assert result.chapters_attempted == 3
    assert result.chapters_succeeded == 1
    assert result.chapters_failed == 2
    assert result.consecutive_failures == 0


def test_daemon_stops_on_consecutive_failures(config: StoryForge3Config) -> None:
    chapter_service = MockChapterService([ChapterStatus.NEEDS_REVIEW, ChapterStatus.NEEDS_REVIEW, ChapterStatus.EXPORTED])
    service = DaemonService(config, chapter_service, MockExportService())

    result = run(
        service.run_batch(
            DaemonConfig(
                book_id="lurenjia",
                start_from_chapter=1,
                target_chapters=5,
                max_consecutive_failures=2,
                max_chapters_per_run=5,
                chapter_interval_seconds=0,
            )
        )
    )

    assert result.stopped_reason == "consecutive_failures"
    assert result.chapters_attempted == 2
    assert result.chapters_succeeded == 0
    assert result.chapters_failed == 2
    assert result.consecutive_failures == 2
    assert chapter_service.calls == [1, 2]


def test_daemon_stops_on_max_chapters_per_run(config: StoryForge3Config) -> None:
    chapter_service = MockChapterService([ChapterStatus.EXPORTED, ChapterStatus.EXPORTED, ChapterStatus.EXPORTED])
    service = DaemonService(config, chapter_service, MockExportService())

    result = run(
        service.run_batch(
            DaemonConfig(
                book_id="lurenjia",
                start_from_chapter=4,
                target_chapters=10,
                max_chapters_per_run=2,
                chapter_interval_seconds=0,
            )
        )
    )

    assert result.stopped_reason == "max_per_run"
    assert result.chapters_attempted == 2
    assert result.chapters_succeeded == 2
    assert result.chapters_failed == 0
    assert chapter_service.calls == [4, 5]
