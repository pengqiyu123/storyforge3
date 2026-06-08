from __future__ import annotations

import asyncio
from pathlib import Path

from storyforge3.config import StoryForge3Config
from storyforge3.services.character_service import CharacterService
from storyforge3.services.volume_service import VolumeService
from storyforge3.services.world_service import WorldService
from storyforge3.storage import BookStorage, StoragePaths


def run(coro):
    return asyncio.run(coro)


class TextFallbackLLM:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[tuple[str, str]] = []

    async def generate_json(self, task_name, system_prompt, user_payload, response_schema, **kwargs):
        self.calls.append(("json", task_name))
        raise RuntimeError("schema mode unavailable")

    async def generate_text(self, task_name, system_prompt, user_payload, **kwargs):
        self.calls.append(("text", task_name))
        return self.text


def test_world_service_falls_back_to_fenced_json_text(tmp_path: Path) -> None:
    llm = TextFallbackLLM(
        """```json
{"setting":"江城","power_system":"存在感系统","core_conflict":"检测中心追踪异常","rules":["存在感可调节"]}
```"""
    )
    paths = StoragePaths(tmp_path / "books")
    service = WorldService(llm, BookStorage(paths.books_root), paths, StoryForge3Config(books_dir=str(paths.books_root), architect_model="architect"))
    world = run(service.build("book", "urban", "存在感系统"))
    assert world.setting == "江城"
    assert world.rules == ("存在感可调节",)
    assert llm.calls == [("json", "world_build"), ("text", "world_build_text")]


def test_character_service_falls_back_to_text_json(tmp_path: Path) -> None:
    llm = TextFallbackLLM(
        """```json
{"name":"林默","role":"protagonist","profile":"高三学生","personality":"谨慎","abilities":["存在感调节"]}
```"""
    )
    paths = StoragePaths(tmp_path / "books")
    service = CharacterService(llm, BookStorage(paths.books_root), paths, StoryForge3Config(books_dir=str(paths.books_root)))
    character = run(service.create("book", "主角：林默"))
    assert character.name == "林默"
    assert llm.calls == [("json", "character_create"), ("text", "character_create_text")]


def test_volume_service_falls_back_to_text_json(tmp_path: Path) -> None:
    llm = TextFallbackLLM(
        """```json
{"volumes":[{"volume_no":1,"title":"异常初现","chapter_count":5,"synopsis":"林默进入检测中心","key_scenes":["检测"],"rhythm_curve":["rise"]}]}
```"""
    )
    paths = StoragePaths(tmp_path / "books")
    service = VolumeService(llm, BookStorage(paths.books_root), paths, StoryForge3Config(books_dir=str(paths.books_root), planner_model="planner"))
    volumes = run(service.plan("book", 1, 5))
    assert volumes[0].title == "异常初现"
    assert llm.calls == [("json", "volume_plan"), ("text", "volume_plan_text")]
