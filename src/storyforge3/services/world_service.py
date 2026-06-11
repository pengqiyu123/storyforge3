from __future__ import annotations

from dataclasses import asdict
from typing import Any

from storyforge3.config import StoryForge3Config
from storyforge3.models import WorldConfig
from storyforge3.services.json_text import parse_json_text
from storyforge3.storage import BookStorage, StoragePaths


WORLD_BUILD_SYSTEM_PROMPT = """你是中文网文设定编辑兼命名审稿人。根据 genre 和 seed_brief 构建可直接服务前三章写作的世界观。

输出必须是 JSON object，字段只能包含：setting, power_system, core_conflict, rules。

字段要求：
- setting：写第一卷能看见、能使用的世界基础。优先交代地点、机构、职业、资源、交易方式、公开认知和隐藏压力；不要写百科式年表或远古神话堆料。
- power_system：写核心能力/力量/技术/翻译机制的规则、限制、代价和可被主角利用的漏洞。
- core_conflict：写主角前期会立刻卷入的冲突，以及中长期会持续施压的矛盾。
- rules：输出 4-7 条可执行写作约束，每条都要能约束后续章节，例如信息边界、能力代价、社会反应、禁用设定或揭示顺序。

命名守门规则：
- 不要默认生成世界总名或大陆名；如果前三章用不上宏观地名，就不要硬造。
- 禁止使用“万X大陆”“X之大陆”“诸X之地”“X帝国”“X纪元”等主题词直译式大名，除非 seed_brief 明确要求这种俗称。
- 专名必须通过“角色能自然说出口”测试，优先从场景、制度、职业、交易、历史事件、地方俗称中产生。
- 不要把作品卖点直接压成名字，例如把“翻译/多语言”直译成“万舌大陆”。
- 好名字应带有使用场景和社会功能；机构、码头、货物、资格、黑市称呼通常比宏大大陆名更适合开篇。

只输出 JSON，不要 Markdown，不要解释。"""
WORLD_BUILD_TEXT_PROMPT = f"""{WORLD_BUILD_SYSTEM_PROMPT}

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
        return {
            "type": "object",
            "required": ["setting", "power_system", "core_conflict", "rules"],
            "properties": {
                "setting": {"type": "string"},
                "power_system": {"type": "string"},
                "core_conflict": {"type": "string"},
                "rules": {"type": "array", "items": {"type": "string"}},
            },
        }

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
