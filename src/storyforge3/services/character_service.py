from __future__ import annotations

from dataclasses import asdict
from typing import Any

from storyforge3.config import StoryForge3Config
from storyforge3.models import Character, CharacterRole, Relationship
from storyforge3.services.json_text import parse_json_text
from storyforge3.storage import BookStorage, StoragePaths


CHARACTER_SYSTEM_PROMPT = """你是中文网文角色设计师兼人设审稿人。根据 spec/specs 为第一卷生成可落地角色。
输出必须是 JSON object，字段必须符合请求。
角色设计要求：
- 角色必须从具体场景、事件、职业或关系压力中诞生，不要用标签堆叠。
- profile 要写清身份、当前处境、第一卷会执行的具体行为。
- personality 必须有矛盾面：在一种场景会做什么，在另一种压力下会反常做什么。
- 参考角色档案维度：身份、性格底色、语癖/说话风格、行为模式、关键关系、信息边界。
- abilities 只写已给出或由 spec 合理推出的能力，不凭空塞强能力。
- arc_direction 写角色在第一卷的变化方向，不写空泛成长。
- 禁止单标签人格：冷酷、温柔、阳光、腹黑、善良、神秘等不能单独充当 personality。
- 禁止模板名和借壳名，如龙傲天、叶凡、萧炎、林凡；名字要适配题材和社会环境。
只输出 JSON，不要解释。"""
CHARACTER_TEXT_PROMPT = f"""{CHARACTER_SYSTEM_PROMPT}

请用 ```json ... ``` 输出一个 JSON object，字段必须符合请求。
单角色必须包含 name, role, profile, personality。
批量角色必须包含 characters，可选 relationships。
不要输出解释。"""


class CharacterService:
    def __init__(self, llm: Any, storage: BookStorage, paths: StoragePaths, config: StoryForge3Config) -> None:
        self.llm = llm
        self.storage = storage
        self.paths = paths
        self.config = config

    async def create(self, book_id: str, spec: str) -> Character:
        payload = {"book_id": book_id, "spec": spec}
        data = await self._generate_character_payload("character_create", "character_create_text", payload, self._schema())
        character = self._load_character(book_id, data)
        characters = [item for item in await self.list_characters(book_id) if item.name != character.name]
        characters.append(character)
        self._save_characters(book_id, characters)
        return character

    async def create_batch(self, book_id: str, specs: tuple[str, ...]) -> tuple[Character, ...]:
        payload = {"book_id": book_id, "specs": specs}
        data = await self._generate_character_payload("character_create_batch", "character_create_batch_text", payload, self._batch_schema())
        characters = tuple(self._load_character(book_id, item) for item in data.get("characters", ()))
        relationships = tuple(self._load_relationship(item) for item in data.get("relationships", ()))
        self._save_characters(book_id, list(characters))
        self._save_relationships(book_id, list(relationships))
        return characters

    async def list_characters(self, book_id: str) -> list[Character]:
        data = self.storage.read_json(self.paths.characters(book_id)) or {"characters": []}
        return [self._load_character(book_id, item) for item in data.get("characters", [])]

    async def get_relationships(self, book_id: str) -> list[Relationship]:
        data = self.storage.read_json(self.paths.relationships(book_id)) or {"relationships": []}
        return [self._load_relationship(item) for item in data.get("relationships", [])]

    async def update(self, book_id: str, name: str, updates: dict) -> Character:
        characters = await self.list_characters(book_id)
        for index, character in enumerate(characters):
            if character.name == name:
                updated = Character(**{**asdict(character), **updates})
                characters[index] = updated
                self._save_characters(book_id, characters)
                return updated
        raise FileNotFoundError(f"character not found: {name}")

    def _save_characters(self, book_id: str, characters: list[Character]) -> None:
        data = [self._dump_character(item) for item in characters]
        self.storage.write_json(self.paths.characters(book_id), {"characters": data})

    def _save_relationships(self, book_id: str, relationships: list[Relationship]) -> None:
        self.storage.write_json(self.paths.relationships(book_id), {"relationships": [asdict(item) for item in relationships]})

    @staticmethod
    def _load_character(book_id: str, data: dict) -> Character:
        return Character(book_id, str(data["name"]), CharacterService._normalize_role(data.get("role")), str(data["profile"]), str(data["personality"]), tuple(data.get("abilities", ())), str(data.get("arc_direction", "")))

    @staticmethod
    def _dump_character(character: Character) -> dict:
        data = asdict(character)
        data["role"] = character.role.value
        return data

    @staticmethod
    def _load_relationship(data: dict) -> Relationship:
        return Relationship(str(data["character_a"]), str(data["character_b"]), str(data["relation_type"]), str(data["description"]))

    @staticmethod
    def _schema() -> dict:
        return {
            "type": "object",
            "required": ["name", "role", "profile", "personality"],
            "properties": {
                "name": {"type": "string"},
                "role": {"type": "string"},
                "profile": {"type": "string"},
                "personality": {"type": "string"},
                "abilities": {"type": "array", "items": {"type": "string"}},
                "arc_direction": {"type": "string"},
            },
        }

    @staticmethod
    def _batch_schema() -> dict:
        return {
            "type": "object",
            "required": ["characters"],
            "properties": {
                "characters": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["name", "role", "profile", "personality"],
                        "properties": {
                            "name": {"type": "string"},
                            "role": {"type": "string"},
                            "profile": {"type": "string"},
                            "personality": {"type": "string"},
                            "abilities": {"type": "array", "items": {"type": "string"}},
                            "arc_direction": {"type": "string"},
                        },
                    },
                },
                "relationships": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["character_a", "character_b", "relation_type", "description"],
                        "properties": {
                            "character_a": {"type": "string"},
                            "character_b": {"type": "string"},
                            "relation_type": {"type": "string"},
                            "description": {"type": "string"},
                        },
                    },
                },
            },
        }

    @staticmethod
    def _normalize_role(value: object) -> CharacterRole:
        raw = str(value or "").strip().lower()
        if raw in {role.value for role in CharacterRole}:
            return CharacterRole(raw)
        if "主角" in raw or "protagonist" in raw:
            return CharacterRole.PROTAGONIST
        if any(marker in raw for marker in ("主要", "配角", "major", "mentor", "ally", "反派", "对手")):
            return CharacterRole.MAJOR
        return CharacterRole.MINOR

    async def _generate_character_payload(self, json_task: str, text_task: str, payload: dict, schema: dict) -> dict:
        model = self.config.model_for_task("architect")
        try:
            return await self.llm.generate_json(
                json_task,
                CHARACTER_SYSTEM_PROMPT,
                payload,
                schema,
                model=model,
            )
        except Exception:
            text = await self.llm.generate_text(
                text_task,
                CHARACTER_TEXT_PROMPT,
                {**payload, "response_schema": schema},
                model=model,
                temperature=0.4,
            )
            return parse_json_text(text)
