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
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def generate_json(self, task_name, system_prompt, user_payload, response_schema, **kwargs):
        self.calls.append({"task_name": task_name, "system_prompt": system_prompt, "response_schema": response_schema, "payload": user_payload})
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


def test_volume_service_keeps_string_list_fields_as_single_items(tmp_path: Path) -> None:
    class StringListVolumeLLM:
        async def generate_json(self, task_name, system_prompt, user_payload, response_schema, **kwargs):
            return {
                "volumes": [
                    {
                        "volume_no": 1,
                        "title": "夜灯仓契约",
                        "chapter_count": 20,
                        "synopsis": "沈听澜成为临时译手。",
                        "key_scenes": "夜灯仓阻止械斗；秤房暂停盖章",
                        "rhythm_curve": "前段慌乱求生，中段追问契约，结尾失去脱身可能。",
                    }
                ]
            }

    paths = StoragePaths(tmp_path / "books")
    service = VolumeService(StringListVolumeLLM(), BookStorage(paths.books_root), paths, StoryForge3Config(books_dir=str(paths.books_root)))

    volumes = run(service.plan("book", 1, 20))

    assert volumes[0].key_scenes == ("夜灯仓阻止械斗；秤房暂停盖章",)
    assert volumes[0].rhythm_curve == ("前段慌乱求生，中段追问契约，结尾失去脱身可能。",)


def test_volume_prompt_includes_anti_template_constraints(tmp_path: Path) -> None:
    paths = StoragePaths(tmp_path / "books")
    llm = MockLLM()
    service = VolumeService(llm, BookStorage(paths.books_root), paths, StoryForge3Config(books_dir=str(paths.books_root)))

    run(service.plan("book", 2, 20))

    prompt = llm.calls[0]["system_prompt"]
    assert "不可逆事件" in prompt
    assert "处境变了什么" in prompt
    assert "觉醒" in prompt
    assert "崛起" in prompt
    assert "core_conflict" in prompt


def test_volume_schema_declares_nested_properties() -> None:
    schema = VolumeService._schema()

    volume_schema = schema["properties"]["volumes"]["items"]
    assert schema["required"] == ["volumes"]
    assert schema["properties"]["volumes"]["type"] == "array"
    assert volume_schema["required"] == ["volume_no", "title", "chapter_count", "synopsis"]
    assert volume_schema["properties"]["volume_no"]["type"] == "integer"
    assert volume_schema["properties"]["title"]["type"] == "string"
    assert volume_schema["properties"]["chapter_count"]["type"] == "integer"
    assert volume_schema["properties"]["synopsis"]["type"] == "string"
    assert volume_schema["properties"]["key_scenes"]["items"]["type"] == "string"
    assert volume_schema["properties"]["rhythm_curve"]["items"]["type"] == "string"
