from __future__ import annotations

import asyncio
from pathlib import Path

from storyforge3.config import StoryForge3Config
from storyforge3.models import BookConfig, WorldConfig
from storyforge3.services.book_service import BookService
from storyforge3.services.world_service import WorldService
from storyforge3.storage import BookStorage, StoragePaths


def run(coro):
    return asyncio.run(coro)


class MockLLM:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def generate_json(self, task_name, system_prompt, user_payload, response_schema, **kwargs):
        self.calls.append({"task_name": task_name, "model": kwargs.get("model"), "payload": user_payload})
        return {
            "setting": "江城二中与市异能检测中心并存。",
            "power_system": "存在感系统",
            "core_conflict": "林默必须在低存在感与被追踪之间求生。",
            "rules": ["存在感可调节", "检测中心记录异常"],
        }


def test_world_service_build_get_update(tmp_path: Path) -> None:
    paths = StoragePaths(tmp_path / "books")
    storage = BookStorage(paths.books_root)
    book = run(BookService(storage, paths).create(BookConfig("我是路人甲", "urban", "tomato", 10, 2000)))
    llm = MockLLM()
    service = WorldService(llm, storage, paths, StoryForge3Config(books_dir=str(paths.books_root), architect_model="architect"))
    world = run(service.build(book.book_id, "urban", "存在感系统"))
    assert world == WorldConfig(book.book_id, "江城二中与市异能检测中心并存。", "存在感系统", "林默必须在低存在感与被追踪之间求生。", ("存在感可调节", "检测中心记录异常"))
    assert llm.calls[0]["model"] == "architect"
    assert run(service.get(book.book_id)) == world
    updated = run(service.update(book.book_id, WorldConfig(book.book_id, "新设定", "新体系", "新冲突", ("规则",))))
    assert updated.setting == "新设定"
