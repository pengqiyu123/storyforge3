from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from storyforge3.models import (
    AuditResult,
    BookConfig,
    BookMeta,
    BookStatus,
    ChapterIntent,
    ChapterResult,
    ChapterStatus,
    Character,
    CharacterRole,
    ShortStoryResult,
    ShortStoryStatus,
    TruthData,
    WorldConfig,
)


def run(coro):
    return asyncio.run(coro)


class FakeBooks:
    def __init__(self) -> None:
        self.create = AsyncMock(
            return_value=BookMeta(
                book_id="new-book",
                title="新书",
                genre="horror",
                platform="tomato",
                status=BookStatus.INCUBATING,
                target_chapters=30,
                chapter_word_count=2200,
            )
        )
        self.items = [
            BookMeta(
                book_id="lurenjia",
                title="我是路人甲",
                genre="urban",
                platform="tomato",
                status=BookStatus.ACTIVE,
                target_chapters=100,
                chapter_word_count=2500,
                current_chapter=7,
            )
        ]

    async def list_books(self) -> list[BookMeta]:
        return self.items

    async def get(self, book_id: str) -> BookMeta | None:
        if book_id == "missing":
            return None
        return self.items[0]


class FakeChapters:
    def __init__(self) -> None:
        self.plan = AsyncMock(return_value=ChapterIntent(3, "进入副楼", outline_node="副楼异常升级"))
        self.draft = AsyncMock(return_value="林默推开副楼的门。")
        self.audit = AsyncMock(return_value=AuditResult(3, False, ("golden_three_hook",), ("markdown_artifacts",), (), ()))
        self.revise = AsyncMock(
            return_value=ChapterResult("lurenjia", 3, ChapterStatus.REVISED, "第3章", "修订正文", error="revision_mode=spot_fix")
        )
        self.get_status = AsyncMock(return_value=ChapterResult("lurenjia", 3, ChapterStatus.DRAFTED, "第3章", "草稿正文"))


class FakeExports:
    def __init__(self) -> None:
        self.export_book = AsyncMock(return_value=Path("books/lurenjia/exports/lurenjia.md"))


class FakeWorld:
    def __init__(self) -> None:
        self.build = AsyncMock(
            return_value=WorldConfig("lurenjia", "近未来江城", "存在感系统", "普通人与异常机构冲突", ("规则一", "规则二"))
        )


class FakeCharacters:
    def __init__(self) -> None:
        self.character = Character("lurenjia", "林默", CharacterRole.PROTAGONIST, "高三学生", "谨慎", ("存在感调节",))
        self.create = AsyncMock(return_value=self.character)
        self.list_characters = AsyncMock(return_value=[self.character])


class FakeShortStories:
    def __init__(self) -> None:
        self.run_full_pipeline = AsyncMock(return_value=ShortStoryResult("story-night", ShortStoryStatus.EXPORTED, "短篇正文"))
        self.status = ShortStoryResult("story-night", ShortStoryStatus.DRAFTED, "短篇草稿")

    def get_status(self, book_id: str) -> ShortStoryResult | None:
        if book_id == "missing":
            return None
        return self.status


class FakeTruth:
    def __init__(self) -> None:
        self.truth = TruthData(
            chapter_no=3,
            source="runtime_native",
            fact_assertions=("林默进入副楼。",),
            character_updates=({"name": "林默", "summary": "更加谨慎。"},),
            relationship_updates=(),
            hook_updates=(),
            irreversible_facts=("副楼异常已暴露。",),
            notes=(),
        )

    def load_latest(self, book_id: str) -> TruthData | None:
        if book_id == "missing":
            return None
        return self.truth


def test_list_books_returns_book_info_models() -> None:
    from storyforge3.mcp.tools import list_books_tool

    result = run(list_books_tool(FakeBooks()))

    assert len(result) == 1
    assert result[0].book_id == "lurenjia"
    assert result[0].title == "我是路人甲"
    assert result[0].status == "active"
    assert result[0].current_chapter == 7


def test_list_books_empty_workspace() -> None:
    from storyforge3.mcp.tools import list_books_tool

    books = FakeBooks()
    books.items = []

    assert run(list_books_tool(books)) == []


def test_get_book_existing_returns_book_info() -> None:
    from storyforge3.mcp.tools import get_book_tool

    result = run(get_book_tool(FakeBooks(), "lurenjia"))

    assert result.book_id == "lurenjia"
    assert result.target_chapters == 100


def test_get_book_not_found_raises_value_error() -> None:
    from storyforge3.mcp.tools import get_book_tool

    with pytest.raises(ValueError, match="list_books.*create_book"):
        run(get_book_tool(FakeBooks(), "missing"))


def test_draft_chapter_calls_plan_and_draft() -> None:
    from storyforge3.mcp.tools import DraftResult, draft_chapter_tool

    chapters = FakeChapters()

    result = run(draft_chapter_tool(chapters, "lurenjia", 3))

    assert isinstance(result, DraftResult)
    assert result.chapter_no == 3
    assert result.text == "林默推开副楼的门。"
    assert result.char_count == 8
    assert "audit_chapter" in result.next_step
    chapters.plan.assert_awaited_once_with("lurenjia", 3)
    chapters.draft.assert_awaited_once_with("lurenjia", 3, chapters.plan.return_value)


def test_audit_chapter_returns_summary() -> None:
    from storyforge3.mcp.tools import audit_chapter_tool

    chapters = FakeChapters()

    result = run(audit_chapter_tool(chapters, "lurenjia", 3))

    assert result.chapter_no == 3
    assert result.passed is False
    assert result.blocking_count == 1
    assert result.warning_count == 1
    assert "revise_chapter" in result.next_step
    chapters.audit.assert_awaited_once_with("lurenjia", 3)


def test_export_book_returns_path_and_format() -> None:
    from storyforge3.mcp.tools import export_book_tool

    exports = FakeExports()

    result = run(export_book_tool(exports, "lurenjia", "md"))

    assert Path(result.path).as_posix() == "books/lurenjia/exports/lurenjia.md"
    assert result.format == "md"
    exports.export_book.assert_awaited_once_with("lurenjia", "md")


def test_create_book_tool_creates_book() -> None:
    from storyforge3.mcp.tools import create_book_tool

    books = FakeBooks()

    result = run(create_book_tool(books, "新书", "horror", "tomato", 30, 2200))

    assert result.book_id == "new-book"
    assert result.status == "incubating"
    books.create.assert_awaited_once_with(BookConfig("新书", "horror", "tomato", 30, 2200))


def test_plan_chapter_tool_returns_plan_info() -> None:
    from storyforge3.mcp.tools import plan_chapter_tool

    result = run(plan_chapter_tool(FakeChapters(), "lurenjia", 3))

    assert result.chapter_no == 3
    assert result.goal == "进入副楼"
    assert result.outline_node == "副楼异常升级"


def test_revise_chapter_tool_calls_service() -> None:
    from storyforge3.mcp.tools import revise_chapter_tool

    chapters = FakeChapters()

    result = run(revise_chapter_tool(chapters, "lurenjia", 3, "spot_fix"))

    assert result.status == "revised"
    assert result.has_text is True
    assert result.error == "revision_mode=spot_fix"
    assert result.next_step == "调用 audit_chapter 重新审计。"
    chapters.revise.assert_awaited_once_with("lurenjia", 3, "spot_fix")


def test_get_chapter_status_tool_returns_status() -> None:
    from storyforge3.mcp.tools import get_chapter_status_tool

    result = run(get_chapter_status_tool(FakeChapters(), "lurenjia", 3))

    assert result.status == "drafted"
    assert result.has_text is True
    assert result.next_step == "调用 audit_chapter 进行审计。"


def test_get_chapter_status_tool_not_found() -> None:
    from storyforge3.mcp.tools import get_chapter_status_tool

    chapters = FakeChapters()
    chapters.get_status = AsyncMock(return_value=None)

    with pytest.raises(ValueError, match="get_book.*draft_chapter"):
        run(get_chapter_status_tool(chapters, "lurenjia", 99))


def test_build_world_tool_returns_world_info() -> None:
    from storyforge3.mcp.tools import build_world_tool

    world = FakeWorld()

    result = run(build_world_tool(world, "lurenjia", "urban", "江城异常机构"))

    assert result.setting == "近未来江城"
    assert result.rules == ["规则一", "规则二"]
    world.build.assert_awaited_once_with("lurenjia", "urban", "江城异常机构")


def test_create_character_tool_returns_character() -> None:
    from storyforge3.mcp.tools import create_character_tool

    characters = FakeCharacters()

    result = run(create_character_tool(characters, "lurenjia", "谨慎男高中生"))

    assert result.name == "林默"
    assert result.role == "protagonist"
    assert result.abilities == ["存在感调节"]
    characters.create.assert_awaited_once_with("lurenjia", "谨慎男高中生")


def test_list_characters_tool_returns_list() -> None:
    from storyforge3.mcp.tools import list_characters_tool

    result = run(list_characters_tool(FakeCharacters(), "lurenjia"))

    assert len(result) == 1
    assert result[0].name == "林默"


def test_run_short_story_tool_calls_pipeline() -> None:
    from storyforge3.mcp.tools import run_short_story_tool

    shorts = FakeShortStories()

    result = run(run_short_story_tool(shorts, "story-night"))

    assert result.status == "exported"
    assert result.has_text is True
    assert result.actual_chars == 4
    assert result.next_step == "短篇已完成并导出。"
    shorts.run_full_pipeline.assert_awaited_once_with("story-night")


def test_get_short_story_status_tool_not_found() -> None:
    from storyforge3.mcp.tools import get_short_story_status_tool

    with pytest.raises(ValueError, match="list_books"):
        run(get_short_story_status_tool(FakeShortStories(), "missing"))


def test_get_truth_tool_returns_truth() -> None:
    from storyforge3.mcp.tools import get_truth_tool

    result = run(get_truth_tool(FakeTruth(), "lurenjia"))

    assert result.chapter_no == 3
    assert result.fact_assertions == ["林默进入副楼。"]
    assert result.character_updates == ["{'name': '林默', 'summary': '更加谨慎。'}"]
    assert result.irreversible_facts == ["副楼异常已暴露。"]


def test_get_truth_tool_no_data() -> None:
    from storyforge3.mcp.tools import get_truth_tool

    with pytest.raises(ValueError, match="draft_chapter.*audit_chapter"):
        run(get_truth_tool(FakeTruth(), "missing"))


def test_chapter_next_step_mapping_gracefully_handles_known_and_unknown_status() -> None:
    from storyforge3.mcp.tools import _suggest_next_step

    assert _suggest_next_step("planned") == "调用 draft_chapter 起草正文。"
    assert _suggest_next_step("drafted") == "调用 audit_chapter 进行审计。"
    assert _suggest_next_step("audited_passed") == "调用 export_book 导出，或继续 draft_chapter 起草下一章。"
    assert _suggest_next_step("audited_failed") == "调用 revise_chapter 修订章节。"
    assert _suggest_next_step("revised") == "调用 audit_chapter 重新审计。"
    assert _suggest_next_step("needs_review") == "章节已手动编辑，可调用 audit_chapter 审计确认质量。"
    assert _suggest_next_step("exported") == "章节已导出。可继续 draft_chapter 起草下一章。"
    assert _suggest_next_step("future_status") is None


def test_short_story_next_step_mapping_gracefully_handles_known_and_unknown_status() -> None:
    from storyforge3.mcp.tools import _suggest_short_story_next_step

    assert _suggest_short_story_next_step("drafted") == "短篇已起草。可调用 run_short_story 运行完整管线，或手动审计。"
    assert _suggest_short_story_next_step("exported") == "短篇已完成并导出。"
    assert _suggest_short_story_next_step("failed") == "短篇管线失败。请检查 error 字段，修正后重试 run_short_story。"
    assert _suggest_short_story_next_step("future_status") is None


def test_register_tools_adds_fifteen_tools() -> None:
    from storyforge3.mcp.tools import register_tools

    class Recorder:
        def __init__(self) -> None:
            self.names: list[str] = []
            self.functions = {}

        def tool(self):
            def decorate(func):
                self.names.append(func.__name__)
                self.functions[func.__name__] = func
                return func

            return decorate

    recorder = Recorder()

    register_tools(
        recorder,
        FakeBooks(),
        FakeChapters(),
        FakeExports(),
        FakeWorld(),
        FakeCharacters(),
        FakeShortStories(),
        FakeTruth(),
    )

    assert recorder.names == [
        "list_books",
        "get_book",
        "draft_chapter",
        "audit_chapter",
        "export_book",
        "create_book",
        "plan_chapter",
        "revise_chapter",
        "get_chapter_status",
        "build_world",
        "create_character",
        "list_characters",
        "run_short_story",
        "get_short_story_status",
        "get_truth",
    ]
    assert recorder.functions["draft_chapter"].__annotations__["return"] in ("DraftResult",)


def test_registered_tools_have_layered_docstrings() -> None:
    from storyforge3.mcp.tools import register_tools

    class Recorder:
        def __init__(self) -> None:
            self.functions = {}

        def tool(self):
            def decorate(func):
                self.functions[func.__name__] = func
                return func

            return decorate

    recorder = Recorder()

    register_tools(
        recorder,
        FakeBooks(),
        FakeChapters(),
        FakeExports(),
        FakeWorld(),
        FakeCharacters(),
        FakeShortStories(),
        FakeTruth(),
    )

    expected_prefixes = {
        "list_books": "[只读]",
        "get_book": "[只读]",
        "draft_chapter": "[LLM 调用·耗时数分钟]",
        "audit_chapter": "[只读·LLM 调用]",
        "export_book": "[创建]",
        "create_book": "[创建]",
        "plan_chapter": "[LLM 调用·耗时数分钟]",
        "revise_chapter": "[修改·LLM 调用·耗时数分钟]",
        "get_chapter_status": "[只读]",
        "build_world": "[创建·LLM 调用]",
        "create_character": "[创建·LLM 调用]",
        "list_characters": "[只读]",
        "run_short_story": "[修改·LLM 调用·耗时较长]",
        "get_short_story_status": "[只读]",
        "get_truth": "[只读]",
    }

    for name, prefix in expected_prefixes.items():
        doc = recorder.functions[name].__doc__ or ""
        assert doc.strip().startswith(prefix)
        assert "Returns:" in doc

    assert "不可逆" in (recorder.functions["revise_chapter"].__doc__ or "")
    assert "10-30 分钟" in (recorder.functions["run_short_story"].__doc__ or "")


def test_mcp_server_instructions_describe_workflows_and_labels() -> None:
    from storyforge3.mcp.server import MCP_INSTRUCTIONS

    assert "长篇工作流" in MCP_INSTRUCTIONS
    assert "短篇工作流" in MCP_INSTRUCTIONS
    assert "create_book → build_world" in MCP_INSTRUCTIONS
    assert "create_book → run_short_story" in MCP_INSTRUCTIONS
    assert "[只读]" in MCP_INSTRUCTIONS
    assert "[LLM 调用]" in MCP_INSTRUCTIONS
    assert "[修改]" in MCP_INSTRUCTIONS
