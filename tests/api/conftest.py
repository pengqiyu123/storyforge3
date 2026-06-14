from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

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
    RuleCategory,
    RuleResult,
    RuleSeverity,
    TruthData,
)
from storyforge3.services.daemon_service import DaemonRunResult
from storyforge3.services.length_normalizer import LengthNormalizationResult
from storyforge3.state.machine import InvalidTransitionError


@pytest.fixture
def config(tmp_path: Path) -> StoryForge3Config:
    """Use isolated book and provider directories for API tests."""
    return StoryForge3Config(
        providers_config_dir=str(tmp_path / ".storyforge3"),
        default_model="test-model",
        books_dir=str(tmp_path / "books"),
    )


@pytest.fixture
def mock_llm():
    async def _generate_json(task_name: str, *_args, **_kwargs):
        if task_name == "world_build":
            return {
                "setting": "现代都市里的异常检测中心",
                "power_system": "存在感调节",
                "core_conflict": "觉醒者隐藏自我与系统追踪之间的冲突",
                "rules": ["存在感越低越难被普通人注意", "异常检测会放大存在痕迹"],
            }
        if task_name == "character_create":
            return {
                "name": "林默",
                "role": "protagonist",
                "profile": "低存在感的都市少年",
                "personality": "谨慎、敏锐、慢热",
                "abilities": ["存在感调节"],
                "arc_direction": "从逃避观察到主动选择",
            }
        if task_name == "character_create_batch":
            return {
                "characters": [
                    {
                        "name": "周岚",
                        "role": "major",
                        "profile": "检测中心咨询员",
                        "personality": "冷静、负责",
                        "abilities": ["异常识别"],
                        "arc_direction": "从怀疑到协作",
                    },
                    {
                        "name": "沈砚",
                        "role": "minor",
                        "profile": "同校学生",
                        "personality": "外向、好奇",
                    },
                ],
                "relationships": [
                    {
                        "character_a": "林默",
                        "character_b": "周岚",
                        "relation_type": "ally",
                        "description": "检测与被检测之间逐步建立信任",
                    }
                ],
            }
        if task_name == "volume_plan":
            return {
                "volumes": [
                    {
                        "volume_no": 1,
                        "title": "存在感异常",
                        "chapter_count": 6,
                        "synopsis": "林默发现自己的存在感可以被调节。",
                        "key_scenes": ["检测中心初检", "走廊异常回响"],
                        "rhythm_curve": ["rise", "peak"],
                    },
                    {
                        "volume_no": 2,
                        "title": "副楼追踪",
                        "chapter_count": 6,
                        "synopsis": "检测中心的记录开始追踪林默。",
                        "key_scenes": ["档案缺页", "夜间回访"],
                        "rhythm_curve": ["rise", "fall"],
                    },
                ]
            }
        raise AssertionError(f"unexpected LLM task: {task_name}")

    return SimpleNamespace(
        generate_json=AsyncMock(side_effect=_generate_json),
        generate_text=AsyncMock(return_value='{"ok": true}'),
        check_health=AsyncMock(return_value=True),
    )


class FakeChapterService:
    def __init__(self) -> None:
        self.raise_audit_not_found = False
        self.raise_run_transition = False
        self.raise_update_not_found = False
        self.raise_update_empty = False
        self.raise_update_conflict = False
        self.last_draft_intent: ChapterIntent | None = None
        self.last_revision_mode: str | None = None
        self.last_export_format: str | None = None
        self.last_update_text: tuple[str, int, str, str | None] | None = None
        self.status_result: ChapterResult | None = None
        self.last_run_id: str | None = None

    async def plan(self, _book_id: str, chapter_no: int) -> ChapterIntent:
        if self.raise_run_transition:
            raise InvalidTransitionError("invalid transition drafted -> planned")
        return ChapterIntent(
            chapter_no=chapter_no,
            goal="推进主线",
            outline_node="检测中心副楼出现异常回响",
            arc_context="林默开始主动调查",
            must_keep=("林默谨慎",),
            must_avoid=("解释设定",),
            style_emphasis=("短句推进",),
        )

    async def get_plan(self, _book_id: str, chapter_no: int) -> ChapterIntent | None:
        return ChapterIntent(
            chapter_no=chapter_no,
            goal="推进主线",
            outline_node="检测中心副楼出现异常回响",
            arc_context="林默开始主动调查",
            must_keep=("林默谨慎",),
            must_avoid=("解释设定",),
            style_emphasis=("短句推进",),
        )

    async def draft(self, book_id: str, chapter_no: int, intent: ChapterIntent | None = None, *, on_chunk_progress=None, on_chunk=None) -> str:
        self.last_draft_intent = intent
        if on_chunk_progress is not None:
            await on_chunk_progress(1, 2)
        if on_chunk is not None:
            await on_chunk("林默停在副楼门口。", 1, 2)
        text = "林默停在副楼门口。\n\n提示音从走廊深处响了一下。"
        self.status_result = ChapterResult(book_id, chapter_no, ChapterStatus.DRAFTED, f"第{chapter_no}章", text)
        return text

    async def audit(self, _book_id: str, chapter_no: int) -> AuditResult:
        if self.raise_audit_not_found:
            raise FileNotFoundError("chapter not found")
        return AuditResult(
            chapter_no=chapter_no,
            passed=True,
            blocking_issues=(),
            warnings=("节奏可继续加强",),
            info=("机械规则通过",),
            rule_results=(
                RuleResult(
                    "info_dump",
                    False,
                    RuleSeverity.WARNING,
                    RuleCategory.STRUCTURE,
                    "长段信息倾倒",
                    {"paragraph_indices": [1], "snippet": "这一段太长，需要拆分。"},
                ),
            ),
        )

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

    async def normalize_length(
        self,
        text: str,
        *,
        target_chars: int,
        soft_ratio: float = 0.15,
        hard_range: tuple[int, int] | None = None,
    ) -> LengthNormalizationResult:
        del soft_ratio, hard_range
        return LengthNormalizationResult(
            text=f"{text} 扩展到{target_chars}字",
            action="expand",
            original_chars=10,
            final_chars=target_chars,
        )

    async def revise(self, book_id: str, chapter_no: int, mode: str = "auto") -> ChapterResult:
        self.last_revision_mode = mode
        return ChapterResult(
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

    async def update_text(self, book_id: str, chapter_no: int, text: str, *, expected_hash: str | None = None) -> ChapterResult:
        self.last_update_text = (book_id, chapter_no, text, expected_hash)
        if self.raise_update_not_found:
            raise FileNotFoundError("chapter not found")
        if self.raise_update_empty:
            raise ValueError("空章节请先使用 draft 管线生成正文")
        if self.raise_update_conflict:
            raise ValueError("章节内容已被修改，请刷新后重试")
        result = ChapterResult(book_id, chapter_no, ChapterStatus.NEEDS_REVIEW, f"第{chapter_no}章", text)
        self.status_result = result
        return result

    async def approve(self, book_id: str, chapter_no: int) -> ChapterResult:
        return ChapterResult(book_id, chapter_no, ChapterStatus.EXPORTED, f"第{chapter_no}章", "已确认正文")

    async def export(self, _book_id: str, chapter_no: int, fmt: str = "tomato_txt") -> Path:
        self.last_export_format = fmt
        return Path("exports") / f"chapter-{chapter_no:04d}.{fmt}"

    async def get_status(self, _book_id: str, _chapter_no: int) -> ChapterResult | None:
        return self.status_result

    async def run_full_pipeline(self, book_id: str, chapter_no: int, *, human_confirm=None) -> ChapterResult:
        if self.raise_run_transition:
            raise InvalidTransitionError("invalid transition drafted -> planned")
        if human_confirm is not None:
            human_confirm(ChapterResult(book_id, chapter_no, ChapterStatus.AUDITED, f"第{chapter_no}章", "预览正文"))
        result = ChapterResult(book_id, chapter_no, ChapterStatus.EXPORTED, f"第{chapter_no}章", "完整管线正文")
        self.status_result = result
        return result

    async def run_full_pipeline_async(self, book_id: str, chapter_no: int, *, human_confirm=None) -> ChapterResult:
        return await self.run_full_pipeline(book_id, chapter_no, human_confirm=human_confirm)


class FakeTruthStore:
    def __init__(self) -> None:
        self.latest = TruthData(
            chapter_no=2,
            source="runtime_native",
            fact_assertions=("林默进入检测中心。",),
            character_updates=({"summary": "林默保持谨慎。"},),
            relationship_updates=(),
            hook_updates=(),
            irreversible_facts=("检测中心存在异常档案。",),
            notes=("继续追踪副楼提示音。",),
        )
        self.history = [
            TruthData(1, "runtime_native", ("林默发现存在感异常。",), (), (), (), (), ()),
            self.latest,
        ]
        self.saved: tuple[str, TruthData] | None = None

    def load_latest(self, _book_id: str) -> TruthData | None:
        return self.latest

    def load(self, _book_id: str, chapter_no: int) -> TruthData | None:
        for item in self.history:
            if item.chapter_no == chapter_no:
                return item
        return None

    def load_history(self, _book_id: str) -> list[TruthData]:
        return self.history

    def save(self, book_id: str, truth: TruthData) -> Path:
        self.saved = (book_id, truth)
        return Path("truth") / f"chapter-{truth.chapter_no:04d}.json"


class FakeTruthExtractor:
    def __init__(self) -> None:
        self.should_fail = False
        self.last_previous_truth: TruthData | None = None

    async def extract(self, chapter_no: int, chapter_text: str, previous_truth: TruthData | None = None) -> TruthData:
        del chapter_text
        if self.should_fail:
            from storyforge3.truth.extractor import TruthExtractionError

            raise TruthExtractionError(chapter_no, "mock failure")
        self.last_previous_truth = previous_truth
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


class FakeExportService:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.last_chapter: tuple[str, int, str] | None = None
        self.last_book: tuple[str, str, bool] | None = None

    async def export_chapter(self, book_id: str, chapter_no: int, fmt: str = "tomato_txt") -> Path:
        self.last_chapter = (book_id, chapter_no, fmt)
        suffix = "epub" if fmt == "epub" else "txt"
        path = self.root / book_id / "exports" / f"chapter-{chapter_no:04d}.{suffix}"
        path.parent.mkdir(parents=True, exist_ok=True)
        if suffix == "epub":
            path.write_bytes(b"epub-bytes")
        else:
            path.write_text(f"chapter {chapter_no} {fmt}", encoding="utf-8")
        return path

    async def export_book(self, book_id: str, fmt: str = "tomato_txt", *, approved_only: bool = True) -> Path:
        self.last_book = (book_id, fmt, approved_only)
        suffix = "epub" if fmt == "epub" else "txt"
        path = self.root / book_id / "exports" / f"{book_id}.{suffix}"
        path.parent.mkdir(parents=True, exist_ok=True)
        if suffix == "epub":
            path.write_bytes(b"book-epub")
        else:
            path.write_text(f"book {fmt} approved={approved_only}", encoding="utf-8")
        return path


class FakeDaemonService:
    def __init__(self) -> None:
        self.last_config = None
        self.should_fail = False

    async def run_batch(self, daemon_config):
        if self.should_fail:
            raise RuntimeError("daemon failed")
        self.last_config = daemon_config
        result = ChapterResult(
            daemon_config.book_id,
            daemon_config.start_from_chapter,
            ChapterStatus.EXPORTED,
            f"第{daemon_config.start_from_chapter}章",
            "daemon正文",
        )
        return DaemonRunResult(
            book_id=daemon_config.book_id,
            chapters_attempted=1,
            chapters_succeeded=1,
            chapters_failed=0,
            consecutive_failures=0,
            stopped_reason="target_reached",
            chapter_results=(result,),
        )


@pytest.fixture
def mock_chapter_service() -> FakeChapterService:
    return FakeChapterService()


@pytest.fixture
def mock_truth_store() -> FakeTruthStore:
    return FakeTruthStore()


@pytest.fixture
def mock_truth_extractor() -> FakeTruthExtractor:
    return FakeTruthExtractor()


@pytest.fixture
def mock_export_service(config: StoryForge3Config) -> FakeExportService:
    return FakeExportService(Path(config.books_dir))


@pytest.fixture
def mock_daemon_service() -> FakeDaemonService:
    return FakeDaemonService()


@pytest.fixture
def client(
    config: StoryForge3Config,
    mock_llm,
    mock_chapter_service: FakeChapterService,
    mock_truth_store: FakeTruthStore,
    mock_truth_extractor: FakeTruthExtractor,
    mock_export_service: FakeExportService,
    mock_daemon_service: FakeDaemonService,
) -> Iterator[TestClient]:
    from storyforge3.api.app import app
    from storyforge3.api.deps import (
        get_chapter_service,
        get_config,
        get_daemon_service,
        get_export_service,
        get_llm_service,
        get_truth_extractor,
        get_truth_store,
    )

    def _override_config() -> StoryForge3Config:
        return config

    def _override_llm():
        return mock_llm

    def _override_chapter_service() -> FakeChapterService:
        return mock_chapter_service

    def _override_truth_store() -> FakeTruthStore:
        return mock_truth_store

    def _override_truth_extractor() -> FakeTruthExtractor:
        return mock_truth_extractor

    def _override_export_service() -> FakeExportService:
        return mock_export_service

    def _override_daemon_service() -> FakeDaemonService:
        return mock_daemon_service

    app.dependency_overrides[get_config] = _override_config
    app.dependency_overrides[get_llm_service] = _override_llm
    app.dependency_overrides[get_chapter_service] = _override_chapter_service
    app.dependency_overrides[get_truth_store] = _override_truth_store
    app.dependency_overrides[get_truth_extractor] = _override_truth_extractor
    app.dependency_overrides[get_export_service] = _override_export_service
    app.dependency_overrides[get_daemon_service] = _override_daemon_service
    yield TestClient(app)
    app.dependency_overrides.clear()
