from __future__ import annotations

import asyncio
from pathlib import Path

from storyforge3.config import StoryForge3Config
from storyforge3.models import CharacterRole
from storyforge3.services.character_service import CharacterService
from storyforge3.storage import BookStorage, StoragePaths


def run(coro):
    return asyncio.run(coro)


class MockLLM:
    async def generate_json(self, task_name, system_prompt, user_payload, response_schema, **kwargs):
        if task_name == "character_create_batch":
            return {
                "characters": [
                    {"name": "林默", "role": "protagonist", "profile": "高三学生", "personality": "谨慎", "abilities": ["存在感调节"], "arc_direction": "从隐身到承担"},
                    {"name": "周晴", "role": "major", "profile": "检测中心实习员", "personality": "敏锐", "abilities": [], "arc_direction": "发现真相"},
                ],
                "relationships": [{"character_a": "林默", "character_b": "周晴", "relation_type": "ally", "description": "互相试探的同盟"}],
            }
        return {"name": "林默", "role": "protagonist", "profile": "高三学生", "personality": "谨慎", "abilities": ["存在感调节"], "arc_direction": "从隐身到承担"}


def test_character_service_create_batch_list_and_update(tmp_path: Path) -> None:
    paths = StoragePaths(tmp_path / "books")
    service = CharacterService(MockLLM(), BookStorage(paths.books_root), paths, StoryForge3Config(books_dir=str(paths.books_root)))
    character = run(service.create("book", "主角：林默"))
    assert character.name == "林默"
    assert character.role == CharacterRole.PROTAGONIST
    characters = run(service.create_batch("book", ("林默", "周晴")))
    assert [item.name for item in characters] == ["林默", "周晴"]
    assert len(run(service.list_characters("book"))) == 2
    assert run(service.get_relationships("book"))[0].relation_type == "ally"
    updated = run(service.update("book", "周晴", {"personality": "冷静敏锐"}))
    assert updated.personality == "冷静敏锐"


def test_character_service_normalizes_chinese_roles(tmp_path: Path) -> None:
    class ChineseRoleLLM:
        async def generate_json(self, task_name, system_prompt, user_payload, response_schema, **kwargs):
            return {"name": "林默", "role": "主角，高三学生", "profile": "高三学生", "personality": "谨慎"}

    paths = StoragePaths(tmp_path / "books")
    service = CharacterService(ChineseRoleLLM(), BookStorage(paths.books_root), paths, StoryForge3Config(books_dir=str(paths.books_root)))
    character = run(service.create("book", "主角：林默"))
    assert character.role == CharacterRole.PROTAGONIST
