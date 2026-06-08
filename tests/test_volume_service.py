from __future__ import annotations

import asyncio
from pathlib import Path

from storyforge3.config import StoryForge3Config
from storyforge3.models import VolumeOutline
from storyforge3.services.volume_service import VolumeService
from storyforge3.storage import BookStorage, StoragePaths


def run(coro):
    return asyncio.run(coro)


class MockLLM:
    async def generate_json(self, task_name, system_prompt, user_payload, response_schema, **kwargs):
        return {
            "volumes": [
                {"volume_no": 1, "title": "存在感异常", "chapter_count": 10, "synopsis": "林默进入异常体系。", "key_scenes": ["检测中心"], "rhythm_curve": ["rise"]},
                {"volume_no": 2, "title": "检测中心", "chapter_count": 10, "synopsis": "林默追查真相。", "key_scenes": ["副楼"], "rhythm_curve": ["peak"]},
            ]
        }


def test_volume_service_plan_get_list_update(tmp_path: Path) -> None:
    paths = StoragePaths(tmp_path / "books")
    service = VolumeService(MockLLM(), BookStorage(paths.books_root), paths, StoryForge3Config(books_dir=str(paths.books_root), planner_model="planner"))
    volumes = run(service.plan("book", 2, 20))
    assert [item.title for item in volumes] == ["存在感异常", "检测中心"]
    assert run(service.get("book", 2)).title == "检测中心"
    assert len(run(service.list_volumes("book"))) == 2
    updated = run(service.update("book", 2, VolumeOutline("book", 2, "新卷", 8, "新概要", ("场景",), ("rise",))))
    assert updated.title == "新卷"


def test_volume_service_normalizes_missing_volume_fields(tmp_path: Path) -> None:
    class LooseVolumeLLM:
        async def generate_json(self, task_name, system_prompt, user_payload, response_schema, **kwargs):
            return {"volumes": [{"title": "异常初现", "synopsis": "林默进入检测中心"}]}

    paths = StoragePaths(tmp_path / "books")
    service = VolumeService(LooseVolumeLLM(), BookStorage(paths.books_root), paths, StoryForge3Config(books_dir=str(paths.books_root)))
    volumes = run(service.plan("book", 1, 5))
    assert volumes == [VolumeOutline("book", 1, "异常初现", 5, "林默进入检测中心", (), ())]
