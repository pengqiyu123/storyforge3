from __future__ import annotations

from dataclasses import asdict
from typing import Any

from storyforge3.config import StoryForge3Config
from storyforge3.models import VolumeOutline
from storyforge3.services.json_text import parse_json_text
from storyforge3.storage import BookStorage, StoragePaths


VOLUME_SYSTEM_PROMPT = "你是中文网文卷纲规划师。请只输出 JSON。"
VOLUME_TEXT_PROMPT = """你是中文网文卷纲规划师。
请用 ```json ... ``` 输出一个 JSON object，字段必须包含 volumes。
每个 volume 包含 volume_no, title, chapter_count, synopsis, key_scenes, rhythm_curve。
不要输出解释。"""


class VolumeService:
    def __init__(self, llm: Any, storage: BookStorage, paths: StoragePaths, config: StoryForge3Config) -> None:
        self.llm = llm
        self.storage = storage
        self.paths = paths
        self.config = config

    async def plan(self, book_id: str, volume_count: int, total_chapters: int) -> list[VolumeOutline]:
        payload = {"book_id": book_id, "volume_count": volume_count, "total_chapters": total_chapters}
        data = await self._generate_volume_payload(payload)
        volumes = [
            self._load(book_id, item, fallback_no=index + 1, total_chapters=total_chapters, volume_count=volume_count)
            for index, item in enumerate(data.get("volumes", ()))
        ]
        self._save(book_id, volumes)
        return volumes

    async def get(self, book_id: str, volume_no: int) -> VolumeOutline | None:
        for volume in await self.list_volumes(book_id):
            if volume.volume_no == volume_no:
                return volume
        return None

    async def list_volumes(self, book_id: str) -> list[VolumeOutline]:
        data = self.storage.read_json(self.paths.volumes(book_id)) or {"volumes": []}
        return [self._load(book_id, item) for item in data.get("volumes", [])]

    async def update(self, book_id: str, volume_no: int, outline: VolumeOutline) -> VolumeOutline:
        volumes = [item for item in await self.list_volumes(book_id) if item.volume_no != volume_no]
        volumes.append(outline)
        volumes.sort(key=lambda item: item.volume_no)
        self._save(book_id, volumes)
        return outline

    def _save(self, book_id: str, volumes: list[VolumeOutline]) -> None:
        self.storage.write_json(self.paths.volumes(book_id), {"volumes": [asdict(item) for item in volumes]})

    @staticmethod
    def _load(book_id: str, data: dict, fallback_no: int = 1, total_chapters: int = 1, volume_count: int = 1) -> VolumeOutline:
        default_chapter_count = max(1, total_chapters // max(1, volume_count))
        return VolumeOutline(
            book_id,
            int(data.get("volume_no") or fallback_no),
            str(data.get("title") or f"第{fallback_no}卷"),
            int(data.get("chapter_count") or default_chapter_count),
            str(data.get("synopsis") or ""),
            tuple(data.get("key_scenes", ())),
            tuple(data.get("rhythm_curve", ())),
        )

    @staticmethod
    def _schema() -> dict:
        return {"type": "object", "required": ["volumes"]}

    async def _generate_volume_payload(self, payload: dict) -> dict:
        model = self.config.model_for_task("planner")
        try:
            return await self.llm.generate_json(
                "volume_plan",
                VOLUME_SYSTEM_PROMPT,
                payload,
                self._schema(),
                model=model,
            )
        except Exception:
            text = await self.llm.generate_text(
                "volume_plan_text",
                VOLUME_TEXT_PROMPT,
                {**payload, "response_schema": self._schema()},
                model=model,
                temperature=0.5,
            )
            return parse_json_text(text)
