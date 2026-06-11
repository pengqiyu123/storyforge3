from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from storyforge3.config import StoryForge3Config
from storyforge3.llm.factory import create_llm_service
from storyforge3.logging.pipeline_logger import PipelineLogger
from storyforge3.mcp.tools import register_tools
from storyforge3.services.book_service import BookService
from storyforge3.services.character_service import CharacterService
from storyforge3.services.chapter_service import ChapterService
from storyforge3.services.export_service import ExportService
from storyforge3.services.short_story_service import ShortStoryService
from storyforge3.services.truth_service import TruthService
from storyforge3.services.world_service import WorldService
from storyforge3.storage import BookStorage, StoragePaths


MCP_INSTRUCTIONS = (
    "StoryForge3 网文创作引擎。支持长篇（逐章管线）和短篇（一键生成）。\n"
    "长篇工作流：create_book → build_world → create_character → plan_chapter → draft_chapter → "
    "audit_chapter → revise_chapter（最多2轮）→ export_book。\n"
    "短篇工作流：create_book → run_short_story（一键全流程）。\n"
    "每个 tool 的描述中标注了操作类型：[只读] 安全可随时调用；[LLM 调用] 需要等待；[修改] 会改变数据。"
)


def create_server() -> FastMCP:
    """Create a StoryForge3 MCP server with real service dependencies."""
    config = StoryForge3Config()
    paths = StoragePaths(Path(config.books_dir))
    storage = BookStorage(paths.books_root)

    book_service = BookService(storage, paths)
    chapter_service = ChapterService(config, storage=storage, paths=paths, pipeline_logger=PipelineLogger(config.books_dir))
    export_service = ExportService(storage, paths)
    world_service = WorldService(create_llm_service(config), storage, paths, config)
    character_service = CharacterService(create_llm_service(config), storage, paths, config)
    short_story_service = ShortStoryService(config, storage=storage, paths=paths)
    truth_service = TruthService(config=config)

    mcp = FastMCP(
        "StoryForge",
        instructions=MCP_INSTRUCTIONS,
    )
    register_tools(
        mcp,
        book_service,
        chapter_service,
        export_service,
        world_service,
        character_service,
        short_story_service,
        truth_service,
    )
    return mcp
