from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from storyforge3.api.app import app
from storyforge3.api.deps import get_chapter_service, get_config, get_pipeline_logger, get_run_registry
from storyforge3.config import StoryForge3Config
from storyforge3.models import AuditResult, ChapterIntent, ChapterResult, ChapterStatus
from storyforge3.services.run_registry import RunRegistry
from storyforge3.storage import BookStorage, StoragePaths


class SlowChapterService:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def plan(self, _book_id: str, chapter_no: int) -> ChapterIntent:
        self.started.set()
        await asyncio.sleep(0.05)
        return ChapterIntent(chapter_no, "推进主线")

    async def draft(self, _book_id: str, _chapter_no: int, **_kwargs) -> str:
        return "完整管线正文"

    async def audit(self, _book_id: str, chapter_no: int) -> AuditResult:
        return AuditResult(chapter_no, True, (), (), (), ())

    async def approve(self, book_id: str, chapter_no: int) -> ChapterResult:
        return ChapterResult(book_id, chapter_no, ChapterStatus.TRUTH_COMMITTED, f"第{chapter_no}章", "完整管线正文")

    async def export(self, _book_id: str, chapter_no: int):
        return Path("exports") / f"chapter-{chapter_no:04d}.txt"


def test_async_run_returns_run_id_and_get_run_exposes_record(tmp_path: Path) -> None:
    config = StoryForge3Config(books_dir=str(tmp_path / "books"), providers_config_dir=str(tmp_path / ".storyforge3"))
    paths = StoragePaths(Path(config.books_dir))
    registry = RunRegistry(BookStorage(paths.books_root), paths)
    service = SlowChapterService()

    app.dependency_overrides[get_config] = lambda: config
    app.dependency_overrides[get_run_registry] = lambda: registry
    app.dependency_overrides[get_chapter_service] = lambda: service
    app.dependency_overrides[get_pipeline_logger] = lambda: None
    try:
        with TestClient(app) as client:
            response = client.post("/api/books/run-api/chapters/2/run")
            assert response.status_code == 200
            run_id = response.json()["data"]["run_id"]
            assert run_id

            current = client.get("/api/books/run-api/chapters/2/run")
            assert current.status_code == 200
            data = current.json()["data"]
            assert data["run_id"] == run_id
            assert data["status"] in {"pending", "running", "completed"}
            assert data["target_stages"] == ["plan", "draft", "audit", "revise", "approve", "truth", "export"]
    finally:
        app.dependency_overrides.clear()
