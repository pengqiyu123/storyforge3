from __future__ import annotations

from dataclasses import asdict
from typing import Any

from storyforge3.config import StoryForge3Config
from storyforge3.models import WorldConfig
from storyforge3.services.json_text import parse_json_text
from storyforge3.storage import BookStorage, StoragePaths


WORLD_BUILD_SYSTEM_PROMPT = "你是中文网文世界观架构师。请只输出 JSON。"
WORLD_BUILD_TEXT_PROMPT = """你是中文网文世界观架构师。
请用 ```json ... ``` 输出一个 JSON object，字段必须包含：
setting, power_system, core_conflict, rules。
不要输出解释，不要输出 Markdown 以外的额外文本。"""


class WorldService:
    def __init__(self, llm: Any, storage: BookStorage, paths: StoragePaths, config: StoryForge3Config) -> None:
        self.llm = llm
        self.storage = storage
        self.paths = paths
        self.config = config

    async def build(self, book_id: str, genre: str, seed_brief: str) -> WorldConfig:
        payload = {"book_id": book_id, "genre": genre, "seed_brief": seed_brief}
        data = await self._generate_world_payload(payload)
        world = WorldConfig(
            book_id,
            str(data["setting"]),
            str(data["power_system"]),
            str(data["core_conflict"]),
            tuple(str(item) for item in data.get("rules", ())),
        )
        return await self.update(book_id, world)

    async def get(self, book_id: str) -> WorldConfig | None:
        data = self.storage.read_json(self.paths.world_config(book_id))
        return self._load(book_id, data) if data else None

    async def update(self, book_id: str, world: WorldConfig) -> WorldConfig:
        self.storage.write_json(self.paths.world_config(book_id), asdict(world))
        return world

    @staticmethod
    def _load(book_id: str, data: dict) -> WorldConfig:
        return WorldConfig(book_id, str(data["setting"]), str(data["power_system"]), str(data["core_conflict"]), tuple(data.get("rules", ())))

    @staticmethod
    def _schema() -> dict:
        return {"type": "object", "required": ["setting", "power_system", "core_conflict"]}

    async def _generate_world_payload(self, payload: dict) -> dict:
        model = self.config.model_for_task("architect")
        try:
            return await self.llm.generate_json(
                "world_build",
                WORLD_BUILD_SYSTEM_PROMPT,
                payload,
                self._schema(),
                model=model,
                temperature=0.7,
            )
        except Exception:
            text = await self.llm.generate_text(
                "world_build_text",
                WORLD_BUILD_TEXT_PROMPT,
                {**payload, "response_schema": self._schema()},
                model=model,
                temperature=0.7,
            )
            return parse_json_text(text)
