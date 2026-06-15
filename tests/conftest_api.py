from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from storyforge3.api.app import app
from storyforge3.config import StoryForge3Config
from storyforge3.audit.llm_auditor import LLMAuditIssue, LLMAuditResult
from storyforge3.models import (
    AuditResult,
    ChapterIntent,
    ChapterResult,
    ChapterStatus,
    RevisionDiff,
    RevisionDiffBlock,
    RevisionDiffSummary,
    TruthData,
)
from storyforge3.services.book_service import BookService
from storyforge3.services.chapter_discarder import ChapterDiscarder
from storyforge3.services.chapter_reconciler import ChapterReconciler
from storyforge3.services.daemon_service import DaemonRunResult
from storyforge3.services.length_normalizer import LengthNormalizationResult
from storyforge3.storage import BookStorage, StoragePaths
from storyforge3.truth.store import TruthStore


@pytest.fixture
def api_config(tmp_path: Path) -> StoryForge3Config:
    return StoryForge3Config(
        providers_config_dir=str(tmp_path / ".storyforge3"),
        default_model="test-model",
        books_dir=str(tmp_path / "books"),
    )


@pytest.fixture
def api_storage(api_config: StoryForge3Config) -> BookStorage:
    return BookStorage(Path(api_config.books_dir))


@pytest.fixture
def api_paths(api_config: StoryForge3Config) -> StoragePaths:
    return StoragePaths(Path(api_config.books_dir))


@pytest.fixture
def api_book_service(api_storage: BookStorage, api_paths: StoragePaths) -> BookService:
    return BookService(api_storage, api_paths)


@pytest.fixture
def api_mock_llm():
    return SimpleNamespace(
        generate_text=AsyncMock(return_value="测试文本。"),
        generate_json=AsyncMock(return_value={"patches": []}),
        check_health=AsyncMock(return_value=True),
        last_call=None,
    )


class ApiFakeChapterService:
    def __init__(self) -> None:
        self.audit_not_found = False
        self.update_not_found = False
        self.update_empty = False
        self.update_conflict = False
        self.status_result: ChapterResult | None = None
        self.audit_result: AuditResult | None = None
        self.last_revision_mode: str | None = None
        self.last_update_text: tuple[str, int, str, str | None] | None = None
        self.approve_calls = 0
        self.export_calls = 0
        self.truth_store = ApiFakeTruthStore()

    async def audit(self, book_id: str, chapter_no: int) -> AuditResult:
        if self.audit_not_found:
            raise FileNotFoundError("chapter not found")
        audit = self.audit_result or AuditResult(
            chapter_no=chapter_no,
            passed=True,
            blocking_issues=(),
            warnings=("节奏可继续加强",),
            info=("机械规则通过",),
            rule_results=(),
        )
        text = self.status_result.text if self.status_result is not None else "正文"
        self.status_result = ChapterResult(book_id, chapter_no, ChapterStatus.AUDITED, f"第{chapter_no}章", text, audit=audit)
        return audit

    async def normalize_length(
        self,
        text: str,
        *,
        target_chars: int,
        soft_ratio: float = 0.15,
        hard_range: tuple[int, int] | None = None,
    ) -> LengthNormalizationResult:
        del soft_ratio, hard_range
        return LengthNormalizationResult(text=text, action="none", original_chars=len(text), final_chars=target_chars)

    async def revise(self, book_id: str, chapter_no: int, mode: str = "auto") -> ChapterResult:
        if mode == "bad":
            raise ValueError("invalid revision mode: bad")
        self.last_revision_mode = mode
        result = ChapterResult(
            book_id,
            chapter_no,
            ChapterStatus.REVISED,
            f"第{chapter_no}章",
            "修订正文",
            revision_diff=RevisionDiff(
                unit="paragraph",
                summary=RevisionDiffSummary(
                    changed_blocks=1,
                    added_blocks=0,
                    removed_blocks=0,
                    before_chars=6,
                    after_chars=4,
                ),
                blocks=(RevisionDiffBlock(kind="replace", before_text="修订前正文", after_text="修订正文"),),
            ),
        )
        self.status_result = result
        return result

    async def update_text(self, book_id: str, chapter_no: int, text: str, *, expected_hash: str | None = None) -> ChapterResult:
        self.last_update_text = (book_id, chapter_no, text, expected_hash)
        if self.update_not_found:
            raise FileNotFoundError("chapter not found")
        if self.update_empty:
            raise ValueError("空章节请先使用 draft 管线生成正文")
        if self.update_conflict:
            raise ValueError("章节内容已被修改，请刷新后重试")
        result = ChapterResult(book_id, chapter_no, ChapterStatus.NEEDS_REVIEW, f"第{chapter_no}章", text)
        self.status_result = result
        return result

    async def get_status(self, _book_id: str, _chapter_no: int) -> ChapterResult | None:
        return self.status_result

    async def plan(self, book_id: str, chapter_no: int) -> ChapterIntent:
        self.status_result = ChapterResult(book_id, chapter_no, ChapterStatus.PLANNED, f"第{chapter_no}章", "")
        return ChapterIntent(chapter_no=chapter_no, goal="推进主线")

    async def draft(
        self,
        book_id: str,
        chapter_no: int,
        intent: ChapterIntent | None = None,
        *,
        on_chunk_progress=None,
        on_chunk=None,
    ) -> str:
        del intent
        if on_chunk_progress is not None:
            await on_chunk_progress(1, 2)
        if on_chunk is not None:
            await on_chunk("林默停在副楼门口。", 1, 2)
        text = "林默停在副楼门口。"
        self.status_result = ChapterResult(book_id, chapter_no, ChapterStatus.DRAFTED, f"第{chapter_no}章", text)
        return text

    async def run_llm_audit(self, _book_id: str, _chapter_no: int, _text: str) -> LLMAuditResult:
        return LLMAuditResult(
            passed=True,
            issues=(
                LLMAuditIssue(
                    severity="warning",
                    dimension="情节逻辑",
                    description="转折略快",
                    suggestion="增加动作承接",
                ),
            ),
        )

    async def approve(self, book_id: str, chapter_no: int) -> ChapterResult:
        self.approve_calls += 1
        result = ChapterResult(book_id, chapter_no, ChapterStatus.TRUTH_COMMITTED, f"第{chapter_no}章", "正文")
        self.status_result = result
        return result

    async def export(self, book_id: str, chapter_no: int, fmt: str = "tomato_txt") -> Path:
        self.export_calls += 1
        self.status_result = ChapterResult(book_id, chapter_no, ChapterStatus.EXPORTED, f"第{chapter_no}章", "正文")
        return Path("exports") / f"chapter-{chapter_no:04d}.{fmt}"

    async def run_full_pipeline(self, book_id: str, chapter_no: int, *, human_confirm=None) -> ChapterResult:
        if human_confirm is not None:
            human_confirm(ChapterResult(book_id, chapter_no, ChapterStatus.AUDITED, f"第{chapter_no}章", "预览正文"))
        result = ChapterResult(book_id, chapter_no, ChapterStatus.EXPORTED, f"第{chapter_no}章", "完整管线正文")
        self.status_result = result
        return result


class ApiFakeTruthStore:
    def __init__(self) -> None:
        self.latest: TruthData | None = None
        self.saved: tuple[str, TruthData] | None = None
        self.by_chapter: dict[tuple[str, int], TruthData] = {}

    def load_latest(self, _book_id: str) -> TruthData | None:
        return self.latest

    def load(self, _book_id: str, _chapter_no: int) -> TruthData | None:
        return self.by_chapter.get((_book_id, _chapter_no))

    def load_history(self, _book_id: str) -> list[TruthData]:
        return [
            TruthData(
                chapter_no=1,
                source="runtime_native",
                fact_assertions=("第1章事实。",),
                character_updates=(),
                relationship_updates=(),
                hook_updates=(),
                irreversible_facts=(),
                notes=(),
            ),
            TruthData(
                chapter_no=2,
                source="runtime_native",
                fact_assertions=("第2章事实。",),
                character_updates=(),
                relationship_updates=(),
                hook_updates=(),
                irreversible_facts=(),
                notes=(),
            ),
        ]

    def save(self, book_id: str, truth: TruthData) -> Path:
        self.saved = (book_id, truth)
        return Path("truth") / f"truth_{truth.chapter_no:04d}.json"


class ApiFakeTruthExtractor:
    async def extract(self, chapter_no: int, chapter_text: str, previous_truth: TruthData | None = None) -> TruthData:
        del chapter_text, previous_truth
        return TruthData(
            chapter_no=chapter_no,
            source="runtime_native",
            fact_assertions=(f"第{chapter_no}章 truth 已提取。",),
            character_updates=(),
            relationship_updates=(),
            hook_updates=(),
            irreversible_facts=(),
            notes=(),
        )


class ApiFakeExportService:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.last_book: tuple[str, str, bool] | None = None

    async def export_book(self, book_id: str, fmt: str = "tomato_txt", *, approved_only: bool = True) -> Path:
        self.last_book = (book_id, fmt, approved_only)
        if book_id == "missing-book":
            raise FileNotFoundError("book not found: missing-book")
        suffix = "epub" if fmt == "epub" else "txt"
        path = self.root / book_id / "exports" / f"{book_id}.{suffix}"
        path.parent.mkdir(parents=True, exist_ok=True)
        if suffix == "epub":
            path.write_bytes(b"epub-bytes")
        else:
            path.write_text(f"book {fmt} approved={approved_only}", encoding="utf-8")
        return path


class ApiFakeDaemonService:
    def __init__(self) -> None:
        self.last_config = None

    async def run_batch(self, daemon_config):
        self.last_config = daemon_config
        return DaemonRunResult(
            book_id=daemon_config.book_id,
            chapters_attempted=0,
            chapters_succeeded=0,
            chapters_failed=0,
            consecutive_failures=0,
            stopped_reason="target_reached",
            chapter_results=(),
        )


@pytest.fixture
def api_chapter_service() -> ApiFakeChapterService:
    return ApiFakeChapterService()


@pytest.fixture
def api_truth_store() -> ApiFakeTruthStore:
    return ApiFakeTruthStore()


@pytest.fixture
def api_truth_extractor() -> ApiFakeTruthExtractor:
    return ApiFakeTruthExtractor()


@pytest.fixture
def api_export_service(api_config: StoryForge3Config) -> ApiFakeExportService:
    return ApiFakeExportService(Path(api_config.books_dir))


@pytest.fixture
def api_daemon_service() -> ApiFakeDaemonService:
    return ApiFakeDaemonService()


@pytest.fixture
async def async_client(
    api_config: StoryForge3Config,
    api_storage: BookStorage,
    api_paths: StoragePaths,
    api_book_service: BookService,
    api_mock_llm,
    api_chapter_service: ApiFakeChapterService,
    api_truth_store: ApiFakeTruthStore,
    api_truth_extractor: ApiFakeTruthExtractor,
    api_export_service: ApiFakeExportService,
    api_daemon_service: ApiFakeDaemonService,
) -> AsyncIterator[AsyncClient]:
    from storyforge3.api.deps import (
        get_book_service,
        get_chapter_discarder,
        get_chapter_service,
        get_config,
        get_daemon_service,
        get_export_service,
        get_llm_service,
        get_truth_extractor,
        get_truth_store,
    )

    app.dependency_overrides[get_config] = lambda: api_config
    app.dependency_overrides[get_book_service] = lambda: api_book_service
    app.dependency_overrides[get_llm_service] = lambda: api_mock_llm
    api_chapter_service.truth_store = api_truth_store
    app.dependency_overrides[get_chapter_service] = lambda: api_chapter_service
    app.dependency_overrides[get_chapter_discarder] = lambda: ChapterDiscarder(
        api_storage,
        api_paths,
        truth_store=TruthStore(api_config.books_dir),
        reconciler=ChapterReconciler(api_storage, api_paths),
    )
    app.dependency_overrides[get_truth_store] = lambda: api_truth_store
    app.dependency_overrides[get_truth_extractor] = lambda: api_truth_extractor
    app.dependency_overrides[get_export_service] = lambda: api_export_service
    app.dependency_overrides[get_daemon_service] = lambda: api_daemon_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


async def create_api_book(client: AsyncClient, *, title: str = "测试小说") -> str:
    response = await client.post(
        "/api/books",
        json={
            "title": title,
            "genre": "urban",
            "platform": "tomato",
            "target_chapters": 50,
            "chapter_word_count": 2500,
        },
    )
    assert response.status_code == 200
    return str(response.json()["data"]["book_id"])


def write_imported_provider(config: StoryForge3Config) -> None:
    config_dir = Path(config.providers_config_dir)
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "providers.json").write_text(
        json.dumps(
            {
                "active_provider_key": "codex",
                "providers": [
                    {
                        "id": "p1",
                        "provider_key": "codex",
                        "label": "Codex 直连中转",
                        "base_url": "https://api.vip1129.cc/v1",
                        "api_key": "secret-key-1234",
                        "model_id": "gpt-5.5",
                        "enabled": True,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
