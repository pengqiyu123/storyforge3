from __future__ import annotations

from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from storyforge3.models import BookConfig


ExportFormat = Literal["tomato_txt", "md", "epub", "qidian_txt"]


class BookInfo(BaseModel):
    """Book summary returned by MCP tools."""

    book_id: str = Field(description="书籍 ID")
    title: str = Field(description="书名")
    genre: str = Field(description="类型")
    status: str = Field(description="状态")
    current_chapter: int = Field(description="当前章节数")
    target_chapters: int = Field(description="目标章节数")


class AuditSummary(BaseModel):
    """Compact audit result for one chapter."""

    chapter_no: int = Field(description="章节号")
    passed: bool = Field(description="是否通过")
    blocking_count: int = Field(description="阻断性问题数")
    warning_count: int = Field(description="警告数")
    next_step: str = Field(description="建议下一步操作")


class DraftResult(BaseModel):
    """Draft output returned by MCP tools."""

    chapter_no: int = Field(description="章节号")
    text: str = Field(description="章节正文")
    char_count: int = Field(description="中文字符数")
    next_step: str = Field(description="建议下一步操作")


class ExportResult(BaseModel):
    """Book export result."""

    path: str = Field(description="导出文件路径")
    format: str = Field(description="导出格式")


class ChapterPlanInfo(BaseModel):
    """Chapter plan returned by MCP tools."""

    chapter_no: int = Field(description="章节号")
    goal: str = Field(description="本章目标")
    outline_node: str = Field(description="卷纲节点")
    must_keep: list[str] = Field(description="必须保留")
    must_avoid: list[str] = Field(description="必须避免")


class ChapterStatusInfo(BaseModel):
    """Chapter status returned by MCP tools."""

    book_id: str = Field(description="书籍 ID")
    chapter_no: int = Field(description="章节号")
    status: str = Field(description="状态")
    title: str = Field(description="章节标题")
    has_text: bool = Field(description="是否已有正文")
    error: str | None = Field(default=None, description="错误信息")
    next_step: str | None = Field(default=None, description="建议下一步操作")


class WorldInfo(BaseModel):
    """World configuration returned by MCP tools."""

    book_id: str = Field(description="书籍 ID")
    setting: str = Field(description="世界观描述")
    power_system: str = Field(description="力量体系")
    core_conflict: str = Field(description="核心冲突")
    rules: list[str] = Field(description="基本规则列表")


class CharacterInfo(BaseModel):
    """Character profile returned by MCP tools."""

    name: str = Field(description="角色名")
    role: str = Field(description="角色定位")
    personality: str = Field(description="性格特征")
    profile: str = Field(description="角色档案")
    abilities: list[str] = Field(description="能力列表")


class ShortStoryStatusInfo(BaseModel):
    """Short story status returned by MCP tools."""

    book_id: str = Field(description="短篇 ID")
    status: str = Field(description="状态")
    has_text: bool = Field(description="是否已有正文")
    actual_chars: int = Field(description="当前正文字符数")
    error: str | None = Field(default=None, description="错误信息")
    next_step: str | None = Field(default=None, description="建议下一步操作")


class TruthInfo(BaseModel):
    """Truth continuity data returned by MCP tools."""

    chapter_no: int = Field(description="章节号")
    source: str = Field(description="来源")
    fact_assertions: list[str] = Field(description="事实断言")
    character_updates: list[str] = Field(description="角色变化摘要")
    irreversible_facts: list[str] = Field(description="不可逆事实")


class ToolRegistrar(Protocol):
    def tool(self): ...


async def list_books_tool(books) -> list[BookInfo]:
    book_list = await books.list_books()
    return [
        BookInfo(
            book_id=book.book_id,
            title=book.title,
            genre=book.genre,
            status=book.status.value if hasattr(book.status, "value") else str(book.status),
            current_chapter=book.current_chapter,
            target_chapters=book.target_chapters,
        )
        for book in book_list
    ]


async def get_book_tool(books, book_id: str) -> BookInfo:
    meta = await books.get(book_id)
    if meta is None:
        raise ValueError(f"书籍不存在: {book_id}。请先调用 list_books 查看现有书籍，或调用 create_book 创建新书。")
    return BookInfo(
        book_id=meta.book_id,
        title=meta.title,
        genre=meta.genre,
        status=meta.status.value if hasattr(meta.status, "value") else str(meta.status),
        current_chapter=meta.current_chapter,
        target_chapters=meta.target_chapters,
    )


async def draft_chapter_tool(chapters, book_id: str, chapter_no: int) -> DraftResult:
    intent = await chapters.plan(book_id, chapter_no)
    text = await chapters.draft(book_id, chapter_no, intent)
    chinese_chars = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return DraftResult(
        chapter_no=chapter_no,
        text=text,
        char_count=chinese_chars,
        next_step=f"起草完成，共 {chinese_chars} 字。请调用 audit_chapter 进行审计。",
    )


async def audit_chapter_tool(chapters, book_id: str, chapter_no: int) -> AuditSummary:
    result = await chapters.audit(book_id, chapter_no)
    next_step = (
        "审计通过。可调用 export_book 导出，或继续 draft_chapter 起草下一章。"
        if result.passed
        else f"审计未通过（{len(result.blocking_issues)} 个阻断性问题）。请调用 revise_chapter 修订章节。"
    )
    return AuditSummary(
        chapter_no=result.chapter_no,
        passed=result.passed,
        blocking_count=len(result.blocking_issues),
        warning_count=len(result.warnings),
        next_step=next_step,
    )


async def export_book_tool(exports, book_id: str, fmt: ExportFormat = "tomato_txt") -> ExportResult:
    path: Path = await exports.export_book(book_id, fmt)
    return ExportResult(path=str(path), format=fmt)


async def create_book_tool(
    books,
    title: str,
    genre: str,
    platform: str,
    target_chapters: int,
    chapter_word_count: int,
) -> BookInfo:
    config = BookConfig(
        title=title,
        genre=genre,
        platform=platform,
        target_chapters=target_chapters,
        chapter_word_count=chapter_word_count,
    )
    meta = await books.create(config)
    return _book_info(meta)


async def plan_chapter_tool(chapters, book_id: str, chapter_no: int) -> ChapterPlanInfo:
    intent = await chapters.plan(book_id, chapter_no)
    return ChapterPlanInfo(
        chapter_no=intent.chapter_no,
        goal=intent.goal,
        outline_node=intent.outline_node,
        must_keep=list(intent.must_keep),
        must_avoid=list(intent.must_avoid),
    )


async def revise_chapter_tool(chapters, book_id: str, chapter_no: int, mode: str = "auto") -> ChapterStatusInfo:
    result = await chapters.revise(book_id, chapter_no, mode)
    return _chapter_status_info(result)


async def get_chapter_status_tool(chapters, book_id: str, chapter_no: int) -> ChapterStatusInfo:
    result = await chapters.get_status(book_id, chapter_no)
    if result is None:
        raise ValueError(f"章节不存在: {book_id} #{chapter_no}。请先调用 get_book 检查当前章节数，再调用 draft_chapter 创建章节。")
    return _chapter_status_info(result)


async def build_world_tool(world_service, book_id: str, genre: str, seed: str) -> WorldInfo:
    world = await world_service.build(book_id, genre, seed)
    return WorldInfo(
        book_id=world.book_id,
        setting=world.setting,
        power_system=world.power_system,
        core_conflict=world.core_conflict,
        rules=list(world.rules),
    )


async def create_character_tool(character_service, book_id: str, spec: str) -> CharacterInfo:
    character = await character_service.create(book_id, spec)
    return _character_info(character)


async def list_characters_tool(character_service, book_id: str) -> list[CharacterInfo]:
    characters = await character_service.list_characters(book_id)
    return [_character_info(character) for character in characters]


async def run_short_story_tool(short_service, book_id: str) -> ShortStoryStatusInfo:
    result = await short_service.run_full_pipeline(book_id)
    return _short_story_status_info(result)


async def get_short_story_status_tool(short_service, book_id: str) -> ShortStoryStatusInfo:
    result = short_service.get_status(book_id)
    if result is None:
        raise ValueError(f"短篇不存在: {book_id}。请先调用 list_books 查看现有书籍，确认 book_id 正确。")
    return _short_story_status_info(result)


async def get_truth_tool(truth_service, book_id: str) -> TruthInfo:
    truth = truth_service.load_latest(book_id)
    if truth is None:
        raise ValueError(f"暂无 truth 数据: {book_id}。请先调用 draft_chapter 起草章节，再调用 audit_chapter 审计后自动提取 truth。")
    return TruthInfo(
        chapter_no=truth.chapter_no,
        source=truth.source,
        fact_assertions=list(truth.fact_assertions),
        character_updates=[str(update) for update in truth.character_updates],
        irreversible_facts=list(truth.irreversible_facts),
    )


def register_tools(mcp: ToolRegistrar, books, chapters, exports, world_service, character_service, short_service, truth_service) -> None:
    """Register StoryForge3 MCP tools on a FastMCP-compatible object."""

    @mcp.tool()
    async def list_books() -> list[BookInfo]:
        """[只读] 列出工作区中的所有书籍。

        返回每本书的 ID、标题、类型、状态和进度信息。无数据时返回空列表。

        建议下一步：调用 get_book 查看某本书的详细信息，或调用 create_book 创建新书。

        Returns:
            list[BookInfo]: 书籍列表。
        """
        return await list_books_tool(books)

    @mcp.tool()
    async def get_book(book_id: str) -> BookInfo:
        """[只读] 获取指定书籍的详细信息。

        返回书籍的 ID、标题、类型、状态、当前章节数和目标章节数。

        前置条件：book_id 必须存在。可从 list_books 获取有效 ID。
        失败时：返回错误信息，建议调用 list_books 查看现有书籍。

        Args:
            book_id: 书籍 ID，可从 list_books 获取。

        Returns:
            BookInfo: 书籍详细信息。
        """
        return await get_book_tool(books, book_id)

    @mcp.tool()
    async def draft_chapter(book_id: str, chapter_no: int) -> DraftResult:
        """[LLM 调用·耗时数分钟] 为指定书籍起草一章。

        完整流程：自动规划（plan），然后起草（draft）并返回正文。此操作可能需要 2-5 分钟。

        前置条件：书籍已创建（create_book），建议已构建世界观（build_world）和创建角色（create_character）。
        建议下一步：调用 audit_chapter 审计章节质量。

        Args:
            book_id: 书籍 ID。
            chapter_no: 章节号，从 1 开始。

        Returns:
            DraftResult: 包含正文、字数统计和建议下一步。
        """
        return await draft_chapter_tool(chapters, book_id, chapter_no)

    @mcp.tool()
    async def audit_chapter(book_id: str, chapter_no: int) -> AuditSummary:
        """[只读·LLM 调用] 审计指定章节。

        运行 36 条机械规则 + 4 维 LLM 审计，返回通过/未通过和问题统计。

        前置条件：章节已有正文（draft_chapter 或手动编辑）。
        建议下一步：审计通过后调用 export_book 导出；未通过则调用 revise_chapter 修订。

        Args:
            book_id: 书籍 ID。
            chapter_no: 章节号。

        Returns:
            AuditSummary: 包含是否通过、阻断/警告计数和建议下一步。
        """
        return await audit_chapter_tool(chapters, book_id, chapter_no)

    @mcp.tool()
    async def export_book(book_id: str, fmt: ExportFormat = "tomato_txt") -> ExportResult:
        """[创建] 导出整本书为指定格式。

        将所有章节格式化后写入文件。支持番茄小说、Markdown、EPUB、起点中文四种格式。

        前置条件：至少有一个章节已完成起草。
        建议下一步：导出完成后可继续 draft_chapter 起草下一章。

        Args:
            book_id: 书籍 ID。
            fmt: 导出格式，支持 tomato_txt、md、epub、qidian_txt。

        Returns:
            ExportResult: 包含导出文件路径和格式。
        """
        return await export_book_tool(exports, book_id, fmt)

    @mcp.tool()
    async def create_book(title: str, genre: str, platform: str, target_chapters: int, chapter_word_count: int) -> BookInfo:
        """[创建] 创建新书。

        在当前工作区中创建一本新书，初始化目录结构和配置文件。

        前置条件：title 不能为空，genre 和 platform 必须是有效值。
        建议下一步：调用 build_world 构建世界观，再调用 create_character 创建角色。

        Args:
            title: 书名。
            genre: 类型，支持 xuanhuan、xianxia、urban、horror、other。
            platform: 平台，支持 tomato、feilu、qidian、other。
            target_chapters: 目标章节数。
            chapter_word_count: 每章目标字数。

        Returns:
            BookInfo: 新创建的书籍信息。
        """
        return await create_book_tool(books, title, genre, platform, target_chapters, chapter_word_count)

    @mcp.tool()
    async def plan_chapter(book_id: str, chapter_no: int) -> ChapterPlanInfo:
        """[LLM 调用·耗时数分钟] 为指定章节生成规划。

        基于世界观、角色和前文上下文，生成章节目标、卷纲节点、必须保留和必须避免。

        前置条件：书籍已创建（create_book），建议已构建世界观（build_world）。
        建议下一步：调用 draft_chapter 根据规划起草正文。

        Args:
            book_id: 书籍 ID。
            chapter_no: 章节号。

        Returns:
            ChapterPlanInfo: 包含章节目标、卷纲节点、必须保留和必须避免。
        """
        return await plan_chapter_tool(chapters, book_id, chapter_no)

    @mcp.tool()
    async def revise_chapter(book_id: str, chapter_no: int, mode: str = "auto") -> ChapterStatusInfo:
        """[修改·LLM 调用·耗时数分钟] 修订章节。

        根据审计结果修订章节正文。支持 6 种模式。auto 模式自动推荐最合适的修订策略。

        前置条件：章节已审计且存在问题（audit_chapter 返回 passed=false）。
        建议下一步：修订后调用 audit_chapter 重新审计确认质量。最多修订 2 轮。

        Args:
            book_id: 书籍 ID。
            chapter_no: 章节号。
            mode: 修订模式 — auto（自动推荐）、polish（润色）、spot_fix（定点修复）、anti_detect（去 AI 痕迹）、surgical（精细手术）、rework（全文重写，不可逆）。

        Returns:
            ChapterStatusInfo: 包含修订后状态和建议下一步。
        """
        return await revise_chapter_tool(chapters, book_id, chapter_no, mode)

    @mcp.tool()
    async def get_chapter_status(book_id: str, chapter_no: int) -> ChapterStatusInfo:
        """[只读] 查询章节当前状态。

        返回章节的状态、标题、是否有正文等基础信息。不触发任何操作。

        建议下一步：根据 next_step 字段的建议执行对应操作。

        Args:
            book_id: 书籍 ID。
            chapter_no: 章节号。

        Returns:
            ChapterStatusInfo: 包含状态信息和下一步建议。
        """
        return await get_chapter_status_tool(chapters, book_id, chapter_no)

    @mcp.tool()
    async def build_world(book_id: str, genre: str, seed: str) -> WorldInfo:
        """[创建·LLM 调用] 构建世界观。

        基于类型和种子描述，生成世界观设定、力量体系、核心冲突和基本规则。

        前置条件：书籍已创建（create_book）。
        建议下一步：调用 create_character 创建角色，再调用 plan_chapter 规划章节。

        Args:
            book_id: 书籍 ID。
            genre: 类型，如 xuanhuan、xianxia、urban、horror、other。
            seed: 世界观种子描述，自由文本，如“近未来都市+存在感系统+异常机构”。

        Returns:
            WorldInfo: 包含世界观描述、力量体系、核心冲突和规则列表。
        """
        return await build_world_tool(world_service, book_id, genre, seed)

    @mcp.tool()
    async def create_character(book_id: str, spec: str) -> CharacterInfo:
        """[创建·LLM 调用] 用自然语言描述创建角色。

        根据描述生成角色名、定位、性格、档案和能力列表，并保存到书籍配置中。

        前置条件：书籍已创建（create_book）。
        建议下一步：可继续调用 create_character 创建更多角色，或调用 list_characters 查看已有角色。

        Args:
            book_id: 书籍 ID。
            spec: 角色描述，自由文本，如“18岁男高中生，性格谨慎，有存在感调节能力”。

        Returns:
            CharacterInfo: 包含角色名、定位、性格、档案和能力列表。
        """
        return await create_character_tool(character_service, book_id, spec)

    @mcp.tool()
    async def list_characters(book_id: str) -> list[CharacterInfo]:
        """[只读] 列出书中的所有角色。

        返回书中已创建的所有角色信息。

        前置条件：书籍已创建（create_book）。

        Args:
            book_id: 书籍 ID。

        Returns:
            list[CharacterInfo]: 角色列表。
        """
        return await list_characters_tool(character_service, book_id)

    @mcp.tool()
    async def run_short_story(book_id: str) -> ShortStoryStatusInfo:
        """[修改·LLM 调用·耗时较长] 一键运行短篇全流程。

        完整流程：规划→起草→审计→修订→导出。此操作可能需要 10-30 分钟，期间会执行多次 LLM 调用。

        前置条件：短篇已创建（create_book）。
        建议下一步：调用 get_short_story_status 查询执行进度。

        Args:
            book_id: 短篇 ID。

        Returns:
            ShortStoryStatusInfo: 包含最终状态和建议下一步。
        """
        return await run_short_story_tool(short_service, book_id)

    @mcp.tool()
    async def get_short_story_status(book_id: str) -> ShortStoryStatusInfo:
        """[只读] 查询短篇当前状态。

        返回短篇的状态、是否有正文、当前字数等基础信息。不触发任何操作。

        建议下一步：根据 next_step 字段的建议执行对应操作。

        Args:
            book_id: 短篇 ID。

        Returns:
            ShortStoryStatusInfo: 包含状态信息和下一步建议。
        """
        return await get_short_story_status_tool(short_service, book_id)

    @mcp.tool()
    async def get_truth(book_id: str) -> TruthInfo:
        """[只读] 获取最新 truth 数据，用于跨章连续性检查。

        返回最近一次 truth 提取的事实断言、角色变化、不可逆事实等数据。

        前置条件：至少有一个章节完成了审计（audit_chapter 通过或修订后通过）。
        建议下一步：truth 数据会自动用于后续 draft_chapter 的上下文，无需手动传递。

        Args:
            book_id: 书籍 ID。

        Returns:
            TruthInfo: 包含事实断言、角色变化和不可逆事实。
        """
        return await get_truth_tool(truth_service, book_id)


def _book_info(meta) -> BookInfo:
    return BookInfo(
        book_id=meta.book_id,
        title=meta.title,
        genre=meta.genre,
        status=meta.status.value if hasattr(meta.status, "value") else str(meta.status),
        current_chapter=meta.current_chapter,
        target_chapters=meta.target_chapters,
    )


def _chapter_status_info(result) -> ChapterStatusInfo:
    status_val = result.status.value if hasattr(result.status, "value") else str(result.status)
    return ChapterStatusInfo(
        book_id=result.book_id,
        chapter_no=result.chapter_no,
        status=status_val,
        title=result.title,
        has_text=bool(result.text),
        error=result.error,
        next_step=_suggest_next_step(status_val),
    )


def _character_info(character) -> CharacterInfo:
    return CharacterInfo(
        name=character.name,
        role=character.role.value if hasattr(character.role, "value") else str(character.role),
        personality=character.personality,
        profile=character.profile,
        abilities=list(character.abilities),
    )


def _short_story_status_info(result) -> ShortStoryStatusInfo:
    status_val = result.status.value if hasattr(result.status, "value") else str(result.status)
    return ShortStoryStatusInfo(
        book_id=result.book_id,
        status=status_val,
        has_text=bool(result.text),
        actual_chars=len(result.text),
        error=result.error,
        next_step=_suggest_short_story_next_step(status_val),
    )


def _suggest_next_step(status: str) -> str | None:
    """Return the recommended next MCP tool for a chapter status."""
    mapping = {
        "planned": "调用 draft_chapter 起草正文。",
        "drafted": "调用 audit_chapter 进行审计。",
        "audited_passed": "调用 export_book 导出，或继续 draft_chapter 起草下一章。",
        "audited_failed": "调用 revise_chapter 修订章节。",
        "revised": "调用 audit_chapter 重新审计。",
        "needs_review": "章节已手动编辑，可调用 audit_chapter 审计确认质量。",
        "exported": "章节已导出。可继续 draft_chapter 起草下一章。",
    }
    return mapping.get(status)


def _suggest_short_story_next_step(status: str) -> str | None:
    """Return the recommended next MCP tool for a short-story status."""
    mapping = {
        "drafted": "短篇已起草。可调用 run_short_story 运行完整管线，或手动审计。",
        "exported": "短篇已完成并导出。",
        "failed": "短篇管线失败。请检查 error 字段，修正后重试 run_short_story。",
    }
    return mapping.get(status)
